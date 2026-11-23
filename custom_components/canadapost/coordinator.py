"""DataUpdateCoordinator for Canada Post My Mail."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import CanadaPostAPI, CanadaPostApiError, CanadaPostReauthRequired
from .const import (
    CONF_TOPIC_ID,
    CONF_USERNAME,
    DOMAIN,
    QUIET_HOUR_END,
    QUIET_HOUR_START,
    SCAN_INTERVAL_DAY_MINUTES,
    SCAN_INTERVAL_NIGHT_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def _next_poll_interval() -> timedelta:
    """Poll hourly during daytime (06:00-22:00) and every 4 hours overnight."""
    hour = dt_util.now().hour
    if hour >= QUIET_HOUR_START or hour < QUIET_HOUR_END:
        return timedelta(minutes=SCAN_INTERVAL_NIGHT_MINUTES)
    return timedelta(minutes=SCAN_INTERVAL_DAY_MINUTES)


class CanadaPostUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator polling Canada Post My Mail notifications."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: CanadaPostAPI,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=_next_poll_interval(),
        )
        self.api = api
        self.entry = entry
        self.topic_id: str = entry.data[CONF_TOPIC_ID]

    async def _async_update_data(self) -> dict[str, Any]:
        self.update_interval = _next_poll_interval()
        today_str = dt_util.now().strftime("%Y%m%d")
        try:
            return await self.api.async_get_mail(self.topic_id, start_date=today_str)
        except CanadaPostReauthRequired as err:
            raise ConfigEntryAuthFailed(
                "Canada Post session expired; please re-authenticate"
            ) from err
        except CanadaPostApiError as err:
            raise UpdateFailed(f"Canada Post API error: {err}") from err

    @property
    def device_info(self) -> DeviceInfo:
        username = self.entry.data.get(CONF_USERNAME)
        name = f"Canada Post My Mail ({username})" if username else "Canada Post My Mail"
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=name,
            manufacturer="Canada Post",
            model="My Mail",
        )
