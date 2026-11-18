"""Serve the bundled card when Home Assistant's frontend is enabled."""

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

CARD_URL = f"/{DOMAIN}/card"
ROOT = Path(__file__).parent


async def async_register_dashboard(hass: HomeAssistant) -> None:
    """Register the card alongside Home Assistant's own dashboard resources."""
    if frontend.DOMAIN not in hass.config.components or hass.http is None:
        return

    # Serve only card assets and the logo. Dashboard state and actions use
    # Home Assistant's own connection and its usual entity permissions.
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(CARD_URL, str(ROOT / "card"), cache_headers=False),
            StaticPathConfig(f"/{DOMAIN}/brand/icon.png", str(ROOT / "brand" / "icon.png")),
        ]
    )
    frontend.add_extra_js_url(hass, f"{CARD_URL}/fonterra-card.js")
