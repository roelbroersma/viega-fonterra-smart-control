"""Exercise the actual upstream client against a local Modbus fixture server.

Reference source and its MIT license are in tests/vendor; no device contacted.
"""

import asyncio
import struct
from unittest.mock import AsyncMock, Mock, patch

import pytest
from conftest import make_entry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.viega_fonterra_modbus import async_reload_entry
from custom_components.viega_fonterra_modbus import modbus_handler as reference
from custom_components.viega_fonterra_modbus.connect.coordinator import ConnectCoordinator
from custom_components.viega_fonterra_modbus.connect.modbus import ModbusError, SharedModbus
from custom_components.viega_fonterra_modbus.connect.number import build_room_input
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.sensor import ViegaConnectUpgradeSensor


@pytest.fixture
async def server():
    class Fixture:
        frames = []
        holding = {1: 1, 106: 228, 63: 210}
        inputs = {258: 7, 62: 210, 63: 0}
        drop_write = False
        bad_ack = False

    fixture = Fixture()
    fixture.frames = []
    fixture.holding = dict(fixture.holding)
    fixture.holding_errors = {}
    fixture.inputs = dict(fixture.inputs)
    fixture.tasks = set()
    words = [int.from_bytes(b"TEST000001"[i : i + 2], "big") for i in range(0, 10, 2)]
    fixture.inputs.update({index + 1: word for index, word in enumerate(words)})

    async def handler(reader, writer):
        task = asyncio.current_task()
        fixture.tasks.add(task)
        try:
            while True:
                header = await reader.readexactly(7)
                tid, pid, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                fixture.frames.append((pid, unit, pdu))
                function, address, count = struct.unpack(">BHH", pdu[:5])
                if function == 3 and address in fixture.holding_errors:
                    response = bytes([function | 0x80, fixture.holding_errors[address]])
                elif function in (3, 4):
                    values = fixture.holding if function == 3 else fixture.inputs
                    data = b"".join(
                        struct.pack(">H", values.get(address + offset, 0) & 0xFFFF)
                        for offset in range(count)
                    )
                    response = bytes([function, len(data)]) + data
                elif function == 16:
                    assert count == 1 and pdu[5] == 2
                    value = struct.unpack(">H", pdu[6:8])[0]
                    if 100 <= address <= 111:
                        # As on the reserve: the room input changes, the write register doesn't.
                        fixture.inputs[50 + 2 * (address - 100)] = value
                    else:
                        fixture.holding[address] = value
                    if fixture.drop_write:
                        # Simulates applied write with the reply lost.
                        writer.close()
                        return
                    response = pdu[:5]
                    if fixture.bad_ack:
                        response = response[:3] + b"\x00\x02"
                else:
                    raise AssertionError(f"Unexpected function {function}")
                writer.write(struct.pack(">HHHB", tid, pid, len(response) + 1, unit) + response)
                await writer.drain()
        except asyncio.IncompleteReadError, ConnectionResetError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            fixture.tasks.discard(task)

    listener = await asyncio.start_server(handler, "127.0.0.1", 0)
    fixture.port = listener.sockets[0].getsockname()[1]
    yield fixture
    listener.close()
    await listener.wait_closed()
    for task in list(fixture.tasks):
        task.cancel()
    await asyncio.gather(*fixture.tasks, return_exceptions=True)


@pytest.mark.parametrize(
    ("exception_code", "expected"), [(None, "detected"), (2, "not_detected"), (3, None)]
)
async def test_connect_detection_reads_only_one_slot_without_configured_rooms(
    hass, server, exception_code, expected
):
    server.holding[111] = -99
    if exception_code is not None:
        server.holding_errors[111] = exception_code
    client = reference.ViegaModbusClient("127.0.0.1", port=server.port)
    await client.connect()
    hass.data[DOMAIN] = {"modbus": {"client": client, "rooms": {}}}
    sensor = ViegaConnectUpgradeSensor("modbus")
    sensor.hass = hass
    try:
        await sensor.async_update()
        await sensor.async_update()
        assert sensor.native_value == expected
        assert server.frames == [(0, 1, bytes.fromhex("03006f0001"))]
        if exception_code in (None, 2):
            # An unused slot and an absent optional register are normal replies.
            assert client.last_failure_time is None
            assert client.invalid_value_count == 0
        if exception_code == 2:
            with pytest.raises(reference.ModbusClientError):
                await client.read_holding_registers(111, 1)
    finally:
        await client.disconnect()


async def test_real_upstream_lock_serializes_climate_and_measurement(hass, server):
    client = reference.ViegaModbusClient("127.0.0.1", port=server.port)
    await client.connect()
    hass.data[DOMAIN] = {
        "modbus": {
            "client": client,
            "identity": {"wlan_serial_number": "TEST000001"},
            "rooms": {"room_7": {"room_number": 7, "actor": [3]}},
        }
    }
    bus = SharedModbus(hass, "modbus", "TEST000001")
    try:
        await bus.check_connection()
        assert await bus.room_present(7)
        await asyncio.gather(client.write_register(63, 210), bus.write_measurement(7, 19.7))
        assert await client.read_input_registers(62, 1) == [197]
        assert server.holding[106] == 228
        assert await client.read_input_registers(63, 1) == [0]
        writes = [pdu for _, _, pdu in server.frames if pdu[0] == 16]
        assert bytes.fromhex("10006a00010200c5") in writes
        assert bytes.fromhex("10003f00010200d2") in writes
        assert len(writes) == 2
        assert all(pid == 0 and unit == 1 for pid, unit, _ in server.frames)
        assert server.holding[63] == 210  # actual measured temperature never targets setpoint
    finally:
        await client.disconnect()


async def test_real_upstream_lost_write_reply_is_not_retried(hass, server):
    client = reference.ViegaModbusClient("127.0.0.1", port=server.port, timeout=0.1)
    await client.connect()
    hass.data[DOMAIN] = {
        "modbus": {"client": client, "identity": {"wlan_serial_number": "TEST000001"}}
    }
    server.drop_write = True
    try:
        bus = SharedModbus(hass, "modbus")
        await bus.check_connection()
        with pytest.raises(ModbusError):
            await bus.write_measurement(7, 19.7)
        writes = [pdu for _, _, pdu in server.frames if pdu[0] == 16]
        assert len(writes) == 1
        assert server.inputs[62] == 197
    finally:
        await client.disconnect()


@pytest.mark.usefixtures("loaded_registries")
async def test_room_inputs_write_independently_and_take_over_existing_sensor_links(hass, server):
    registry = er.async_get(hass)
    entry = make_entry(
        entry_id="modbus", options={"sources": {"7": {"entity_id": "sensor.existing"}}}
    )
    with patch.object(hass.config_entries, "async_setup", AsyncMock(return_value=True)):
        await hass.config_entries.async_add(entry)
    entry.add_update_listener(async_reload_entry)
    client = reference.ViegaModbusClient("127.0.0.1", port=server.port)
    await client.connect()
    server.inputs[252] = 3
    rooms = {
        "room_7": {"room_number": 7, "name": "Living", "actor": [3]},
        "room_3": {"room_number": 3, "name": "Bath", "actor": [1]},
    }
    coordinator = ConnectCoordinator(hass, entry, SharedModbus(hass, entry.entry_id, "TEST000001"))
    hass.data[DOMAIN] = {
        entry.entry_id: {
            "client": client,
            "identity": {"wlan_serial_number": "TEST000001"},
            "rooms": rooms,
            "connect": coordinator,
            "applied_config": (dict(entry.data), dict(entry.options)),
        }
    }
    inputs = {}
    try:
        for room_id, config in rooms.items():
            (entity,) = build_room_input(entry.entry_id, room_id, config)
            assert entity.entity_registry_enabled_default
            registered = registry.async_get_or_create("number", DOMAIN, entity.unique_id)
            entity.hass = hass
            entity.entity_id = registered.entity_id
            entity.async_write_ha_state = Mock()
            inputs[room_id] = entity

        living, bath = inputs["room_7"], inputs["room_3"]
        registry.async_update_entity(living.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        with pytest.raises(HomeAssistantError):
            await living.async_set_native_value(20.1)
        registry.async_update_entity(living.entity_id, disabled_by=None)
        hass.states.async_set("sensor.existing", "19.7", {"unit_of_measurement": "°C"})
        await coordinator._async_update_data()
        assert server.inputs[62] == 197

        server.drop_write = True
        with pytest.raises(HomeAssistantError):
            await living.async_set_native_value(20.1)
        assert entry.options["sources"]["7"]["entity_id"] == "sensor.existing"
        server.drop_write = False

        with patch.object(hass.config_entries, "async_schedule_reload") as reload_entry:
            await asyncio.gather(
                living.async_set_native_value(20.1), bath.async_set_native_value(23.2)
            )
            await hass.async_block_till_done()
            reload_entry.assert_not_called()
        assert not entry.options["sources"]
        assert (server.inputs[62], server.inputs[54]) == (201, 232)
        assert (living.native_value, bath.native_value) == (20.1, 23.2)
        assert server.holding[63] == 210
        hass.states.async_set("sensor.existing", "21.5", {"unit_of_measurement": "°C"})
        await coordinator._async_update_data()
        assert server.inputs[62] == 201

        # Persisted takeover survives reloading the sender.
        restarted = ConnectCoordinator(hass, entry, coordinator.bus)
        try:
            hass.states.async_set("sensor.existing", "24", {"unit_of_measurement": "°C"})
            await restarted._async_update_data()
            assert server.inputs[62] == 201
        finally:
            await restarted.async_shutdown()

        # Repeated measurements are writes, even when the display did not change.
        await bath.async_set_native_value(23.2)
        assert sum(pdu == bytes.fromhex("10006600010200e8") for _, _, pdu in server.frames) == 2

        server.inputs[252] = 4
        with pytest.raises(HomeAssistantError):
            await bath.async_set_native_value(22)
        assert server.inputs[54] == 232

        registry.async_update_entity(living.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        await coordinator._async_update_data()
        assert server.inputs[62] == 201
    finally:
        await coordinator.async_shutdown()
        await client.disconnect()


async def test_connect_revalidates_identity_after_a_new_socket(hass, server):
    client = reference.ViegaModbusClient("127.0.0.1", port=server.port)
    await client.connect()
    hass.data[DOMAIN] = {
        "modbus": {"client": client, "identity": {"wlan_serial_number": "TEST000001"}}
    }
    bus = SharedModbus(hass, "modbus")
    try:
        await bus.check_connection()
        client._discard_connection("fixture reconnect")
        assert await client.read_holding_registers(1) == [1]
        with pytest.raises(ModbusError):
            await bus.write_measurement(7, 19.7)
        assert not any(pdu[0] == 16 for _, _, pdu in server.frames)
        await bus.check_connection()
        await bus.write_measurement(7, 19.7)
        assert server.inputs[62] == 197
    finally:
        await client.disconnect()


async def test_write_rejects_acknowledgement_for_wrong_register_count(server):
    client = reference.ViegaModbusClient("127.0.0.1", port=server.port)
    await client.connect()
    server.bad_ack = True
    try:
        with pytest.raises(reference.ModbusClientError, match="acknowledgement does not match"):
            await client.write_register(63, 215)
        assert sum(pdu[0] == 16 for _, _, pdu in server.frames) == 1
    finally:
        await client.disconnect()
