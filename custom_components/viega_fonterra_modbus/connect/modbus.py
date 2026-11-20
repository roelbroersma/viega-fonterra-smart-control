"""Connect writes use the same Modbus client and lock as the climate entities."""

from __future__ import annotations

import math
import re

from homeassistant.core import HomeAssistant

from ..const import DOMAIN
from ..identity import read_wlan_serial
from ..registers import actor_registers
from .const import EXTERNAL_TEMPERATURE_REGISTER


class ModbusError(Exception):
    """Sanitized companion error."""


class SharedModbus:
    def __init__(self, hass: HomeAssistant, entry_id: str, serial: str | None = None) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.serial = serial
        self._verified = None

    def runtime(self) -> dict:
        """Resolve each cycle so an upstream unload cannot leave a stale client."""
        data = self.hass.data.get(DOMAIN, {}).get(self.entry_id)
        if not isinstance(data, dict) or not data.get("client"):
            raise ModbusError("Modbus unavailable; enable Modbus and load Viega Fonterra")
        if self.serial is not None and self.identity(data) != self.serial:
            raise ModbusError("The configured WiFi module identity has changed")
        return data

    @staticmethod
    def identity(data) -> str:
        identity = data.get("identity")
        serial = identity.get("wlan_serial_number") if isinstance(identity, dict) else None
        if not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", serial):
            raise ModbusError("WiFi identity unavailable; reload Viega Fonterra")
        return serial

    def rooms(self) -> dict[int, dict]:
        rooms = {}
        discovered = self.runtime().get("rooms")
        if not isinstance(discovered, dict):
            raise ModbusError("Viega room discovery unavailable")
        for config in discovered.values():
            if not isinstance(config, dict):
                raise ModbusError("Unsupported Viega room data")
            room = config.get("room_number")
            if type(room) is int and 1 <= room <= 12:
                rooms[room] = config
        return rooms

    async def _call(self, method, *args):
        client = self.runtime()["client"]
        operation = getattr(client, method, None)
        if operation is None:
            raise ModbusError("Unsupported Viega Modbus client version")
        try:
            return await operation(*args)
        except Exception as err:
            # The upstream owns protocol validation, reconnects and its shared lock.
            raise ModbusError("Modbus request failed; check connection and Modbus setting") from err

    async def check_connection(self) -> None:
        self._verified = None
        runtime = self.runtime()
        client = runtime["client"]
        # The actual serial matters even if the cached HA identity still matches.
        try:
            actual = await read_wlan_serial(client)
        except Exception as err:
            raise ModbusError("Could not read the WLAN identity") from err
        expected = self.serial or self.identity(runtime)
        if actual != expected:
            raise ModbusError("The WiFi module at this address has changed")
        self._verified = (client, client.reconnect_count)

    async def room_present(self, room: int) -> bool:
        """Re-read real actor association before sending, not screen/slot order."""
        config = self.rooms().get(room)
        if not config:
            return False
        actors = config.get("actor", [])
        if type(actors) is int:
            actors = [actors]
        if not isinstance(actors, list):
            raise ModbusError("Unsupported Viega actor mapping")
        for actor in actors:
            if type(actor) is not int or not 1 <= actor <= 12:
                continue
            values = await self._call("read_input_registers", actor_registers(actor)["room_id"], 1)
            if values == [room]:
                return True
        return False

    @staticmethod
    def _validate_room(room):
        if type(room) is not int or not 1 <= room <= 12:
            raise ValueError("Invalid room ID")

    async def write_measurement(self, room: int, value: float) -> float:
        self._validate_room(room)
        if type(value) not in (float, int) or not math.isfinite(value) or not 5 <= value <= 40:
            raise ValueError("Invalid measured temperature")
        raw = math.floor(value * 10 + 0.5)
        client = self.runtime()["client"]
        if self._verified is None or self._verified[0] is not client:
            raise ModbusError("The connection needs WLAN identity verification before writing")
        # Use the same client lock for checking the socket and sending FC16.
        try:
            await client.write_register(
                EXTERNAL_TEMPERATURE_REGISTER + room - 1,
                raw,
                verified_reconnect_count=self._verified[1],
            )
        except Exception as err:
            raise ModbusError("Could not write the external temperature") from err
        return raw / 10
