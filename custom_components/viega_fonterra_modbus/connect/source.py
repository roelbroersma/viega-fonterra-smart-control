"""Validate a source at the moment of transmission, using HA report time."""

from __future__ import annotations

import math
from datetime import datetime

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import State
from homeassistant.util.unit_conversion import TemperatureConverter


def measurement(
    state: State | None, now: datetime, max_age: int, started: datetime
) -> float | None:
    """An identical re-report is fresh; a cached/restored value isn't a report."""
    if (
        state is None
        or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        or state.attributes.get("restored")
    ):
        return None
    age = (now - state.last_reported).total_seconds()
    # Equal reports renew last_reported while last_changed stays the same.
    # After a restart, an old state must not start a new stream of writes.
    if age < 0 or age > max_age or state.last_reported < started:
        return None
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit not in (
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.FAHRENHEIT,
        UnitOfTemperature.KELVIN,
    ):
        return None
    try:
        value = TemperatureConverter.convert(float(state.state), unit, UnitOfTemperature.CELSIUS)
    except ValueError, TypeError:
        return None
    if not math.isfinite(value) or not 5 <= value <= 40:
        return None
    # Firmware rounds positive measurements to tenths, half up.
    return math.floor(value * 10 + 0.5) / 10
