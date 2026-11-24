"""What the readings of a quicgate mean: which backends are down, which
certificates need attention, how much was blocked. Plain functions over the
data, so they can be tested without Home Assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .const import BLOCK_REASONS, CERTIFICATE_SOON_DAYS


def parse_time(value: Any) -> datetime | None:
    """Read a time as quicgate writes it (RFC 3339)."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def backends_down(hosts: dict[int, dict[str, Any]]) -> list[dict[str, str]]:
    """Every backend that does not answer, with the host it belongs to."""
    out: list[dict[str, str]] = []
    for host in hosts.values():
        for backend in host.get("backends") or []:
            if not backend.get("up"):
                out.append(
                    {
                        "host": str(host.get("name") or ""),
                        "backend": str(backend.get("target") or ""),
                        "error": str(backend.get("lastErr") or ""),
                    }
                )
    return out


def host_backends_up(host: dict[str, Any]) -> bool | None:
    """Whether all backends of one host answer; None when quicgate probes none."""
    backends = host.get("backends") or []
    if not backends:
        return None
    return all(b.get("up") for b in backends)


def certificate_expiry(host: dict[str, Any]) -> datetime | None:
    """When the first certificate of a host expires."""
    return parse_time((host.get("certificate") or {}).get("notAfter"))


def first_certificate_expiry(
    hosts: dict[int, dict[str, Any]],
) -> tuple[datetime, dict[str, Any]] | None:
    """The certificate that expires first, and the host it is on."""
    best: tuple[datetime, dict[str, Any]] | None = None
    for host in hosts.values():
        expires = certificate_expiry(host)
        if expires is not None and (best is None or expires < best[0]):
            best = (expires, host)
    return best


def days_left(expires: datetime, now: datetime) -> int:
    """Whole days until a certificate expires; negative once it has."""
    return int((expires - now).total_seconds() // 86400)


def certificates_failed(hosts: dict[int, dict[str, Any]]) -> list[dict[str, str]]:
    """Hosts whose certificate could not be obtained or renewed."""
    out: list[dict[str, str]] = []
    for host in hosts.values():
        cert = host.get("certificate") or {}
        if cert.get("status") == "failed":
            out.append(
                {
                    "host": str(host.get("name") or ""),
                    "domain": str(cert.get("domain") or host.get("name") or ""),
                    "error": str(cert.get("lastError") or ""),
                }
            )
    return out


def certificates_soon(
    hosts: dict[int, dict[str, Any]], now: datetime
) -> list[dict[str, Any]]:
    """Hosts whose certificate ends within two weeks: renewal is not working."""
    out: list[dict[str, Any]] = []
    for host in hosts.values():
        expires = certificate_expiry(host)
        if expires is not None and days_left(expires, now) < CERTIFICATE_SOON_DAYS:
            out.append(
                {
                    "host": str(host.get("name") or ""),
                    "expires": expires.isoformat(),
                    "days_left": days_left(expires, now),
                }
            )
    return out


def ports_failed(traffic: dict[str, Any]) -> list[dict[str, str]]:
    """Ports quicgate should listen on but could not open."""
    out: list[dict[str, str]] = []
    for port in traffic.get("ports") or []:
        if port.get("state") == "failed":
            out.append(
                {
                    "port": str(port.get("key") or ""),
                    "service": str(port.get("service") or ""),
                    "error": str(port.get("error") or ""),
                }
            )
    return out


def totals(traffic: dict[str, Any]) -> dict[str, Any]:
    return traffic.get("totals") or {}


def blocked_total(traffic: dict[str, Any]) -> int:
    return int(sum((totals(traffic).get("blocked") or {}).values()))


def blocked_by_reason(traffic: dict[str, Any]) -> dict[str, int]:
    """Refused requests per reason, in words."""
    blocked = totals(traffic).get("blocked") or {}
    return {
        BLOCK_REASONS.get(reason, reason): int(count)
        for reason, count in sorted(blocked.items(), key=lambda kv: -kv[1])
    }


def vpn_problem(overview: dict[str, Any]) -> bool | None:
    """Whether the WireGuard endpoint is switched on but not working."""
    vpn = overview.get("vpn") or {}
    if not vpn.get("enabled"):
        return None
    return not vpn.get("running") or bool(vpn.get("error"))
