"""Access to the Xiaomi cloud session of the Xiaomi Cloud Map Extractor integration.

The extractor has no public API for this, so this module reads two of its internal attributes. It is written against
the v3 line (tested with v3.0.0-alpha-24) and turns any layout change into a clear error instead of a crash."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import SOURCE_DOMAIN

SUPPORTED_PREFIX = "xiaomi.vacuum."


class SourceError(Exception):
    """The map source cannot be used right now. The message is shown on the card."""


@dataclass(slots=True)
class MapSource:
    connector: Any  # the extractor's vacuum connector; has `async get_raw_map_data(map_name) -> bytes | None`
    model: str
    device_id: str


def source_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return hass.config_entries.async_entries(SOURCE_DOMAIN)


def get_source(hass: HomeAssistant, entry_id: str) -> MapSource:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != SOURCE_DOMAIN:
        raise SourceError("The Xiaomi Cloud Map Extractor entry this map uses was removed")
    if entry.state is not ConfigEntryState.LOADED:
        raise SourceError("Xiaomi Cloud Map Extractor is not loaded")
    model = str(entry.data.get("model") or "")
    if not model.startswith(SUPPORTED_PREFIX):
        raise SourceError(f"{model or 'This robot'} is not supported: only Xiaomi-platform vacuums (xiaomi.vacuum.*)")
    try:
        connector = entry.runtime_data.coordinator.connector
        vacuum = connector._vacuum_connector
        cloud = connector._cloud_connector
    except AttributeError as err:
        raise SourceError("This version of Xiaomi Cloud Map Extractor is not supported (needs v3)") from err
    if vacuum is None or cloud is None:
        raise SourceError("Xiaomi Cloud Map Extractor is still connecting")
    if not hasattr(vacuum, "get_raw_map_data"):
        raise SourceError("This version of Xiaomi Cloud Map Extractor is not supported (needs v3)")
    try:
        if not cloud.is_authenticated():
            raise SourceError("Xiaomi cloud session expired: log in again in Xiaomi Cloud Map Extractor")
    except AttributeError:
        pass
    return MapSource(vacuum, model, str(entry.data.get("device_id")))
