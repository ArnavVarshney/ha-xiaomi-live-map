"""Xiaomi Live Map: live robot position and cleaning path for Xiaomi vacuums, drawn by a dashboard card.

Reuses the Xiaomi cloud session of the Xiaomi Cloud Map Extractor integration, reads the robot's live map file often
while it cleans, and pushes changes to the card over the websocket API. The integration also serves the card."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
import voluptuous as vol

from .const import CARD_URL, DOMAIN
from .manager import LiveMap

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type LiveMapConfigEntry = ConfigEntry[LiveMap]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the websocket command and serve the card on every dashboard."""
    websocket_api.async_register_command(hass, ws_subscribe)
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "frontend" / "xiaomi-live-map-card.js"), False)]
    )
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

        add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LiveMapConfigEntry) -> bool:
    live = LiveMap(hass, entry)
    entry.runtime_data = live
    await live.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: LiveMapConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LiveMapConfigEntry) -> bool:
    entry.runtime_data.close_subscribers()
    return True


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe", vol.Optional("entry_id"): str})
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Stream map updates. `entry_id` is needed only when more than one robot is set up."""
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    if entry_id := msg.get("entry_id"):
        entries = [e for e in entries if e.entry_id == entry_id]
    if not entries:
        connection.send_error(
            msg["id"], "not_found", "No Xiaomi Live Map is set up" + (" with that entry_id" if entry_id else "")
        )
        return
    if len(entries) > 1:
        connection.send_error(msg["id"], "entry_id_required", "Several robots are set up: set entry_id on the card")
        return
    live: LiveMap = entries[0].runtime_data

    @callback
    def send(data: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], data))

    @callback
    def closed() -> None:
        # The entry is unloading (reload, options change, removal): the card subscribes again.
        connection.subscriptions.pop(msg["id"], None)
        send({"closed": True})

    connection.send_result(msg["id"])
    connection.subscriptions[msg["id"]] = live.subscribe(send, closed)
