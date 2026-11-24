"""Sensors of a quicgate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import status
from .const import MAX_LISTED
from .coordinator import QuicgateConfigEntry, QuicgateCoordinator, QuicgateData
from .entity import QuicgateEntity, QuicgateHostEntity, setup_host_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class QuicgateSensorDescription(SensorEntityDescription):
    """A sensor and how to read it from one reading of quicgate."""

    value: Callable[[QuicgateData], Any]
    attributes: Callable[[QuicgateData], dict[str, Any]] | None = None


def _hosts_attributes(data: QuicgateData) -> dict[str, Any]:
    hosts = data.overview.get("hosts") or {}
    return {
        "total": hosts.get("total"),
        "switched_off": sorted(
            str(h.get("name")) for h in data.hosts.values() if not h.get("enabled")
        )[:MAX_LISTED],
    }


def _certificate_days(data: QuicgateData) -> int | None:
    first = status.first_certificate_expiry(data.hosts)
    if first is None:
        return None
    return status.days_left(first[0], dt_util.utcnow())


def _certificate_days_attributes(data: QuicgateData) -> dict[str, Any]:
    first = status.first_certificate_expiry(data.hosts)
    if first is None:
        return {}
    expires, host = first
    return {"host": host.get("name"), "expires": expires.isoformat()}


def _response_time(data: QuicgateData) -> float | None:
    p50 = status.totals(data.traffic).get("p50")
    if p50 is None or p50 < 0:
        return None
    return p50


def _response_time_attributes(data: QuicgateData) -> dict[str, Any]:
    totals = status.totals(data.traffic)
    return {
        name: totals.get(key)
        for name, key in (("slowest_5_percent_ms", "p95"), ("slowest_1_percent_ms", "p99"))
        if totals.get(key) is not None and totals.get(key) >= 0
    }


def _bans_attributes(data: QuicgateData) -> dict[str, Any]:
    return {
        "addresses": [
            {
                "address": ban.get("ip"),
                "country": ban.get("country"),
                "host": ban.get("host"),
                "reason": ban.get("reason"),
                "until": ban.get("until"),
            }
            for ban in data.bans[:MAX_LISTED]
        ]
    }


def _started(data: QuicgateData) -> datetime | None:
    started = data.overview.get("startedAt")
    if not started:
        return None
    return dt_util.utc_from_timestamp(int(started))


SENSORS: tuple[QuicgateSensorDescription, ...] = (
    QuicgateSensorDescription(
        key="hosts_enabled",
        translation_key="hosts_enabled",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: (d.overview.get("hosts") or {}).get("enabled"),
        attributes=_hosts_attributes,
    ),
    QuicgateSensorDescription(
        key="backends_down",
        translation_key="backends_down",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(status.backends_down(d.hosts)),
        attributes=lambda d: {"backends": status.backends_down(d.hosts)[:MAX_LISTED]},
    ),
    QuicgateSensorDescription(
        key="certificate_days",
        translation_key="certificate_days",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value=_certificate_days,
        attributes=_certificate_days_attributes,
    ),
    QuicgateSensorDescription(
        key="certificates_failed",
        translation_key="certificates_failed",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(status.certificates_failed(d.hosts)),
        attributes=lambda d: {
            "certificates": status.certificates_failed(d.hosts)[:MAX_LISTED]
        },
    ),
    QuicgateSensorDescription(
        key="requests",
        translation_key="requests",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: status.totals(d.traffic).get("requests"),
        attributes=lambda d: {
            "by_http_version": status.totals(d.traffic).get("protocols") or {},
            "by_status": status.totals(d.traffic).get("status") or {},
        },
    ),
    QuicgateSensorDescription(
        key="blocked",
        translation_key="blocked",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: status.blocked_total(d.traffic),
        attributes=lambda d: {"by_reason": status.blocked_by_reason(d.traffic)},
    ),
    QuicgateSensorDescription(
        key="server_errors",
        translation_key="server_errors",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: (status.totals(d.traffic).get("status") or {}).get("5xx", 0),
    ),
    QuicgateSensorDescription(
        key="data_in",
        translation_key="data_in",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: status.totals(d.traffic).get("in"),
    ),
    QuicgateSensorDescription(
        key="data_out",
        translation_key="data_out",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: status.totals(d.traffic).get("out"),
    ),
    QuicgateSensorDescription(
        key="open_connections",
        translation_key="open_connections",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.traffic.get("open"),
    ),
    QuicgateSensorDescription(
        key="banned",
        translation_key="banned",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.bans),
        attributes=_bans_attributes,
    ),
    QuicgateSensorDescription(
        key="response_time",
        translation_key="response_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value=_response_time,
        attributes=_response_time_attributes,
    ),
    QuicgateSensorDescription(
        key="started",
        translation_key="started",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_started,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QuicgateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of one quicgate."""
    coordinator = entry.runtime_data
    async_add_entities(QuicgateSensor(coordinator, description) for description in SENSORS)
    setup_host_entities(
        hass,
        entry,
        async_add_entities,
        "sensor",
        "certificate",
        lambda host_id: HostCertificateSensor(coordinator, host_id),
    )


class QuicgateSensor(QuicgateEntity, SensorEntity):
    """A number or a moment about the whole quicgate."""

    entity_description: QuicgateSensorDescription

    def __init__(
        self, coordinator: QuicgateCoordinator, description: QuicgateSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator.data)


class HostCertificateSensor(QuicgateHostEntity, SensorEntity):
    """When the certificate of one host expires. Off until you switch it on."""

    _attr_translation_key = "host_certificate"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: QuicgateCoordinator, host_id: int) -> None:
        super().__init__(coordinator, host_id, "certificate")

    @property
    def native_value(self) -> datetime | None:
        host = self.host
        return status.certificate_expiry(host) if host else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        cert = (self.host or {}).get("certificate")
        if not cert:
            return None
        return {
            "state": cert.get("status"),
            "domain": cert.get("domain"),
            "error": cert.get("lastError"),
        }
