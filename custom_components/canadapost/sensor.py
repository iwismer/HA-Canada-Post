"""Sensor platform for Canada Post My Mail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_INCLUDE_ADS, CONF_TOPIC_ID, DOMAIN
from .coordinator import CanadaPostUpdateCoordinator
from .models import categorize_mail


@dataclass(frozen=True)
class _SensorSpec:
    key: str
    bucket: str
    translation_key: str
    icon: str
    unique_id_fmt: str


_SENSORS: tuple[_SensorSpec, ...] = (
    _SensorSpec(
        key="out_for_delivery",
        bucket="out_for_delivery",
        translation_key="out_for_delivery",
        icon="mdi:email-fast-outline",
        unique_id_fmt="cp_v2_{topic_id}_out_for_delivery",
    ),
    _SensorSpec(
        key="arriving_soon",
        bucket="arriving_soon",
        translation_key="arriving_soon",
        icon="mdi:newspaper-variant-multiple-outline",
        unique_id_fmt="cp_v2_{topic_id}_arriving_soon",
    ),
    _SensorSpec(
        key="transit",
        bucket="in_transit",
        translation_key="transit",
        icon="mdi:truck-delivery-outline",
        unique_id_fmt="cp_v2_{topic_id}_transit",
    ),
    _SensorSpec(
        key="delivered",
        bucket="delivered",
        translation_key="delivered",
        icon="mdi:package-variant-closed-check",
        unique_id_fmt="cp_v2_{topic_id}_delivered",
    ),
    _SensorSpec(
        key="mail_updated",
        bucket="delivered",
        translation_key="mail_updated",
        icon="mdi:mailbox-outline",
        unique_id_fmt="cp_mail_updated_compat_{topic_id}",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canada Post My Mail sensors."""
    coordinator: CanadaPostUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    topic_id: str = entry.data[CONF_TOPIC_ID]

    async_add_entities(
        CanadaPostMailSensor(coordinator, topic_id, spec) for spec in _SENSORS
    )


class CanadaPostMailSensor(
    CoordinatorEntity[CanadaPostUpdateCoordinator], SensorEntity
):
    """Sensor representing a category of Canada Post My Mail items."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: CanadaPostUpdateCoordinator,
        topic_id: str,
        spec: _SensorSpec,
    ) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._attr_device_info = coordinator.device_info
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = spec.unique_id_fmt.format(topic_id=topic_id)
        self._attr_icon = spec.icon

    def _include_ads(self) -> bool:
        return bool(
            self.coordinator.entry.options.get(
                CONF_INCLUDE_ADS,
                self.coordinator.entry.data.get(CONF_INCLUDE_ADS, True),
            )
        )

    def _lang(self) -> str:
        language = getattr(self.hass.config, "language", "en") or "en"
        return "fr" if language.lower().startswith("fr") else "en"

    def _items(self) -> list[dict[str, Any]]:
        buckets = categorize_mail(
            self.coordinator.data,
            today=dt_util.now().date(),
            include_ads=self._include_ads(),
            lang=self._lang(),
        )
        return buckets[self._spec.bucket]

    @property
    def native_value(self) -> int:
        return len(self._items())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self._items()
        logos = [item["image_url"] for item in items if item.get("image_url")]
        digital_flyers = [item for item in items if item.get("has_digital_flyer")]

        attributes: dict[str, Any] = {
            "items": items,
            "packages": items,
            "count": len(items),
            "digital_flyer_count": len(digital_flyers),
            "ads_included": self._include_ads(),
            "integration_id": DOMAIN,
            "last_check": dt_util.now().isoformat(),
        }
        if logos:
            attributes["image_url"] = logos[0]
            attributes["logos"] = list(dict.fromkeys(logos))
        return attributes
