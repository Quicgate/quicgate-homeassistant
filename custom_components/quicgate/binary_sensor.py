"""Problem indicators of a quicgate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import status
from .const import MAX_LISTED
from .coordinator import QuicgateConfigEntry, QuicgateCoordinator, QuicgateData
from .entity import QuicgateEntity, QuicgateHostEntity, setup_host_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class QuicgateProblemDescription(BinarySensorEntityDescription):
    """A problem indicator and how to read it from one reading of quicgate."""

    problem: Callable[[QuicgateData], bool | None]
    attributes: Callable[[QuicgateData], dict[str, Any]] | None = None


def _certificate_problem(data: QuicgateData) -> bool:
    return bool(
        status.certificates_failed(data.hosts)
        or status.certificates_soon(data.hosts, dt_util.utcnow())
    )


def _certificate_attributes(data: QuicgateData) -> dict[str, Any]:
    return {
        "failed": status.certificates_failed(data.hosts)[:MAX_LISTED],
        "expiring_soon": status.certificates_soon(data.hosts, dt_util.utcnow())[
            :MAX_LISTED
        ],
    }


PROBLEMS: tuple[QuicgateProblemDescription, ...] = (
    QuicgateProblemDescription(
        key="backends_problem",
        translation_key="backends_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        problem=lambda d: bool(status.backends_down(d.hosts)),
        attributes=lambda d: {"unreachable": status.backends_down(d.hosts)[:MAX_LISTED]},
    ),
    QuicgateProblemDescription(
        key="certificates_problem",
        translation_key="certificates_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        problem=_certificate_problem,
        attributes=_certificate_attributes,
    ),
    QuicgateProblemDescription(
        key="ports_problem",
        translation_key="ports_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        problem=lambda d: bool(status.ports_failed(d.traffic)),
        attributes=lambda d: {"not_listening": status.ports_failed(d.traffic)[:MAX_LISTED]},
    ),
    QuicgateProblemDescription(
        key="vpn_problem",
        translation_key="vpn_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        problem=lambda d: status.vpn_problem(d.overview),
        attributes=lambda d: {"error": (d.overview.get("vpn") or {}).get("error") or None},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QuicgateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the problem indicators of one quicgate."""
    coordinator = entry.runtime_data
    async_add_entities(
        QuicgateProblemSensor(coordinator, description) for description in PROBLEMS
    )

    def make(host_id: int) -> HostBackendSensor | None:
        if coordinator.data.hosts[host_id].get("type") != "proxy":
            return None
        return HostBackendSensor(coordinator, host_id)

    setup_host_entities(hass, entry, async_add_entities, "binary_sensor", "backend", make)


class QuicgateProblemSensor(QuicgateEntity, BinarySensorEntity):
    """On when something about the whole quicgate needs attention."""

    entity_description: QuicgateProblemDescription

    def __init__(
        self, coordinator: QuicgateCoordinator, description: QuicgateProblemDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.problem(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator.data)


class HostBackendSensor(QuicgateHostEntity, BinarySensorEntity):
    """Whether the backend of one host answers. Off until you switch it on."""

    _attr_translation_key = "host_backend"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: QuicgateCoordinator, host_id: int) -> None:
        super().__init__(coordinator, host_id, "backend")

    @property
    def is_on(self) -> bool | None:
        host = self.host
        return status.host_backends_up(host) if host else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        host = self.host
        if not host:
            return None
        return {
            "backends": [
                {
                    "backend": b.get("target"),
                    "answers": bool(b.get("up")),
                    "error": b.get("lastErr") or None,
                }
                for b in (host.get("backends") or [])[:MAX_LISTED]
            ]
        }
