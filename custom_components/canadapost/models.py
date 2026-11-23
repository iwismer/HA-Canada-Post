"""Pure normalization and grouping helpers for Canada Post My Mail payloads."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from .const import SERVICE_TYPE_GENERAL_MAIL, SERVICE_TYPE_NEIGHBOURHOOD_MAIL


def encode_image_url(url: str | None) -> str | None:
    """Percent-encode spaces and unsafe chars in CloudFront logo paths."""
    if not url or not isinstance(url, str):
        return None
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return None
    encoded_path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    return urlunsplit(
        (parts.scheme, parts.netloc, encoded_path, parts.query, parts.fragment)
    )


def _localized(mapping: Any, lang: str) -> str | None:
    if not isinstance(mapping, dict):
        return None
    primary = "Fr" if lang == "fr" else "En"
    fallback = "En" if primary == "Fr" else "Fr"
    val = mapping.get(primary) or mapping.get(fallback)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_mailpiece(
    piece: dict[str, Any],
    *,
    delivery_date: date,
    today: date,
    lang: str = "en",
) -> dict[str, Any]:
    """Normalize one raw Canada Post My Mail mailpiece."""
    service_type = piece.get("ServiceType")
    is_neighbourhood = service_type == SERVICE_TYPE_NEIGHBOURHOOD_MAIL
    is_general = service_type == SERVICE_TYPE_GENERAL_MAIL

    mailer = piece.get("Mailer") if isinstance(piece.get("Mailer"), dict) else {}
    raw_sender = _localized(mailer.get("Name"), lang)
    sender_known = raw_sender is not None
    default_sender = "Courrier général" if lang == "fr" else "General Mail"
    sender = raw_sender or default_sender

    image_url = encode_image_url(_localized(mailer.get("Logo"), lang))
    campaign_name = _localized(piece.get("CampaignName"), lang)
    has_digital_flyer = bool(piece.get("HasAd"))

    actual_start = _parse_iso_date(piece.get("ActualStartDate"))

    if delivery_date < today:
        category = "delivered"
        tracking_status = "Delivered"
    elif is_neighbourhood:
        category = "arriving_soon"
        tracking_status = "Arriving soon"
    else:
        category = "out_for_delivery"
        tracking_status = "Out for delivery"

    if is_neighbourhood:
        mail_type = "flyer"
        tracking_description = "Flyer / Arriving soon"
    elif is_general:
        mail_type = "general_mail"
        tracking_description = "General Mail"
    else:
        mail_type = "letter"
        tracking_description = "Letter"

    return {
        "oid": piece.get("OID"),
        "sender": sender,
        "sender_known": sender_known,
        "image_url": image_url,
        "estimated_delivery": delivery_date.isoformat(),
        "actual_start_date": actual_start.isoformat() if actual_start else None,
        "service_type": service_type,
        "category": category,
        "mail_type": mail_type,
        "has_digital_flyer": has_digital_flyer,
        "campaign_name": campaign_name,
        "som_identifier": piece.get("SOMIdentifier"),
        "reference_id": piece.get("ReferenceID"),
        # Compatibility keys for Mail & Packages / flex-table-card
        "tracking_number": piece.get("SOMIdentifier") or piece.get("ReferenceID") or "N/A",
        "tracking_description": tracking_description,
        "tracking_status": tracking_status,
    }


def categorize_mail(
    raw_data: dict[str, Any] | None,
    *,
    today: date,
    include_ads: bool = True,
    lang: str = "en",
) -> dict[str, list[dict[str, Any]]]:
    """Split raw My Mail API response into out_for_delivery, arriving_soon, and delivered."""
    buckets: dict[str, list[dict[str, Any]]] = {
        "out_for_delivery": [],
        "arriving_soon": [],
        "in_transit": [],
        "delivered": [],
    }
    if not isinstance(raw_data, dict):
        return buckets

    for result in raw_data.get("Results") or []:
        if not isinstance(result, dict):
            continue
        delivery_date = _parse_iso_date(result.get("Date")) or today
        for piece in result.get("Mailpieces") or []:
            if not isinstance(piece, dict):
                continue
            if (
                piece.get("ServiceType") == SERVICE_TYPE_NEIGHBOURHOOD_MAIL
                and not include_ads
            ):
                continue
            normalized = normalize_mailpiece(
                piece, delivery_date=delivery_date, today=today, lang=lang
            )
            cat = normalized["category"]
            buckets[cat].append(normalized)
            if cat in ("out_for_delivery", "arriving_soon"):
                buckets["in_transit"].append(normalized)

    return buckets
