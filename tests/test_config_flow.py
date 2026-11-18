from ipaddress import IPv4Address
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_entry
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.viega_fonterra_modbus.config_flow import (
    ViegaFonterraConfigFlow,
    ViegaFonterraOptionsFlow,
)
from custom_components.viega_fonterra_modbus.connect.const import DOMAIN


def manager(hass, entries):
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries.side_effect = lambda domain, *args: [
        entry for entry in entries if entry.domain == domain
    ]
    hass.config_entries.async_get_entry.side_effect = lambda entry_id: next(
        (entry for entry in entries if entry.entry_id == entry_id), None
    )
    hass.config_entries.async_get_known_entry.side_effect = (
        hass.config_entries.async_get_entry.side_effect
    )
    hass.config_entries.flow.async_progress_by_handler.return_value = []
    hass.config_entries.async_entry_for_domain_unique_id.return_value = None


async def test_one_setup_flow_for_standard_and_connect(hass):
    manager(hass, [])
    flow = ViegaFonterraConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {"source": "user"}
    form = await flow.async_step_user()
    data = form["data_schema"]({"host": "fonterra.example", "port": 502, "device_name": "Fonterra"})
    assert data["connect_upgrade"] is False
    client = AsyncMock()
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient", return_value=client
    ):
        result = await flow.async_step_user({**data, "connect_upgrade": True})
    assert result["type"] == "create_entry"
    assert result["data"]["host"] == "fonterra.example"
    assert result["data"]["connect_upgrade"] is True
    assert flow.unique_id == "fonterra.example:502"
    client.write_register.assert_not_called()
    hass.config_entries.async_entry_for_domain_unique_id.return_value = make_entry()
    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_user(data)


def options_flow(hass, entry):
    manager(hass, [entry])
    flow = ViegaFonterraOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    return flow


async def test_single_options_menu_contains_both_features(hass, entry):
    flow = options_flow(hass, entry)
    menu = await flow.async_step_init()
    assert menu["type"] == "menu"
    assert menu["menu_options"] == ["module", "connect"]
    form = await flow.async_step_module()
    assert form["step_id"] == "module"
    form = await flow.async_step_connect()
    assert form["step_id"] == "connect"


async def test_connect_options_preserve_all_normal_settings(hass):
    previous = {
        "rooms": {"room_1": {"name": "Living", "room_number": 1, "actor": [1, 2]}},
        "device_id": "original",
        "future_option": 42,
        "_identity": {"wlan_serial_number": "TEST000001"},
    }
    entry = make_entry(options=previous)
    flow = options_flow(hass, entry)
    bus = MagicMock()
    bus.rooms.return_value = {1: {"name": "Living"}}
    bus.room_present = AsyncMock(return_value=True)
    bus.check_connection = AsyncMock()
    bus.identity.return_value = "TEST000001"
    with patch(
        "custom_components.viega_fonterra_modbus.connect.options.SharedModbus", return_value=bus
    ):
        assert (await flow.async_step_connect({"connect_upgrade": True, "configure_source": True}))[
            "step_id"
        ] == "room"
        assert (await flow.async_step_room({"room": "1"}))["step_id"] == "source"
        hass.states.async_set(
            "sensor.room", "20", {"unit_of_measurement": "°C", "device_class": "temperature"}
        )
        invalid = await flow.async_step_source(
            {"entity_id": "sensor.room", "max_age": 600, "external_confirmed": False}
        )
        assert invalid["errors"] == {"base": "external_required"}
        result = await flow.async_step_source(
            {"entity_id": "sensor.room", "max_age": 600, "external_confirmed": True}
        )
    assert result["data"]["sources"]["1"]["entity_id"] == "sensor.room"
    assert result["data"]["_connect_wifi_serial"] == "TEST000001"
    for key, value in previous.items():
        assert result["data"][key] == value
    assert entry.options == previous
    bus.write_measurement.assert_not_called()


async def test_disabling_connect_does_not_remove_room_configuration(hass, entry):
    flow = options_flow(hass, entry)
    result = await flow.async_step_connect({"connect_upgrade": False, "configure_source": True})
    assert result["type"] == "create_entry"
    assert result["data"]["connect_upgrade"] is False
    assert result["data"]["sources"] == entry.options["sources"]


async def test_old_sender_must_be_stopped_before_new_one(hass, entry):
    flow = options_flow(hass, entry)
    old = make_entry(
        domain="fonterra_connect", entry_id="old", data={"modbus_entry_id": entry.entry_id}
    )
    manager(hass, [entry, old])
    result = await flow.async_step_connect({"connect_upgrade": True, "configure_source": True})
    assert result["errors"] == {"base": "legacy_companion_active"}


async def test_connection_form_has_no_topology_fields_and_preserves_rooms(hass):
    options = {
        "rooms": {"room_7": {"room_number": 7, "name": "Room", "actor": [2, 4]}},
        "sources": {"7": {"entity_id": "sensor.room"}},
    }
    entry = make_entry(data={"host": "fonterra.example", "port": 502}, options=options)
    flow = options_flow(hass, entry)
    form = await flow.async_step_module()
    assert set(form["data_schema"].schema) == {
        "host",
        "port",
        "device_name",
        "polling_interval",
        "modbus_timeout",
    }
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
        return_value=AsyncMock(),
    ):
        result = await flow.async_step_module(form["data_schema"]({"device_name": "Test module"}))
    assert result["data"] == options


def advertisement(ip, name, port=502):
    address = IPv4Address(ip)
    return ZeroconfServiceInfo(
        ip_address=address,
        ip_addresses=[address],
        port=port,
        hostname=f"{name}.local.",
        type="_modbus._tcp.local.",
        name=f"{name}._modbus._tcp.local.",
        properties={"Vendor": "Viega", "Model": "Fonterra Smart Control"},
    )


@pytest.mark.parametrize("existing_host", ["192.0.2.200", "SMART-ONE.local."])
async def test_zeroconf_skips_existing_hub_at_ip_or_hostname(hass, existing_host):
    manager(hass, [make_entry(data={"host": existing_host, "port": 502})])
    flow = ViegaFonterraConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {"source": "zeroconf"}
    with patch("custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient") as client:
        result = await flow.async_step_zeroconf(advertisement("192.0.2.200", "smart-one"))
    assert result["reason"] == "already_configured"
    client.assert_not_called()


async def test_zeroconf_offers_two_hubs_without_connecting_until_confirmation(hass):
    manager(hass, [])
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
        return_value=AsyncMock(),
    ) as client:
        pending = []
        for suffix, name in [(200, "smart-one"), (201, "smart-two")]:
            flow = ViegaFonterraConfigFlow()
            flow.hass = hass
            flow.handler = DOMAIN
            flow.context = {"source": "zeroconf"}
            host = f"192.0.2.{suffix}"
            form = await flow.async_step_zeroconf(advertisement(host, name))
            data = form["data_schema"]({})
            assert data["host"] == host
            assert not data["connect_upgrade"]
            pending.append((flow, data))
        client.assert_not_called()
        assert pending[0][0].unique_id != pending[1][0].unique_id
        flow, data = pending[1]
        result = await flow.async_step_user(data)
        assert result["type"] == "create_entry"
        assert result["data"]["host"] == "192.0.2.201"
        client.assert_called_once_with("192.0.2.201", 502, timeout=5.0)
        client.return_value.write_register.assert_not_called()
