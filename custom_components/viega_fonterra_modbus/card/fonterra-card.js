import { available, dashboard, nextValue, numeric } from "./card-model.js";
import { labels } from "./card-strings.js";

const TYPE = "viega-fonterra-card";
const EDITOR = "viega-fonterra-card-editor";
const BRAND = "Viega Fonterra Smart";
const LOGO = new URL("../brand/icon.png", import.meta.url).href;
const STYLE = new URL("./fonterra-card.css", import.meta.url).href;

const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);

const icon = (name) => '<ha-icon icon="mdi:' + name + '" aria-hidden="true"></ha-icon>';

function renderPill(text, status) {
  return '<span class="pill" data-tone="' + status + '">' + escapeHTML(text) + '</span>';
}

class FonterraCard extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    const sheet = document.createElement("link");
    sheet.rel = "stylesheet";
    sheet.href = STYLE;
    this._body = document.createElement("div");
    root.append(sheet, this._body);
    this._body.addEventListener("click", (event) => this._handleClick(event));
    this._pending = new Set();
    this._failed = new Set();
  }

  static getStubConfig() {
    return { type: "custom:" + TYPE };
  }

  static getConfigElement() {
    return document.createElement(EDITOR);
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getGridOptions() {
    return { columns: this._config?.entity ? 6 : 12, min_columns: 4, rows: "auto" };
  }

  getCardSize() {
    return this._config?.entity ? 5 : 3 + 3 * Math.ceil((this._rooms?.length ?? 0) / 2);
  }

  _render() {
    if (!this._hass || !this._config) return;
    const hass = this._hass;
    const t = labels(hass);
    const single = Boolean(this._config.entity);
    const modules = dashboard(hass, this._config.entity);
    this._rooms = modules.flatMap((module) => module.rooms);
    const locale = hass.locale?.language ?? hass.language;
    this._number = new Intl.NumberFormat(locale, {
      minimumFractionDigits: 0, maximumFractionDigits: 1,
    });
    this._unit = hass.config?.unit_system?.temperature ?? "°C";
    const room = single ? this._rooms[0] : null;
    const title = this._config.title || room?.name || t.heading;
    const caption = room ? modules[0].name : this._rooms.length
      ? this._number.format(this._rooms.length) + " " + (this._rooms.length === 1 ? t.room : t.rooms)
      : "";
    const active = this._rooms.find((item) => item.status === "heating" || item.status === "cooling");
    const heroTone = room?.status ?? active?.status ?? "idle";
    const html = `<ha-card class="shell" data-view="${single ? "room" : "overview"}">
      <header class="hero" data-tone="${heroTone}">
        <div class="brand"><img src="${LOGO}" alt="" width="24" height="24"><span>${BRAND}</span></div>
        <h2>${escapeHTML(title)}</h2>
        ${caption ? `<p>${escapeHTML(caption)}</p>` : ""}
      </header>
      <div class="body">
        ${modules.length ? modules.map((module) => this._module(module, t, single)).join("") :
          `<p class="empty" role="status">${t.empty}</p>`}
      </div>
    </ha-card>`;
    if (html === this._html) return;
    const focus = this.shadowRoot.activeElement?.dataset.key;
    this._html = html;
    this._body.innerHTML = html;
    if (focus) {
      this.shadowRoot.querySelector('[data-key="' + CSS.escape(focus) + '"]')?.focus({ preventScroll: true });
    }
  }

  _module(module, t, single) {
    const hass = this._hass;
    const live = hass.connected !== false;
    const flow = live && available(module.flow) ? hass.formatEntityState(module.flow) : null;
    const pump = live && available(module.pump) ? (module.pump.state === "on" ? t.running : t.off) : null;
    const hasHeader = (!single && module.name) || flow || pump;
    return `<section class="module">
      ${hasHeader ? `<div class="module-head">
        ${!single && module.name ? `<h3>${escapeHTML(module.name)}</h3>` : ""}
        <div class="hub-metrics">
          ${flow ? `<span>${icon("water-thermometer")} ${t.flow} <b>${escapeHTML(flow)}</b></span>` : ""}
          ${pump ? `<span>${icon("pump")} ${t.pump} <b>${escapeHTML(pump)}</b></span>` : ""}
        </div>
      </div>` : ""}
      <div class="rooms" data-count="${module.rooms.length}">${module.rooms.map((room) => this._tile(room, t, single)).join("")}</div>
    </section>`;
  }

  _reading(value, unit) {
    if (value === null) return '<span aria-label="' + labels(this._hass).unavailable + '">–</span>';
    return escapeHTML(this._number.format(value)) + (unit ? '<small>' + escapeHTML(unit) + '</small>' : "");
  }

  _tile(room, t, single) {
    const manual = room.status === "power";
    const current = manual ? room.power : room.current;
    const unit = manual ? (room.powerMax === null ? "" : "/ " + room.powerMax) : this._unit;
    const busy = this._pending.has(room.id);
    const info = this._failed.has(room.id) ? t.failed : busy ? t.saving : "";
    const fault = !single && this._hass.connected !== false && available(room.diagnostic) &&
      numeric(room.diagnostic.attributes.error_code) > 0
      ? this._hass.formatEntityState(room.diagnostic) : null;
    const name = escapeHTML(room.name);
    const id = escapeHTML(room.id);

    return `<article class="tile" data-tone="${room.status}" aria-label="${name}">
      <div class="tile-top">
        ${single ? `<span class="caption">${manual ? t.power : t.current}</span>` :
          `<button class="room-name" data-room="${id}" data-action="details" data-key="${id}-details">
            ${name}${icon("chevron-right")}
          </button>`}
        ${renderPill(manual ? t.manual : t[room.status], room.status)}
      </div>
      <div class="temperature" aria-label="${manual ? t.power : t.current}">
        ${this._reading(current, unit)}
      </div>
      ${this._controls(room, t, busy)}
      <p class="feedback" role="status" ${info ? "" : "hidden"}>${info}</p>
      ${fault ? `<p class="fault">${t.diagnostic} · ${escapeHTML(fault)}</p>` : ""}
      ${single ? this._details(room, t) : ""}
      ${single ? `<button class="more" data-room="${id}" data-action="details" data-key="${id}-details">
        ${t.details} ${icon("chevron-right")}
      </button>` : ""}
    </article>`;
  }

  _controls(room, t, busy) {
    const c = room.control;
    if (!c) return "";
    const id = escapeHTML(room.id);
    const target = c.kind === "target";
    const unit = target ? this._unit : "";
    const button = (action, direction, glyph) => `<button class="adjust" type="button"
      data-room="${id}" data-action="${action}" data-key="${id}-${action}"
      aria-label="${t[action]}: ${escapeHTML(room.name)}"
      ${nextValue(c, direction) === null ? "disabled" : ""} aria-disabled="${busy}">${glyph}</button>`;
    return `<div class="control" data-kind="${c.kind}">
      ${target ? `<div><span class="caption">${t.target}</span>
        <strong>${this._reading(room.target, unit)}</strong></div>` : ""}
      <div class="stepper">${button("lower", -1, "−")} ${button("raise", 1, "+")}</div>
    </div>`;
  }

  _details(room, t) {
    const hass = this._hass;
    const live = hass.connected !== false;
    const value = (state) => live && available(state) ? escapeHTML(hass.formatEntityState(state)) : "–";
    return `${room.diagnostic ? `<dl class="metadata">
      <div><dt>${t.diagnostic}</dt><dd>${value(room.diagnostic)}</dd></div>
      </dl>` : ""}
      ${room.actors.length ? `<ul class="actors">${room.actors.map((actor) => {
        const position = actor.position === 1 || actor.position === true ? t.open :
          actor.position === 0 || actor.position === false ? t.closed : "–";
        return `<li><span>${icon("valve")} ${t.actor} ${actor.number}</span>
          <strong>${position}</strong><span>${t.return} <b>${value(actor.temperature)}</b></span></li>`;
      }).join("")}</ul>` : ""}`;
  }

  async _handleClick(event) {
    const button = event.target.closest("button[data-action]");
    if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") return;
    const { room: id, action } = button.dataset;
    if (action === "details") {
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        detail: { entityId: id }, bubbles: true, composed: true,
      }));
      return;
    }
    if (this._pending.has(id)) return;
    const room = this._rooms.find((item) => item.id === id);
    const c = room?.control;
    const next = c ? nextValue(c, action === "raise" ? 1 : -1) : null;
    if (next === null) return;
    this._failed.delete(id);
    this._pending.add(id);
    this._render();
    try {
      const target = { entity_id: c.entity };
      if (c.kind === "target") {
        await this._hass.callService("climate", "set_temperature", { temperature: next }, target, false);
      } else {
        await this._hass.callService("number", "set_value", { value: next }, target, false);
      }
    } catch {
      this._failed.add(id);
    } finally {
      this._pending.delete(id);
      this._render();
    }
  }
}

class FonterraCardEditor extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>
      :host { display:grid; gap:8px; color:var(--primary-text-color); padding:6px 0; }
      label { font-weight:600; }
      select { font:inherit; padding:12px; width:100%; color:var(--primary-text-color);
        background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:10px; }
      select:focus-visible { outline:2px solid var(--primary-color); outline-offset:2px; }
    </style><label for="room"></label><select id="room"></select>`;
    this._select = root.querySelector("select");
    this._select.addEventListener("change", () => {
      const config = { ...this._config };
      if (this._select.value) config.entity = this._select.value;
      else delete config.entity;
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config }, bubbles: true, composed: true,
      }));
    });
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    const t = labels(this._hass);
    const devices = dashboard(this._hass);
    const rooms = devices.flatMap(({ name, rooms }) => rooms.map((room) => [
      room.id, devices.length > 1 && name ? name + " · " + room.name : room.name,
    ]));
    const options = [["", t.all], ...rooms];
    if (this._config.entity && !rooms.some(([id]) => id === this._config.entity)) {
      options.push([this._config.entity, t.unavailable]);
    }
    const key = JSON.stringify(options);
    if (this._options !== key) {
      this._options = key;
      this._select.replaceChildren(...options.map(([id, name]) => new Option(name, id)));
    }
    this._select.value = this._config.entity || "";
    this.shadowRoot.querySelector("label").textContent = t.choose;
  }
}

if (!customElements.get(TYPE)) {
  customElements.define(TYPE, FonterraCard);
  customElements.define(EDITOR, FonterraCardEditor);
  (window.customCards ??= []).push({
    type: TYPE, name: BRAND, preview: true,
  });
}
