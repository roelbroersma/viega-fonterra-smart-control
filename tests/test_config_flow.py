from ipaddress import IPv4Address
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_entry
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.viega_fonterra_modbus.config_flow import (
    ViegaFonterraConfigFlow,
    ViegaFonterraOptionsFlow,
)
from custom_components.viega_fonterra_modbus.const import DOMAIN


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


async def test_settings_show_connection_settings_and_saved_connect_flag(hass):
    entry = make_entry(data={"host": "fonterra.example", "port": 502, "connect_upgrade": True})
    flow = options_flow(hass, entry)
    form = await flow.async_step_init()
    assert form["type"] == "form"
    assert form["step_id"] == "init"
    schema = form["data_schema"]
    assert set(schema.schema) == {
        "host",
        "port",
        "device_name",
        "polling_interval",
        "modbus_timeout",
        "connect_upgrade",
    }
    assert schema({})["connect_upgrade"] is True

    disabled = make_entry(data=dict(entry.data), options={"connect_upgrade": False})
    flow = options_flow(hass, disabled)
    assert (await flow.async_step_init())["data_schema"]({})["connect_upgrade"] is False


async def test_connection_change_verifies_identity_and_preserves_options(hass):
    previous = {
        "rooms": {"room_1": {"name": "Badkamer", "room_number": 1, "actor": [2, 4]}},
        "device_id": "original",
        "sources": {"1": {"entity_id": "sensor.room"}},
        "_identity": {"wlan_serial_number": "TEST000001"},
    }
    entry = make_entry(data={"host": "old.example", "port": 502}, options=previous)
    flow = options_flow(hass, entry)
    schema = (await flow.async_step_init())["data_schema"]
    client = AsyncMock()
    with (
        patch(
            "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
            return_value=client,
        ) as factory,
        patch(
            "custom_components.viega_fonterra_modbus.config_flow.read_wlan_serial",
            AsyncMock(return_value="TEST000001"),
        ),
    ):
        result = await flow.async_step_init(
            schema({"host": "new.example", "port": 1502, "connect_upgrade": True})
        )
        factory.assert_called_once_with("new.example", 1502, timeout=5)

    assert result["type"] == "create_entry"
    assert result["data"] == {
        **previous,
        "connect_upgrade": True,
        "_connect_wifi_serial": "TEST000001",
    }
    updated = hass.config_entries.async_update_entry.call_args.kwargs
    assert updated["options"] == result["data"]
    assert updated["data"]["host"] == "new.example"
    assert updated["data"]["port"] == 1502
    hass.config_entries.async_update_entry.assert_called_once()
    client.write_register.assert_not_called()


async def test_turn_off_connect_without_contacting_an_offline_controller(hass):
    entry = make_entry(
        data={"host": "fonterra.example", "port": 502},
        options={"connect_upgrade": True, "sources": {"1": {"entity_id": "sensor.room"}}},
    )
    flow = options_flow(hass, entry)
    schema = (await flow.async_step_init())["data_schema"]
    with patch("custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient") as client:
        result = await flow.async_step_init(schema({"connect_upgrade": False}))
    assert result["type"] == "create_entry"
    assert result["data"]["connect_upgrade"] is False
    assert result["data"]["sources"] == entry.options["sources"]
    client.assert_not_called()


async def test_concurrent_settings_change_does_not_overwrite_the_entry(hass):
    entry = make_entry(
        data={"host": "fonterra.example", "port": 502},
        options={"connect_upgrade": True},
    )
    flow = options_flow(hass, entry)
    schema = (await flow.async_step_init())["data_schema"]

    async def validate(data, options):
        object.__setattr__(entry, "options", MappingProxyType({"connect_upgrade": False}))

    with patch.object(flow, "_validate_endpoint", side_effect=validate):
        result = await flow.async_step_init(schema({"host": "new.example"}))
    assert result["reason"] == "settings_changed"
    hass.config_entries.async_update_entry.assert_not_called()


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
