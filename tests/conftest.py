"""Use real HA State/StateMachine/ConfigEntry/Coordinator APIs, mocked I/O."""

from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.viega_fonterra_modbus.connect.const import (
    CONF_CONNECT,
    CONF_SERIAL,
    CONF_UPSTREAM,
    DOMAIN,
    UPSTREAM_DOMAIN,
)


def make_entry(
    *,
    domain=DOMAIN,
    entry_id="connect",
    data=None,
    options=None,
    unique_id="TEST000001",
    state=ConfigEntryState.NOT_LOADED,
):
    return ConfigEntry(
        domain=domain,
        entry_id=entry_id,
        version=1,
        minor_version=1,
        title="Test Fonterra",
        data=data or {CONF_CONNECT: True, CONF_SERIAL: unique_id, CONF_UPSTREAM: "modbus"},
        options=options or {},
        source="user",
        unique_id=unique_id,
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
        state=state,
    )


@pytest.fixture
async def hass(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    yield hass
    await hass.async_block_till_done()


@pytest.fixture
def upstream_entry():
    return make_entry(
        domain=UPSTREAM_DOMAIN, entry_id="modbus", data={"host": "fonterra.example", "port": 502}
    )


@pytest.fixture
def entry():
    return make_entry(options={"sources": {"1": {"entity_id": "sensor.room", "max_age": 900}}})
