from unittest.mock import AsyncMock

import pytest

from custom_components.viega_fonterra_modbus.room_mapping import RoomMappingDiscovery


@pytest.mark.parametrize(
    ("assigned", "expected"),
    [
        ({1: 1, 2: 7, 6: 7, 8: 10, 11: 11, 12: 12}, {1: 1, 7: [2, 6], 10: 8, 11: 11, 12: 12}),
        ({i: i for i in range(1, 13)}, {i: i for i in range(1, 13)}),
    ],
)
async def test_topology_reads_all_12_actor_slots_and_groups_by_native_room(assigned, expected):
    async def read(address, count):
        if count == 1:
            return [assigned.get((address - 252) // 3 + 1, -99)]
        room_id = (address - 74) // 12 + 1
        raw = f"Room {room_id}".encode().ljust(24, b"\0")
        return [int.from_bytes(raw[i : i + 2], "big") for i in range(0, 24, 2)]

    client = AsyncMock()
    client.read_input_registers.side_effect = read
    rooms = await RoomMappingDiscovery.discover_from_device(client)
    assert set(rooms) == {f"room_{i}" for i in expected}
    for room_id, actors in expected.items():
        assert rooms[f"room_{room_id}"] == {
            "room_number": room_id,
            "name": f"Room {room_id}",
            "sensor": room_id,
            "actor": actors,
        }
    assert [
        c.args[0] for c in client.read_input_registers.await_args_list if c.args[1] == 1
    ] == list(range(252, 286, 3))
    client.write_register.assert_not_called()
