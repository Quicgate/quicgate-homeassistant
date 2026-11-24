"""Shared test setup: a quicgate that answers over the mocked HTTP session."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.quicgate.const import CONF_VERIFY_SSL, DOMAIN, RELEASES_URL
from homeassistant.const import CONF_TOKEN, CONF_URL

URL = "http://quicgate.test:81"

OVERVIEW: dict[str, Any] = {
    "version": "v1.19.0",
    "startedAt": 1795000000,
    "hosts": {"total": 3, "enabled": 2, "byType": {"proxy": 2, "redirect": 1}},
    "certs": {"issued": 2, "pending": 0, "failed": 0},
    "upstreams": {"up": 1, "down": 1},
    "vpn": {"enabled": True, "running": True, "error": ""},
    "secrets": {"locked": False, "source": "/data/secret.key", "keyId": "abcd1234"},
}

HOSTS: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "app.example.com",
        "domains": ["app.example.com"],
        "type": "proxy",
        "enabled": True,
        "target": "http://10.0.0.5:8080",
        "backends": [{"target": "http://10.0.0.5:8080", "up": True}],
        "certificate": {
            "mode": "auto",
            "status": "issued",
            "domain": "app.example.com",
            "notAfter": "2099-03-01T00:00:00Z",
        },
    },
    {
        "id": 2,
        "name": "git.example.com",
        "domains": ["git.example.com"],
        "type": "proxy",
        "enabled": True,
        "target": "http://10.0.0.6:3000",
        "backends": [
            {"target": "http://10.0.0.6:3000", "up": False, "lastErr": "connection refused"}
        ],
        "certificate": {
            "mode": "auto",
            "status": "issued",
            "domain": "git.example.com",
            "notAfter": "2099-01-15T00:00:00Z",
        },
    },
    {
        "id": 3,
        "name": "old.example.com",
        "domains": ["old.example.com"],
        "type": "redirect",
        "enabled": False,
        "target": "301 -> new.example.com",
        "backends": [],
    },
]

TRAFFIC: dict[str, Any] = {
    "range": "1h",
    "open": 7,
    "banned": 1,
    "totals": {
        "in": 1_500_000,
        "out": 42_000_000,
        "requests": 1234,
        "status": {"2xx": 1200, "3xx": 20, "4xx": 11, "5xx": 3},
        "protocols": {"HTTP/2": 800, "HTTP/3": 434},
        "blocked": {"accessList": 40, "banned": 2},
        "p50": 12.5,
        "p95": 180.0,
        "p99": 900.0,
    },
    "ports": [
        {"key": "tcp:443", "service": "HTTPS", "state": "listening"},
        {"key": "tcp:993", "service": "Stream", "state": "listening"},
    ],
}

BANS: list[dict[str, Any]] = [
    {
        "ip": "203.0.113.9",
        "country": "NL",
        "since": "2026-11-24T10:00:00Z",
        "until": "2026-11-24T11:00:00Z",
        "failures": 5,
        "host": "app.example.com",
        "reason": 'address not allowed by access list "home"',
    }
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration under test."""


class FakeQuicgate:
    """What the mocked quicgate answers; tests change it and call apply()."""

    def __init__(self, mocker: AiohttpClientMocker) -> None:
        self.mocker = mocker
        self.access = "switch"
        self.overview = copy.deepcopy(OVERVIEW)
        self.hosts = copy.deepcopy(HOSTS)
        self.traffic = copy.deepcopy(TRAFFIC)
        self.bans = copy.deepcopy(BANS)
        # The newest published version; None means GitHub does not answer.
        self.newest: str | None = "v1.19.0"

    def apply(self) -> None:
        mocker = self.mocker
        mocker.clear_requests()
        mocker.get(f"{URL}/api/me", json={"token": True, "access": self.access})
        mocker.get(f"{URL}/api/overview", json=self.overview)
        mocker.get(f"{URL}/api/hosts/status", json=self.hosts)
        mocker.get(f"{URL}/api/traffic?range=1h", json=self.traffic)
        mocker.get(f"{URL}/api/bans", json=self.bans)
        for host in self.hosts:
            mocker.put(
                f"{URL}/api/hosts/{host['id']}/enabled",
                json={"id": host["id"], "enabled": True},
            )
        if self.newest is None:
            mocker.get(RELEASES_URL, status=503)
            return
        mocker.get(
            RELEASES_URL,
            json={
                "tag_name": self.newest,
                "html_url": f"https://github.com/Quicgate/quicgate/releases/tag/{self.newest}",
                "body": "What changed in this version.",
            },
        )


@pytest.fixture
def quicgate(aioclient_mock: AiohttpClientMocker) -> FakeQuicgate:
    fake = FakeQuicgate(aioclient_mock)
    fake.apply()
    return fake


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="quicgate",
        unique_id=URL,
        data={CONF_URL: URL, CONF_TOKEN: "qgs_test", CONF_VERIFY_SSL: True},
    )
