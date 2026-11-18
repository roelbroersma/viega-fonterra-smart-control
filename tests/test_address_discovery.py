"""Run address-change discovery through Home Assistant's real flow manager."""

import shutil
from dataclasses import replace
from ipaddress import IPv4Address
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from conftest import make_entry
from homeassistant import loader
from homeassistant.components.persistent_notification.helpers import (
    _async_get_or_create_notifications,
)
from homeassistant.components.zeroconf.discovery import _match_against_props
from homeassistant.config_entries import (
    SOURCE_DHCP,
    SOURCE_ZEROCONF,
    ConfigEntries,
    ConfigEntryState,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.storage import Store
from test_config_flow import advertisement
from zeroconf.asyncio import AsyncServiceInfo

from custom_components.viega_fonterra_modbus import (
    async_reload_entry,
    async_remove_entry,
    async_setup,
)
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.discovery_store import (
    STORAGE_KEY,
    async_get_discovery_store,
    async_restore_discoveries,
)
from custom_components.viega_fonterra_modbus.modbus_handler import ModbusClientError

OLD = "192.0.2.150"
NEW = "192.0.2.143"
SERIAL = "1234567890"
ENTRY_ID = "reserve"


def registers(serial):
    raw = serial.encode().ljust(10, b"\0")
    return [int.from_bytes(raw[index : index + 2], "big") for index in range(0, 10, 2)]


@pytest.fixture
async def config(hass):
    target = Path(hass.config.path("custom_components", DOMAIN))
    target.mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).parents[1] / "custom_components" / DOMAIN / "manifest.json",
        target / "manifest.json",
    )
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    dr.async_setup(hass)
    await dr.async_load(hass, load_empty=True)
    await er.async_load(hass, load_empty=True)
    return hass.config_entries


async def add_entry(config, host=OLD, identity=True, entry_id=ENTRY_ID, loaded=False):
    options = {
        "rooms": {"room_3": {"name": "Bathroom", "actor": 4, "room_number": 3}},
        "sources": {"3": {"entity_id": "sensor.knx_room", "max_age": 900}},
    }
    if identity:
        options["_identity"] = {"wlan_serial_number": SERIAL}
    entry = make_entry(
        entry_id=entry_id,
        data={"host": host, "port": 502, "polling_interval": 30},
        options=options,
        unique_id=f"{host}:502",
        state=ConfigEntryState.LOADED if loaded else ConfigEntryState.SETUP_RETRY,
    )
    with patch.object(config, "async_setup", AsyncMock()):
        await config.async_add(entry)
    return entry


async def discover(config):
    return await config.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=advertisement(NEW, f"smart-{SERIAL}"),
    )


async def test_home_assistant_zeroconf_matcher_accepts_viega_txt_case(hass, config):
    service = "_modbus._tcp.local."
    info = AsyncServiceInfo(
        service,
        f"smart-{SERIAL}.{service}",
        properties={b"Model": b"Fonterra Smart Control", b"Vendor": b"Viega"},
    )
    matchers = await loader.async_get_zeroconf(hass)
    matcher = next(item for item in matchers[service] if item["domain"] == DOMAIN)
    assert _match_against_props(matcher["properties"], info.decoded_properties)
    assert not _match_against_props(
        matcher["properties"], {**info.decoded_properties, "Vendor": "Other"}
    )


def web_advertisement():
    return replace(
        advertisement(NEW, f"smart-{SERIAL}"),
        port=80,
        type="_http._tcp.local.",
        name=f"smart-{SERIAL}._http._tcp.local.",
    )


async def test_web_only_notice_disappears_on_modbus_advertisement(hass, config):
    web = web_advertisement()
    with (
        patch("homeassistant.components.zeroconf.async_get_async_instance") as zc,
        patch(
            "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
            return_value=AsyncMock(),
        ) as client,
    ):
        zc.return_value.async_get_service_info = AsyncMock(return_value=None)
        client.return_value.connect.side_effect = ModbusClientError("offline")
        result = await config.flow.async_init(DOMAIN, context={"source": SOURCE_ZEROCONF}, data=web)
        assert result["reason"] == "enable_modbus"
        notifications = _async_get_or_create_notifications(hass)
        assert len(notifications) == 1
        record = next(iter(notifications.values()))
        assert NEW in record["message"] and "Modbus TCP" in record["message"]
        assert (await discover(config))["type"] == "form"
        assert not notifications
        client.assert_called_once_with(NEW, 502, timeout=3)
        client.return_value.write_register.assert_not_awaited()
        assert not config.async_entries(DOMAIN)


async def test_web_announcing_known_modbus_unit_only_offers_the_hub(hass, config):
    web = web_advertisement()
    modbus = AsyncServiceInfo(
        "_modbus._tcp.local.",
        f"smart-{SERIAL}._modbus._tcp.local.",
        port=502,
        server=web.hostname,
        properties={b"Model": b"Fonterra Smart Control", b"Vendor": b"Viega"},
        addresses=[IPv4Address(NEW).packed],
    )
    with (
        patch("homeassistant.components.zeroconf.async_get_async_instance") as zc,
        patch("custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient") as client,
    ):
        zc.return_value.async_get_service_info = AsyncMock(return_value=modbus)
        result = await config.flow.async_init(DOMAIN, context={"source": SOURCE_ZEROCONF}, data=web)
        assert result["type"] == "form"
        assert result["data_schema"]({})["host"] == NEW
        assert not _async_get_or_create_notifications(hass)
        client.assert_not_called()


@pytest.mark.parametrize("actual", [SERIAL, "9876543210"])
async def test_web_only_with_working_modbus_requires_matching_wlan_identity(hass, config, actual):
    with (
        patch("homeassistant.components.zeroconf.async_get_async_instance") as zc,
        patch(
            "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
            return_value=AsyncMock(),
        ) as client,
    ):
        zc.return_value.async_get_service_info = AsyncMock(return_value=None)
        client.return_value.read_input_registers.return_value = registers(actual)
        result = await config.flow.async_init(
            DOMAIN, context={"source": SOURCE_ZEROCONF}, data=web_advertisement()
        )
        if actual == SERIAL:
            assert result["type"] == "form"
            assert result["data_schema"]({})["host"] == NEW
            assert result["data_schema"]({})["port"] == 502
        else:
            assert result["reason"] == "identity_unverified"
        client.return_value.read_input_registers.assert_awaited_once_with(1, 5)
        client.return_value.write_register.assert_not_awaited()
        assert not _async_get_or_create_notifications(hass)
        assert not config.async_entries(DOMAIN)


async def test_https_alone_finds_and_remembers_matching_viega_unit(hass, config):
    https = replace(
        web_advertisement(),
        type="_https._tcp.local.",
        port=443,
        name=f"smart-{SERIAL}._https._tcp.local.",
    )
    with (
        patch("homeassistant.components.zeroconf.async_get_async_instance") as zc,
        patch(
            "custom_components.viega_fonterra_modbus.config_flow._probe_serial", return_value=SERIAL
        ),
    ):
        zc.return_value.async_get_service_info = AsyncMock(return_value=None)
        result = await config.flow.async_init(
            DOMAIN, context={"source": SOURCE_ZEROCONF}, data=https
        )
    assert result["type"] == "form"
    assert result["data_schema"]({})["host"] == NEW
    assert await async_get_discovery_store(hass).async_addresses() == {SERIAL: NEW}


async def test_start_restores_both_discovery_suggestions_without_mdns(hass, config):
    hosts = {"1234567890": "192.0.2.200", "0987654321": "192.0.2.201"}
    await Store(hass, 1, STORAGE_KEY, private=True).async_save(hosts)
    serial_by_host = {host: serial for serial, host in hosts.items()}

    async def probe(host, port, timeout):
        assert port == 502 and timeout == 3
        return serial_by_host[host]

    with patch(
        "custom_components.viega_fonterra_modbus.config_flow._probe_serial", side_effect=probe
    ):
        assert await async_setup(hass, {})
        await hass.async_block_till_done(wait_background_tasks=True)

    assert {
        flow["context"]["title_placeholders"]["name"]
        for flow in config.flow.async_progress_by_handler(DOMAIN)
    } == {"Fonterra (192.0.2.200)", "Fonterra (192.0.2.201)"}

    native = advertisement("192.0.2.201", "smart-0987654321")
    await config.flow.async_init(DOMAIN, context={"source": SOURCE_ZEROCONF}, data=native)
    assert len(config.flow.async_progress_by_handler(DOMAIN)) == 2
    assert not config.async_entries(DOMAIN)


async def test_removed_entry_is_offered_without_waiting_for_an_announcement(hass, config):
    entry = make_entry(
        data={"host": NEW, "port": 502}, options={"_identity": {"wlan_serial_number": SERIAL}}
    )
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow._probe_serial", return_value=SERIAL
    ):
        await async_remove_entry(hass, entry)
        await hass.async_block_till_done(wait_background_tasks=True)

    (flow,) = config.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["title_placeholders"]["name"] == f"Fonterra ({NEW})"
    assert await async_get_discovery_store(hass).async_addresses() == {SERIAL: NEW}
    assert not config.async_entries(DOMAIN)


async def test_first_viega_announcement_recovers_other_hubs_without_configured_entries(
    hass, config
):
    await Store(hass, 1, STORAGE_KEY, private=True).async_save({SERIAL: NEW})
    hass.config.components.add("zeroconf")
    fresh_serial = "9876543210"
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow._probe_serial",
        side_effect=lambda host, port, timeout: SERIAL if host == NEW else fresh_serial,
    ):
        result = await config.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_ZEROCONF},
            data=advertisement(OLD, f"smart-{fresh_serial}"),
        )
        await hass.async_block_till_done(wait_background_tasks=True)
    assert result["type"] == "form"
    assert {
        flow["context"]["title_placeholders"]["name"]
        for flow in config.flow.async_progress_by_handler(DOMAIN)
    } == {f"Fonterra ({NEW})", f"Fonterra ({OLD})"}


async def test_restore_retries_unreachable_but_never_offers_a_reused_address(hass, config):
    await Store(hass, 1, STORAGE_KEY, private=True).async_save(
        {SERIAL: NEW, "0987654321": "192.0.2.201"}
    )
    with (
        patch("custom_components.viega_fonterra_modbus.discovery_store._RETRY_DELAY", 0),
        patch(
            "custom_components.viega_fonterra_modbus.config_flow._probe_serial",
            side_effect=[ModbusClientError("starting"), "1111111111", SERIAL],
        ) as probe,
    ):
        await async_restore_discoveries(hass)

    assert [call.args[0] for call in probe.await_args_list] == [NEW, "192.0.2.201", NEW]
    (flow,) = config.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["title_placeholders"]["name"] == f"Fonterra ({NEW})"
    assert not _async_get_or_create_notifications(hass)


async def test_start_finds_new_address_when_remembered_address_is_gone(hass, config):
    await Store(hass, 1, STORAGE_KEY, private=True).async_save({SERIAL: OLD})
    hass.config.components.add("zeroconf")
    service = "_modbus._tcp.local."
    info = AsyncServiceInfo(
        service,
        f"smart-{SERIAL}.{service}",
        port=502,
        server=f"smart-{SERIAL}.local.",
        properties={b"Model": b"Fonterra Smart Control", b"Vendor": b"Viega"},
        addresses=[IPv4Address(NEW).packed],
    )
    with (
        patch("homeassistant.components.zeroconf.async_get_async_instance") as zc,
        patch(
            "custom_components.viega_fonterra_modbus.config_flow._probe_serial",
            side_effect=[ModbusClientError("old address offline"), SERIAL],
        ) as probe,
    ):
        zc.return_value.async_get_service_info = AsyncMock(return_value=info)
        await async_restore_discoveries(hass)

    zc.return_value.async_get_service_info.assert_awaited_once_with(
        service, f"smart-{SERIAL}.{service}", timeout=6000
    )
    assert [call.args[0] for call in probe.await_args_list] == [OLD, NEW]
    (flow,) = config.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["title_placeholders"]["name"] == f"Fonterra ({NEW})"
    assert await async_get_discovery_store(hass).async_addresses() == {SERIAL: NEW}


@pytest.mark.parametrize("matching", [True, False])
async def test_known_unconfigured_dhcp_move_replaces_one_discovery(hass, config, matching):
    initial = await config.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=advertisement(OLD, f"smart-{SERIAL}")
    )
    assert initial["type"] == "form"
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow._probe_serial",
        return_value=SERIAL if matching else "0987654321",
    ) as probe:
        result = await config.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_DHCP},
            data=DhcpServiceInfo(NEW, f"smart-{SERIAL}", "0123456789ab"),
        )

    probe.assert_awaited_once_with(NEW, 502, timeout=3)
    (flow,) = config.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["title_placeholders"]["name"] == f"Fonterra ({NEW if matching else OLD})"
    assert result["type"] == ("form" if matching else "abort")


async def test_dhcp_does_not_query_unknown_smart_device(hass, config):
    with patch("custom_components.viega_fonterra_modbus.config_flow._probe_serial") as probe:
        result = await config.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_DHCP},
            data=DhcpServiceInfo(NEW, f"smart-{SERIAL}", "0123456789ab"),
        )
    assert result["reason"] == "invalid_discovery"
    probe.assert_not_called()


def clients(*, old_live=False, response=None):
    previous = AsyncMock()
    if not old_live:
        previous.connect.side_effect = ModbusClientError("offline")
    candidate = AsyncMock()
    candidate.read_input_registers.return_value = (
        registers(SERIAL) if response is None else response
    )
    return previous, candidate


async def test_configured_hub_moves_on_verified_dhcp_update(config):
    entry = await add_entry(config)
    previous, candidate = clients()
    with (
        patch(
            "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
            side_effect=[previous, candidate],
        ),
        patch.object(config, "async_schedule_reload"),
    ):
        result = await config.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_DHCP},
            data=DhcpServiceInfo(NEW, f"smart-{SERIAL}", "0123456789ab"),
        )
    assert result["reason"] == "address_updated"
    assert config.async_get_entry(ENTRY_ID) is entry
    assert entry.data["host"] == NEW


@pytest.mark.parametrize("loaded", [False, True])
async def test_verified_move_preserves_config_device_entities_and_options(hass, config, loaded):
    entry = await add_entry(config, loaded=loaded)
    options = entry.options
    if loaded:
        entry.add_update_listener(async_reload_entry)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)}, name="Reserve"
    )
    entity = er.async_get(hass).async_get_or_create(
        "climate",
        DOMAIN,
        f"{entry.entry_id}_room_3_thermostat",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="reserve_bathroom",
    )
    previous, candidate = clients()
    with (
        patch.object(config, "async_reload", AsyncMock()) as reload_entry,
        patch(
            "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
            side_effect=[previous, candidate],
        ),
    ):
        assert (await discover(config))["reason"] == "address_updated"
        await hass.async_block_till_done()
        reload_entry.assert_awaited_once_with(entry.entry_id)

    assert config.async_entries(DOMAIN) == [entry]
    assert entry.unique_id == f"wlan:{SERIAL}"
    assert config.async_entry_for_domain_unique_id(DOMAIN, f"{OLD}:502") is None
    assert entry.data == {"host": NEW, "port": 502, "polling_interval": 30}
    assert entry.options is options
    assert dr.async_get(hass).async_get(device.id) is device
    assert er.async_get(hass).async_get(entity.entity_id) is entity
    candidate.read_input_registers.assert_awaited_once_with(1, 5)
    for client in (previous, candidate):
        client.disconnect.assert_awaited_once()
        client.write_register.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [registers("9876543210"), [-99] * 5, [0] * 5, [123], ModbusClientError("read error")],
)
async def test_invalid_or_unreadable_serial_never_moves_entry(config, response):
    entry = await add_entry(config)
    previous, candidate = clients()
    if isinstance(response, Exception):
        candidate.read_input_registers.side_effect = response
    else:
        candidate.read_input_registers.return_value = response
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
        side_effect=[previous, candidate],
    ):
        assert (await discover(config))["reason"] == "identity_unverified"
    assert entry.data["host"] == OLD


@pytest.mark.parametrize("reason", ["legacy", "occupied", "old_reachable", "old_unreadable"])
async def test_discovery_does_not_take_over_unverified_or_active_entries(config, reason):
    entry = await add_entry(config, identity=reason != "legacy")
    if reason == "occupied":
        await add_entry(config, host=NEW, identity=False, entry_id="second")
    previous, _ = clients(old_live=True)
    if reason == "old_unreadable":
        previous.read_input_registers.side_effect = ModbusClientError("read error")
    else:
        previous.read_input_registers.return_value = registers(SERIAL)
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
        return_value=previous,
    ) as factory:
        result = await discover(config)
    if reason == "legacy":
        assert result["type"] == "form"
        factory.assert_not_called()
    elif reason == "occupied":
        assert result["reason"] == "already_configured"
        factory.assert_not_called()
    else:
        assert result["reason"] == "current_address_available"
        factory.assert_called_once_with(OLD, 502, timeout=5.0)
    assert entry.data["host"] == OLD


async def test_valid_other_serial_on_old_ip_allows_verified_move(config):
    entry = await add_entry(config)
    previous, candidate = clients(old_live=True)
    previous.read_input_registers.return_value = registers("9876543210")
    with (
        patch.object(config, "async_reload", AsyncMock()),
        patch(
            "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
            side_effect=[previous, candidate],
        ),
    ):
        assert (await discover(config))["reason"] == "address_updated"
    assert entry.data["host"] == NEW


async def test_concurrent_reconfigure_wins_over_discovery(config):
    entry = await add_entry(config)
    previous, candidate = clients()

    async def read(*args):
        config.async_update_entry(entry, data={**entry.data, "host": "192.0.2.99"})
        return registers(SERIAL)

    candidate.read_input_registers.side_effect = read
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient",
        side_effect=[previous, candidate],
    ):
        assert (await discover(config))["reason"] == "already_configured"
    assert entry.data["host"] == "192.0.2.99"
