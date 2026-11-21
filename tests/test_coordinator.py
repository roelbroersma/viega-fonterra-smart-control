from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from conftest import make_entry
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.viega_fonterra_modbus.connect.coordinator import ConnectCoordinator
from custom_components.viega_fonterra_modbus.connect.modbus import ModbusError

CLOCK = "custom_components.viega_fonterra_modbus.connect.coordinator.dt_util.utcnow"
pytestmark = pytest.mark.usefixtures("loaded_registries")


def mock_bus():
    bus = AsyncMock()
    bus.rooms = lambda: {1: {"room_number": 1, "actor": 4}}
    bus.room_present.return_value = True
    bus.check_connection.return_value = ("connection", 1)
    return bus


async def test_unchanged_value_is_not_repeated_and_changed_measurement_is_sent(hass, entry):
    bus = mock_bus()
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    await coordinator._async_update_data()
    bus.write_measurement.assert_awaited_once_with(1, 19.7)
    await coordinator._async_update_data()
    assert bus.write_measurement.await_count == 1
    with patch(CLOCK, return_value=dt_util.utcnow() + timedelta(seconds=61)):
        await coordinator._async_update_data()
    assert bus.write_measurement.await_count == 1
    with patch(CLOCK, return_value=dt_util.utcnow() + timedelta(seconds=901)):
        await coordinator._async_update_data()
    assert bus.write_measurement.await_count == 1
    hass.states.async_set("sensor.room", "20.1", {"unit_of_measurement": "°C"})
    await coordinator._async_update_data()
    assert bus.write_measurement.await_count == 2
    bus.write_measurement.assert_awaited_with(1, 20.1)
    await coordinator.async_shutdown()


async def test_reconnect_sends_first_measurement_again(hass, entry):
    bus = mock_bus()
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    await coordinator._async_update_data()
    await coordinator._async_update_data()
    assert bus.write_measurement.await_count == 1
    bus.check_connection.return_value = ("connection", 2)
    await coordinator._async_update_data()
    assert bus.write_measurement.await_count == 2
    bus.write_measurement.assert_awaited_with(1, 19.7)
    await coordinator._async_update_data()
    assert bus.write_measurement.await_count == 2
    await coordinator.async_shutdown()


@pytest.mark.parametrize("value", ["unknown", "unavailable", "nan", "41"])
async def test_no_fallback_or_writes_on_invalid_source(hass, entry, value):
    bus = mock_bus()
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", value, {"unit_of_measurement": "°C"})
    await coordinator._async_update_data()
    bus.write_measurement.assert_not_called()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("options", [{"connect_upgrade": False}, {"sources": {}}])
async def test_unused_connect_does_not_poll_the_bus(hass, entry, options):
    entry = make_entry(data=dict(entry.data), options={**entry.options, **options})
    bus = mock_bus()
    coordinator = ConnectCoordinator(hass, entry, bus)
    await coordinator._async_update_data()
    bus.check_connection.assert_not_called()
    bus.write_measurement.assert_not_called()
    await coordinator.async_shutdown()


async def test_room_removed_no_write(hass, entry):
    bus = mock_bus()
    bus.room_present.return_value = False
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    await coordinator._async_update_data()
    bus.write_measurement.assert_not_called()
    await coordinator.async_shutdown()


async def test_timeout_is_not_blindly_retried(hass, entry):
    bus = mock_bus()
    bus.write_measurement.side_effect = ModbusError()
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    await coordinator._async_update_data()
    bus.reset_mock()
    await coordinator._async_update_data()
    bus.write_measurement.assert_not_called()
    with patch(CLOCK, return_value=dt_util.utcnow() + timedelta(seconds=61)):
        await coordinator._async_update_data()
    assert bus.check_connection.await_count == 2
    bus.room_present.assert_awaited_once_with(1)
    bus.write_measurement.assert_awaited_once_with(1, 19.7)
    await coordinator.async_shutdown()


async def test_disconnected_coordinator_resumes_after_identity_check(hass, entry):
    bus = mock_bus()
    bus.check_connection.side_effect = ModbusError()
    coordinator = ConnectCoordinator(hass, entry, bus)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    bus.write_measurement.assert_not_called()
    bus.check_connection.side_effect = None
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    await coordinator._async_update_data()
    bus.write_measurement.assert_awaited_once_with(1, 19.7)
    await coordinator.async_shutdown()
