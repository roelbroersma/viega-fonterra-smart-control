"""Connect settings within the normal Fonterra options flow."""

import voluptuous as vol
from homeassistant.helpers import selector

from .const import CONF_CONNECT, CONF_MAPPINGS, CONF_MAX_AGE, DEFAULT_MAX_AGE
from .modbus import ModbusError, SharedModbus
from .runtime import CONF_PIN, legacy_entries


class ConnectOptionsMixin:
    room = None

    @property
    def connect_bus(self):
        return SharedModbus(
            self.hass, self.config_entry.entry_id, self.config_entry.options.get(CONF_PIN)
        )

    def _finish_connect(self, enabled, mappings=None):
        options = {**self.config_entry.options, CONF_CONNECT: enabled}
        if mappings is not None:
            options[CONF_MAPPINGS] = mappings
        if enabled and CONF_PIN not in options:
            options[CONF_PIN] = self.connect_bus.identity(self.connect_bus.runtime())
        return self.async_create_entry(title="", data=options)

    async def async_step_connect(self, user_input=None):
        enabled = self.config_entry.options.get(
            CONF_CONNECT, self.config_entry.data.get(CONF_CONNECT, False)
        )
        errors = {}
        if user_input is not None:
            enabled = user_input[CONF_CONNECT]
            if enabled and any(
                not old.disabled_by for old in legacy_entries(self.hass, self.config_entry)
            ):
                errors["base"] = "legacy_companion_active"
            elif not enabled or not user_input.get("configure_source", True):
                try:
                    if enabled:
                        await self.connect_bus.check_connection()
                    return self._finish_connect(enabled)
                except ModbusError:
                    errors["base"] = "cannot_connect"
            else:
                return await self.async_step_room()
        return self.async_show_form(
            step_id="connect",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONNECT, default=enabled): bool,
                    vol.Required("configure_source", default=True): bool,
                }
            ),
        )

    async def async_step_room(self, user_input=None):
        if user_input is not None:
            self.room = int(user_input["room"])
            return await self.async_step_source()
        try:
            rooms = self.connect_bus.rooms()
        except ModbusError:
            return self.async_abort(reason="modbus_required")
        if not rooms:
            return self.async_abort(reason="no_rooms")
        return self.async_show_form(
            step_id="room",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": str(room), "label": f"{room}: {config.get('name', room)}"}
                                for room, config in sorted(rooms.items())
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_source(self, user_input=None):
        mappings = dict(self.config_entry.options.get(CONF_MAPPINGS, {}))
        current = mappings.get(str(self.room), {})
        errors = {}
        if user_input is not None:
            if user_input.get("remove", False):
                mappings.pop(str(self.room), None)
                try:
                    return self._finish_connect(True, mappings)
                except ModbusError:
                    errors["base"] = "cannot_connect"
            elif not user_input.get("external_confirmed", False):
                errors["base"] = "external_required"
            else:
                entity_id = user_input.get("entity_id")
                if (
                    not entity_id
                    or not entity_id.startswith("sensor.")
                    or self.hass.states.get(entity_id) is None
                ):
                    errors["base"] = "invalid_sensor"
                else:
                    try:
                        bus = self.connect_bus
                        if not await bus.room_present(self.room):
                            return self.async_abort(reason="no_rooms")
                        await bus.check_connection()
                        mappings[str(self.room)] = {
                            "entity_id": entity_id,
                            CONF_MAX_AGE: int(user_input[CONF_MAX_AGE]),
                        }
                        return self._finish_connect(True, mappings)
                    except ModbusError:
                        errors["base"] = "cannot_connect"
        marker = (
            vol.Optional("entity_id", default=current["entity_id"])
            if current
            else vol.Optional("entity_id")
        )
        return self.async_show_form(
            step_id="source",
            description_placeholders={"room": str(self.room)},
            errors=errors,
            data_schema=vol.Schema(
                {
                    marker: selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                    ),
                    vol.Required(
                        CONF_MAX_AGE, default=current.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)
                    ): vol.All(vol.Coerce(int), vol.Range(min=90, max=86400)),
                    vol.Required("external_confirmed", default=False): bool,
                    vol.Required("remove", default=False): bool,
                }
            ),
        )
