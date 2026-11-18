/** Read the same entity and device registries that the Home Assistant dashboard uses. */
const DOMAIN = "viega_fonterra_modbus";
const TARGET_TEMPERATURE = 1;
const UNAVAILABLE = new Set(["unknown", "unavailable"]);

export const available = (state) => Boolean(state && !UNAVAILABLE.has(state.state));

export function numeric(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}

const roomOf = (state, id) => String(state.attributes.room_id ?? id).replace(/^room_/, "");

function controlFor(climate, power, connected) {
  const thermostat = Boolean(climate.attributes.supported_features & TARGET_TEMPERATURE);
  const entity = thermostat ? climate : power;
  if (!available(entity) || !connected || !available(climate)) return null;

  const a = entity.attributes;
  const value = numeric(thermostat ? a.temperature : entity.state);
  const min = numeric(thermostat ? a.min_temp : a.min);
  const max = numeric(thermostat ? a.max_temp : a.max);
  const step = numeric(thermostat ? a.target_temp_step : a.step);
  if (value === null || min === null || max === null || min >= max || !(step > 0)) return null;
  return { kind: thermostat ? "target" : "power", entity: entity.entity_id, value, min, max, step };
}

export function nextValue(control, direction) {
  const current = control.value;
  if ((direction < 0 && current <= control.min) || (direction > 0 && current >= control.max)) {
    return null;
  }
  const following = Math.min(control.max, Math.max(control.min, current + direction * control.step));
  const value = Number(following.toFixed(3));
  return value === current ? null : value;
}

function roomStatus(climate, power, connected) {
  if (!connected || !available(climate)) return "unavailable";
  if (power && available(power)) return "power";
  const action = climate.attributes.hvac_action;
  if (["heating", "cooling", "idle", "off"].includes(action)) return action;
  return climate.state === "off" ? "off" : "idle";
}

function linked(room, name) {
  return room?.get(name)?.[0];
}

export function dashboard(hass, entityId) {
  const groups = new Map();
  const connected = hass.connected !== false;
  // Room numbers are local to each divider. Use the device ID first so two
  // rooms named "Bathroom", both numbered 3, never share controls or details.
  for (const record of Object.values(hass.entities ?? {})) {
    const state = hass.states[record.entity_id];
    if (record.platform !== DOMAIN || record.hidden || record.hidden_by || !state) continue;
    const deviceId = record.device_id ?? "";
    if (!groups.has(deviceId)) groups.set(deviceId, { rooms: [], roomsById: new Map(), hub: new Map() });
    const group = groups.get(deviceId);

    if (record.entity_id.startsWith("climate.")) {
      group.rooms.push({ record, state });
      continue;
    }
    if (!record.translation_key) continue;
    const roomId = state.attributes.room_id;
    let members = group.hub;
    if (roomId != null) {
      const id = roomOf(state);
      if (!group.roomsById.has(id)) group.roomsById.set(id, new Map());
      members = group.roomsById.get(id);
    }
    const list = members.get(record.translation_key) ?? [];
    list.push(state);
    members.set(record.translation_key, list);
  }

  const collator = new Intl.Collator(hass.locale?.language ?? hass.language, { numeric: true });
  const modules = [];
  for (const [deviceId, group] of groups) {
    const device = hass.devices?.[deviceId];
    const name = device?.name_by_user ?? device?.name ?? "";
    const rooms = [];
    for (const { record, state } of group.rooms) {
      if (entityId && state.entity_id !== entityId) continue;
      const id = roomOf(state, state.entity_id);
      const attributes = state.attributes;
      const members = group.roomsById.get(id);
      const power = linked(members, "power_level");
      const control = controlFor(state, power, connected);
      const thermostat = Boolean(attributes.supported_features & TARGET_TEMPERATURE);
      const position = attributes.actuator_positions ?? {};
      const returns = (members?.get("actuator_return_temperature") ?? [])
        .map((item) => [String(item.attributes.actor_number), item]);
      const byActor = new Map(returns);
      const actors = [...new Set([...Object.keys(position), ...byActor.keys()])]
        .filter((actor) => /^\d+$/.test(actor))
        .sort((a, b) => Number(a) - Number(b))
        .map((actor) => ({
          number: actor,
          position: connected && available(state) ? position[actor] : null,
          temperature: byActor.get(actor),
        }));
      rooms.push({
        id: state.entity_id,
        name: record.entity_name || attributes.friendly_name || state.entity_id,
        status: roomStatus(state, thermostat ? undefined : power, connected),
        control,
        current: connected && available(state) ? numeric(attributes.current_temperature) : null,
        target: connected && available(state) && thermostat ? numeric(attributes.temperature) : null,
        power: available(power) && connected && !thermostat ? numeric(power.state) : null,
        powerMax: numeric(power?.attributes.max),
        diagnostic: linked(members, "room_diagnostic"),
        actors,
      });
    }
    if (!rooms.length) continue;
    rooms.sort((a, b) => collator.compare(a.name, b.name));
    modules.push({
      name,
      rooms,
      flow: linked(group.hub, "flow_temperature"),
      pump: linked(group.hub, "circulation_pump"),
    });
  }
  return modules.sort((a, b) => collator.compare(a.name, b.name));
}
