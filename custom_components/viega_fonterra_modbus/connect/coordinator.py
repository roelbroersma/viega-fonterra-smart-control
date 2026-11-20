"""Forward recent Home Assistant temperature readings to Connected Upgrade."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from .const import (
    CONF_CONNECT,
    CONF_MAPPINGS,
    CONF_MAX_AGE,
    DEFAULT_MAX_AGE,
    POLL_SECONDS,
    REFRESH_SECONDS,
    temperature_input_id,
)
from .modbus import ModbusError, SharedModbus
from .source import measurement


class ConnectCoordinator(DataUpdateCoordinator[None]):
    """Send measurements. The normal Fonterra diagnosis reports room faults."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, bus: SharedModbus) -> None:
        super().__init__(
            hass,
            logging.getLogger(__name__),
            config_entry=entry,
            name="Fonterra Connect",
            update_interval=timedelta(seconds=POLL_SECONDS),
        )
        self.bus = bus
        self.entry = entry
        self.started = dt_util.utcnow()
        self.last_sent = {}
        self._updates = set()
        self._write_lock = asyncio.Lock()
        self._stopping = False

    async def _async_update_data(self) -> None:
        task = asyncio.current_task()
        self._updates.add(task)
        try:
            async with self._write_lock:
                if not self._stopping:
                    await self._update_measurements()
        finally:
            self._updates.discard(task)

    async def async_shutdown(self) -> None:
        self._stopping = True
        await super().async_shutdown()
        # Stopping HA's poll timer leaves any running read or queued write in
        # progress. Drain our tasks before the shared connection is closed.
        active = [task for task in self._updates if task is not asyncio.current_task()]
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)
        # Finish any direct write before the shared connection is closed.
        async with self._write_lock:
            pass

    def _input_entry(self, room: int) -> er.RegistryEntry | None:
        registry = er.async_get(self.hass)
        entity_id = registry.async_get_entity_id(
            "number", DOMAIN, temperature_input_id(self.entry.entry_id, room)
        )
        return registry.async_get(entity_id) if entity_id else None

    def _input_enabled(self, room: int) -> bool:
        registered = self._input_entry(room)
        return registered is not None and not registered.disabled

    def _uses_sensor_link(self, room: int) -> bool:
        # An untouched input is disabled by the integration. Disabling an input
        # manually must stop sending instead of silently reviving an old link.
        registered = self._input_entry(room)
        return registered is None or registered.disabled_by == er.RegistryEntryDisabler.INTEGRATION

    async def async_write_input(self, room: int, value: float) -> float:
        """Send one explicit measurement to a verified unit and room."""
        async with self._write_lock:
            if self._stopping or not self._input_enabled(room):
                raise ModbusError("External temperature input unavailable")
            await self.bus.check_connection()
            if not await self.bus.room_present(room):
                raise ModbusError("The room is no longer assigned to its actuators")
            if self._stopping or not self._input_enabled(room):
                raise ModbusError("External temperature input unavailable")
            return await self.bus.write_measurement(room, value)

    async def _send_sample(self, room, entity_id, max_age, value) -> None:
        # The actor check awaited Modbus. A sensor may have changed in the meantime.
        now = dt_util.utcnow()
        state = self.hass.states.get(entity_id)
        if (
            state is None
            or measurement(state, now, max_age, self.started) != value
            or not self._uses_sensor_link(room)
        ):
            return
        remaining = max_age - (now - state.last_reported).total_seconds()

        @callback
        def changed(event):
            if (
                measurement(event.data["new_state"], dt_util.utcnow(), max_age, self.started)
                != value
            ):
                operation.cancel()

        unsubscribe = async_track_state_change_event(self.hass, [entity_id], changed)
        # Count an attempted write even if its acknowledgement is lost.
        self.last_sent[room] = (value, now)
        operation = asyncio.create_task(self.bus.write_measurement(room, value))
        try:
            # Climate operations share this socket; cancel if this sample
            # expires or is replaced before its turn in the queue.
            async with asyncio.timeout(remaining):
                await operation
        except TimeoutError:
            pass
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
        finally:
            unsubscribe()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)

    async def _update_measurements(self) -> None:
        enabled = self.entry.options.get(CONF_CONNECT, self.entry.data.get(CONF_CONNECT, False))
        mappings = self.entry.options.get(CONF_MAPPINGS, {})
        if not enabled or not mappings:
            return

        try:
            # Preserve existing links until the user enables the room's new input.
            rooms = [
                room
                for room in self.bus.rooms()
                if str(room) in mappings and self._uses_sensor_link(room)
            ]
            if not rooms:
                return
            await self.bus.check_connection()
        except ModbusError as err:
            raise UpdateFailed("Could not verify the Fonterra Modbus connection") from err

        for room in rooms:
            mapping = mappings[str(room)]
            entity_id = mapping["entity_id"]
            max_age = mapping.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)
            now = dt_util.utcnow()
            value = measurement(self.hass.states.get(entity_id), now, max_age, self.started)
            if value is None:
                continue
            previous = self.last_sent.get(room)
            if (
                previous
                and previous[0] == value
                and (now - previous[1]).total_seconds() < REFRESH_SECONDS
            ):
                continue
            try:
                # The room may have been reassigned locally since discovery.
                if await self.bus.room_present(room):
                    await self._send_sample(room, entity_id, max_age, value)
            except ModbusError:
                self.logger.debug(
                    "Could not send the external temperature for room %s", room, exc_info=True
                )
