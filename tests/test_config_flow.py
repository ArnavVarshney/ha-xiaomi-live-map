"""Config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_live_map.const import (
    CONF_ACTIVE_ENTITY,
    CONF_SOURCE,
    CONF_VACUUM_ENTITY,
    CONF_WATCH_INTERVAL,
    DOMAIN,
    SOURCE_DOMAIN,
)

from .conftest import VACUUM


async def test_no_source_aborts(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_source"


async def test_user_flow(hass: HomeAssistant, source_entry: MockConfigEntry) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: source_entry.entry_id, CONF_VACUUM_ENTITY: VACUUM}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Robot"
    assert result["data"] == {CONF_SOURCE: source_entry.entry_id}
    assert result["options"] == {CONF_VACUUM_ENTITY: VACUUM}
    assert result["result"].unique_id == source_entry.entry_id

    # Every robot has a map now.
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_unsupported_model(hass: HomeAssistant) -> None:
    other = MockConfigEntry(domain=SOURCE_DOMAIN, title="Roborock", data={"model": "roborock.vacuum.s5"})
    other.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SOURCE: other.entry_id})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SOURCE: "unsupported_model"}


async def test_options_flow(hass: HomeAssistant, live_entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(live_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(live_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ACTIVE_ENTITY: "binary_sensor.job", CONF_WATCH_INTERVAL: 5, "active_interval": 10, "idle_interval": 300},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    # The vacuum entity was cleared in the form, so it is gone.
    assert live_entry.options == {
        CONF_ACTIVE_ENTITY: "binary_sensor.job",
        CONF_WATCH_INTERVAL: 5,
        "active_interval": 10,
        "idle_interval": 300,
    }
    assert live_entry.runtime_data.opts[CONF_WATCH_INTERVAL] == 5
