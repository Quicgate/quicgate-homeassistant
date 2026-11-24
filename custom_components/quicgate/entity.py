"""What every quicgate entity shares."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import QuicgateConfigEntry, QuicgateCoordinator


class QuicgateEntity(CoordinatorEntity[QuicgateCoordinator]):
    """An entity of one quicgate."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: QuicgateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Quicgate",
            model="Reverse proxy",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=coordinator.data.version.removeprefix("v") or None,
            configuration_url=coordinator.client.url,
        )


class QuicgateHostEntity(QuicgateEntity):
    """An entity about one host of a quicgate."""

    def __init__(self, coordinator: QuicgateCoordinator, host_id: int, kind: str) -> None:
        super().__init__(coordinator, host_unique_key(host_id, kind))
        self._host_id = host_id
        self._attr_translation_placeholders = {"host": self._host_name()}

    @property
    def host(self) -> dict[str, Any] | None:
        """The host as quicgate last reported it, or None once it is deleted."""
        return self.coordinator.data.hosts.get(self._host_id)

    def _host_name(self) -> str:
        host = self.coordinator.data.hosts.get(self._host_id) or {}
        return str(host.get("name") or f"host {self._host_id}")

    @property
    def available(self) -> bool:
        return super().available and self.host is not None


def host_unique_key(host_id: int, kind: str) -> str:
    """The part of a host entity's unique id after the config entry."""
    return f"host_{host_id}_{kind}"


def setup_host_entities(
    hass: HomeAssistant,
    entry: QuicgateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    platform: str,
    kind: str,
    make: Callable[[int], Entity | None],
) -> None:
    """Keep one entity per host: add them as hosts appear, remove them as hosts go."""
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def sync() -> None:
        current = set(coordinator.data.hosts)
        new: Iterable[int] = sorted(current - known)
        entities = [e for e in (make(host_id) for host_id in new) if e is not None]
        known.update(new)
        if entities:
            async_add_entities(entities)
        gone = known - current
        if gone:
            registry = er.async_get(hass)
            for host_id in gone:
                unique_id = f"{entry.entry_id}_{host_unique_key(host_id, kind)}"
                if entity_id := registry.async_get_entity_id(platform, DOMAIN, unique_id):
                    registry.async_remove(entity_id)
            known.difference_update(gone)

    sync()
    entry.async_on_unload(coordinator.async_add_listener(sync))
