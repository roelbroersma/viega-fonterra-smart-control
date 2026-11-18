from unittest.mock import AsyncMock

import pytest

from custom_components.viega_fonterra_modbus.connect.modbus import ModbusError, SharedModbus
from custom_components.viega_fonterra_modbus.const import DOMAIN


def runtime(client):
    return {
        "client": client,
        "rooms": {"room_7": {"room_number": 7, "actor": [3, 8]}},
        "identity": {"wlan_serial_number": "TEST000001"},
    }


async def test_shared_client_exact_register_and_scaling(hass):
    client = AsyncMock()
    hass.data[DOMAIN] = {"modbus": runtime(client)}
    bus = SharedModbus(hass, "modbus", "TEST000001")
    client.reconnect_count = 2
    token = [int.from_bytes(b"TEST000001"[i : i + 2], "big") for i in range(0, 10, 2)]
    client.read_input_registers.return_value = token
    await bus.check_connection()
    await bus.write_measurement(7, 19.7)
    client.write_register.assert_awaited_once_with(106, 197, verified_reconnect_count=2)
    client.read_input_registers.return_value = [7]
    assert await bus.room_present(7)
    client.read_input_registers.assert_awaited_with(258, 1)
    client.connect.assert_not_called()
    client.disconnect.assert_not_called()


@pytest.mark.parametrize(
    "room,value", [(0, 20), (13, 20), (True, 20), (1, float("nan")), (1, 4.9), (1, 40.1), (1, True)]
)
async def test_rejects_bad_writes(hass, room, value):
    client = AsyncMock()
    hass.data[DOMAIN] = {"modbus": runtime(client)}
    with pytest.raises(ValueError):
        await SharedModbus(hass, "modbus").write_measurement(room, value)
    client.write_register.assert_not_called()


async def test_unload_and_changed_module_fail_closed(hass):
    client = AsyncMock()
    hass.data[DOMAIN] = {"modbus": runtime(client)}
    bus = SharedModbus(hass, "modbus", "OTHER00001")
    with pytest.raises(ModbusError):
        await bus.write_measurement(1, 20)
    hass.data[DOMAIN].clear()
    with pytest.raises(ModbusError):
        await bus.write_measurement(1, 20)
    client.write_register.assert_not_called()


async def test_connection_checks_actual_wifi_identity(hass):
    client = AsyncMock()
    client.read_holding_registers.return_value = [1]
    words = [int.from_bytes(b"TEST000001"[i : i + 2], "big") for i in range(0, 10, 2)]
    client.read_input_registers.return_value = words
    hass.data[DOMAIN] = {"modbus": runtime(client)}
    bus = SharedModbus(hass, "modbus", "TEST000001")
    await bus.check_connection()
    client.read_input_registers.assert_awaited_with(1, 5)
    client.read_input_registers.return_value = [0] * 5
    with pytest.raises(ModbusError):
        await bus.check_connection()


@pytest.mark.parametrize(
    "data",
    [
        {"identity": None},
        {"identity": {"wlan_serial_number": "TEST000001"}, "rooms": None},
        {"identity": {"wlan_serial_number": "TEST000001"}, "rooms": {"room_1": None}},
    ],
)
async def test_changed_upstream_data_fails_with_a_clear_error(hass, data):
    client = AsyncMock()
    hass.data[DOMAIN] = {"modbus": {"client": client, **data}}
    bus = SharedModbus(hass, "modbus", "TEST000001")
    with pytest.raises(ModbusError):
        bus.rooms()
    client.write_register.assert_not_called()
