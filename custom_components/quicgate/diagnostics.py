"""What a diagnostics download of a quicgate contains: numbers, no names, no token."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant

from .coordinator import QuicgateConfigEntry

TO_REDACT = {CONF_TOKEN, CONF_URL, "source", "keyId"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: QuicgateConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    by_type: dict[str, int] = {}
    for host in data.hosts.values():
        kind = str(host.get("type"))
        by_type[kind] = by_type.get(kind, 0) + 1
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "token_may": coordinator.access,
        "version": data.version,
        "newest_version": data.release.version if data.release else None,
        "hosts": {"count": len(data.hosts), "by_kind": by_type},
        "bans": len(data.bans),
        "overview": async_redact_data(data.overview, TO_REDACT),
        "traffic_totals": (data.traffic or {}).get("totals"),
    }
