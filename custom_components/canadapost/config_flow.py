"""Config flow and options flow for Canada Post My Mail."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
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
    CONF_ID_TOKEN,
    CONF_INCLUDE_ADS,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_TOPIC_ID,
    CONF_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _best_effort_revoke(hass: Any, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    try:
        await async_revoke_token(async_get_clientsession(hass), refresh_token)
    except CanadaPostApiError as err:
        _LOGGER.warning("Could not revoke Canada Post refresh token: %s", err)


class CanadaPostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Canada Post My Mail."""

    VERSION = 2

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            include_ads = user_input.get(CONF_INCLUDE_ADS, True)

            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = CanadaPostAPI(session)
            tokens: dict[str, Any] | None = None
            try:
                tokens = await api.async_login(username, password)
                topic_id = extract_topic_id(tokens[CONF_ID_TOKEN])
                if not topic_id:
                    await _best_effort_revoke(self.hass, tokens.get(CONF_REFRESH_TOKEN))
                    errors["base"] = "cannot_discover_id"
                else:
                    # Verify My Mail endpoint is reachable for this account
                    await api.async_get_mail(topic_id)
                    return self.async_create_entry(
                        title=username,
                        data={
                            CONF_USERNAME: username,
                            CONF_TOPIC_ID: topic_id,
                            **tokens,
                        },
                        options={CONF_INCLUDE_ADS: include_ads},
                    )
            except CanadaPostTwoStepRequired:
                errors["base"] = "two_step_not_supported"
            except CanadaPostAuthError:
                errors["base"] = "auth_failed"
            except CanadaPostApiError as err:
                _LOGGER.error("Canada Post setup error: %s", err)
                if tokens:
                    await _best_effort_revoke(self.hass, tokens.get(CONF_REFRESH_TOKEN))
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_INCLUDE_ADS, default=True): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        username = self._reauth_entry.data.get(CONF_USERNAME, "")

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = CanadaPostAPI(session)
            try:
                tokens = await api.async_login(username, user_input[CONF_PASSWORD])
                topic_id = extract_topic_id(tokens[CONF_ID_TOKEN]) or self._reauth_entry.data.get(
                    CONF_TOPIC_ID
                )
                if not topic_id:
                    await _best_effort_revoke(self.hass, tokens.get(CONF_REFRESH_TOKEN))
                    errors["base"] = "cannot_discover_id"
                else:
                    old_refresh = self._reauth_entry.data.get(CONF_REFRESH_TOKEN)
                    new_data = {
                        CONF_USERNAME: username,
                        CONF_TOPIC_ID: topic_id,
                        **tokens,
                    }
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry, data=new_data
                    )
                    if old_refresh and old_refresh != tokens.get(CONF_REFRESH_TOKEN):
                        await _best_effort_revoke(self.hass, old_refresh)
                    await self.hass.config_entries.async_reload(
                        self._reauth_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")
            except CanadaPostTwoStepRequired:
                errors["base"] = "two_step_not_supported"
            except CanadaPostAuthError:
                errors["base"] = "auth_failed"
            except CanadaPostApiError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"username": username},
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry) -> OptionsFlow:
        return CanadaPostOptionsFlowHandler()


class CanadaPostOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Canada Post My Mail."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_val = self.config_entry.options.get(
            CONF_INCLUDE_ADS,
            self.config_entry.data.get(CONF_INCLUDE_ADS, True),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_INCLUDE_ADS, default=current_val): bool,
                }
            ),
        )
