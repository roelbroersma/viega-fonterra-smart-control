from pathlib import Path
from shutil import copyfile, copytree

from homeassistant import loader
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.translation import async_get_translations

from custom_components.viega_fonterra_modbus.binary_sensor import build_room_entities
from custom_components.viega_fonterra_modbus.const import DOMAIN


async def test_actor_positions_have_numbered_binary_sensor_translations(hass, tmp_path):
    component = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN
    target = tmp_path / "custom_components" / DOMAIN
    target.mkdir(parents=True)
    copyfile(component / "manifest.json", target / "manifest.json")
    copytree(component / "translations", target / "translations")
    loader.async_setup(hass)

    translations = await async_get_translations(hass, "nl", "entity", {DOMAIN})
    positions = build_room_entities("test", "room_1", {"name": "Badkamer", "actor": [1, 2]})

    assert [actor.unique_id for actor in positions] == [
        "test_room_1_actor1_position",
        "test_room_1_actor2_position",
    ]
    prefix = f"component.{DOMAIN}.entity.binary_sensor"
    assert [
        translations[f"{prefix}.{actor.translation_key}.name"].format(
            **actor.translation_placeholders
        )
        for actor in positions
    ] == ["Actor 1", "Actor 2"]
    assert all(actor.device_class == BinarySensorDeviceClass.OPENING for actor in positions)
    assert translations[f"{prefix}.circulation_pump.name"] == "Circulatiepomp"
