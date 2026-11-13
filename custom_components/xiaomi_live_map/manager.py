"""Polls the robot's live map file and pushes changes to subscribed cards."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
import hashlib
import json
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from . import mapdata
from .const import (
    ACTIVE_STATES,
    CONF_ACTIVE_ENTITY,
    CONF_ACTIVE_INTERVAL,
    CONF_IDLE_INTERVAL,
    CONF_MAP_NAME_ENTITY,
    CONF_SOURCE,
    CONF_VACUUM_ENTITY,
    CONF_WATCH_INTERVAL,
    DEFAULT_ACTIVE_INTERVAL,
    DEFAULT_IDLE_INTERVAL,
    DEFAULT_WATCH_INTERVAL,
    DOMAIN,
    DOWNLOAD_TIMEOUT,
    ERROR_MIN_INTERVAL,
    IDLE_VIEW_INTERVAL,
    LINGER,
    MIN_JOB_POINTS,
)
from .source import SourceError, get_source

_LOGGER = logging.getLogger(__name__)

type Subscriber = Callable[[dict[str, Any]], None]


class LiveMap:
    """State of one robot's map. Sends a full snapshot to new subscribers, then only what changed."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.opts = {**entry.data, **entry.options}
        self.subs: dict[Subscriber, Callable[[], None]] = {}
        self.rev = 0
        self.base: dict[str, Any] | None = None
        self.grid: str | None = None
        self.robot: dict[str, float] | None = None
        self.path: list[int] = []
        self.last_path: list[int] = []
        self.last_ts: float | None = None
        self.error: str | None = "Starting"
        self.updated: float | None = None
        self.summary: dict[str, Any] | None = None
        self._raw_hash: str | None = None
        self._wake = asyncio.Event()
        self._active_until = 0.0
        self._sent_active: bool | None = None
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        self.last_path = stored.get("last_path") or []
        self.last_ts = stored.get("last_ts")
        watch = [e for e in (self.opts.get(CONF_VACUUM_ENTITY), self.opts.get(CONF_ACTIVE_ENTITY)) if e]
        if watch:
            self.entry.async_on_unload(async_track_state_change_event(self.hass, watch, self._state_changed))
        self.entry.async_create_background_task(self.hass, self._loop(), f"{DOMAIN} poll {self.entry.title}")

    @callback
    def _state_changed(self, _event: Event[EventStateChangedData]) -> None:
        self._wake.set()

    @callback
    def subscribe(self, send: Subscriber, closed: Callable[[], None]) -> Callable[[], None]:
        """Send a full snapshot now and every change later. `closed` is called if this map unloads first."""
        self.subs[send] = closed
        send(self.full())
        self._wake.set()

        @callback
        def unsubscribe() -> None:
            self.subs.pop(send, None)

        return unsubscribe

    @callback
    def close_subscribers(self) -> None:
        subs, self.subs = self.subs, {}
        for closed in subs.values():
            closed()

    def active(self) -> bool:
        """A job is running: the active entity is on, or the vacuum is cleaning, returning or paused."""
        on = False
        if (e := self.opts.get(CONF_ACTIVE_ENTITY)) and (s := self.hass.states.get(e)):
            on = s.state == "on"
        if not on and (e := self.opts.get(CONF_VACUUM_ENTITY)) and (s := self.hass.states.get(e)):
            on = s.state in ACTIVE_STATES
        if on:
            self._active_until = time.monotonic() + LINGER
        return on

    def _map_name(self) -> str:
        """Name of the live map object. Read from an entity holding {"obj_name": ".../<name>"}, else "0"."""
        if (e := self.opts.get(CONF_MAP_NAME_ENTITY)) and (s := self.hass.states.get(e)):
            try:
                name = json.loads(s.state).get("obj_name")
            except (ValueError, AttributeError):
                name = s.state if s.state.isdigit() else None
            if name:
                return str(name).split("/")[-1]
        return "0"

    def _delay(self, active: bool) -> float:
        if active or time.monotonic() < self._active_until:
            if self.subs:
                delay = self.opts.get(CONF_WATCH_INTERVAL, DEFAULT_WATCH_INTERVAL)
            else:
                delay = self.opts.get(CONF_ACTIVE_INTERVAL, DEFAULT_ACTIVE_INTERVAL)
        else:
            delay = IDLE_VIEW_INTERVAL if self.subs else self.opts.get(CONF_IDLE_INTERVAL, DEFAULT_IDLE_INTERVAL)
        return max(delay, ERROR_MIN_INTERVAL) if self.error else delay

    async def _loop(self) -> None:
        while True:
            active = self.active()
            try:
                await self.refresh(active)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                text = str(err) or type(err).__name__
                if text != self.error:
                    if isinstance(err, (SourceError, mapdata.UnsupportedMapError, TimeoutError)):
                        _LOGGER.warning("Map update failed: %s", text)
                    else:
                        _LOGGER.exception("Unexpected error updating the map")
                    self.error = text
                    self._notify({})
            delay = self._delay(active)
            self._wake.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), delay)

    async def refresh(self, active: bool) -> None:
        source = get_source(self.hass, self.entry.data[CONF_SOURCE])
        try:
            raw = await asyncio.wait_for(source.connector.get_raw_map_data(self._map_name()), DOWNLOAD_TIMEOUT)
        except TimeoutError as err:
            raise TimeoutError("The Xiaomi cloud did not answer in time") from err
        if not raw:
            raise SourceError("Could not download the map from the Xiaomi cloud")
        digest = hashlib.sha1(raw).hexdigest()
        if digest == self._raw_hash:
            if self.error or active != self._sent_active:
                self.error = None
                self._notify({})
            return
        new, self.summary = await self.hass.async_add_executor_job(
            mapdata.decode_and_build, raw, source.model, source.device_id
        )
        self._raw_hash = digest
        self.error = None
        self.apply(new)

    @callback
    def apply(self, new: dict[str, Any]) -> None:
        msg: dict[str, Any] = {}
        old, path = self.path, new["path"]
        # Longest shared prefix, in points. The robot may still be moving the newest point, so walk back from the end.
        keep = min(len(old), len(path)) // 4
        if keep and old[:4] != path[:4]:
            keep = 0
        while keep and old[(keep - 1) * 4 : keep * 4] != path[(keep - 1) * 4 : keep * 4]:
            keep -= 1
        if len(path) < len(old) and len(path) <= 8 and len(old) >= MIN_JOB_POINTS * 4:
            # A new job (or docking) reset the path: keep the finished one as "last clean".
            self.last_path, self.last_ts = old, time.time()
            msg["last_path"], msg["last_ts"] = self.last_path, self.last_ts
            self._store.async_delay_save(lambda: {"last_path": self.last_path, "last_ts": self.last_ts}, 5)
        if self.base != new["base"]:
            grid_changed = not self.base or self.base["grid_rev"] != new["base"]["grid_rev"]
            self.base = msg["base"] = new["base"]
            if grid_changed:
                self.grid = msg["grid"] = new["grid"]
        self.robot = new["robot"]
        self.path = path
        self.updated = time.time()
        msg.update({"robot": self.robot, "path_from": keep, "path_pts": path[keep * 4 :], "path_len": len(path) // 4})
        self._notify(msg)

    def _status(self) -> dict[str, Any]:
        self._sent_active = self.active()
        self.rev += 1
        return {"rev": self.rev, "active": self._sent_active, "error": self.error, "updated": self.updated}

    def _notify(self, msg: dict[str, Any]) -> None:
        msg = {**self._status(), **msg}
        for send in list(self.subs):
            send(msg)

    def full(self) -> dict[str, Any]:
        return {
            **self._status(),
            "base": self.base,
            "grid": self.grid,
            "robot": self.robot,
            "path_from": 0,
            "path_pts": self.path,
            "path_len": len(self.path) // 4,
            "last_path": self.last_path,
            "last_ts": self.last_ts,
        }
