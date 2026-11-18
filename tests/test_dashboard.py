"""Check that an already-running Home Assistant can load the bundled module."""

from aiohttp import ClientSession
from homeassistant.components import frontend
from homeassistant.components.http.cors import setup_cors
from homeassistant.components.http.server import HomeAssistantHTTP
from homeassistant.util.ssl import SSLProfile

from custom_components.viega_fonterra_modbus.dashboard import CARD_URL, async_register_dashboard


async def test_card_is_registered_with_the_running_frontend(hass):
    hass.config.components.add(frontend.DOMAIN)
    hass.data[frontend.DATA_EXTRA_MODULE_URL] = frontend.UrlManager(lambda *_: None, [])
    hass.http = HomeAssistantHTTP(
        hass, None, None, None, ["127.0.0.1"], 0, [], SSLProfile.MODERN_V4
    )
    setup_cors(hass.http.app, [])
    await hass.http.async_bind()
    await hass.http.start()
    try:
        await async_register_dashboard(hass)
        path = f"{CARD_URL}/fonterra-card.js"
        assert hass.data[frontend.DATA_EXTRA_MODULE_URL].urls == {path}
        port = hass.http._server.sockets[0].getsockname()[1]
        async with ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}{path}") as response:
                assert response.status == 200
                assert "customElements.define(TYPE, FonterraCard)" in await response.text()
            async with session.get(
                f"http://127.0.0.1:{port}{CARD_URL}/fonterra-card.css"
            ) as response:
                assert response.status == 200
                assert response.content_type == "text/css"
    finally:
        await hass.http.stop()
