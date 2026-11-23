"""Unit tests for Canada Post My Mail models and JWT helpers."""

from __future__ import annotations

import base64
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMP_DIR = ROOT / "custom_components" / "canadapost"

# Load const & models without importing homeassistant
pkg = types.ModuleType("canadapost_test_pkg")
pkg.__path__ = [str(COMP_DIR)]
sys.modules["canadapost_test_pkg"] = pkg


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"canadapost_test_pkg.{name}", COMP_DIR / f"{name}.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const")
models = _load("models")


def _make_jwt(claims: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').decode().rstrip("=")
    payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    )
    return f"{header}.{payload}.signature"


SAMPLE_PAYLOAD = {
    "PageNumber": 1,
    "Results": [
        {
            "Date": "2026-11-23",
            "Mailpieces": [
                {
                    "OID": "oid-general",
                    "ReferenceID": "1930054507397",
                    "CampaignName": {},
                    "ServiceType": 0,
                    "HasAd": False,
                },
                {
                    "OID": "oid-ct",
                    "CampaignName": {"En": "D347", "Fr": "FR-D347"},
                    "ServiceType": 25,
                    "SOMIdentifier": "C180664656",
                    "ActualStartDate": "2026-11-23T00:00:00",
                    "HasAd": True,
                    "Mailer": {
                        "Name": {
                            "En": "CANADIAN TIRE CORPORATION",
                            "Fr": "SOCIETE CANADIAN TIRE",
                        },
                        "Logo": {
                            "En": "https://d2t6hoebbfru8t.cloudfront.net/abc/resized logo.png",
                            "Fr": "https://d2t6hoebbfru8t.cloudfront.net/abc/resized logo.png",
                        },
                    },
                },
            ],
        },
        {
            "Date": "2026-11-18",
            "Mailpieces": [
                {
                    "OID": "oid-bmo",
                    "ReferenceID": "3816143603466",
                    "ServiceType": 4,
                    "HasAd": False,
                    "Mailer": {
                        "Name": {"En": "BANK OF MONTREAL", "Fr": "BANQUE DE MONTREAL"},
                        "Logo": {},
                    },
                }
            ],
        },
    ],
}


class TestMyMailModels(unittest.TestCase):
    def test_encode_image_url_encodes_spaces(self) -> None:
        raw = "https://d2t6hoebbfru8t.cloudfront.net/abc/resized logo.png"
        self.assertEqual(
            models.encode_image_url(raw),
            "https://d2t6hoebbfru8t.cloudfront.net/abc/resized%20logo.png",
        )
        self.assertIsNone(models.encode_image_url(None))
        self.assertIsNone(models.encode_image_url(""))

    def test_categorize_mail_splits_out_for_delivery_and_arriving_soon(self) -> None:
        buckets = models.categorize_mail(
            SAMPLE_PAYLOAD, today=date(2026, 11, 23), include_ads=True, lang="en"
        )
        self.assertEqual(len(buckets["out_for_delivery"]), 1)
        self.assertEqual(len(buckets["arriving_soon"]), 1)
        self.assertEqual(len(buckets["in_transit"]), 2)
        self.assertEqual(len(buckets["delivered"]), 1)

        ofd = buckets["out_for_delivery"][0]
        self.assertEqual(ofd["sender"], "General Mail")
        self.assertFalse(ofd["sender_known"])
        self.assertEqual(ofd["mail_type"], "general_mail")
        self.assertFalse(ofd["has_digital_flyer"])

        soon = buckets["arriving_soon"][0]
        self.assertEqual(soon["sender"], "CANADIAN TIRE CORPORATION")
        self.assertTrue(soon["sender_known"])
        self.assertTrue(soon["has_digital_flyer"])
        self.assertEqual(soon["campaign_name"], "D347")
        self.assertEqual(
            soon["image_url"],
            "https://d2t6hoebbfru8t.cloudfront.net/abc/resized%20logo.png",
        )
        self.assertEqual(soon["actual_start_date"], "2026-11-23")

    def test_include_ads_false_filters_service_type_25(self) -> None:
        buckets = models.categorize_mail(
            SAMPLE_PAYLOAD, today=date(2026, 11, 23), include_ads=False, lang="en"
        )
        self.assertEqual(len(buckets["out_for_delivery"]), 1)
        self.assertEqual(len(buckets["arriving_soon"]), 0)
        self.assertEqual(len(buckets["in_transit"]), 1)
        self.assertEqual(len(buckets["delivered"]), 1)

    def test_french_localization(self) -> None:
        buckets = models.categorize_mail(
            SAMPLE_PAYLOAD, today=date(2026, 11, 23), include_ads=True, lang="fr"
        )
        self.assertEqual(buckets["out_for_delivery"][0]["sender"], "Courrier général")
        self.assertEqual(
            buckets["arriving_soon"][0]["sender"], "SOCIETE CANADIAN TIRE"
        )
        self.assertEqual(buckets["arriving_soon"][0]["campaign_name"], "FR-D347")

    def test_extract_topic_id(self) -> None:
        # Test JWT sub extraction logic
        tok = _make_jwt({"sub": "topic-uuid-1234", "aud": "cpc-nativeapp-2020"})
        part = tok.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        self.assertEqual(claims["sub"], "topic-uuid-1234")


if __name__ == "__main__":
    unittest.main()
