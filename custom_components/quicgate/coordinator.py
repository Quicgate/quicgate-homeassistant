"""Fetches the state of one quicgate once a minute."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ACCESS_FULL,
    ACCESS_SWITCH,
    QuicgateAuthError,
    QuicgateClient,
    QuicgateError,
    QuicgateTooOldError,
)
from .const import (
    DOMAIN,
    LOGGER,
    RELEASE_CHECK_INTERVAL,
    RELEASES_URL,
    UPDATE_INTERVAL,
)

type QuicgateConfigEntry = ConfigEntry[QuicgateCoordinator]


@dataclass
class Release:
    """The newest published version of quicgate."""

    version: str
    url: str | None = None
    notes: str | None = None


@dataclass
class QuicgateData:
    """One reading of a quicgate."""

    version: str
    overview: dict[str, Any]
    hosts: dict[int, dict[str, Any]]
    traffic: dict[str, Any]
    bans: list[dict[str, Any]] = field(default_factory=list)
    release: Release | None = None


class QuicgateCoordinator(DataUpdateCoordinator[QuicgateData]):
    """Reads one quicgate and shares the result with every entity."""

    config_entry: QuicgateConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: QuicgateConfigEntry,
        client: QuicgateClient,
        session: aiohttp.ClientSession,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.access = ACCESS_FULL
        self._session = session
        self._release: Release | None = None
        self._release_checked: datetime | None = None

    @property
    def can_switch(self) -> bool:
        """Whether the token may switch hosts on and off."""
        return self.access in (ACCESS_SWITCH, ACCESS_FULL)

    async def _async_setup(self) -> None:
        try:
            self.access = await self.client.access()
        except QuicgateAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except QuicgateError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_update_data(self) -> QuicgateData:
        try:
            overview, hosts, traffic, bans = await asyncio.gather(
                self.client.overview(),
                self.client.hosts(),
                self.client.traffic(),
                self.client.bans(),
            )
        except QuicgateAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except QuicgateTooOldError as err:
            raise UpdateFailed(
                "quicgate 1.19.0 or newer is needed; update quicgate first"
            ) from err
        except QuicgateError as err:
            raise UpdateFailed(str(err)) from err

        await self._check_release()
        version = str(overview.get("version") or "")
        if self.data is not None and self.data.version != version:
            self._note_new_version(version)
        return QuicgateData(
            version=version,
            overview=overview,
            hosts={int(h["id"]): h for h in hosts if "id" in h},
            traffic=traffic or {},
            bans=bans,
            release=self._release,
        )

    def _note_new_version(self, version: str) -> None:
        """quicgate was updated: show the new version on its device too."""
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(
            registry, self.config_entry.entry_id
        ):
            registry.async_update_device(
                device.id, sw_version=version.removeprefix("v") or None
            )

    async def _check_release(self) -> None:
        """Look up the newest quicgate now and then. Failing is fine."""
        now = dt_util.utcnow()
        if (
            self._release_checked is not None
            and now - self._release_checked < RELEASE_CHECK_INTERVAL
        ):
            return
        self._release_checked = now
        try:
            async with self._session.get(
                RELEASES_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return
        tag = str(data.get("tag_name") or "")
        if not tag:
            return
        self._release = Release(
            version=tag.removeprefix("v"),
            url=data.get("html_url"),
            notes=data.get("body"),
        )
