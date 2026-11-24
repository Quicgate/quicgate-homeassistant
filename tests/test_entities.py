"""What Home Assistant shows of a quicgate, and what the switches do."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.quicgate.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import URL, FakeQuicgate


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _next_reading(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done(wait_background_tasks=True)


def _state(hass: HomeAssistant, entity_id: str):
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} does not exist; there is: " + ", ".join(
        sorted(s.entity_id for s in hass.states.async_all())
    )
    return state


async def test_the_overall_sensors(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)

    assert _state(hass, "sensor.quicgate_hosts_switched_on").state == "2"
    assert _state(hass, "sensor.quicgate_hosts_switched_on").attributes["switched_off"] == [
        "old.example.com"
    ]

    down = _state(hass, "sensor.quicgate_backends_unreachable")
    assert down.state == "1"
    assert down.attributes["backends"] == [
        {"host": "git.example.com", "backend": "http://10.0.0.6:3000", "error": "connection refused"}
    ]

    days = _state(hass, "sensor.quicgate_days_until_first_certificate_expires")
    assert int(days.state) > 14
    assert days.attributes["host"] == "git.example.com"

    assert _state(hass, "sensor.quicgate_certificates_with_a_problem").state == "0"
    assert _state(hass, "sensor.quicgate_requests_last_hour").state == "1234"
    blocked = _state(hass, "sensor.quicgate_blocked_requests_last_hour")
    assert blocked.state == "42"
    assert blocked.attributes["by_reason"] == {"access list": 40, "banned address": 2}
    assert _state(hass, "sensor.quicgate_server_errors_last_hour").state == "3"
    assert float(_state(hass, "sensor.quicgate_data_sent_last_hour").state) == pytest.approx(42.0)
    assert float(_state(hass, "sensor.quicgate_data_received_last_hour").state) == pytest.approx(1.5)
    assert _state(hass, "sensor.quicgate_open_connections").state == "7"
    assert _state(hass, "sensor.quicgate_response_time").state == "12.5"

    banned = _state(hass, "sensor.quicgate_banned_addresses")
    assert banned.state == "1"
    assert banned.attributes["addresses"][0]["address"] == "203.0.113.9"
    assert banned.attributes["addresses"][0]["host"] == "app.example.com"


async def test_the_problem_indicators(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)
    assert _state(hass, "binary_sensor.quicgate_backends").state == "on"
    assert _state(hass, "binary_sensor.quicgate_certificates").state == "off"
    assert _state(hass, "binary_sensor.quicgate_ports").state == "off"
    assert _state(hass, "binary_sensor.quicgate_vpn").state == "off"

    quicgate.hosts[1]["backends"][0]["up"] = True
    quicgate.hosts[0]["certificate"] = {"status": "failed", "domain": "app.example.com", "lastError": "DNS problem"}
    quicgate.traffic["ports"][1]["state"] = "failed"
    quicgate.overview["vpn"]["running"] = False
    quicgate.apply()
    await _next_reading(hass)

    assert _state(hass, "binary_sensor.quicgate_backends").state == "off"
    certificates = _state(hass, "binary_sensor.quicgate_certificates")
    assert certificates.state == "on"
    assert certificates.attributes["failed"][0]["error"] == "DNS problem"
    assert _state(hass, "binary_sensor.quicgate_ports").state == "on"
    assert _state(hass, "binary_sensor.quicgate_vpn").state == "on"
    assert _state(hass, "sensor.quicgate_certificates_with_a_problem").state == "1"


async def test_a_switch_per_host(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)
    app = _state(hass, "switch.quicgate_app_example_com")
    assert app.state == "on"
    assert app.attributes["friendly_name"] == "quicgate app.example.com"
    assert app.attributes["forwards_to"] == "http://10.0.0.5:8080"
    assert _state(hass, "switch.quicgate_old_example_com").state == "off"

    quicgate.mocker.mock_calls.clear()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.quicgate_app_example_com"}, blocking=True
    )
    puts = [c for c in quicgate.mocker.mock_calls if c[0] == "PUT"]
    assert len(puts) == 1
    assert str(puts[0][1]) == f"{URL}/api/hosts/1/enabled"
    assert puts[0][2] == {"enabled": False}
    assert puts[0][3]["Authorization"] == "Bearer qgs_test"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.quicgate_old_example_com"}, blocking=True
    )
    puts = [c for c in quicgate.mocker.mock_calls if c[0] == "PUT"]
    assert str(puts[-1][1]) == f"{URL}/api/hosts/3/enabled"
    assert puts[-1][2] == {"enabled": True}


async def test_a_monitoring_token_gets_no_switches(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    quicgate.access = "monitor"
    quicgate.apply()
    await _setup(hass, entry)
    assert hass.states.async_entity_ids("switch") == []
    assert _state(hass, "sensor.quicgate_requests_last_hour").state == "1234"


async def test_a_refused_switch_says_why(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)
    quicgate.mocker.clear_requests()
    quicgate.mocker.put(
        f"{URL}/api/hosts/1/enabled", status=403, json={"error": "this API token may not do that"}
    )
    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": "switch.quicgate_app_example_com"}, blocking=True
        )
    assert raised.value.translation_key == "switch_not_allowed"
    assert _state(hass, "switch.quicgate_app_example_com").state == "on"


async def test_the_per_host_details_start_switched_off(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)
    registry = er.async_get(hass)
    backend = registry.async_get("binary_sensor.quicgate_app_example_com_backend")
    certificate = registry.async_get("sensor.quicgate_app_example_com_certificate_expires")
    assert backend is not None and backend.disabled
    assert certificate is not None and certificate.disabled
    # A redirect has no backend to watch.
    assert registry.async_get("binary_sensor.quicgate_old_example_com_backend") is None


async def test_hosts_come_and_go(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)
    registry = er.async_get(hass)

    quicgate.hosts = [h for h in quicgate.hosts if h["id"] != 3]
    quicgate.hosts.append(
        {"id": 4, "name": "new.example.com", "domains": ["new.example.com"], "type": "proxy",
         "enabled": True, "target": "http://10.0.0.7:80", "backends": []}
    )
    quicgate.hosts[0]["name"] = "renamed.example.com"
    quicgate.apply()
    await _next_reading(hass)

    assert _state(hass, "switch.quicgate_new_example_com").state == "on"
    assert registry.async_get("switch.quicgate_old_example_com") is None
    assert hass.states.get("switch.quicgate_old_example_com") is None
    # A renamed host keeps its entity and shows the new name.
    renamed = _state(hass, "switch.quicgate_app_example_com")
    assert renamed.attributes["friendly_name"] == "quicgate renamed.example.com"


async def test_the_version_check(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    quicgate.newest = "v1.20.0"
    quicgate.apply()
    await _setup(hass, entry)
    update = _state(hass, "update.quicgate")
    assert update.state == "on"
    assert update.attributes["installed_version"] == "1.19.0"
    assert update.attributes["latest_version"] == "1.20.0"
    assert update.attributes["release_url"].endswith("/v1.20.0")


async def test_an_updated_quicgate_shows_its_new_version(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    from homeassistant.helpers import device_registry as dr

    quicgate.newest = "v1.20.0"
    quicgate.apply()
    await _setup(hass, entry)
    devices = dr.async_get(hass)
    (device,) = dr.async_entries_for_config_entry(devices, entry.entry_id)
    assert device.sw_version == "1.19.0"

    quicgate.overview["version"] = "v1.20.0"
    quicgate.apply()
    await _next_reading(hass)
    assert _state(hass, "update.quicgate").state == "off"
    (device,) = dr.async_entries_for_config_entry(devices, entry.entry_id)
    assert device.sw_version == "1.20.0"


async def test_no_word_from_github_means_nothing_new(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    quicgate.newest = None
    quicgate.apply()
    await _setup(hass, entry)
    update = _state(hass, "update.quicgate")
    assert update.state == "off"
    assert update.attributes["installed_version"] == "1.19.0"


async def test_a_token_that_stops_working_asks_for_a_new_one(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)
    quicgate.mocker.clear_requests()
    quicgate.mocker.get(f"{URL}/api/overview", status=401, json={"error": "invalid API token"})
    quicgate.mocker.get(f"{URL}/api/hosts/status", status=401, json={"error": "invalid API token"})
    quicgate.mocker.get(f"{URL}/api/traffic?range=1h", status=401, json={"error": "invalid API token"})
    quicgate.mocker.get(f"{URL}/api/bans", status=401, json={"error": "invalid API token"})
    await _next_reading(hass)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_a_quicgate_that_is_down_makes_everything_unavailable(
    hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry
) -> None:
    await _setup(hass, entry)
    quicgate.mocker.clear_requests()
    for path in ("overview", "hosts/status", "traffic?range=1h", "bans"):
        quicgate.mocker.get(f"{URL}/api/{path}", status=502, text="bad gateway")
    await _next_reading(hass)
    assert _state(hass, "sensor.quicgate_requests_last_hour").state == "unavailable"
    assert _state(hass, "switch.quicgate_app_example_com").state == "unavailable"
    assert entry.state is ConfigEntryState.LOADED

    quicgate.apply()
    await _next_reading(hass)
    assert _state(hass, "sensor.quicgate_requests_last_hour").state == "1234"


async def test_unloading(hass: HomeAssistant, quicgate: FakeQuicgate, entry: MockConfigEntry) -> None:
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
