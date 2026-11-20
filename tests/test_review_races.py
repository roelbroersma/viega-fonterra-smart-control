"""Regression checks for the additional lifecycle/concurrency review."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from test_coordinator import mock_bus

from custom_components.viega_fonterra_modbus.connect.coordinator import ConnectCoordinator

pytestmark = pytest.mark.usefixtures("loaded_registries")


async def test_shutdown_during_read_must_not_send_a_measurement(hass, entry):
    bus = mock_bus()
    reading = asyncio.Event()
    release = asyncio.Event()

    async def read(room):
        reading.set()
        await release.wait()
        return True

    bus.room_present.side_effect = read
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    task = asyncio.create_task(coordinator._async_update_data())
    await reading.wait()
    await coordinator.async_shutdown()
    release.set()
    await asyncio.gather(task, return_exceptions=True)
    bus.write_measurement.assert_not_called()


@pytest.mark.parametrize("invalid", ["unknown", "unavailable", "nan", "41"])
async def test_invalid_source_cancels_a_queued_write(hass, entry, invalid):
    bus = mock_bus()
    waiting = asyncio.Event()
    reached_wire = []

    async def write(room, value):
        waiting.set()
        # Simulate waiting for the shared client's lock.
        await asyncio.Event().wait()
        reached_wire.append((room, value))

    bus.write_measurement.side_effect = write
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    task = asyncio.create_task(coordinator._async_update_data())
    await waiting.wait()
    hass.states.async_set("sensor.room", invalid, {"unit_of_measurement": "°C"})
    await asyncio.wait_for(task, timeout=1)
    assert reached_wire == []
    await coordinator.async_shutdown()


async def test_source_expiry_cancels_a_queued_write(hass, entry):
    bus = mock_bus()
    cancelled = asyncio.Event()

    async def write(room, value):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    bus.write_measurement.side_effect = write
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    now = hass.states.get("sensor.room").last_reported + timedelta(seconds=899.95)
    with patch(
        "custom_components.viega_fonterra_modbus.connect.coordinator.dt_util.utcnow",
        return_value=now,
    ):
        await asyncio.wait_for(coordinator._async_update_data(), timeout=1)
    assert cancelled.is_set()
    await coordinator.async_shutdown()


async def test_new_measurement_replaces_a_queued_value(hass, entry):
    bus = mock_bus()
    waiting = asyncio.Event()
    writes = []

    async def write(room, value):
        if value == 19.7:
            waiting.set()
            await asyncio.Event().wait()
        writes.append((room, value))

    bus.write_measurement.side_effect = write
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    task = asyncio.create_task(coordinator._async_update_data())
    await asyncio.wait_for(waiting.wait(), timeout=1)
    hass.states.async_set("sensor.room", "20.1", {"unit_of_measurement": "°C"})
    await asyncio.wait_for(task, timeout=1)
    assert writes == []

    await coordinator._async_update_data()
    assert writes == [(1, 20.1)]
    await coordinator.async_shutdown()


async def test_shutdown_cancels_a_queued_write(hass, entry):
    bus = mock_bus()
    waiting = asyncio.Event()
    cancelled = asyncio.Event()

    async def write(room, value):
        waiting.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    bus.write_measurement.side_effect = write
    coordinator = ConnectCoordinator(hass, entry, bus)
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    task = asyncio.create_task(coordinator._async_update_data())
    await waiting.wait()
    await coordinator.async_shutdown()
    assert task.cancelled()
    assert cancelled.is_set()
