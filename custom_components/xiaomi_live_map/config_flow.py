"""UI setup: pick the Xiaomi Cloud Map Extractor entry to read from, plus optional helper entities."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
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
)
from .source import SUPPORTED_PREFIX, source_entries

ENTITY_FIELDS = {
    CONF_VACUUM_ENTITY: selector.EntitySelector(selector.EntitySelectorConfig(domain="vacuum")),
    CONF_ACTIVE_ENTITY: selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
    ),
    CONF_MAP_NAME_ENTITY: selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
}


def _seconds(minimum: int, maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX
        )
    )


def _entities_schema(current: dict[str, Any]) -> dict:
    return {
        vol.Optional(key, description={"suggested_value": current.get(key)}): sel for key, sel in ENTITY_FIELDS.items()
    }


class LiveMapConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        sources = {e.entry_id: e for e in source_entries(self.hass)}
        if not sources:
            return self.async_abort(reason="no_source")
        configured = {e.unique_id for e in self._async_current_entries()}
        choices = {k: e for k, e in sources.items() if k not in configured}
        if not choices:
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            source = sources.get(user_input[CONF_SOURCE])
            if source is None:
                errors[CONF_SOURCE] = "unknown_source"
            elif not str(source.data.get("model", "")).startswith(SUPPORTED_PREFIX):
                errors[CONF_SOURCE] = "unsupported_model"
            else:
                await self.async_set_unique_id(source.entry_id)
                self._abort_if_unique_id_configured()
                options = {k: v for k, v in user_input.items() if k != CONF_SOURCE and v}
                return self.async_create_entry(title=source.title, data={CONF_SOURCE: source.entry_id}, options=options)

        options = [
            selector.SelectOptionDict(value=k, label=f"{e.title} ({e.data.get('model', '?')})")
            for k, e in choices.items()
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE, default=next(iter(choices))): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
                **_entities_schema(user_input or {}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return LiveMapOptionsFlow()


class LiveMapOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={k: v for k, v in user_input.items() if v not in (None, "")})
        current = self.config_entry.options
        schema = vol.Schema(
            {
                **_entities_schema(current),
                vol.Required(
                    CONF_WATCH_INTERVAL, default=current.get(CONF_WATCH_INTERVAL, DEFAULT_WATCH_INTERVAL)
                ): _seconds(1, 60),
                vol.Required(
                    CONF_ACTIVE_INTERVAL, default=current.get(CONF_ACTIVE_INTERVAL, DEFAULT_ACTIVE_INTERVAL)
                ): _seconds(1, 300),
                vol.Required(
                    CONF_IDLE_INTERVAL, default=current.get(CONF_IDLE_INTERVAL, DEFAULT_IDLE_INTERVAL)
                ): _seconds(30, 3600),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
