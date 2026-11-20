from unittest.mock import AsyncMock, Mock, patch

import pytest
from conftest import make_entry
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.config_entries import ConfigEntries
from homeassistant.const import UnitOfTemperature
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.viega_fonterra_modbus.climate import (
    ViegaRoomClimateEntity,
    build_room_entities,
)
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.number import (
    ViegaPowerLevelNumber,
)
from custom_components.viega_fonterra_modbus.number import (
    async_setup_entry as setup_power_controls,
)


def test_existing_control_ids_and_registers_are_preserved():
    assert DOMAIN == "viega_fonterra_modbus"
    room = {"room_number": 7, "name": "Living", "actor": [2, 4], "sensor": 7}
    climate = ViegaRoomClimateEntity("original", "room_7", "Living", 19.7, 21, room)
    power = ViegaPowerLevelNumber("original", "room_7", room)
    assert climate.unique_id == "original_room_7_thermostat"
    assert power.unique_id == "original_room_7_power_level"
    assert climate._registers["current_temperature"] == 62
    assert climate._registers["target_temperature"] == 63


async def test_legacy_fahrenheit_restore_becomes_native_celsius(hass):
    climate = ViegaRoomClimateEntity("original", "room_1", "Living", 19.7, 21)
    climate.hass = hass
    previous = State(
        "climate.living",
        "heat",
        {"current_temperature": 68, "temperature": 71.6, "temperature_unit": "°F"},
    )
    with (
        patch(
            "custom_components.viega_fonterra_modbus.entity.ViegaCoordinatedEntity.async_added_to_hass",
            AsyncMock(),
        ),
        patch.object(climate, "async_get_last_state", AsyncMock(return_value=previous)),
        patch.object(climate, "async_get_last_extra_data", AsyncMock(return_value=None)),
    ):
        await climate.async_added_to_hass()
    assert climate.native_temperature_unit == UnitOfTemperature.CELSIUS
    assert climate.native_current_temperature == pytest.approx(20)
    assert climate.native_target_temperature == pytest.approx(22)
    restored = climate.extra_restore_state_data.as_dict()
    assert restored["native_current_temperature"] == pytest.approx(20)
    assert restored["native_temperature_unit"] == "°C"


async def test_native_temperatures_update_from_device(hass):
    climate = ViegaRoomClimateEntity("original", "room_1", "Living", 19.7, 21)
    climate.hass = hass
    hass.data[DOMAIN] = {"original": {"client": object()}}
    with patch.object(
        climate,
        "_read_values",
        AsyncMock(return_value={"current_temperature": 203, "target_temperature": 225}),
    ):
        await climate.async_update()
    assert climate.native_current_temperature == 20.3
    assert climate.native_target_temperature == 22.5


@pytest.mark.parametrize("write_fails", [False, True])
async def test_native_target_write_and_failed_write_restore(hass, write_fails):
    climate = ViegaRoomClimateEntity("original", "room_1", "Living", 19.7, 21)
    climate.hass = hass
    hass.data[DOMAIN] = {"original": {"client": object()}}
    write = AsyncMock(side_effect=HomeAssistantError("test failure") if write_fails else None)
    with (
        patch("custom_components.viega_fonterra_modbus.climate.async_write_register", write),
        patch.object(climate, "_async_after_write", AsyncMock()),
    ):
        if write_fails:
            with pytest.raises(HomeAssistantError):
                await climate.async_set_temperature(temperature=22.5)
        else:
            await climate.async_set_temperature(temperature=22.5)
    write.assert_awaited_once_with(hass, "original", 51, 225)
    assert climate.native_target_temperature == (21 if write_fails else 22.5)


async def test_unavailable_power_level_rejects_control_and_cancels_queued_write(hass):
    room = {"room_number": 1, "name": "Living"}
    power = ViegaPowerLevelNumber("original", "room_1", room)
    power.hass = hass
    client = AsyncMock()
    client.read_holding_registers.side_effect = [[3], [-99], [5]]
    hass.data[DOMAIN] = {"original": {"client": client}}
    with pytest.raises(ServiceValidationError) as error:
        await power.async_set_native_value(4)
    assert error.value.translation_key == "power_level_unavailable"

    await power.async_update()
    assert power.available
    assert power.native_value == 3
    cancel = Mock()
    with patch.object(power, "_async_send_when_stable", AsyncMock()) as queue:
        await power.async_set_native_value(4)
        key, send = queue.await_args.args
    power._waiting_sends = {key: (cancel, send)}
    await power.async_update()
    assert not power.available
    assert power.native_value is None
    cancel.assert_called_once()
    with pytest.raises(ServiceValidationError):
        await power.async_set_native_value(6)
    await send()
    client.write_register.assert_not_awaited()
    await power.async_update()
    assert power.available
    assert power.native_value == 5
    await power.async_set_native_value(6)
    client.write_register.assert_awaited_once_with(50, 6)


async def test_power_control_is_listed_only_when_a_single_group_has_a_valid_level(hass):
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    dr.async_setup(hass)
    await dr.async_load(hass, load_empty=True)
    await er.async_load(hass, load_empty=True)
    registry = er.async_get(hass)
    entry = make_entry(entry_id="original")
    thermostat = registry.async_get_or_create(
        "number", DOMAIN, "original_room_1_power_level", suggested_object_id="living_power"
    )
    user_disabled = registry.async_get_or_create(
        "number",
        DOMAIN,
        "original_room_4_power_level",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    rooms = {
        "room_1": {"actor": 1},
        "room_2": {"actor": 2},
        "room_3": {"actor": [3, 4]},
        "room_4": {"actor": 5},
        "room_5": {"actor": 6},
    }
    coordinator = Mock(
        data={
            ("holding", 50, 1): [-99],
            ("holding", 52, 1): [5],
            ("holding", 54, 1): [5],
            ("holding", 56, 1): [5],
            ("holding", 58, 1): [5],
            ("holding", 59, 1): [210],
        }
    )
    hass.data[DOMAIN] = {"original": {"rooms": rooms, "polling": coordinator}}
    added = Mock()
    await setup_power_controls(hass, entry, added)

    assert (
        registry.async_get(thermostat.entity_id).disabled_by == er.RegistryEntryDisabler.INTEGRATION
    )
    assert registry.async_get(user_disabled.entity_id).disabled_by == er.RegistryEntryDisabler.USER
    assert [entities.args[0][0].unique_id for entities in added.call_args_list] == [
        "original_room_2_power_level"
    ]

    sync = coordinator.async_add_listener.call_args.args[0]
    coordinator.data[("holding", 50, 1)] = [3]
    sync()
    sync()
    assert registry.async_get(thermostat.entity_id).disabled_by is None
    assert added.call_count == 2
    assert added.call_args.args[0][0].unique_id == thermostat.unique_id


@pytest.mark.usefixtures("loaded_registries")
@pytest.mark.parametrize("connect_enabled", [False, True])
async def test_number_platform_adds_one_external_input_per_discovered_room(hass, connect_enabled):
    entry = make_entry()
    rooms = {
        "room_1": {"name": "Living", "room_number": 1, "actor": [2, 4]},
        "room_7": {"name": "Bath", "room_number": 7, "actor": 1},
    }
    hass.data[DOMAIN] = {
        entry.entry_id: {
            "rooms": rooms,
            "polling": Mock(data={}),
            "connect": Mock() if connect_enabled else None,
        }
    }
    added = Mock()
    await setup_power_controls(hass, entry, added)
    assert [call.args[0][0].unique_id for call in added.call_args_list] == (
        ["connect_room_1_external_temperature", "connect_room_7_external_temperature"]
        if connect_enabled
        else []
    )


async def test_missing_measurement_is_not_a_default_or_restored_temperature(hass):
    climate = build_room_entities("original", "room_1", {"name": "Living"})[0]
    assert climate.native_current_temperature is None
    assert climate.native_target_temperature is None
    climate.hass = hass
    hass.data[DOMAIN] = {"original": {"client": object()}}
    values = [
        {"current_temperature": 203, "target_temperature": 225},
        {},
        {"current_temperature": -99, "target_temperature": -99},
    ]
    with patch.object(climate, "_read_values", AsyncMock(side_effect=values)):
        await climate.async_update()
        await climate.async_update()
        assert climate.native_current_temperature == 20.3
        assert climate.native_target_temperature == 22.5
        await climate.async_update()
    assert climate.native_current_temperature is None
    assert climate.native_target_temperature is None
    assert ClimateEntityFeature.TARGET_TEMPERATURE not in climate.supported_features
    with pytest.raises(ServiceValidationError) as error:
        await climate.async_set_temperature(temperature=20)
    assert error.value.translation_key == "target_temperature_unavailable"
