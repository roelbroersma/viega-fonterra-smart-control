"""Optional Connect sender using the integration's existing client and entry."""

from ..const import DOMAIN
from .const import CONF_CONNECT, CONF_MAPPINGS
from .coordinator import ConnectCoordinator
from .modbus import SharedModbus

CONF_PIN = "_connect_wifi_serial"


async def async_setup_connect(hass, entry):
    """Connect failure must not take away ordinary climate control."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    runtime["connect"] = None
    enabled = entry.options.get(CONF_CONNECT, entry.data.get(CONF_CONNECT, False))
    if not enabled:
        return
    bus = SharedModbus(hass, entry.entry_id, entry.options.get(CONF_PIN))
    coordinator = ConnectCoordinator(hass, entry, bus)
    runtime["connect"] = coordinator
    if entry.options.get(CONF_MAPPINGS):
        # Only existing sensor links need periodic updates. Number inputs send on demand.
        await coordinator.async_refresh()
        entry.async_on_unload(coordinator.async_add_listener(lambda: None))


async def async_stop_connect(hass, entry):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("connect")
    if coordinator:
        await coordinator.async_shutdown()
