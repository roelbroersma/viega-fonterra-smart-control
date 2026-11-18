"""Read and validate the WLAN identity shared by setup and address discovery."""

import re

from .modbus_handler import ModbusClientError, ViegaModbusClient
from .registers import BASE_UNIT_REGISTERS, decode_text_registers

WLAN_SERIAL_KEY = "wlan_serial_number"
WLAN_SERIAL_LENGTH = 5
_SERIAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,9}")


def saved_wlan_serial(options) -> str | None:
    """Return a WLAN serial learned from the configured Modbus endpoint."""
    identity = options.get("_identity")
    serial = identity.get(WLAN_SERIAL_KEY) if isinstance(identity, dict) else None
    return serial if isinstance(serial, str) and _SERIAL.fullmatch(serial) else None


async def read_wlan_serial(client: ViegaModbusClient) -> str:
    """Read a complete, valid WLAN serial from the documented FC04 register."""
    words = await client.read_input_registers(
        BASE_UNIT_REGISTERS[WLAN_SERIAL_KEY], WLAN_SERIAL_LENGTH
    )
    if len(words) != WLAN_SERIAL_LENGTH:
        raise ModbusClientError("Incomplete WLAN serial response")
    serial = decode_text_registers(words)
    if not _SERIAL.fullmatch(serial):
        raise ModbusClientError("Invalid WLAN serial response")
    return serial
