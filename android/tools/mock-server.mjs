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

const SESSION = 'casa_session';
const sessions = new Set(['mock']);
const streams = new Set();
const writes = [];
const json = (res, code, body, headers = {}) => res.writeHead(code, {'Content-Type': 'application/json', ...headers}).end(JSON.stringify(body));
const cookie = req => Object.fromEntries((req.headers.cookie || '').split(';').map(c => c.trim().split('=')).filter(p => p[0]));
const authed = req => sessions.has(cookie(req)[SESSION]);
const snapshot = () => ({...fixture, connected: true, last_update: Date.now() / 1000, csrf: 'mock-csrf'});
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
  if (req.method === 'POST') {
    const b = await body(req);
    writes.push({path: p, data: b});
    console.log('  recorded write (mock only):', JSON.stringify(b));
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
        push({type: 'delta', connected: true, last_update: Date.now() / 1000, states: {[st.entity_id]: st}});
      }, 700);
    }
    return json(res, 200, {accepted: true});
  }
  json(res, 404, {error: 'Resursa inexistenta.'});
}).listen(8787, '0.0.0.0', () => console.log('Mock Casa on http://0.0.0.0:8787/casa  (emulator: http://10.0.2.2:8787/casa)'));
