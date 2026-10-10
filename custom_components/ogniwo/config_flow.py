"""Config flow of the Ogniwo integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OgniwoClient
from .const import (
    CONF_READ_ONLY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import OgniwoConfigEntry
from .errors import OgniwoAuthError, OgniwoConnectionError, OgniwoError, OgniwoInvalidHostError
from .models import ControllerInfo

DEFAULT_TITLE = "Ogniwo"

CONNECTION_FIELDS = {
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
}
USER_SCHEMA = vol.Schema({**CONNECTION_FIELDS, vol.Optional(CONF_NAME): str})
RECONFIGURE_SCHEMA = vol.Schema(CONNECTION_FIELDS)
REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _connection(user_input: Mapping[str, Any]) -> dict[str, str]:
    return {key: user_input[key] for key in (CONF_HOST, CONF_USERNAME, CONF_PASSWORD)}


class OgniwoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a controller by its address and credentials."""

    VERSION = 1

    async def _async_probe(
        self, host: str, username: str, password: str
    ) -> tuple[ControllerInfo | None, dict[str, str]]:
        """Try to talk to the controller; return its identity or a form error."""
        try:
            client = OgniwoClient(async_get_clientsession(self.hass), host, username, password)
        except OgniwoInvalidHostError:
            return None, {"base": "invalid_host"}

        try:
            # Identifying the controller may already fall back to the registers,
            # but the values have to be readable for the entry to be of any use.
            info = await client.async_get_info()
            await client.async_get_snapshot()
        except OgniwoAuthError:
            return None, {"base": "invalid_auth"}
        except OgniwoConnectionError:
            # Something answers at this address but not with the register API.
            return None, {"base": await self._async_diagnose(client, "cannot_connect")}
        except OgniwoError:
            return None, {"base": await self._async_diagnose(client, "unknown")}
        return info, {}

    async def _async_diagnose(self, client: OgniwoClient, fallback: str) -> str:
        """Name the reason the register API did not answer, as far as it can be told."""
        return "legacy_api" if await client.async_speaks_legacy_api() else fallback

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the address and credentials of the controller."""
        errors: dict[str, str] = {}
        if user_input is not None:
            connection = _connection(user_input)
            info, errors = await self._async_probe(**connection)
            if info is not None:
                await self.async_set_unique_id(info.mac)
                self._abort_if_unique_id_configured(updates={CONF_HOST: connection[CONF_HOST]})
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or info.name or DEFAULT_TITLE,
                    data=connection,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address or credentials, e.g. after the controller got a new address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            connection = _connection(user_input)
            info, errors = await self._async_probe(**connection)
            if info is not None:
                await self.async_set_unique_id(info.mac)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=connection)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                RECONFIGURE_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start again after the controller rejected the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            info, errors = await self._async_probe(
                entry.data[CONF_HOST], user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if info is not None:
                await self.async_set_unique_id(info.mac)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        suggested = user_input or {CONF_USERNAME: entry.data[CONF_USERNAME]}
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(REAUTH_SCHEMA, suggested),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: OgniwoConfigEntry) -> OgniwoOptionsFlow:
        """Return the options flow."""
        return OgniwoOptionsFlow()


class OgniwoOptionsFlow(OptionsFlowWithReload):
    """Polling interval and read-only mode; read-only mode changes which entities exist."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL)),
                vol.Required(CONF_READ_ONLY, default=options.get(CONF_READ_ONLY, False)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
