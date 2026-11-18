"""Config flow for the Viega Fonterra Modbus integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import monotonic
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.translation import async_get_translations

from .address_discovery import MODBUS_SERVICE, is_viega_service
from .connect.const import CONF_CONNECT, CONF_MAPPINGS, CONF_MAX_AGE, DEFAULT_MAX_AGE
from .connect.modbus import ModbusError, SharedModbus
from .connect.runtime import CONF_PIN
from .const import (
    CONF_DEVICE_NAME,
    CONF_MODBUS_TIMEOUT,
    CONF_POLLING_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_MODBUS_TIMEOUT,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
)
from .discovery_store import (
    async_get_discovery_store,
    async_schedule_discoveries,
    discovery_serial,
)
from .identity import read_wlan_serial, saved_wlan_serial
from .modbus_handler import ModbusClientError, ViegaModbusClient
from .registers import actor_registers, room_actor_numbers

_LOGGER = logging.getLogger(__name__)
_WEB_SERVICES = {"_http._tcp.local.", "_https._tcp.local."}
_ADVERTISEMENTS = f"{DOMAIN}_modbus_advertisements"
_NOTICE_TIMEOUT = 120


def _normalize_host(host: str) -> str:
    return host.rstrip(".").casefold()


def _notification_id(hostname: str) -> str:
    return f"{DOMAIN}_enable_modbus_{hostname}"


def _address_in_use(
    hass: HomeAssistant, addresses: set[str], port: int, except_entry: str | None = None
) -> bool:
    return any(
        entry.entry_id != except_entry
        and entry.source != config_entries.SOURCE_IGNORE
        and _normalize_host(str(entry.data.get(CONF_HOST, ""))) in addresses
        and entry.data.get(CONF_PORT, DEFAULT_PORT) == port
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


async def _probe_serial(host: str, port: int, timeout: float) -> str:
    client = ViegaModbusClient(host, port, timeout=timeout)
    try:
        await client.connect()
        return await read_wlan_serial(client)
    finally:
        await client.disconnect()


def _update_entry_data(hass: HomeAssistant, entry: config_entries.ConfigEntry, **kwargs) -> None:
    """Use the update listener when loaded and schedule a reload if offline."""
    if hass.config_entries.async_update_entry(entry, **kwargs) and not entry.update_listeners:
        hass.config_entries.async_schedule_reload(entry.entry_id)


class ViegaFonterraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Viega Fonterra."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for an existing module.

        `config_entry` is unused: the base `OptionsFlow` class resolves it
        itself from the flow's `handler` (see `ViegaFonterraOptionsFlow`).
        """
        return ViegaFonterraOptionsFlow()

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._device_config: dict[str, object] = {}
        self._discovery_defaults: dict[str, object] = {}

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo):
        """Offer the discovered unit with a prefilled connection form."""
        if not is_viega_service(discovery_info.properties):
            return self.async_abort(reason="invalid_discovery")
        if "zeroconf" in self.hass.config.components:
            async_schedule_discoveries(self.hass)
        if discovery_info.type in _WEB_SERVICES:
            return await self._async_step_web_discovery(discovery_info)
        if discovery_info.type != MODBUS_SERVICE or discovery_info.port != DEFAULT_PORT:
            return self.async_abort(reason="invalid_discovery")

        return await self._async_step_modbus_discovery(discovery_info)

    async def async_step_integration_discovery(self, data: tuple[str, str]):
        """Verify a remembered or actively resolved address."""
        serial, host = data
        return await self._async_discovery_endpoint(host, {host}, serial, verify=True)

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo):
        """Use DHCP address changes only for already identified Fonterra units."""
        hostname = discovery_info.hostname.partition(".")[0]
        serial = discovery_serial(f"{hostname}.local")
        if serial is None:
            return self.async_abort(reason="invalid_discovery")
        known = await async_get_discovery_store(self.hass).async_addresses()
        if serial not in known and not any(
            (saved_wlan_serial(entry.options) or "").casefold() == serial
            for entry in self._async_current_entries(include_ignore=False)
        ):
            return self.async_abort(reason="invalid_discovery")
        return await self.async_step_integration_discovery((serial, discovery_info.ip))

    async def _async_step_web_discovery(self, web: ZeroconfServiceInfo):
        """Ask for the matching DNS-SD record before showing an activation notice."""
        from homeassistant.components.zeroconf import async_get_async_instance, info_from_service

        hostname = _normalize_host(web.hostname)
        if (serial := discovery_serial(hostname)) is None:
            return self.async_abort(reason="invalid_discovery")
        label = f"smart-{serial}"
        # The existing Viega firmware uses the same instance label for its
        # HTTP and Modbus services. Prefer the existing DNS-SD record.
        web_addresses = set(web.addresses) | {web.host}
        if self._recent_modbus_advertisement(hostname, web_addresses):
            return self.async_abort(reason="modbus_advertised")
        zeroconf = await async_get_async_instance(self.hass)
        try:
            info = await zeroconf.async_get_service_info(
                MODBUS_SERVICE, f"{label}.{MODBUS_SERVICE}", timeout=6000
            )
        except OSError:
            info = None
        candidate = info_from_service(info) if info is not None else None
        if (
            candidate is not None
            and candidate.port == DEFAULT_PORT
            and is_viega_service(candidate.properties)
            and _normalize_host(candidate.hostname) == hostname
            and (
                matching_address := next(
                    (
                        address
                        for address in candidate.ip_addresses
                        if str(address) in web_addresses
                        and not address.is_link_local
                        and not address.is_unspecified
                    ),
                    None,
                )
            )
            is not None
        ):
            # This record can supply more than one address. Keep the one
            # which matched the web discovery event for this unit.
            candidate.ip_address = matching_address
            return await self._async_step_modbus_discovery(candidate)

        if self._recent_modbus_advertisement(hostname, web_addresses):
            return self.async_abort(reason="modbus_advertised")
        # Some units serve Modbus without advertising it. Use the same
        # documented read-only identity register as address relocation.
        try:
            actual = await _probe_serial(web.host, DEFAULT_PORT, timeout=3)
        except ModbusClientError:
            pass
        else:
            if actual.casefold() != serial:
                return self.async_abort(reason="identity_unverified")
            return await self._async_step_modbus_discovery(web, verified=True)

        strings = await async_get_translations(
            self.hass, self.hass.config.language, "issues", {DOMAIN}
        )
        # A real Modbus event may have arrived while resolving or translating.
        if self._recent_modbus_advertisement(hostname, web_addresses):
            return self.async_abort(reason="modbus_advertised")
        prefix = f"component.{DOMAIN}.issues.enable_modbus"
        title = strings.get(f"{prefix}.title", "Fonterra: enable Modbus TCP")
        message = strings.get(
            f"{prefix}.description",
            "Fonterra at **{host}** announced its web interface. "
            "Modbus did not respond. Check **Modbus TCP** in the Fonterra settings.",
        )
        persistent_notification.async_create(
            self.hass,
            message.format(host=web.host),
            title=title,
            notification_id=_notification_id(hostname),
        )
        return self.async_abort(reason="enable_modbus")

    def _recent_modbus_advertisement(self, hostname: str, addresses: set[str]) -> bool:
        seen = self.hass.data.get(_ADVERTISEMENTS, {}).get(hostname)
        if seen and monotonic() - seen[0] < _NOTICE_TIMEOUT and addresses & seen[1]:
            return True
        return any(
            (host := str(entry.data.get(CONF_HOST))) in addresses
            and self._recent_connection(entry, host)
            for entry in self._async_current_entries(include_ignore=False)
        )

    async def _async_step_modbus_discovery(
        self, discovery_info: ZeroconfServiceInfo, *, verified: bool = False
    ):
        hostname = _normalize_host(discovery_info.hostname)
        ips = set(discovery_info.addresses) | {discovery_info.host}
        self.hass.data.setdefault(_ADVERTISEMENTS, {})[hostname] = (monotonic(), ips)
        persistent_notification.async_dismiss(self.hass, _notification_id(hostname))
        addresses = {hostname, *discovery_info.addresses, discovery_info.host}
        return await self._async_discovery_endpoint(
            discovery_info.host, addresses, discovery_serial(hostname), verified=verified
        )

    async def _async_discovery_endpoint(
        self,
        host: str,
        addresses: set[str],
        serial: str | None,
        *,
        verify: bool = False,
        verified: bool = False,
    ):
        if serial is not None:
            addresses.add(f"smart-{serial}.local")
        if _address_in_use(self.hass, addresses, DEFAULT_PORT):
            return self.async_abort(reason="already_configured")
        if serial is None:
            return await self._async_offer_discovery(host, None)

        matches = []
        for entry in self._async_current_entries(include_ignore=False):
            saved_serial = saved_wlan_serial(entry.options)
            if saved_serial and saved_serial.casefold() == serial:
                matches.append((entry, saved_serial))
        if len(matches) > 1:
            return self.async_abort(reason="identity_unverified")
        if matches:
            entry, saved_serial = matches[0]
            return await self._async_move_existing(entry, saved_serial, host, addresses)

        store = async_get_discovery_store(self.hass)
        remembered = (await store.async_addresses()).get(serial)
        if not verified and (verify or (remembered is not None and remembered != host)):
            try:
                actual = await _probe_serial(host, DEFAULT_PORT, timeout=3)
            except ModbusClientError:
                return self.async_abort(reason="cannot_connect")
            if actual.casefold() != serial:
                return self.async_abort(reason="identity_unverified")
        await store.async_remember(serial, host)
        persistent_notification.async_dismiss(self.hass, _notification_id(f"smart-{serial}.local"))
        return await self._async_offer_discovery(host, serial)

    async def _async_offer_discovery(self, host: str, serial: str | None):
        await self.async_set_unique_id(f"{host}:{DEFAULT_PORT}")
        self._abort_if_unique_id_configured()
        if serial is not None:
            for flow in self._async_in_progress(match_context={"fonterra_serial": serial}):
                if flow["flow_id"] != self.flow_id and flow["context"].get("fonterra_host") != host:
                    self.hass.config_entries.flow.async_abort(flow["flow_id"])
            self.context.update(fonterra_serial=serial, fonterra_host=host)
        self.context["title_placeholders"] = {"name": f"Fonterra ({host})"}
        self._discovery_defaults = {
            CONF_HOST: host,
            CONF_PORT: DEFAULT_PORT,
            CONF_DEVICE_NAME: f"Fonterra ({host})",
        }
        return await self.async_step_user()

    async def _async_move_existing(self, entry, serial, host, addresses):
        """Update the same entry after verifying its new endpoint."""
        if entry.disabled_by or entry.data.get(CONF_PORT) != DEFAULT_PORT:
            return self.async_abort(reason="identity_unverified")
        old_data = entry.data
        old_host = old_data[CONF_HOST]
        timeout = float(old_data.get(CONF_MODBUS_TIMEOUT, DEFAULT_MODBUS_TIMEOUT))
        # An open port with an unreadable identity is inconclusive. A valid
        # different serial means this old address now belongs to another hub.
        old_address_reused = False
        old_client = ViegaModbusClient(old_host, DEFAULT_PORT, timeout=timeout)
        try:
            await old_client.connect()
        except ModbusClientError:
            if self._recent_connection(entry, old_host):
                return self.async_abort(reason="current_address_available")
        else:
            try:
                previous_serial = await read_wlan_serial(old_client)
            except ModbusClientError:
                return self.async_abort(reason="current_address_available")
            if previous_serial == serial:
                return self.async_abort(reason="current_address_available")
            old_address_reused = True
        finally:
            await old_client.disconnect()

        if _address_in_use(self.hass, addresses, DEFAULT_PORT, entry.entry_id):
            return self.async_abort(reason="already_configured")
        try:
            actual = await _probe_serial(host, DEFAULT_PORT, timeout)
        except ModbusClientError:
            return self.async_abort(reason="identity_unverified")
        if actual != serial:
            return self.async_abort(reason="identity_unverified")

        # The probes yield to HA. Recheck occupancy, identity and connection
        # state before committing, with no await between checks and update.
        unique_id = f"wlan:{serial.casefold()}"
        owner = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)
        if (
            self.hass.config_entries.async_get_entry(entry.entry_id) is not entry
            or entry.data is not old_data
            or entry.disabled_by
            or saved_wlan_serial(entry.options) != serial
            or not entry.state.recoverable
            or (owner is not None and owner is not entry)
            or _address_in_use(self.hass, addresses, DEFAULT_PORT, entry.entry_id)
        ):
            return self.async_abort(reason="already_configured")
        if not old_address_reused and self._recent_connection(entry, old_host):
            return self.async_abort(reason="current_address_available")

        _update_entry_data(
            self.hass, entry, data={**old_data, CONF_HOST: host}, unique_id=unique_id
        )
        _LOGGER.info("Updated the Fonterra Modbus address after WLAN serial verification")
        return self.async_abort(reason="address_updated")

    def _recent_connection(self, entry: config_entries.ConfigEntry, host: str) -> bool:
        runtime = self.hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        client = runtime.get("client")
        if client is None or runtime.get("host") != host:
            return False
        success = client.last_success_time
        failure = client.last_failure_time
        return (
            success is not None
            and (failure is None or success >= failure)
            and (datetime.now(UTC) - success).total_seconds()
            <= float(entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)) * 2
        )

    async def async_step_user(self, user_input: dict[str, object] | None = None):
        """Configure a connection; the room topology comes from the device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate connection to the device
            host = user_input.get(CONF_HOST)
            port = user_input.get(CONF_PORT)
            timeout = user_input.get(CONF_MODBUS_TIMEOUT)

            # Validate host
            if not host or not isinstance(host, str):
                errors[CONF_HOST] = "invalid_host"
            else:
                host = host.strip()
                if not host:
                    errors[CONF_HOST] = "invalid_host"

            # Validate port
            if port is None:
                errors[CONF_PORT] = "required"
            else:
                try:
                    port = int(port)
                    if port < 1 or port > 65535:
                        errors[CONF_PORT] = "invalid_port"
                except ValueError, TypeError:
                    errors[CONF_PORT] = "invalid_port"

            # Validate timeout
            if timeout is None:
                errors[CONF_MODBUS_TIMEOUT] = "required"
            else:
                try:
                    timeout = float(timeout)
                    if timeout < 1 or timeout > 30:
                        errors[CONF_MODBUS_TIMEOUT] = "invalid_timeout"
                except ValueError, TypeError:
                    errors[CONF_MODBUS_TIMEOUT] = "invalid_timeout"

            if not errors:
                unique_id = f"{host}:{port}"
                if self.unique_id != unique_id:
                    await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                if _address_in_use(self.hass, {_normalize_host(host)}, port):
                    return self.async_abort(reason="already_configured")

                try:
                    client = ViegaModbusClient(host, port, timeout=timeout)
                    await client.connect()
                    await client.disconnect()
                except Exception as err:
                    _LOGGER.error("Failed to connect to device: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    if _address_in_use(self.hass, {_normalize_host(host)}, port):
                        return self.async_abort(reason="already_configured")
                    self._device_config = {
                        CONF_CONNECT: bool(user_input.get(CONF_CONNECT, False)),
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_DEVICE_NAME: str(user_input.get(CONF_DEVICE_NAME, "Fonterra")),
                        CONF_POLLING_INTERVAL: int(
                            user_input.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)
                        ),
                        CONF_MODBUS_TIMEOUT: timeout,
                    }
                    return await self.async_step_finalize()

        return self._show_user_form(user_input, errors)

    def _show_user_form(
        self,
        user_input: dict[str, object] | None,
        errors: dict[str, str],
    ) -> config_entries.FlowResult:
        """Show the single-step module setup form."""
        defaults = user_input if user_input is not None else self._discovery_defaults
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CONNECT, default=defaults.get(CONF_CONNECT, False)): bool,
                    vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)): str,
                    vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Required(
                        CONF_DEVICE_NAME,
                        default=defaults.get(CONF_DEVICE_NAME, "Fonterra"),
                    ): str,
                    vol.Optional(
                        CONF_POLLING_INTERVAL,
                        default=defaults.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                    vol.Optional(
                        CONF_MODBUS_TIMEOUT,
                        default=defaults.get(CONF_MODBUS_TIMEOUT, DEFAULT_MODBUS_TIMEOUT),
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
                }
            ),
            errors=errors,
        )

    async def async_step_finalize(
        self, user_input: dict[str, object] | None = None
    ) -> config_entries.FlowResult:
        """Finalize and create the config entry."""
        device_id = f"fonterra_{self._device_config.get(CONF_HOST, 'unknown')}"

        return self.async_create_entry(
            title=str(self._device_config.get(CONF_DEVICE_NAME, "Fonterra")),
            data=self._device_config,
            options={
                "rooms": {},
                "device_id": device_id,
            },
        )


class ViegaFonterraOptionsFlow(config_entries.OptionsFlow):
    """Edit the connection and optionally link an external room sensor."""

    def _rooms(self) -> dict[int, dict]:
        try:
            return SharedModbus(self.hass, self.config_entry.entry_id).rooms()
        except ModbusError:
            return {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        entry = self.config_entry
        current_data, current_options = entry.data, entry.options
        enabled = current_options.get(CONF_CONNECT, current_data.get(CONF_CONNECT, False))
        rooms = self._rooms()
        schema: dict[vol.Marker, Any] = {
            vol.Required(CONF_HOST, default=current_data.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=current_data.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Required(
                CONF_DEVICE_NAME,
                default=current_data.get(CONF_DEVICE_NAME, "Fonterra"),
            ): str,
            vol.Required(
                CONF_POLLING_INTERVAL,
                default=current_data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            vol.Required(
                CONF_MODBUS_TIMEOUT,
                default=current_data.get(CONF_MODBUS_TIMEOUT, DEFAULT_MODBUS_TIMEOUT),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
            vol.Required(CONF_CONNECT, default=enabled): bool,
        }
        if rooms:
            schema[vol.Optional("sensor_room")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": str(room), "label": str(config.get("name", room))}
                        for room, config in sorted(rooms.items())
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        errors: dict[str, str] = {}
        if user_input is not None:
            values = {**user_input}
            activate = values.pop(CONF_CONNECT)
            selected_room = values.pop("sensor_room", None)
            host, port = values[CONF_HOST].strip(), values[CONF_PORT]
            values[CONF_HOST] = host
            values[CONF_DEVICE_NAME] = values[CONF_DEVICE_NAME].strip()
            if not host:
                errors[CONF_HOST] = "invalid_host"
            if not values[CONF_DEVICE_NAME]:
                errors[CONF_DEVICE_NAME] = "required"
            if selected_room and not activate:
                errors["sensor_room"] = "connect_required"
            if selected_room and selected_room not in {str(room) for room in rooms}:
                return self.async_abort(reason="no_rooms")
            if host and _address_in_use(self.hass, {_normalize_host(host)}, port, entry.entry_id):
                errors["base"] = "address_in_use"

            options = {**current_options, CONF_CONNECT: activate}
            data = {**current_data, **values}
            endpoint_changed = (host, port) != (
                current_data.get(CONF_HOST),
                current_data.get(CONF_PORT),
            )
            if not errors and (endpoint_changed or (activate and not enabled)):
                if error := await self._validate_endpoint(data, options):
                    errors["base"] = error
            if not errors:
                self._original = (current_data, current_options)
                if selected_room:
                    # Keep both connection settings and sensor edits pending until Save.
                    self._pending = data, options
                    self._room = int(selected_room)
                    self._room_name = str(rooms[self._room].get("name", self._room))
                    if not self._unchanged():
                        return self.async_abort(reason="settings_changed")
                    return await self.async_step_source()
                return self._save(data, options)

        form = vol.Schema(schema)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(form, user_input),
            errors=errors,
        )

    async def _validate_endpoint(
        self, data: dict[str, Any], options: dict[str, Any], room: dict | None = None
    ) -> str | None:
        # A sensor must be tied to the actual unit at the proposed address.
        expected = options.get(CONF_PIN) or saved_wlan_serial(options)
        client = ViegaModbusClient(
            data[CONF_HOST], data[CONF_PORT], timeout=data[CONF_MODBUS_TIMEOUT]
        )
        try:
            await client.connect()
            if expected or options[CONF_CONNECT]:
                serial = await read_wlan_serial(client)
                if expected and serial != expected:
                    return "identity_unverified"
                if options[CONF_CONNECT]:
                    options[CONF_PIN] = serial
            if room is not None:
                for actor in room_actor_numbers(room):
                    address = actor_registers(actor)["room_id"]
                    if await client.read_input_registers(address, 1) == [self._room]:
                        break
                else:
                    return "room_changed"
        except ModbusClientError, OSError, ValueError:
            return "cannot_connect"
        finally:
            await client.disconnect()
        return None

    def _unchanged(self) -> bool:
        entry = self.config_entry
        return entry.data is self._original[0] and entry.options is self._original[1]

    def _save(self, data, options) -> config_entries.FlowResult:
        if not self._unchanged():
            return self.async_abort(reason="settings_changed")
        entry = self.config_entry
        if _address_in_use(
            self.hass, {_normalize_host(data[CONF_HOST])}, data[CONF_PORT], entry.entry_id
        ):
            return self.async_abort(reason="address_in_use")
        # Update data and options together so the entry reloads with both changes.
        _update_entry_data(
            self.hass, entry, data=data, title=data[CONF_DEVICE_NAME], options=options
        )
        return self.async_create_entry(title="", data=options)

    async def async_step_source(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if not self._unchanged():
            return self.async_abort(reason="settings_changed")
        data, options = self._pending
        mappings = dict(options.get(CONF_MAPPINGS, {}))
        room_key = str(self._room)
        current = mappings.get(room_key, {})
        errors = {}
        if user_input is not None:
            if user_input.get("remove"):
                mappings.pop(room_key, None)
                return self._save(data, {**options, CONF_MAPPINGS: mappings})
            entity_id = user_input.get("entity_id")
            if not user_input.get("external_confirmed"):
                errors["base"] = "external_required"
            elif (
                not entity_id
                or not entity_id.startswith("sensor.")
                or not self.hass.states.get(entity_id)
            ):
                errors["base"] = "invalid_sensor"
            else:
                room = self._rooms().get(self._room)
                if room is None:
                    return self.async_abort(reason="no_rooms")
                if error := await self._validate_endpoint(data, options, room):
                    errors["base"] = error
                else:
                    mappings[room_key] = {
                        "entity_id": entity_id,
                        CONF_MAX_AGE: user_input[CONF_MAX_AGE],
                    }
                    return self._save(data, {**options, CONF_MAPPINGS: mappings})

        schema = vol.Schema(
            {
                vol.Optional(
                    "entity_id", **({"default": current["entity_id"]} if current else {})
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Required(
                    CONF_MAX_AGE, default=current.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)
                ): vol.All(vol.Coerce(int), vol.Range(min=90, max=86400)),
                vol.Required("external_confirmed", default=False): bool,
                **({vol.Required("remove", default=False): bool} if current else {}),
            }
        )
        return self.async_show_form(
            step_id="source",
            description_placeholders={"room": self._room_name},
            errors=errors,
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
        )
