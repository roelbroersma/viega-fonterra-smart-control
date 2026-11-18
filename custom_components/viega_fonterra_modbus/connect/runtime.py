"""Optional Connect sender using the integration's existing client and entry."""

import logging

from ..const import DOMAIN
from .const import CONF_CONNECT, CONF_MAPPINGS, CONF_SERIAL, CONF_UPSTREAM
from .coordinator import ConnectCoordinator
from .modbus import SharedModbus

_LOGGER = logging.getLogger(__name__)
LEGACY_DOMAIN = "fonterra_connect"
CONF_PIN = "_connect_wifi_serial"


def legacy_entries(hass, entry):
    return [
        old
        for old in hass.config_entries.async_entries(LEGACY_DOMAIN)
        if old.data.get(CONF_UPSTREAM) == entry.entry_id
    ]


def merged_options(hass, entry):
    """Copy a disabled companion once; keep all ordinary module options."""
    options = dict(entry.options)
    old = legacy_entries(hass, entry)
    if CONF_CONNECT not in options and len(old) == 1 and old[0].disabled_by:
        previous = old[0]
        options.update(
            {
                CONF_CONNECT: previous.options.get(
                    CONF_CONNECT, previous.data.get(CONF_CONNECT, False)
                ),
                CONF_MAPPINGS: dict(previous.options.get(CONF_MAPPINGS, {})),
                CONF_PIN: previous.data[CONF_SERIAL],
            }
        )
    return options


async def async_setup_connect(hass, entry):
    """Connect failure must not take away ordinary climate control."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    runtime["connect"] = None
    enabled = entry.options.get(CONF_CONNECT, entry.data.get(CONF_CONNECT, False))
    if not enabled:
        return
    if any(not old.disabled_by for old in legacy_entries(hass, entry)):
        _LOGGER.warning("Disable the old Connect companion before enabling the merged sender")
        return
    bus = SharedModbus(hass, entry.entry_id, entry.options.get(CONF_PIN))
    coordinator = ConnectCoordinator(hass, entry, bus)
    runtime["connect"] = coordinator
    await coordinator.async_refresh()
    # The sender has no entities of its own. A listener keeps HA's polling
    # interval active until the config entry is unloaded.
    entry.async_on_unload(coordinator.async_add_listener(lambda: None))


async def async_stop_connect(hass, entry):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("connect")
    if coordinator:
        await coordinator.async_shutdown()
