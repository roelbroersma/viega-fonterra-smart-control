"""Recover known Fonterra discovery suggestions after Home Assistant starts."""

import asyncio
import re
from ipaddress import ip_address

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store

from .address_discovery import async_find_new_address
from .const import DOMAIN

STORAGE_KEY = f"{DOMAIN}.discovery"
_RESTORE_STARTED = f"{STORAGE_KEY}.restore_started"
_LIMIT = 32
_RETRY_DELAY = 15
_WLAN_HOSTNAME = re.compile(r"smart-([a-z0-9][a-z0-9-]{0,9})\.local")


def discovery_serial(hostname: str) -> str | None:
    """Extract the WLAN identity from Viega's service hostname."""
    match = _WLAN_HOSTNAME.fullmatch(hostname.rstrip(".").casefold())
    return match[1] if match else None


def _is_usable_address(host: str) -> bool:
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return not (
        address.is_unspecified
        or address.is_loopback
        or address.is_multicast
        or address.is_link_local
    )


class DiscoveryStore:
    """Keep the last advertised address for each recognized Viega identity."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store[dict[str, str]](hass, 1, STORAGE_KEY, private=True)
        self._lock = asyncio.Lock()
        self._addresses: dict[str, str] | None = None

    async def _async_load(self) -> dict[str, str]:
        if self._addresses is None:
            stored = await self._store.async_load()
            self._addresses = {
                serial: host
                for serial, host in (stored or {}).items()
                if discovery_serial(f"smart-{serial}.local") == serial
                and isinstance(host, str)
                and _is_usable_address(host)
            }
        return self._addresses

    async def async_remember(self, serial: str, host: str) -> None:
        """Remember an address advertised by a recognized Viega service."""
        if not _is_usable_address(host):
            return
        async with self._lock:
            addresses = await self._async_load()
            if addresses.get(serial) == host:
                return
            addresses.pop(serial, None)
            addresses[serial] = host
            if len(addresses) > _LIMIT:
                addresses.pop(next(iter(addresses)))
            self._store.async_delay_save(addresses.copy, 2)

    async def async_addresses(self) -> dict[str, str]:
        """Read remembered endpoints before attempting a new identity probe."""
        async with self._lock:
            return (await self._async_load()).copy()


@singleton(STORAGE_KEY)
@callback
def async_get_discovery_store(hass: HomeAssistant) -> DiscoveryStore:
    return DiscoveryStore(hass)


@callback
def async_schedule_discoveries(hass: HomeAssistant) -> None:
    """Start recovery once, even if the first discovery arrives before any entry."""
    if hass.data.get(_RESTORE_STARTED):
        return
    hass.data[_RESTORE_STARTED] = True
    hass.async_create_background_task(async_restore_discoveries(hass), "Find known Fonterra hubs")


async def async_restore_discovery(hass: HomeAssistant, serial: str, host: str) -> bool:
    """Offer one known hub and return whether a temporary failure can be retried."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data=(serial, host),
    )
    reason = result.get("reason")
    if reason in {"cannot_connect", "identity_unverified"}:
        found = await async_find_new_address(hass, serial, host)
        return not found and reason == "cannot_connect"
    return False


async def async_restore_discoveries(hass: HomeAssistant) -> None:
    """Verify remembered hosts over Modbus and offer the matching unconfigured hubs."""
    store = async_get_discovery_store(hass)
    addresses = await store.async_addresses()
    pending = []
    for serial, host in addresses.items():
        if await async_restore_discovery(hass, serial, host):
            pending.append((serial, host))

    if pending:
        await asyncio.sleep(_RETRY_DELAY)
        addresses = await store.async_addresses()
        for serial, host in pending:
            if addresses.get(serial) == host:
                await async_restore_discovery(hass, serial, host)
