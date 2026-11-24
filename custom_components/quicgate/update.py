"""Tells you when a newer quicgate is out. It does not install it."""

from __future__ import annotations

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import QuicgateConfigEntry, QuicgateCoordinator
from .entity import QuicgateEntity

PARALLEL_UPDATES = 0

# Home Assistant shows at most this much of a summary.
SUMMARY_LENGTH = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: QuicgateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the version check of one quicgate."""
    async_add_entities([QuicgateUpdate(entry.runtime_data)])


class QuicgateUpdate(QuicgateEntity, UpdateEntity):
    """The version quicgate runs, next to the newest one published."""

    _attr_name = None
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_title = "quicgate"

    def __init__(self, coordinator: QuicgateCoordinator) -> None:
        super().__init__(coordinator, "version")

    @property
    def installed_version(self) -> str | None:
        return self.coordinator.data.version.removeprefix("v") or None

    @property
    def latest_version(self) -> str | None:
        release = self.coordinator.data.release
        # Without word from GitHub there is nothing newer to report.
        return release.version if release else self.installed_version

    @property
    def release_url(self) -> str | None:
        release = self.coordinator.data.release
        return release.url if release else None

    @property
    def release_summary(self) -> str | None:
        release = self.coordinator.data.release
        if not release or not release.notes:
            return None
        notes = " ".join(release.notes.split())
        if len(notes) > SUMMARY_LENGTH:
            notes = notes[: SUMMARY_LENGTH - 1].rstrip() + "…"
        return notes
