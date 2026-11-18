import assert from "node:assert/strict";
import { test } from "node:test";
import { dashboard, nextValue } from "../custom_components/viega_fonterra_modbus/card/card-model.js";
import { labels } from "../custom_components/viega_fonterra_modbus/card/card-strings.js";

function data() {
  const entities = {};
  const states = {};
  const put = (id, device, key, state, attributes, extra = {}) => {
    entities[id] = { entity_id: id, platform: "viega_fonterra_modbus", device_id: device, translation_key: key, ...extra };
    states[id] = { entity_id: id, state, attributes };
  };
  put("climate.living", "ground", "room", "heat", {
    room_id: 1, current_temperature: 20.5, temperature: 21, hvac_action: "heating",
    min_temp: 5, max_temp: 30, target_temp_step: 0.5, supported_features: 1,
    actuator_positions: { "1": 1, "2": 0 },
  }, { entity_name: "Woonkamer" });
  put("climate.utility", "upper", "room", "heat", { room_id: 1, supported_features: 0 }, {
    entity_name: "Bijkeuken",
  });
  put("number.ground", "ground", "power_level", "4", { room_id: 1, min: 0, max: 10, step: 1 });
  put("number.upper", "upper", "power_level", "6", { room_id: "room_1", min: 0, max: 10, step: 1 });
  put("sensor.return", "ground", "actuator_return_temperature", "24", { room_id: 1, actor_number: 1 });
  put("sensor.diagnosis", "ground", "room_diagnostic", "no_thermostat", { room_id: 1, error_code: 21 });
  put("sensor.flow", "ground", "flow_temperature", "32", {});
  put("climate.other", "ground", "room", "heat", {}, { platform: "generic_thermostat" });
  put("climate.hidden", "ground", "room", "heat", {}, { hidden: true });
  return { entities, states, devices: { ground: { name: "A" }, upper: { name: "B" } }, connected: true };
}

test("filters rooms and matches controls, sources and actuators to the right divider", () => {
  const result = dashboard(data());
  assert.deepEqual(result.map((module) => module.rooms.map((room) => room.id)), [["climate.living"], ["climate.utility"]]);
  const [[living], [utility]] = result.map((module) => module.rooms);
  assert.equal(living.status, "heating");
  assert.equal(living.control.entity, "climate.living");
  assert.equal(living.power, null);
  assert.equal(living.actors[0].temperature.entity_id, "sensor.return");
  assert.equal(living.actors[1].position, 0);
  assert.equal(living.diagnostic.attributes.error_code, 21);
  assert.equal(result[0].flow.state, "32");
  assert.equal(utility.control.entity, "number.upper");
  assert.equal(utility.power, 6);
  assert.equal(utility.status, "power");
});

test("selects a room, hides controls when unavailable and clamps steps", () => {
  const hass = data();
  const [module] = dashboard(hass, "climate.living");
  const [{ control }] = module.rooms;
  assert.equal(nextValue(control, 1), 21.5);
  assert.equal(nextValue({ ...control, value: 30 }, 1), null);
  assert.equal(nextValue({ ...control, value: 5 }, -1), null);
  hass.states["number.upper"].state = "unavailable";
  assert.equal(dashboard(hass, "climate.utility")[0].rooms[0].control, null);
  hass.connected = false;
  const [room] = dashboard(hass, "climate.living")[0].rooms;
  assert.equal(room.status, "unavailable");
  assert.equal(room.control, null);
  assert.equal(room.current, null);
  assert.deepEqual(dashboard(hass, "climate.hidden"), []);
});

test("provides the full same set of labels in the five integration languages", () => {
  const base = Object.keys(labels({ language: "en" }));
  for (const language of ["nl", "de", "fr", "it", "nl-BE", "fr-BE"]) {
    const translated = labels({ language });
    assert.deepEqual(Object.keys(translated), base);
    assert.notEqual(translated.heading, "Underfloor heating");
  }
});
