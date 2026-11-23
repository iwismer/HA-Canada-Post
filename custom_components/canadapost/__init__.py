"""The Canada Post My Mail integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    CanadaPostAPI,
    CanadaPostApiError,
    CanadaPostAuthError,
    CanadaPostTwoStepRequired,
    async_revoke_token,
    extract_topic_id,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_ID_TOKEN,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_TOPIC_ID,
    CONF_USERNAME,
    DOMAIN,
)
from .coordinator import CanadaPostUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy v1 entries (which stored plaintext password) to token-only v2."""
    if entry.version >= 2:
        return True

    _LOGGER.info("Migrating Canada Post My Mail entry %s from v1 to v2", entry.entry_id)
    data = dict(entry.data)
    password = data.pop(CONF_PASSWORD, None)
    username = data.get(CONF_USERNAME)

    if password and username and not data.get(CONF_REFRESH_TOKEN):
        session = async_get_clientsession(hass)
        api = CanadaPostAPI(session)
        try:
            tokens = await api.async_login(username, password)
            data.update(tokens)
            if not data.get(CONF_TOPIC_ID):
                topic_id = extract_topic_id(tokens[CONF_ID_TOKEN])
                if topic_id:
                    data[CONF_TOPIC_ID] = topic_id
        except (CanadaPostAuthError, CanadaPostTwoStepRequired, CanadaPostApiError) as err:
            _LOGGER.warning(
                "Could not migrate v1 credentials automatically (%s); reauth will be requested",
                err,
            )

    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Canada Post My Mail from a config entry."""
    if not entry.data.get(CONF_REFRESH_TOKEN) or not entry.data.get(CONF_TOPIC_ID):
        raise ConfigEntryAuthFailed("Missing Canada Post tokens; please re-authenticate")

    session = async_get_clientsession(hass)

    async def _persist_tokens(tokens: dict[str, Any]) -> None:
        new_data = {**entry.data, **tokens}
        new_data.pop(CONF_PASSWORD, None)
        hass.config_entries.async_update_entry(entry, data=new_data)

    api = CanadaPostAPI(
        session,
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        id_token=entry.data.get(CONF_ID_TOKEN),
        expires_at=entry.data.get(CONF_EXPIRES_AT),
        token_callback=_persist_tokens,
    )

    coordinator = CanadaPostUpdateCoordinator(hass, api, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(f"Unable to connect to Canada Post: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    last_options = dict(entry.options)

    async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        nonlocal last_options
        if dict(updated_entry.options) != last_options:
            last_options = dict(updated_entry.options)
            await hass.config_entries.async_reload(updated_entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Revoke stored refresh token at Canada Post when the entry is removed."""
    refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
    if not refresh_token:
        return
    session = async_get_clientsession(hass)
    try:
        await async_revoke_token(session, refresh_token)
    except CanadaPostApiError as err:
        _LOGGER.warning(
            "Could not revoke Canada Post refresh token for entry %s: %s",
            entry.entry_id,
            err,
        )
