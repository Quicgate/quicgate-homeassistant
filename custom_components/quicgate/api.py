"""Client for the quicgate management API.

Uses only what a limited API token may reach: the account, the overview, the
host status, traffic, bans and, for a token that may switch hosts, the host
switch. Nothing in here depends on Home Assistant.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

ACCESS_FULL = "full"
ACCESS_MONITOR = "monitor"
ACCESS_SWITCH = "switch"

TIMEOUT = aiohttp.ClientTimeout(total=15)


class QuicgateError(Exception):
    """Something went wrong talking to quicgate."""


class QuicgateConnectionError(QuicgateError):
    """quicgate could not be reached, or did not answer like quicgate."""


class QuicgateAuthError(QuicgateError):
    """The token is not valid (any more)."""


class QuicgateNotAllowedError(QuicgateError):
    """The token is valid but may not do this."""


class QuicgateTooOldError(QuicgateError):
    """This quicgate predates what the integration needs (1.19.0)."""


def normalize_url(url: str) -> str:
    """Return the address of a quicgate admin interface without a path."""
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = "http://" + url
    return url


class QuicgateClient:
    """Talks to one quicgate."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        token: str,
        verify_ssl: bool = True,
    ) -> None:
        self.url = normalize_url(url)
        self._session = session
        self._token = token.strip()
        self._ssl: bool | None = None if verify_ssl else False

    async def _request(
        self, method: str, path: str, *, json: Any = None, auth: bool = True
    ) -> Any:
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with self._session.request(
                method,
                self.url + path,
                json=json,
                headers=headers,
                ssl=self._ssl,
                timeout=TIMEOUT,
                allow_redirects=False,
            ) as resp:
                if resp.status == 401:
                    raise QuicgateAuthError("quicgate does not accept this token")
                if resp.status == 403:
                    raise QuicgateNotAllowedError(await _error_text(resp))
                if resp.status in (404, 405) and path.startswith("/api/hosts/"):
                    raise QuicgateTooOldError(
                        "this quicgate is older than 1.19.0 and has no host status"
                    )
                if resp.status >= 400:
                    raise QuicgateConnectionError(
                        f"quicgate answered {resp.status}: {await _error_text(resp)}"
                    )
                try:
                    return await resp.json(content_type=None)
                except ValueError as err:
                    raise QuicgateConnectionError(
                        "the answer is not from a quicgate admin interface"
                    ) from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise QuicgateConnectionError(str(err) or type(err).__name__) from err

    async def me(self) -> dict[str, Any]:
        """Who the token is: {token, access, version}."""
        data = await self._request("GET", "/api/me")
        if not isinstance(data, dict):
            raise QuicgateConnectionError("unexpected answer to /api/me")
        return data

    async def access(self) -> str:
        """What the token may do. A quicgate before 1.19.0 knows only full tokens."""
        return (await self.me()).get("access") or ACCESS_FULL

    async def overview(self) -> dict[str, Any]:
        return await self._request("GET", "/api/overview")

    async def hosts(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/hosts/status") or []

    async def traffic(self, period: str = "1h") -> dict[str, Any]:
        return await self._request("GET", f"/api/traffic?range={period}")

    async def bans(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/bans") or []

    async def set_host_enabled(self, host_id: int, enabled: bool) -> None:
        await self._request(
            "PUT", f"/api/hosts/{host_id}/enabled", json={"enabled": enabled}
        )


async def _error_text(resp: aiohttp.ClientResponse) -> str:
    try:
        data = await resp.json(content_type=None)
    except (ValueError, aiohttp.ClientError):
        return ""
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return ""
