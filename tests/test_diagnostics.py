from homeassistant.components.diagnostics.const import REDACTED

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_host_and_serial_numbers(hass, entry):
    identity = {
        "wlan_serial_number": "WLAN000001",
        "base_unit_serial_number": "BASE000001",
    }
    hass.data[DOMAIN] = {
        entry.entry_id: {
            "host": "smart-wlan000001.local",
            "port": 502,
            "identity": identity,
        },
    }

    report = await async_get_config_entry_diagnostics(hass, entry)

    assert report["unit"]["host"] == REDACTED
    assert report["unit"]["wlan_module_serial_number"] == REDACTED
    assert report["unit"]["base_unit_serial_number"] == REDACTED
    assert report["unit"]["port"] == 502
    assert identity["wlan_serial_number"] == "WLAN000001"
    assert identity["base_unit_serial_number"] == "BASE000001"
