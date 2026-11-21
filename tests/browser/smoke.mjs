import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = fileURLToPath(new URL("../../custom_components/viega_fonterra_modbus/", import.meta.url));
const output = process.argv[2];
const pageHTML = `<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Viega Fonterra Smart</title>
<style>
html { background:#edf1f4; color:#182837; }
body { margin:0; min-width:0; font-family:system-ui,sans-serif;
  --primary-text-color:#182837; --secondary-text-color:#526071; --card-background-color:#fff;
  --ha-card-border-radius:22px; --primary-color:#006d82; --divider-color:#c9d3dc; }
main {display:grid; grid-template-columns:minmax(0,2fr) minmax(290px,1fr); gap:22px;
  max-width:1120px; margin:0 auto; padding:36px 26px;}
ha-card {display:block; box-shadow:0 8px 28px #132c4017;}
ha-icon {display:inline-flex; align-items:center; justify-content:center; width:var(--mdc-icon-size,1rem); }
@media (max-width:720px) {main {grid-template-columns:minmax(0,1fr); gap:18px; padding:15px;}}
html[data-theme="dark"] { background:#131b23; color:#edf2f7; }
html[data-theme="dark"] body { --primary-text-color:#edf2f7; --secondary-text-color:#b9c6d1;
  --card-background-color:#202a35; --primary-color:#8bd9ed; }
</style><script type="module">
import "/card/fonterra-card.js";
class Icon extends HTMLElement {
  connectedCallback() { this.textContent = {"mdi:water-thermometer":"≋", "mdi:radiator":"♨", "mdi:valve":"◇",
    "mdi:chevron-right":"›"}[this.getAttribute("icon")] ?? ""; }
}
customElements.define("ha-icon",Icon);
window.calls = [];
window.states = {};
const entities = {};
const put = (id, device, key, state, attributes, entity_name) => {
  entities[id] = {entity_id:id, platform:"viega_fonterra_modbus", device_id:device, translation_key:key, entity_name};
  states[id] = {entity_id:id, state, attributes};
};
const room = (id, name, room_id, state, current, target, hvac_action, actor) => put(id,"unit","room",state,{
  room_id, current_temperature:current, temperature:target, min_temp:5, max_temp:30,
  target_temp_step:.5, supported_features:target === null ? 0 : 1, hvac_action,
  actuator_positions:{[actor]:hvac_action === "heating" ? 1 : 0},
},name);
room("climate.living","Woonkamer",1,"heat",20.8,21.5,"heating",1);
room("climate.bath","Badkamer",2,"heat",22.4,23,"heating",2);
room("climate.kitchen","Keuken",3,"heat",21,20.5,"idle",3);
room("climate.utility","Bijkeuken",4,"heat",null,null,"idle",4);
put("number.utility","unit","power_level","6",{room_id:4,min:0,max:10,step:1});
put("sensor.flow","unit","flow_temperature","32.4",{unit_of_measurement:"°C"});
put("binary_sensor.pump","unit","circulation_pump","on",{});
put("sensor.return","unit","actuator_return_temperature","28.1",{room_id:2,actor_number:2,unit_of_measurement:"°C"});
put("sensor.diag","unit","room_diagnostic","ok",{room_id:2});
const display = new Intl.NumberFormat("nl-NL");
const hass = {
  entities, states, devices:{unit:{name:"Verdeler begane grond"}}, language:"nl", connected:true,
  config:{unit_system:{temperature:"°C"}}, formatEntityState(s) {
    if (s.state === "ok") return "Geen fout";
    if (s.state === "no_thermostat") return "Geen verbinding met de thermostaat";
    return display.format(Number(s.state)) + " " + s.attributes.unit_of_measurement;
  },
  async callService(domain,service,data,target) {
    calls.push({domain,service,data,target});
    if (window.rejectService) throw Error("Test service failure");
    if (domain === "climate") states[target.entity_id].attributes.temperature = data.temperature;
    else states[target.entity_id].state = String(data.value);
    paint();
  },
};
window.paint = () => document.querySelectorAll("viega-fonterra-card").forEach((el)=>el.hass=hass);
window.setOffline = () => { hass.connected=false; paint(); };
document.getElementById("overview").setConfig({type:"custom:viega-fonterra-card"});
document.getElementById("room").setConfig({type:"custom:viega-fonterra-card",entity:"climate.bath"});
document.addEventListener("hass-more-info",(event)=>window.moreInfo=event.detail.entityId);
window.makeEditor = () => {
  const edit = customElements.get("viega-fonterra-card").getConfigElement();
  edit.hass = hass;
  edit.setConfig({type:"custom:viega-fonterra-card"});
  edit.addEventListener("config-changed",(event)=>window.saved=event.detail.config);
  document.body.append(edit);
};
paint();
</script></head>
<body><main><viega-fonterra-card id="overview"></viega-fonterra-card><viega-fonterra-card id="room"></viega-fonterra-card></main></body></html>`;

const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/") return res.writeHead(200, { "content-type": "text/html;charset=UTF-8" }).end(pageHTML);
  const known = {
    "/card/fonterra-card.js":"text/javascript;charset=UTF-8",
    "/card/card-model.js":"text/javascript;charset=UTF-8",
    "/card/card-strings.js":"text/javascript;charset=UTF-8",
    "/card/fonterra-card.css":"text/css;charset=UTF-8",
    "/brand/icon.png":"image/png",
  };
  if (!known[url.pathname]) return res.writeHead(404).end();
  return res.writeHead(200, { "content-type": known[url.pathname] })
    .end(await readFile(resolve(root,url.pathname.slice(1))));
});
await new Promise((ready)=>server.listen(0,"127.0.0.1",ready));
const browser = await chromium.launch({ executablePath: process.env.FONTERRA_CHROMIUM_PATH });
try {
  const page = await browser.newPage({viewport:{width:1220,height:710},deviceScaleFactor:1});
  const errors = [];
  page.on("pageerror",(error)=>errors.push(error.message));
  await page.goto("http://127.0.0.1:"+server.address().port);
  await page.getByRole("heading",{name:"Vloerverwarming"}).waitFor();
  await page.getByRole("heading",{name:"Badkamer"}).waitFor();
  const overview=page.locator("#overview");
  assert.equal(await overview.locator(".tile").count(),4);
  assert.equal(await overview.locator('[data-kind="power"]').count(),1);
  await overview.getByText(/Warmtevraag\s+Actief/).waitFor();
  if (output) await page.screenshot({path:resolve(output,"Fonterra-dashboardkaart.png")});
  assert.equal(await page.getByText("Sensorstatus", { exact:true }).count(), 0);
  await page.evaluate(() => {
    states["sensor.diag"].state = "no_thermostat";
    states["sensor.diag"].attributes.error_code = 21;
    paint();
  });
  await overview.getByText("Diagnose · Geen verbinding met de thermostaat").waitFor();
  const increase = overview.getByRole("button",{name:"Verhogen: Woonkamer"});
  await increase.focus();
  await increase.press("Enter");
  await overview.getByRole("button",{name:"Verlagen: Bijkeuken"}).click();
  assert.deepEqual(await page.evaluate(()=>calls),[
    {domain:"climate",service:"set_temperature",data:{temperature:22},target:{entity_id:"climate.living"}},
    {domain:"number",service:"set_value",data:{value:5},target:{entity_id:"number.utility"}},
  ]);
  assert.equal(await overview.locator('[aria-label="Woonkamer"] .control strong').textContent(),"22°C");
  await page.evaluate(()=>window.rejectService=true);
  await overview.getByRole("button",{name:"Verhogen: Woonkamer"}).click();
  await overview.getByText("Opslaan mislukt. Probeer opnieuw.").waitFor();
  await overview.getByRole("button",{name:"Badkamer",exact:true}).click();
  assert.equal(await page.evaluate(()=>moreInfo),"climate.bath");
  await page.evaluate(()=>makeEditor());
  await page.getByLabel("Kies een ruimte").selectOption("climate.bath");
  assert.equal(await page.evaluate(()=>saved.entity),"climate.bath");
  await page.evaluate(()=>setOffline());
  assert.equal(await page.locator(".adjust").count(),0);
  assert.equal(await page.getByText("Niet beschikbaar",{exact:true}).count(),5);
  assert.deepEqual(errors,[]);
  await page.setViewportSize({width:390,height:820});
  await page.reload();
  await page.getByRole("heading",{name:"Vloerverwarming"}).waitFor();
  await page.evaluate(()=>document.documentElement.dataset.theme="dark");
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
  if (output) await page.locator("#room").screenshot({path:resolve(output,"Fonterra-ruimtekaart-mobiel.png")});
  console.log("Browser PASS: overview, room detail, keyboard-compatible controls, calls, errors, picker, offline and 390px dark layout");
} finally {
  await browser.close();
  server.close();
}
