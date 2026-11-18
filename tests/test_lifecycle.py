from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_entry
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from test_config_flow import manager

from custom_components.viega_fonterra_modbus import async_setup_entry, async_unload_entry
from custom_components.viega_fonterra_modbus.connect.const import DOMAIN
from custom_components.viega_fonterra_modbus.connect.modbus import ModbusError
from custom_components.viega_fonterra_modbus.connect.runtime import merged_options


def fake_client():
    client = AsyncMock()
    client.read_holding_registers.return_value = [1]
    words = [int.from_bytes(b"TEST000001"[i : i + 2], "big") for i in range(0, 10, 2)]
    client.read_input_registers.return_value = words
    return client


@pytest.mark.parametrize("enabled", [False, True])
async def test_one_entry_one_client_and_all_platforms(hass, enabled):
    entry = make_entry(
        entry_id="original_entry",
        data={"host": "fonterra.example", "port": 502},
        options={"connect_upgrade": enabled, "_connect_wifi_serial": "TEST000001"},
        state=ConfigEntryState.SETUP_IN_PROGRESS,
    )
    manager(hass, [entry])
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    client = fake_client()
    normal = MagicMock(async_refresh=AsyncMock())
    issues = MagicMock()
    issues.async_start.return_value = lambda: None
    rooms = {"room_1": {"room_number": 1, "name": "Living", "actor": 1, "sensor": 1}}
    with (
        patch(
            "custom_components.viega_fonterra_modbus.ViegaModbusClient", return_value=client
        ) as factory,
        patch(
            "custom_components.viega_fonterra_modbus.RoomMappingDiscovery.discover_from_device",
            AsyncMock(return_value=rooms),
        ),
        patch("custom_components.viega_fonterra_modbus.ViegaDataCoordinator", return_value=normal),
        patch("custom_components.viega_fonterra_modbus.ModuleIssues", return_value=issues),
    ):
        assert await async_setup_entry(hass, entry)
    assert factory.call_count == 1
    assert entry.entry_id == "original_entry"
    platforms = hass.config_entries.async_forward_entry_setups.await_args.args[1]
    assert set(platforms) == {"sensor", "binary_sensor", "climate", "number"}
    runtime = hass.data[DOMAIN][entry.entry_id]
    assert runtime["client"] is client
    assert (runtime["connect"] is not None) is enabled
    if not enabled:
        client.read_holding_registers.assert_not_called()
    if enabled:
        assert runtime["connect"].bus.entry_id == entry.entry_id
        await runtime["connect"].async_shutdown()
    client.write_register.assert_not_called()
    normal.async_refresh.assert_awaited_once()


async def test_connect_read_failure_keeps_normal_climate_platforms(hass):
    entry = make_entry(
        entry_id="original",
        data={"host": "fonterra.example", "port": 502},
        options={
            "connect_upgrade": True,
            "_connect_wifi_serial": "TEST000001",
            "sources": {"1": {"entity_id": "sensor.room", "max_age": 900}},
        },
        state=ConfigEntryState.SETUP_IN_PROGRESS,
    )
    manager(hass, [entry])
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    client = fake_client()
    normal = MagicMock(async_refresh=AsyncMock())
    issues = MagicMock()
    issues.async_start.return_value = lambda: None
    rooms = {"room_1": {"room_number": 1, "name": "Living", "actor": 1, "sensor": 1}}
    with (
        patch(
            "custom_components.viega_fonterra_modbus.connect.modbus.SharedModbus.check_connection",
            AsyncMock(side_effect=ModbusError("fixture outage")),
        ),
        patch("custom_components.viega_fonterra_modbus.ViegaModbusClient", return_value=client),
        patch(
            "custom_components.viega_fonterra_modbus.RoomMappingDiscovery.discover_from_device",
            AsyncMock(return_value=rooms),
        ),
        patch("custom_components.viega_fonterra_modbus.ViegaDataCoordinator", return_value=normal),
        patch("custom_components.viega_fonterra_modbus.ModuleIssues", return_value=issues),
    ):
        assert await async_setup_entry(hass, entry)
    assert "climate" in hass.config_entries.async_forward_entry_setups.await_args.args[1]
    coordinator = hass.data[DOMAIN][entry.entry_id]["connect"]
    assert not coordinator.last_update_success
    client.write_register.assert_not_called()
    await coordinator.async_shutdown()


async def test_unload_stops_sender_before_disconnecting_single_client(hass):
    entry = make_entry(entry_id="original")
    order = []
    coordinator = MagicMock(async_shutdown=AsyncMock(side_effect=lambda: order.append("stop")))
    client = MagicMock(disconnect=AsyncMock(side_effect=lambda: order.append("disconnect")))
    hass.data[DOMAIN] = {entry.entry_id: {"connect": coordinator, "client": client}}
    manager(hass, [entry])

    async def unload(*args):
        order.append("platforms")
        return True

    hass.config_entries.async_unload_platforms = AsyncMock(side_effect=unload)
    assert await async_unload_entry(hass, entry)
    assert order == ["stop", "platforms", "disconnect"]


def test_disabled_legacy_companion_options_are_copied_without_losing_module_options(hass):
    entry = make_entry(
        entry_id="base",
        data={"host": "fonterra.example", "port": 502},
        options={"rooms": {"room_1": {"name": "Keep"}}, "custom_option": 7},
    )
    old = make_entry(
        domain="fonterra_connect",
        entry_id="old",
        data={"modbus_entry_id": "base", "wifi_serial": "TEST000001", "connect_upgrade": True},
        options={"sources": {"1": {"entity_id": "sensor.room", "max_age": 900}}},
    )
    object.__setattr__(old, "disabled_by", ConfigEntryDisabler.USER)
    manager(hass, [entry, old])
    result = merged_options(hass, entry)
    assert result["rooms"] == entry.options["rooms"]
    assert result["custom_option"] == 7
    assert result["sources"] == old.options["sources"]
    assert result["_connect_wifi_serial"] == "TEST000001"
    assert result["connect_upgrade"] is True
    assert "connect_upgrade" not in entry.options


def test_existing_merged_options_are_never_overwritten_by_old_companion(hass):
    entry = make_entry(
        entry_id="base", options={"connect_upgrade": False, "sources": {}, "rooms": {}}
    )
    old = make_entry(
        domain="fonterra_connect",
        data={"modbus_entry_id": "base", "wifi_serial": "TEST000001", "connect_upgrade": True},
    )
    object.__setattr__(old, "disabled_by", ConfigEntryDisabler.USER)
    manager(hass, [entry, old])
    assert merged_options(hass, entry) == dict(entry.options)
