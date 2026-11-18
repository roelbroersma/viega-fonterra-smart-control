from datetime import timedelta

import pytest
from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.viega_fonterra_modbus.connect.source import measurement


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        ("19.7", "°C", 19.7),
        ("68", "°F", 20.0),
        ("293.15", "K", 20.0),
        ("5", "°C", 5.0),
        ("40", "°C", 40.0),
        ("19.65", "°C", 19.7),
    ],
)
def test_real_temperature_conversion(value, unit, expected):
    now = dt_util.utcnow()
    state = State("sensor.room", value, {"unit_of_measurement": unit}, last_reported=now)
    assert measurement(state, now, 900, now - timedelta(seconds=1)) == expected


@pytest.mark.parametrize(
    "value,attrs",
    [
        ("unknown", {"unit_of_measurement": "°C"}),
        ("unavailable", {"unit_of_measurement": "°C"}),
        ("20", {"unit_of_measurement": "°C", "restored": True}),
        ("nan", {"unit_of_measurement": "°C"}),
        ("inf", {"unit_of_measurement": "°C"}),
        ("-99", {"unit_of_measurement": "°C"}),
        ("6543.7", {"unit_of_measurement": "°C"}),
        ("4.9", {"unit_of_measurement": "°C"}),
        ("40.1", {"unit_of_measurement": "°C"}),
        ("20", {}),
        ("20", {"unit_of_measurement": "%"}),
    ],
)
def test_rejects_invalid_or_restored(value, attrs):
    now = dt_util.utcnow()
    assert (
        measurement(
            State("sensor.room", value, attrs, last_reported=now),
            now,
            900,
            now - timedelta(seconds=1),
        )
        is None
    )


async def test_identical_report_refreshes_last_reported_not_last_changed(hass):
    now = dt_util.utcnow()
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    first = hass.states.get("sensor.room")
    first_reported = first.last_reported
    hass.states.async_set("sensor.room", "19.7", {"unit_of_measurement": "°C"})
    second = hass.states.get("sensor.room")
    assert second.last_changed == first.last_changed
    assert second.last_reported > first_reported
    assert measurement(second, dt_util.utcnow(), 900, now) == 19.7
    assert measurement(second, second.last_reported + timedelta(seconds=901), 900, now) is None


def test_restart_requires_a_new_real_report():
    now = dt_util.utcnow()
    state = State(
        "sensor.room", "20", {"unit_of_measurement": "°C"}, last_reported=now - timedelta(seconds=1)
    )
    assert measurement(state, now, 900, now) is None
    assert measurement(None, now, 900, now) is None


def test_future_report_is_not_valid():
    now = dt_util.utcnow()
    state = State(
        "sensor.room", "20", {"unit_of_measurement": "°C"}, last_reported=now + timedelta(seconds=1)
    )
    assert measurement(state, now, 900, now) is None
