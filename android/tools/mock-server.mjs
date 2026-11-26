// Mock Casa backend for the Android `mock` build (emulator -> http://10.0.2.2:8787/casa).
// Synthetic data only: reads the redacted fixtures used by tests/browser.mjs, never
// talks to Home Assistant. Commands are recorded and "confirmed" with an SSE delta
// so the UI can be exercised end to end without touching a physical device.
//
//   node android/tools/mock-server.mjs <fixtures-dir>
//   (fixtures-dir default: ../home-control-web/tests/fixtures, gitignored)
//
// Casa-account login: any username, password "parola-test", TOTP code "123456".
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';

const dir = process.argv[2] || process.env.CASA_FIXTURES || 'tests/fixtures';
const fixture = JSON.parse(await readFile(path.join(dir, 'ha.json'), 'utf8'));
try {
  const tcl = JSON.parse(await readFile(path.join(dir, 'tcl.json'), 'utf8'));
  fixture.states[tcl.entity_id] = tcl;
  fixture.entities.push({entity_id: tcl.entity_id, device_id: '64f01c0359ebb3569a50e8eb51041183'});
} catch {}
fixture.house = JSON.parse(await readFile(new URL('../../server/house.json', import.meta.url), 'utf8'));
// Synthetic live energy values so the flow animates (test inputs, not telemetry).
const put = (id, state, unit) => fixture.states[id] = {entity_id: id, state: String(state), last_updated: new Date().toISOString(), attributes: {unit_of_measurement: unit, friendly_name: id}};
put('sensor.productie_solara_curenta', 4.2, 'kW');
put('sensor.consum_total_curent', 1.6, 'kW');
put('sensor.consum_din_retea', 0, 'kW');
put('sensor.injectie_in_retea', 0.9, 'kW');
put('sensor.baterie_incarcare_putere', 1.7, 'kW');
put('sensor.baterie_descarcare_putere', 0, 'kW');
put('sensor.tesla_charging_power', 0, 'kW');
put('sensor.ariston_boiler_power_estimated', 0, 'kW');
put('sensor.deye_today_energy_import', 2.1, 'kWh');
put('sensor.deye_today_load_consumption', 9.4, 'kWh');
put('sensor.deye_productie_solara_astazi', 14.8, 'kWh');
// Synthetic car (2026-11-25 controls) so the Tesla page can be exercised.
const car = (id, state, attributes = {}) => fixture.states[id] = {entity_id: id, state: String(state), last_updated: new Date().toISOString(), attributes: {friendly_name: 'Salavat T3 ' + id.split('salavat_t3_')[1].replace(/_/g, ' '), ...attributes}};
car('sensor.salavat_t3_battery', 64, {unit_of_measurement: '%'});
car('sensor.salavat_t3_range', 312, {unit_of_measurement: 'km'});
car('number.salavat_t3_charge_limit', 80, {min: 50, max: 100});
car('number.salavat_t3_charging_amps', 10, {min: 0, max: 16, step: 1});
car('switch.salavat_t3_charger', 'off');
car('switch.salavat_t3_sentry_mode', 'off');
car('lock.salavat_t3_doors', 'locked');
car('cover.salavat_t3_trunk', 'closed');
car('cover.salavat_t3_charger_door', 'closed');
car('button.salavat_t3_horn', 'unknown');
car('button.salavat_t3_flash_lights', 'unknown');
car('select.salavat_t3_heated_seat_left', 'Off', {options: ['Off', 'Low', 'Medium', 'High']});
car('time.salavat_t3_scheduled_charging', '23:00:00');
car('binary_sensor.salavat_t3_charger', 'on');
car('binary_sensor.salavat_t3_charging', 'off');
car('device_tracker.salavat_t3_location_tracker', 'home', {latitude: 44.43, longitude: 26.1});
fixture.states['climate.salavat_t3_hvac_climate_system'] = {...(fixture.states['climate.salavat_t3_hvac_climate_system'] || {}), entity_id: 'climate.salavat_t3_hvac_climate_system', state: 'off',
  attributes: {friendly_name: 'Salavat T3 Climatizare', temperature: 21, current_temperature: 9, min_temp: 15, max_temp: 28, hvac_modes: ['off', 'heat_cool'], preset_modes: ['normal', 'defrost']}};
put('sensor.deye_load_l1_power', 620, 'W'); put('sensor.deye_load_l2_power', 410, 'W'); put('sensor.deye_load_l3_power', 570, 'W');
// Shared server state the real server now puts in every snapshot.
let layout = {sort: 'default', order: [], groups: [], favorites: [], views: []};
const profiles = [{id: 'iarna', name: 'Iarna', icon: 'snow', values: {season: 'Winter'}}, {id: 'vara', name: 'Vara', icon: 'sun', values: {season: 'Summer'}},
  {id: 'auto', name: 'Automat dupa luna', icon: 'auto', values: {season: 'Auto'}}];
let active = null, stamp = 0;
let policy = null;
try { policy = JSON.parse(await readFile(path.join(dir, 'policy.json'), 'utf8')); } catch {}

const SESSION = 'casa_session';
const sessions = new Set(['mock']);
const streams = new Set();
const writes = [];
const json = (res, code, body, headers = {}) => res.writeHead(code, {'Content-Type': 'application/json', ...headers}).end(JSON.stringify(body));
const cookie = req => Object.fromEntries((req.headers.cookie || '').split(';').map(c => c.trim().split('=')).filter(p => p[0]));
const authed = req => sessions.has(cookie(req)[SESSION]);
const snapshot = () => ({...fixture, connected: true, last_update: Date.now() / 1000, csrf: 'mock-csrf',
  user: {...(fixture.user || {}), id: 'test', name: 'Cosmin', role: 'configure', admin: true}, layout, profiles, active_profile: active, policy_stamp: stamp});
const push = packet => streams.forEach(s => s.write('data: ' + JSON.stringify(packet) + '\n\n'));
const body = async req => { let t = ''; for await (const c of req) t += c; return JSON.parse(t || '{}'); };

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const p = url.pathname;
  console.log(req.method, p);
  if (p === '/casa/auth/local' && req.method === 'POST') {
    const b = await body(req);
    if (b.password !== 'parola-test') return json(res, 401, {error: 'Utilizator sau parola gresita.'});
    return json(res, 200, {next: 'code', must_change: false, name: b.username || 'Test'}, {'Set-Cookie': 'casa_local=c; Path=/casa/auth; HttpOnly'});
  }
  if (p === '/casa/auth/local/verify' && req.method === 'POST') {
    const b = await body(req);
    if (b.code !== '123456') return json(res, 401, {error: 'Cod incorect sau expirat.'});
    const sid = 'mock-' + Math.random().toString(36).slice(2);
    sessions.add(sid);
    return json(res, 200, {ok: true}, {'Set-Cookie': `${SESSION}=${sid}; Path=/casa/; HttpOnly; Max-Age=2592000`});
  }
  if (p.startsWith('/casa/api/') && !authed(req)) return json(res, 401, {error: 'Autentificare necesara.'});
  if (p === '/casa/api/session') return json(res, 200, snapshot());
  if (p === '/casa/api/events') {
    res.writeHead(200, {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive'});
    res.write('data: ' + JSON.stringify(snapshot()) + '\n\n');
    streams.add(res);
    const ping = setInterval(() => res.write(': heartbeat\n\n'), 20000);
    // Gentle synthetic drift so the energy flow and numbers move.
    const drift = setInterval(() => {
      const s = fixture.states['sensor.productie_solara_curenta'];
      s.state = String(Math.max(0, (Number(s.state) + (Math.random() - 0.5) * 0.4)).toFixed(2));
      push({type: 'delta', connected: true, last_update: Date.now() / 1000, states: {[s.entity_id]: s}});
    }, 4000);
    req.on('close', () => { clearInterval(ping); clearInterval(drift); streams.delete(res); });
    return;
  }
  if (p === '/casa/api/history') {
    const period = url.searchParams.get('period') || 'day';
    const n = {day: 96, week: 168, month: 30, year: 12}[period];
    const step = {day: 900e3, week: 3600e3, month: 86400e3, year: 30 * 86400e3}[period];
    const points = Array.from({length: n}, (_, i) => {
      const h = (i / n) * 24;
      const sun = Math.max(0, Math.sin((h - 6) / 12 * Math.PI)) * 6;
      return {time: Date.now() - (n - i) * step, solar: sun, load: 1 + Math.random(), battery: Math.max(0, 1.2 - sun / 4), grid: Math.max(0, 1.5 - sun)};
    });
    return json(res, 200, {period, unit: period === 'day' ? 'kW' : 'kWh', points});
  }
  if (p === '/casa/api/v1/energy-policy' && req.method === 'GET') return policy ? json(res, 200, policy) : json(res, 503, {error: 'Fara fixture de politica.'});
  if (p === '/casa/api/v1/energy-profiles' && req.method === 'GET') return json(res, 200, {profiles, active});
  if (p === '/casa/api/layout' && req.method === 'GET') return json(res, 200, {...layout, usage: {}, usage_days: 30});
  if (p === '/casa/api/battery/bms') return json(res, 200, {available: true, status: 'Citire reusita', latest: {ts: Date.now() / 1000 - 120, heater_phase: 'oprita',
    pack: {cells: Array.from({length: 16}, (_, i) => 3.30 + (i % 5) * 0.003), cell_temps: [11.5, 12.1], cell_min: 3.300, cell_max: 3.312, cell_spread_mv: 12, soh: 99, cycles: 41, mos_temp: 14}}, history: []});
  if (p === '/casa/api/battery/history') return json(res, 200, {points: Array.from({length: 96}, (_, i) => ({time: Date.now() - (96 - i) * 900e3, soc: 40 + 40 * Math.sin(i / 30), temp: 10 + i / 20, power: -1500 * Math.sin(i / 15)}))});
  if (p === '/casa/api/tesla/log') {
    const day = 86400, now = Date.now() / 1000;
    return json(res, 200, {cost_per_kwh: 0.9, active: {drive: null, charge: null}, monthly_km: [{start: (now - 40 * day) * 1000, km: 820}, {start: (now - 10 * day) * 1000, km: 640}],
      charges: [{id: 1, start: now - 2 * day, end: now - 2 * day + 5 * 3600, start_soc: 30, end_soc: 62, home: true, kwh: 18.4, hours: 5, max_kw: 7.2, solar_kwh: 11, battery_kwh: 3, grid_kwh: 4.4, split_s: 1, price_kwh: null, note: null, cost: 5.1, lat: 44.43, lon: 26.1},
                {id: 2, start: now - 6 * day, end: now - 6 * day + 3600, start_soc: 20, end_soc: 70, home: false, kwh: 30, hours: 0.6, max_kw: 150, solar_kwh: 0, battery_kwh: 0, grid_kwh: 0, split_s: 0, price_kwh: 2.35, note: 'Supercharger', cost: 70.5, lat: 44.5, lon: 26.0}],
      drives: [{id: 7, start: now - day, end: now - day + 1800, approx_start: false, start_soc: 64, end_soc: 58, start_lat: 44.43, start_lon: 26.1, end_lat: 44.48, end_lon: 26.05, start_home: true, end_home: false,
        km: 14.2, kwh: 2.3, hours: 0.5, wh_km: 162, avg_kmh: 28, max_kmh: 71, outside: 6, cost: 2.1, path: Array.from({length: 30}, (_, i) => [44.43 + i * 0.0017, 26.1 - i * 0.0017 + Math.sin(i / 3) * 0.002])}]});
  }
  if (p.startsWith('/casa/api/tesla/drive/')) return json(res, 200, {path: Array.from({length: 30}, (_, i) => [44.43 + i * 0.0017, 26.1 - i * 0.0017 + Math.sin(i / 3) * 0.002]), speeds: Array.from({length: 30}, (_, i) => 20 + i * 2), profile: []});
  if (req.method === 'POST') {
    const b = await body(req);
    writes.push({path: p, data: b});
    console.log('  recorded write (mock only):', JSON.stringify(b));
    if (p === '/casa/api/layout') { layout = {...layout, ...b}; push(snapshot()); return json(res, 200, {saved: true}); }
    const activate = p.match(/^\/casa\/api\/v1\/energy-profiles\/([^/]+)\/activate$/);
    if (activate) {
      const item = profiles.find(x => x.id === activate[1]);
      if (!item) return json(res, 404, {error: 'Profil inexistent.'});
      if (policy) { Object.assign(policy.config, item.values); policy.revision++; }
      active = {id: item.id, at: Date.now() / 1000, by: 'test'}; stamp++; push(snapshot());
      return json(res, 200, {active, changed: Object.keys(item.values), policy});
    }
    if (p === '/casa/api/v1/energy-policy' && policy) { Object.assign(policy.config, b.values || {}); policy.revision++; stamp++; push(snapshot()); return json(res, 200, policy); }
    if (p === '/casa/api/logout' || p === '/casa/api/logout-all') {
      sessions.delete(cookie(req)[SESSION]);
      return json(res, 200, {ok: true}, {'Set-Cookie': `${SESSION}=; Path=/casa/; Max-Age=0`});
    }
    if (p === '/casa/api/command' && fixture.states[b.entity_id]) {
      const st = fixture.states[b.entity_id];
      setTimeout(() => {
        if (b.action === 'turn_on' || b.action === 'turn_off') st.state = b.action === 'turn_on' ? 'on' : 'off';
        if (b.action === 'set_temperature') st.attributes.temperature = b.value;
        if (b.action === 'set_hvac_mode') st.state = b.value;
        if (b.action === 'set_brightness') { st.state = 'on'; st.attributes.brightness = Math.round(b.value * 2.55); }
        if (b.action === 'lock' || b.action === 'unlock') st.state = b.action === 'lock' ? 'locked' : 'unlocked';
        if (b.action === 'open_cover' || b.action === 'close_cover') st.state = b.action === 'open_cover' ? 'open' : 'closed';
        if (b.action === 'set_value') st.state = String(b.value);
        if (b.action === 'select_option') st.state = b.value;
        push({type: 'delta', connected: true, last_update: Date.now() / 1000, states: {[st.entity_id]: st}});
      }, 700);
    }
    return json(res, 200, {accepted: true});
  }
  json(res, 404, {error: 'Resursa inexistenta.'});
}).listen(8787, '0.0.0.0', () => console.log('Mock Casa on http://0.0.0.0:8787/casa  (emulator: http://10.0.2.2:8787/casa)'));
