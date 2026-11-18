"""Look up an already identified Fonterra through Home Assistant's mDNS."""

from time import monotonic
from typing import Any

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DEFAULT_PORT, DOMAIN
from .identity import saved_wlan_serial

MODBUS_SERVICE = "_modbus._tcp.local."


def is_viega_service(properties: dict[str, Any]) -> bool:
    props = {str(key).casefold(): str(value).casefold() for key, value in properties.items()}
    return props.get("vendor") == "viega" and props.get("model") == "fonterra smart control"


async def async_find_new_address(hass: HomeAssistant, serial: str, previous: str) -> bool:
    """Query the exact service instance and verify any new address in the config flow."""
    if "zeroconf" not in hass.config.components:
        return False

    from homeassistant.components.zeroconf import async_get_async_instance
    from zeroconf import IPVersion

    label = f"smart-{serial.casefold()}"
    instance = await async_get_async_instance(hass)
    try:
        info = await instance.async_get_service_info(
            MODBUS_SERVICE, f"{label}.{MODBUS_SERVICE}", timeout=6000
        )
    except OSError:
        return False
    if (
        info is None
        or info.port != DEFAULT_PORT
        or (info.server or "").rstrip(".").casefold() != f"{label}.local"
        or not is_viega_service(info.decoded_properties)
    ):
        return False

    for address in info.ip_addresses_by_version(IPVersion.All):
        host = str(address)
        if host == previous or (
            address.is_unspecified
            or address.is_link_local
            or address.is_loopback
            or address.is_multicast
        ):
            continue
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_INTEGRATION_DISCOVERY}, data=(serial.casefold(), host)
        )
        if result["type"] == "form" or result.get("reason") == "address_updated":
            return True
    return False


@callback
def async_lookup_if_disconnected(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Limit traffic for configured hubs that temporarily cannot be reached."""
    if (
        "zeroconf" not in hass.config.components
        or entry.disabled_by
        or entry.data.get("port") != DEFAULT_PORT
        or (serial := saved_wlan_serial(entry.options)) is None
    ):
        return
    deadlines = hass.data.setdefault(f"{DOMAIN}_address_lookup", {})
    now = monotonic()
    if deadlines.get(entry.entry_id, 0) > now:
        return
    deadlines[entry.entry_id] = now + 60
    hass.async_create_background_task(
        async_find_new_address(hass, serial, entry.data["host"]), "Find Fonterra at its new address"
    )
