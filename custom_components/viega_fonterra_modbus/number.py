"""Writable actuator power levels and external room temperatures."""

from __future__ import annotations

import time

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .connect.number import build_room_input
from .const import DOMAIN, WRITE_CONFIRM_GRACE
from .device import build_device_info
from .entity import ViegaCoordinatedEntity
from .entity_tracking import register_platform
from .errors import async_write_register, invalid_request
from .registers import resolve_room_number, room_actor_numbers, room_registers


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Expose power controls only where a fresh poll confirms manual operation."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["polling"]
    platform = register_platform(hass, entry.entry_id, "number", async_add_entities)
    registry = er.async_get(hass)

    if runtime.get("connect") is not None:
        inputs = register_platform(hass, entry.entry_id, "external_temperature", async_add_entities)
        for room_id, room_config in runtime["rooms"].items():
            entities = build_room_input(entry.entry_id, room_id, room_config)
            for entity in entities:
                entity_id = registry.async_get_entity_id("number", DOMAIN, entity.unique_id)
                registered = registry.async_get(entity_id) if entity_id else None
                # Upgrade the former default while preserving the user's own disable choice.
                if registered and registered.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
                    registry.async_update_entity(registered.entity_id, disabled_by=None)
            inputs.add_room(room_id, entities)

    @callback
    def sync_power_controls() -> None:
        samples = coordinator.data or {}
        for room_id, room_config in runtime["rooms"].items():
            active = platform.by_room.get(room_id)
            entities = active or build_room_entities(entry.entry_id, room_id, room_config)
            if not entities:
                continue
            power = entities[0]
            values = samples.get(("holding", power.address, 1), [])
            target = samples.get(("holding", power.target_address, 1), [])
            manual_group = len(room_actor_numbers(room_config)) <= 1 and not (
                target and target[0] != -99
            )
            if not values and manual_group:
                continue
            entity_id = registry.async_get_entity_id("number", DOMAIN, power.unique_id)
            registered = registry.async_get(entity_id) if entity_id else None
            if not manual_group or not _valid_power_level(values[0]):
                if registered is not None and not registered.disabled:
                    registry.async_update_entity(
                        registered.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                    )
                    platform.by_room.pop(room_id, None)
                continue
            if registered is not None and registered.disabled:
                if registered.disabled_by != er.RegistryEntryDisabler.INTEGRATION:
                    continue
                registry.async_update_entity(registered.entity_id, disabled_by=None)
            if not active:
                power._attr_available = True
                power._attr_native_value = values[0]
                platform.add_room(room_id, entities)

    entry.async_on_unload(coordinator.async_add_listener(sync_power_controls))
    sync_power_controls()


def _valid_power_level(value: object) -> bool:
    return type(value) is int and 0 <= value <= 10


def build_room_entities(
    entry_id: str, room_id: str, room_config: object
) -> list["ViegaPowerLevelNumber"]:
    """Build the power-level Number entity a room contributes, if any.

    Rooms without a resolvable register do not contribute a control.
    """
    if not isinstance(room_config, dict):
        return []
    entity = ViegaPowerLevelNumber(entry_id, room_id, room_config)
    return [entity] if entity.address is not None else []


class ViegaPowerLevelNumber(ViegaCoordinatedEntity, NumberEntity):
    """Read and write the documented room power-level register."""

    _attr_has_entity_name = True
    _attr_available = False
    _attr_native_min_value = 0
    _attr_native_max_value = 10
    _attr_native_step = 1
    # The unit is a word, so it is translated (spec.md 5d):
    # entity.number.power_level.unit_of_measurement.

    def __init__(self, entry_id: str, room_id: str, room_config: dict[str, object]) -> None:
        room_number = resolve_room_number(room_id, room_config)
        registers = room_registers(room_number) if room_number else {}
        address = room_config.get("power_level_register", registers.get("power_level"))
        target = room_config.get("target_temperature_register", registers.get("target_temperature"))
        self._entry_id = entry_id
        self._room_id = room_id
        self._attr_extra_state_attributes = {"room_id": room_number or room_id}
        # No configured/derivable register means the write feature must not
        # be advertised at all (spec.md 5a); async_setup_entry skips adding
        # this entity when `address` is None instead of falling back to
        # register 0, which collides with the base unit's operating-mode
        # register and would let an unconfigured entity write to it.
        self.address: int | None = int(address) if address is not None else None
        self.target_address = int(target) if target is not None else None
        self._attr_unique_id = f"{entry_id}_{room_id}_power_level"
        self._attr_translation_key = "power_level"
        self._attr_translation_placeholders = {"room": str(room_config.get("name", room_id))}
        self._attr_native_value = None
        self.last_error_message = ""
        # Read-after-write verification (spec.md 16c): the level most
        # recently written, cleared once the next successfully-read raw
        # value (from a cache generation newer than the write) has been
        # compared against it. See climate.py's `_verify_pending_writes`
        # for why the generation check matters.
        self._pending_write: tuple[int, int, float] | None = None

    async def async_update(self) -> None:
        """Read the current actuator power level."""
        entry_data = self.hass.data[DOMAIN][self._entry_id]
        if self.address is None:
            return
        client = entry_data["client"]
        try:
            shared = entry_data.get("polling")
            values = await (
                shared.read(self.hass, self._entry_id, "holding", self.address, 1)
                if shared
                else client.read_holding_registers(self.address, 1)
            )
        except Exception:
            values = []
        if values and _valid_power_level(values[0]):
            self._attr_available = True
            self._verify_pending_write(values[0], entry_data.get("polling"))
            # Keep showing a written level until a newer cycle confirms it
            # (spec.md 16c): older data must not flicker it back.
            if self._pending_write is None and not self._is_waiting("power_level"):
                self._attr_native_value = values[0]
        else:
            self._attr_available = False
            self._attr_native_value = None
            self._pending_write = None
            pending = getattr(self, "_waiting_sends", {}).pop("power_level", None)
            if pending:
                pending[0]()

    def _verify_pending_write(self, raw: int, shared) -> None:
        """Check a just-written power level against the device's own next
        valid read of it (spec.md 16c)."""
        if self._pending_write is None:
            return
        expected, write_generation, written_at = self._pending_write
        generation = shared.generation if shared is not None else 0
        if shared is not None and generation <= write_generation:
            return
        if raw != expected and time.monotonic() - written_at < WRITE_CONFIRM_GRACE:
            return  # the device may still be applying the write
        self._pending_write = None
        if raw != expected:
            self.last_error_message = (
                f"warning: power_level write not confirmed - wrote {expected} "
                f"to register {self.address}, device now reports {raw}"
            )

    async def async_set_native_value(self, value: float) -> None:
        """Write a new actuator power level."""
        if self.address is None:
            raise invalid_request(
                "register_not_configured", room=self._attr_translation_placeholders["room"]
            )
        if not self.available:
            raise invalid_request(
                "power_level_unavailable", room=self._attr_translation_placeholders["room"]
            )
        level = round(value)
        if not 0 <= level <= 10:
            raise invalid_request("power_level_out_of_range", value=level, min=0, max=10)
        if not self._is_waiting("power_level"):
            # Shown again if the write fails (spec.md 10a).
            self._level_before_change = self._attr_native_value
        self._attr_native_value = level

        async def send() -> None:
            if not self.available:
                return
            try:
                await async_write_register(self.hass, self._entry_id, self.address, level)
            except HomeAssistantError:
                self._attr_native_value = self._level_before_change
                raise
            shared = self.hass.data[DOMAIN][self._entry_id].get("polling")
            self._pending_write = (
                level,
                shared.generation if shared is not None else 0,
                time.monotonic(),
            )
            await self._async_after_write()

        # Shown at once, sent once the value has been stable (spec.md 16c).
        await self._async_send_when_stable("power_level", send)

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)
