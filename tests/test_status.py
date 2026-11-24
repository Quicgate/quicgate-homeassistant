"""What the readings mean."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.quicgate import status

from .conftest import HOSTS, OVERVIEW, TRAFFIC

BY_ID = {h["id"]: h for h in HOSTS}
NOW = datetime(2099, 1, 10, tzinfo=timezone.utc)


def test_backends_down_names_the_host_and_the_error() -> None:
    assert status.backends_down(BY_ID) == [
        {
            "host": "git.example.com",
            "backend": "http://10.0.0.6:3000",
            "error": "connection refused",
        }
    ]


def test_host_backends_up() -> None:
    assert status.host_backends_up(BY_ID[1]) is True
    assert status.host_backends_up(BY_ID[2]) is False
    # A host quicgate does not probe is neither up nor down.
    assert status.host_backends_up(BY_ID[3]) is None


def test_first_certificate_expiry_is_the_earliest() -> None:
    expires, host = status.first_certificate_expiry(BY_ID)
    assert host["name"] == "git.example.com"
    assert expires == datetime(2099, 1, 15, tzinfo=timezone.utc)
    assert status.days_left(expires, NOW) == 5
    assert status.first_certificate_expiry({3: BY_ID[3]}) is None


def test_days_left_goes_negative_after_expiry() -> None:
    expired = datetime(2099, 1, 9, 12, tzinfo=timezone.utc)
    assert status.days_left(expired, NOW) == -1


def test_certificates_soon_only_lists_those_within_two_weeks() -> None:
    soon = status.certificates_soon(BY_ID, NOW)
    assert [c["host"] for c in soon] == ["git.example.com"]
    assert soon[0]["days_left"] == 5
    assert status.certificates_soon(BY_ID, datetime(2098, 1, 1, tzinfo=timezone.utc)) == []


def test_certificates_failed() -> None:
    hosts = {
        1: {
            "name": "app.example.com",
            "certificate": {
                "status": "failed",
                "domain": "www.example.com",
                "lastError": "DNS problem",
            },
        },
        2: BY_ID[2],
    }
    assert status.certificates_failed(hosts) == [
        {"host": "app.example.com", "domain": "www.example.com", "error": "DNS problem"}
    ]
    assert status.certificates_failed(BY_ID) == []


def test_ports_failed() -> None:
    assert status.ports_failed(TRAFFIC) == []
    traffic = {
        "ports": [
            {"key": "tcp:993", "service": "Stream", "state": "failed", "error": "address in use"}
        ]
    }
    assert status.ports_failed(traffic) == [
        {"port": "tcp:993", "service": "Stream", "error": "address in use"}
    ]


def test_blocked_is_counted_and_named_in_words() -> None:
    assert status.blocked_total(TRAFFIC) == 42
    assert status.blocked_by_reason(TRAFFIC) == {"access list": 40, "banned address": 2}
    assert status.blocked_total({}) == 0


def test_vpn_problem() -> None:
    assert status.vpn_problem(OVERVIEW) is False
    assert status.vpn_problem({"vpn": {"enabled": True, "running": False}}) is True
    assert status.vpn_problem({"vpn": {"enabled": True, "running": True, "error": "x"}}) is True
    # A VPN that is switched off is not a problem and not fine: it is not there.
    assert status.vpn_problem({"vpn": {"enabled": False}}) is None
    assert status.vpn_problem({}) is None


def test_parse_time() -> None:
    assert status.parse_time("2099-01-15T00:00:00Z") == datetime(
        2099, 1, 15, tzinfo=timezone.utc
    )
    assert status.parse_time("") is None
    assert status.parse_time("not a time") is None
    assert status.parse_time(None) is None
