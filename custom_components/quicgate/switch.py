"""A switch per host: on means quicgate serves it."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import QuicgateError, QuicgateNotAllowedError
from .const import DOMAIN
from .coordinator import QuicgateConfigEntry, QuicgateCoordinator
from .entity import QuicgateHostEntity, setup_host_entities

# One change at a time: every switch makes quicgate rebuild its routes.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QuicgateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the host switches, when the token may switch hosts."""
    coordinator = entry.runtime_data
    if not coordinator.can_switch:
        return
    setup_host_entities(
        hass,
        entry,
        async_add_entities,
        "switch",
        "enabled",
        lambda host_id: HostSwitch(coordinator, host_id),
    )


class HostSwitch(QuicgateHostEntity, SwitchEntity):
    """Switches one host on or off."""

    _attr_translation_key = "host"

    def __init__(self, coordinator: QuicgateCoordinator, host_id: int) -> None:
        super().__init__(coordinator, host_id, "enabled")

    @property
    def is_on(self) -> bool | None:
        host = self.host
        return bool(host.get("enabled")) if host else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        host = self.host
        if not host:
            return None
        return {
            "kind": host.get("type"),
            "forwards_to": host.get("target") or None,
            "names": host.get("domains") or [],
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._switch(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._switch(False)

    async def _switch(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_host_enabled(self._host_id, enabled)
        except QuicgateNotAllowedError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="switch_not_allowed"
            ) from err
        except QuicgateError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="switch_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        # Show the new state at once, then read what quicgate made of it.
        if (host := self.host) is not None:
            host["enabled"] = enabled
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
