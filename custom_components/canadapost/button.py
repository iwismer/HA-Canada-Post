"""Button platform for Canada Post My Mail."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TOPIC_ID, DOMAIN
from .coordinator import CanadaPostUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canada Post My Mail refresh button."""
    coordinator: CanadaPostUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    topic_id: str = entry.data[CONF_TOPIC_ID]
    async_add_entities([CanadaPostRefreshButton(coordinator, topic_id)])


class CanadaPostRefreshButton(
    CoordinatorEntity[CanadaPostUpdateCoordinator], ButtonEntity
):
    """Button to trigger an immediate My Mail refresh."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(
        self, coordinator: CanadaPostUpdateCoordinator, topic_id: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"cp_v2_{topic_id}_refresh"

    async def async_press(self) -> None:
        """Request an immediate coordinator refresh."""
        await self.coordinator.async_request_refresh()
