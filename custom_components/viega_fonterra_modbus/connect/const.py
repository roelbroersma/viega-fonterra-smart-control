"""Settings and register for external temperature input."""

CONF_CONNECT = "connect_upgrade"
CONF_MAPPINGS = "sources"
CONF_MAX_AGE = "max_age"
DEFAULT_MAX_AGE = 900
POLL_SECONDS = 30
REFRESH_SECONDS = 60
EXTERNAL_TEMPERATURE_REGISTER = 100


def temperature_input_id(entry_id: str, room: int) -> str:
    """Identify the input by the Fonterra room ID, independent of its name."""
    return f"{entry_id}_room_{room}_external_temperature"
