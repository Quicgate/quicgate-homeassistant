"""Connecting a quicgate."""

from __future__ import annotations

import aiohttp
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.quicgate.const import CONF_VERIFY_SSL, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME, CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import URL, FakeQuicgate

FORM = {
    CONF_NAME: "quicgate",
    CONF_URL: URL + "/",
    CONF_TOKEN: " qgs_test ",
    CONF_VERIFY_SSL: True,
}


async def _start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return result


async def test_a_limited_token_connects_right_away(
    hass: HomeAssistant, quicgate: FakeQuicgate
) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "quicgate"
    # The address is stored without the trailing slash, the token without spaces.
    assert result["data"] == {CONF_URL: URL, CONF_TOKEN: "qgs_test", CONF_VERIFY_SSL: True}


async def test_a_full_token_is_questioned_but_can_be_used(
    hass: HomeAssistant, quicgate: FakeQuicgate
) -> None:
    quicgate.access = "full"
    quicgate.apply()
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "full_access"
    assert result["menu_options"] == ["user", "use_full_token"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "use_full_token"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_a_full_token_can_be_swapped_for_another(
    hass: HomeAssistant, quicgate: FakeQuicgate
) -> None:
    quicgate.access = "full"
    quicgate.apply()
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_a_token_quicgate_refuses(hass: HomeAssistant, quicgate: FakeQuicgate) -> None:
    quicgate.mocker.clear_requests()
    quicgate.mocker.get(f"{URL}/api/me", status=401, json={"error": "invalid API token"})
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_token"}
    # With a good token the same form goes through.
    quicgate.apply()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_a_quicgate_that_is_too_old(hass: HomeAssistant, quicgate: FakeQuicgate) -> None:
    quicgate.mocker.clear_requests()
    # Before 1.19.0: a token has no access level, and there is no host status.
    quicgate.mocker.get(f"{URL}/api/me", json={"token": True})
    quicgate.mocker.get(f"{URL}/api/hosts/status", status=404, text="404 page not found")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["errors"] == {"base": "too_old"}


async def test_nothing_answers_at_the_address(
    hass: HomeAssistant, quicgate: FakeQuicgate
) -> None:
    quicgate.mocker.clear_requests()
    quicgate.mocker.get(f"{URL}/api/me", exc=aiohttp.ClientConnectionError("refused"))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_something_else_answers_at_the_address(
    hass: HomeAssistant, quicgate: FakeQuicgate
) -> None:
    quicgate.mocker.clear_requests()
    quicgate.mocker.get(f"{URL}/api/me", text="<html>welcome</html>")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_the_same_quicgate_is_not_connected_twice(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_a_new_token_after_the_old_one_stopped_working(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    quicgate.mocker.clear_requests()
    quicgate.mocker.get(f"{URL}/api/me", status=401, json={"error": "invalid API token"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "qgs_wrong"}
    )
    assert result["errors"] == {"base": "invalid_token"}

    quicgate.apply()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "qgs_new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "qgs_new"
    assert entry.data[CONF_URL] == URL
