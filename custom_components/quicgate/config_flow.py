"""Connecting a quicgate to Home Assistant."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME, CONF_TOKEN, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    ACCESS_FULL,
    QuicgateAuthError,
    QuicgateClient,
    QuicgateConnectionError,
    QuicgateError,
    QuicgateTooOldError,
    normalize_url,
)
from .const import CONF_VERIFY_SSL, DEFAULT_NAME, DOMAIN, LOGGER

_TOKEN = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_URL): _URL,
        vol.Required(CONF_TOKEN): _TOKEN,
        vol.Required(CONF_VERIFY_SSL, default=True): bool,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): _TOKEN})


class QuicgateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Asks where quicgate is and for a token, and checks both."""

    VERSION = 1

    def __init__(self) -> None:
        self._title = DEFAULT_NAME
        self._data: dict[str, Any] = {}

    async def _check(self, data: Mapping[str, Any]) -> tuple[str | None, str | None]:
        """Try a token. Returns what it may do, or why it does not work."""
        verify_ssl = data.get(CONF_VERIFY_SSL, True)
        client = QuicgateClient(
            async_get_clientsession(self.hass, verify_ssl=verify_ssl),
            data[CONF_URL],
            data[CONF_TOKEN],
            verify_ssl,
        )
        try:
            access = await client.access()
            await client.hosts()
        except QuicgateAuthError:
            return None, "invalid_token"
        except QuicgateTooOldError:
            return None, "too_old"
        except QuicgateConnectionError:
            return None, "cannot_connect"
        except QuicgateError:
            LOGGER.exception("Unexpected answer from quicgate")
            return None, "unknown"
        return access, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_URL: normalize_url(user_input[CONF_URL]),
                CONF_TOKEN: user_input[CONF_TOKEN].strip(),
                CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, True),
            }
            await self.async_set_unique_id(data[CONF_URL].lower())
            self._abort_if_unique_id_configured()
            access, error = await self._check(data)
            if error:
                errors["base"] = error
            else:
                self._title = user_input.get(CONF_NAME) or DEFAULT_NAME
                self._data = data
                if access == ACCESS_FULL:
                    return await self.async_step_full_access()
                return self.async_create_entry(title=self._title, data=self._data)
        shown = {k: v for k, v in (user_input or {}).items() if k != CONF_TOKEN}
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, shown),
            errors=errors,
        )

    async def async_step_full_access(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A full token works, but is more than this needs: say so, then let them choose."""
        return self.async_show_menu(
            step_id="full_access", menu_options=["user", "use_full_token"]
        )

    async def async_step_use_full_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_create_entry(title=self._title, data=self._data)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The token stopped working: ask for a new one."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_TOKEN: user_input[CONF_TOKEN].strip()}
            _, error = await self._check(data)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"url": entry.data[CONF_URL]},
        )
