"""Fixtures: a loaded Xiaomi Cloud Map Extractor entry whose vacuum connector serves a synthetic map."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_live_map.const import CONF_SOURCE, CONF_VACUUM_ENTITY, DOMAIN, SOURCE_DOMAIN

from .synthetic import DEVICE_ID, MODEL, encrypt, make_map

VACUUM = "vacuum.robot"


class FakeVacuumConnector:
    """Stands in for the extractor's XiaomiCloudVacuum: serves whatever map the test sets."""

    def __init__(self) -> None:
        self.raw: bytes | None = encrypt(make_map(path_points=40))
        self.calls: list[str] = []
        self.error: Exception | None = None

    async def get_raw_map_data(self, map_name: str) -> bytes | None:
        self.calls.append(map_name)
        if self.error:
            raise self.error
        return self.raw

    def set_map(self, decoded: dict[str, Any]) -> None:
        self.raw = encrypt(decoded)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components."""


@pytest.fixture
def vacuum() -> FakeVacuumConnector:
    return FakeVacuumConnector()


@pytest.fixture
def source_entry(hass: HomeAssistant, vacuum: FakeVacuumConnector) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=SOURCE_DOMAIN,
        title="Robot",
        data={"model": MODEL, "device_id": DEVICE_ID},
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)
    cloud = SimpleNamespace(is_authenticated=lambda: True)
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(connector=SimpleNamespace(_vacuum_connector=vacuum, _cloud_connector=cloud))
    )
    return entry


@pytest.fixture
def live_entry(hass: HomeAssistant, source_entry: MockConfigEntry) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robot",
        unique_id=source_entry.entry_id,
        data={CONF_SOURCE: source_entry.entry_id},
        options={CONF_VACUUM_ENTITY: VACUUM},
    )
    entry.add_to_hass(hass)
    return entry
