"""Writable measured temperature for a room set to External measured in Fonterra."""

from __future__ import annotations

import math

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature

from ..const import DOMAIN
from ..device import build_device_info
from ..errors import action_failed, invalid_request
from .const import temperature_input_id
from .modbus import ModbusError


def build_room_input(entry_id: str, room_id: str, config: object) -> list[ExternalTemperatureInput]:
    """Use the discovered room ID regardless of how many actuators it has."""
    if not isinstance(config, dict):
        return []
    room = config.get("room_number")
    if type(room) is not int or not 1 <= room <= 12:
        return []
    return [ExternalTemperatureInput(entry_id, room, str(config.get("name", room_id)))]


class ExternalTemperatureInput(NumberEntity):
    """Send a measurement on each call. Never restore or replay a previous value."""

    _attr_has_entity_name = True
    # Modbus cannot report the room's source. Enable only for rooms set to external.
    _attr_entity_registry_enabled_default = False
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 5
    _attr_native_max_value = 40
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX
    _attr_should_poll = False
    _attr_native_value = None
    _attr_translation_key = "external_temperature"

    def __init__(self, entry_id: str, room: int, name: str) -> None:
        self._entry_id = entry_id
        self._room = room
        self._room_name = name
        self._attr_unique_id = temperature_input_id(entry_id, room)
        self._attr_translation_placeholders = {"room": name}

    async def async_set_native_value(self, value: float) -> None:
        """Send the caller's current measurement, including repeated equal values."""
        if not math.isfinite(value) or not self.native_min_value <= value <= self.native_max_value:
            raise invalid_request("external_temperature_range")
        runtime = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        coordinator = runtime.get("connect")
        try:
            if coordinator is None:
                raise ModbusError("Connect Upgrade is disabled")
            self._attr_native_value = await coordinator.async_write_input(self._room, value)
        except ModbusError as err:
            raise action_failed("external_temperature_write_failed", room=self._room_name) from err
        self.async_write_ha_state()

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)
