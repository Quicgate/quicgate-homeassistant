"""quicgate: see and switch your reverse proxy from Home Assistant."""

from __future__ import annotations

import re

from homeassistant.const import CONF_TOKEN, CONF_URL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import QuicgateClient
from .const import CONF_VERIFY_SSL
from .coordinator import QuicgateConfigEntry, QuicgateCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

_HOST_ENTITY = re.compile(r"_host_(\d+)_[a-z]+$")


async def async_setup_entry(hass: HomeAssistant, entry: QuicgateConfigEntry) -> bool:
    """Set up one quicgate."""
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = QuicgateClient(
        session, entry.data[CONF_URL], entry.data[CONF_TOKEN], verify_ssl
    )
    coordinator = QuicgateCoordinator(
        hass, entry, client, async_get_clientsession(hass)
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_entities_of_deleted_hosts(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _reload_when_a_host_changes_shape(hass, entry, coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: QuicgateConfigEntry) -> bool:
    """Unload one quicgate."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _reload_when_a_host_changes_shape(
    hass: HomeAssistant, entry: QuicgateConfigEntry, coordinator: QuicgateCoordinator
) -> None:
    """Set the entities up again when a host is renamed or becomes another kind.

    An entity is named after its host when it is made, and which entities a
    host gets depends on its kind. Both are rare changes, and starting over is
    the simple way to follow them.
    """

    def shape() -> dict[int, tuple[object, object]]:
        return {
            host_id: (host.get("name"), host.get("type"))
            for host_id, host in coordinator.data.hosts.items()
        }

    before = shape()

    @callback
    def check() -> None:
        now = shape()
        if any(before[host_id] != now[host_id] for host_id in before.keys() & now.keys()):
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(coordinator.async_add_listener(check))


def _remove_entities_of_deleted_hosts(
    hass: HomeAssistant, entry: QuicgateConfigEntry, coordinator: QuicgateCoordinator
) -> None:
    """Drop the entities of hosts that were deleted while Home Assistant was off.

    Also drops the switches when the token may no longer switch.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        match = _HOST_ENTITY.search(entity.unique_id)
        if match is None:
            continue
        gone = int(match.group(1)) not in coordinator.data.hosts
        switch_without_right = entity.domain == "switch" and not coordinator.can_switch
        if gone or switch_without_right:
            registry.async_remove(entity.entity_id)
