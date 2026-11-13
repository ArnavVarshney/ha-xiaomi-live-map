"""Diagnostics: settings, polling state and a summary of the last map file (no coordinates or room names)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import LiveMapConfigEntry
from .const import CONF_SOURCE
from .source import SourceError, get_source


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: LiveMapConfigEntry) -> dict[str, Any]:
    live = entry.runtime_data
    try:
        source = get_source(hass, entry.data[CONF_SOURCE])
        model, connector = source.model, type(source.connector).__name__
    except SourceError as err:
        model, connector = None, str(err)
    base = live.base or {}
    return {
        "options": dict(entry.options),
        "source": {"model": model, "connector": connector},
        "state": {
            "error": live.error,
            "active": live.active(),
            "updated": live.updated,
            "subscribers": len(live.subs),
            "path_points": len(live.path) // 4,
            "last_clean_points": len(live.last_path) // 4,
        },
        "map": {
            "size": [base.get("w"), base.get("h"), base.get("res")],
            "rooms": len(base.get("rooms") or []),
            "carpets": len(base.get("carpets") or []),
            "virtual_walls": len(base.get("vwalls") or []),
            "has_charger": bool(base.get("charger")),
        },
        "last_file": live.summary,
    }
