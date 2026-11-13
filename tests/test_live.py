"""Polling, websocket streaming, path deltas, last-clean handling and errors."""

from __future__ import annotations

from datetime import timedelta
import json

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator, WebSocketGenerator

from custom_components.xiaomi_live_map.const import CARD_URL, DOMAIN

from .conftest import VACUUM, FakeVacuumConnector
from .synthetic import make_map


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float = 31) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_subscribe_streams_snapshot_then_deltas(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    live_entry: MockConfigEntry,
    vacuum: FakeVacuumConnector,
    freezer: FrozenDateTimeFactory,
) -> None:
    hass.states.async_set(VACUUM, "cleaning")
    await _setup(hass, live_entry)
    assert live_entry.state is ConfigEntryState.LOADED
    assert vacuum.calls == ["0"]

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    full = (await client.receive_json())["event"]
    assert full["active"] is True
    assert full["error"] is None
    assert full["base"]["rooms"][0]["name"] == "Kitchen"
    assert full["grid"]
    assert full["path_len"] == 40

    # The robot moves on: only the new points are sent, and the static map is not repeated.
    vacuum.set_map(make_map(path_points=60))
    await _poll(hass, freezer, 4)
    delta = (await client.receive_json())["event"]
    assert "base" not in delta
    assert "grid" not in delta
    assert delta["path_len"] == 60
    assert delta["path_from"] == 40
    assert len(delta["path_pts"]) == 20 * 4


async def test_finished_clean_is_kept(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    live_entry: MockConfigEntry,
    vacuum: FakeVacuumConnector,
    freezer: FrozenDateTimeFactory,
) -> None:
    vacuum.set_map(make_map(path_points=200))
    await _setup(hass, live_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    await client.receive_json()
    await client.receive_json()

    vacuum.set_map(make_map(path_points=1))  # docked: the robot resets its path
    await _poll(hass, freezer)
    msg = (await client.receive_json())["event"]
    assert msg["path_len"] == 1
    assert len(msg["last_path"]) == 200 * 4
    assert msg["last_ts"]


async def test_errors_are_reported_and_recover(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    live_entry: MockConfigEntry,
    vacuum: FakeVacuumConnector,
    freezer: FrozenDateTimeFactory,
) -> None:
    vacuum.raw = b"not a map"
    await _setup(hass, live_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    await client.receive_json()
    first = (await client.receive_json())["event"]
    assert "decrypt" in first["error"]
    assert first["base"] is None

    vacuum.set_map(make_map())
    await _poll(hass, freezer)
    fixed = (await client.receive_json())["event"]
    assert fixed["error"] is None
    assert fixed["base"]


async def test_source_not_loaded(hass: HomeAssistant, live_entry: MockConfigEntry, source_entry) -> None:
    source_entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    await _setup(hass, live_entry)
    assert live_entry.runtime_data.error == "Xiaomi Cloud Map Extractor is not loaded"


async def test_map_name_entity(hass: HomeAssistant, live_entry: MockConfigEntry, vacuum: FakeVacuumConnector) -> None:
    hass.config_entries.async_update_entry(live_entry, options={"map_name_entity": "sensor.map"})
    hass.states.async_set("sensor.map", json.dumps({"obj_name": "123/456/7"}))
    await _setup(hass, live_entry)
    assert vacuum.calls == ["7"]


async def test_reload_closes_subscription(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, live_entry: MockConfigEntry
) -> None:
    await _setup(hass, live_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    await client.receive_json()
    await client.receive_json()
    assert await hass.config_entries.async_reload(live_entry.entry_id)
    await hass.async_block_till_done()
    assert (await client.receive_json())["event"] == {"closed": True}


async def test_subscribe_without_entry(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_card_is_served(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, live_entry: MockConfigEntry
) -> None:
    await _setup(hass, live_entry)
    client = await hass_client()
    resp = await client.get(CARD_URL)
    assert resp.status == 200
    assert 'customElements.define("xiaomi-live-map-card"' in await resp.text()


async def test_diagnostics(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, live_entry: MockConfigEntry
) -> None:
    assert await async_setup_component(hass, "diagnostics", {})
    await _setup(hass, live_entry)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, live_entry)
    assert diag["source"]["model"] == "xiaomi.vacuum.test01"
    assert diag["map"]["rooms"] == 5
    assert diag["last_file"]["path_points"] == 40
    assert "Kitchen" not in json.dumps(diag)
