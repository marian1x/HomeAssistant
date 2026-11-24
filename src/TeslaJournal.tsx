import { useEffect, useMemo, useState } from 'react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Activity, CircleAlert, Clock, Euro, Gauge, Home, Leaf, MapPin, Navigation, PlugZap, Radio, Route, Save, Thermometer, Zap } from 'lucide-react';
import { format } from './model';
import TeslaMap, { SPEED_BANDS, type Track } from './TeslaMap';

const BASE = import.meta.env.BASE_URL + 'api/tesla/';

export type Charge = {
  id: number; start: number; end: number; start_soc: number | null; end_soc: number | null; lat: number | null; lon: number | null;
  home: boolean; kwh: number; hours: number; max_kw: number; solar_kwh: number; battery_kwh: number; grid_kwh: number; split_s: number;
  price_kwh: number | null; note: string | null; cost: number | null;
};
export type Drive = {
  id: number; start: number; end: number; approx_start: boolean; start_soc: number | null; end_soc: number | null;
  start_lat: number | null; start_lon: number | null; end_lat: number | null; end_lon: number | null; start_home?: boolean; end_home?: boolean;
  km: number; kwh: number | null; hours: number; wh_km: number | null; avg_kmh: number | null; outside: number | null; cost: number | null;
  path: [number, number][]; max_kmh?: number | null; source?: 'telemetry' | 'reads'; energy_basis?: 'energy' | 'soc' | null;
};
export type Telemetry = {
  live: boolean; status: string; last_message: number | null; signals_day: number; signals_month: number;
  stopped: { reason: string; at: number } | null; config_exp: number | null; pushed_at?: number | null;
  costs: { stream_month_usd: number; api_month_usd: number; api_reserve_usd: number; stream_total_usd: number; trial: boolean; stream_allowed_usd: number };
};
type Log = { charges: Charge[]; drives: Drive[]; cost_per_kwh: number; prices: { import: number; export: number };
  active: { drive: any; charge: any }; monthly_km: { start: number; km: number }[]; days: number; telemetry?: Telemetry | null };
type Detail = { path: [number, number][]; speeds: (number | null)[]; profile: { min: number; kmh: number }[] };

const tz = 'Europe/Bucharest';
const day = (s: number) => new Intl.DateTimeFormat('ro-RO', { timeZone: tz, weekday: 'short', day: 'numeric', month: 'short' }).format(s * 1000);
const clock = (s: number) => new Intl.DateTimeFormat('ro-RO', { timeZone: tz, hour: '2-digit', minute: '2-digit' }).format(s * 1000);
const month = (ms: number) => new Intl.DateTimeFormat('ro-RO', { timeZone: tz, month: 'short', year: '2-digit' }).format(ms);
const duration = (h: number) => { const m = Math.round(h * 60); return m < 60 ? m + ' min' : Math.floor(m / 60) + ' h ' + String(m % 60).padStart(2, '0'); };
const lei = (v: number) => new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v);
const ron = (v: number | null | undefined) => v === null || v === undefined ? '--' : lei(v) + ' lei';
const place = (home: boolean | undefined, lat: number | null, lon: number | null) =>
  home ? 'Acasa' : lat !== null && lon !== null ? format(lat, 4) + ', ' + format(lon, 4) : 'Locatie necunoscuta';
const osm = (lat: number, lon: number) => `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=15/${lat}/${lon}`;

export function useTeslaLog(days: number, enabled: boolean) {
  const [log, setLog] = useState<Log | null>(null);
  const [error, setError] = useState('');
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    fetch(BASE + 'log?days=' + days).then(async (r) => {
      const body = await r.json().catch(() => ({}));
      if (!live) return;
      if (!r.ok) { setError(body.error || 'Jurnalul Tesla nu este disponibil.'); return; }
      setError(''); setLog(body);
    }).catch(() => live && setError('Jurnalul Tesla nu este disponibil.'));
    return () => { live = false; };
  }, [days, tick, enabled]);
  return { log, error, reload: () => setTick((n) => n + 1) };
}

function Split({ c }: { c: Charge }) {
  const total = c.solar_kwh + c.battery_kwh + c.grid_kwh;
  if (!c.home) return <span className="split-note">Statie externa</span>;
  if (total <= 0) return <span className="split-note">Fara masurare (inainte de jurnal)</span>;
  const part = (v: number) => (v / total * 100);
  return (
    <span className="charge-split" role="img" aria-label={`Solar ${format(part(c.solar_kwh), 0)}%, baterie ${format(part(c.battery_kwh), 0)}%, retea ${format(part(c.grid_kwh), 0)}%`}>
      {c.solar_kwh > 0 && <i className="solar" style={{ width: part(c.solar_kwh) + '%' }} />}
      {c.battery_kwh > 0 && <i className="battery" style={{ width: part(c.battery_kwh) + '%' }} />}
      {c.grid_kwh > 0 && <i className="grid" style={{ width: part(c.grid_kwh) + '%' }} />}
    </span>
  );
}

function PriceEditor({ c, csrf, onSaved }: { c: Charge; csrf: string; onSaved: () => void }) {
  const [price, setPrice] = useState(c.price_kwh === null ? '' : String(c.price_kwh));
  const [note, setNote] = useState(c.note || '');
  const [state, setState] = useState('');
  const save = async () => {
    const value = price.trim() === '' ? null : Number(price.replace(',', '.'));
    if (value !== null && (!Number.isFinite(value) || value < 0 || value > 20)) { setState('Pret intre 0 si 20 lei/kWh'); return; }
    setState('Se salveaza...');
    const r = await fetch(BASE + 'charge-price', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify({ id: c.id, price_kwh: value, note: note.trim().slice(0, 120) }) }).catch(() => null);
    if (r?.ok) { setState('Salvat'); onSaved(); } else setState((await r?.json().catch(() => null))?.error || 'Nu s-a salvat');
  };
  return (
    <div className="price-editor">
      <label>Pret statie <input inputMode="decimal" value={price} placeholder={c.home ? 'tarif casa' : 'lei/kWh'} onChange={(e) => setPrice(e.target.value)} aria-label="Pret pe kWh" /><small>lei/kWh</small></label>
      <label>Nota <input value={note} maxLength={120} placeholder="ex. Kaufland, Supercharger" onChange={(e) => setNote(e.target.value)} aria-label="Nota" /></label>
      <button className="button" onClick={save}><Save size={14} />Salveaza</button>
      {state && <small role="status">{state}</small>}
    </div>
  );
}

export function Charges({ log, canControl, csrf, reload }: { log: Log; canControl: boolean; csrf: string; reload: () => void }) {
  const [open, setOpen] = useState<number | null>(null);
  const home = log.charges.filter((c) => c.home), away = log.charges.filter((c) => !c.home);
  const kwh = log.charges.reduce((s, c) => s + c.kwh, 0);
  const cost = log.charges.reduce((s, c) => s + (c.cost ?? 0), 0);
  const measured = home.reduce((s, c) => s + c.solar_kwh + c.battery_kwh + c.grid_kwh, 0);
  const solar = home.reduce((s, c) => s + c.solar_kwh, 0);
  return (
    <section aria-label="Incarcari">
      <div className="tesla-kpis">
        <div><span>Incarcari</span><strong>{log.charges.length}</strong><small>{home.length} acasa · {away.length} externe</small></div>
        <div><span>Energie</span><strong>{format(kwh, 1)}<small> kWh</small></strong><small>in baterie</small></div>
        <div><span>Cost</span><strong>{lei(cost)}<small> lei</small></strong><small>{away.some((c) => c.cost === null) ? 'lipsesc preturi la statii' : 'toate incarcarile'}</small></div>
        <div><span>Din solar acasa</span><strong>{measured > 0 ? format(solar / measured * 100, 0) : '--'}<small> %</small></strong><small>energie masurata</small></div>
      </div>
      {log.active.charge && <p className="tesla-live" role="status"><PlugZap size={15} />Incarcare in curs de la {clock(log.active.charge.start)}: {format(log.active.charge.added, 1)} kWh, {format(log.active.charge.start_soc, 0)}% → {format(log.active.charge.end_soc, 0)}%</p>}
      {log.charges.length === 0 ? <p className="tesla-empty">Nicio incarcare in perioada aleasa.</p> :
        <ol className="tesla-list">
          {log.charges.map((c) => (
            <li key={c.id} className={open === c.id ? 'open' : ''}>
              <button className="tesla-row" onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id}>
                <span className="when"><b>{day(c.start)}</b><small>{clock(c.start)} – {clock(c.end)}</small></span>
                <span className="where">{c.home ? <Home size={14} /> : <MapPin size={14} />}{c.note || place(c.home, c.lat, c.lon)}</span>
                <span className="num"><b>{format(c.kwh, 1)}</b> kWh</span>
                <span className="num soc">{format(c.start_soc, 0)}→{format(c.end_soc, 0)}%</span>
                <Split c={c} />
                <span className="num cost">{c.cost === null ? <em>adauga pret</em> : ron(c.cost)}</span>
              </button>
              {open === c.id && (
                <div className="tesla-detail">
                  <dl>
                    <div><dt><Clock size={14} />Durata</dt><dd>{duration(c.hours)}</dd></div>
                    <div><dt><Zap size={14} />Putere maxima</dt><dd>{format(c.max_kw, 1)} kW</dd></div>
                    {c.home && <><div><dt><Leaf size={14} />Solar</dt><dd>{format(c.solar_kwh, 2)} kWh</dd></div>
                      <div><dt>Baterie casa</dt><dd>{format(c.battery_kwh, 2)} kWh</dd></div>
                      <div><dt>Retea</dt><dd>{format(c.grid_kwh, 2)} kWh</dd></div></>}
                    <div><dt><Euro size={14} />Pret aplicat</dt><dd>{c.price_kwh !== null ? lei(c.price_kwh) + ' lei/kWh (introdus)' : c.home ? 'tarif casa (solar ' + lei(log.prices.export) + ', retea ' + lei(log.prices.import) + ' lei/kWh)' : 'necunoscut'}</dd></div>
                    {c.lat !== null && c.lon !== null && <div><dt><MapPin size={14} />Harta</dt><dd><a href={osm(c.lat, c.lon)} target="_blank" rel="noreferrer">Deschide locatia</a></dd></div>}
                  </dl>
                  {canControl && <PriceEditor c={c} csrf={csrf} onSaved={reload} />}
                </div>
              )}
            </li>
          ))}
        </ol>}
      <p className="battery-note"><CircleAlert size={14} />Acasa, energia e impartita pe solar, bateria casei si retea din fluxurile Deye la fiecare 30 s; solarul e evaluat la pretul de vanzare, bateria la acelasi pret / 90% randament. La statii costul apare dupa ce introduci pretul.</p>
    </section>
  );
}

function SpeedLegend() {
  return (
    <div className="speed-legend" aria-label="Legenda viteza, km/h">
      <span>km/h</span>{SPEED_BANDS.map((b) => <span key={b.label}><i style={{ background: `var(${b.token}, ${b.fallback})` }} />{b.label}</span>)}
    </div>
  );
}

function SpeedProfile({ profile, max }: { profile: Detail['profile']; max?: number | null }) {
  if (profile.length < 3) return null;
  const axis = { stroke: 'var(--muted)', fontSize: 11, tickLine: false, axisLine: false };
  return (
    <figure className="battery-chart speed-profile">
      <figcaption><span><i style={{ background: 'var(--speed-3, #d69a1c)' }} />Profil de viteza</span><small>{max ? 'maxim ' + format(max, 0) + ' km/h' : 'km/h in timp'}</small></figcaption>
      <div className="speed-profile-body"><ResponsiveContainer>
        <AreaChart data={profile} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
          <defs><linearGradient id="speedFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--speed-3, #d69a1c)" stopOpacity={0.45} /><stop offset="100%" stopColor="var(--speed-3, #d69a1c)" stopOpacity={0.04} /></linearGradient></defs>
          <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="2 4" />
          <XAxis dataKey="min" type="number" domain={['dataMin', 'dataMax']} {...axis} tickFormatter={(v: number) => format(v, 0) + ' min'} />
          <YAxis {...axis} width={36} />
          <Tooltip formatter={(v: any) => [format(v, 0) + ' km/h', 'Viteza']} labelFormatter={(v: any) => 'minutul ' + format(v, 1)} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--edge)', borderRadius: 10, color: 'var(--text)' }} />
          <Area type="monotone" dataKey="kmh" stroke="var(--speed-3, #d69a1c)" strokeWidth={2} fill="url(#speedFill)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer></div>
    </figure>
  );
}

function LiveDrive({ active, telemetry }: { active: any; telemetry?: Telemetry | null }) {
  const trail: [number, number][] = active?.trail || [];
  const lastKey = trail.length ? trail[trail.length - 1].join(',') : '';
  const tracks: Track[] = useMemo(() => trail.length > 1 ? [{ path: trail, live: true }] : [], [trail.length, lastKey]);
  if (!active) return null;
  const km = typeof active.end_odo === 'number' && typeof active.start_odo === 'number' ? active.end_odo - active.start_odo : null;
  return (
    <section className="tesla-live-drive" aria-label="Deplasare in curs">
      <p className="tesla-live" role="status"><Navigation size={15} />In mers de la {clock(active.start)}{km !== null ? ' · ' + format(km, 1) + ' km' : ''}
        {telemetry?.live && typeof active.kmh === 'number' && <b className="live-speed">{format(active.kmh, 0)} km/h</b>}</p>
      {tracks.length > 0 && <TeslaMap tracks={tracks} compact label="Traseul deplasarii in curs" />}
    </section>
  );
}

export function Drives({ log }: { log: Log }) {
  const [selected, setSelected] = useState(0);
  const [detail, setDetail] = useState<Record<number, Detail>>({});
  const drive = log.drives[selected];
  useEffect(() => {
    if (!drive || detail[drive.id]) return;
    fetch(BASE + 'drive/' + drive.id).then((r) => r.ok ? r.json() : null).then((d) => {
      if (!d?.points) return;
      const pts: number[][] = d.points;
      const t0 = pts[0]?.[0] ?? drive.start;
      const step = Math.max(1, Math.ceil(pts.length / 400));
      const profile = pts.filter((p, i) => p.length > 3 && typeof p[3] === 'number' && i % step === 0).map((p) => ({ min: (p[0] - t0) / 60, kmh: p[3] }));
      setDetail((all) => ({ ...all, [drive.id]: { path: pts.map((p) => [p[1], p[2]] as [number, number]), speeds: pts.map((p) => p.length > 3 && typeof p[3] === 'number' ? p[3] : null), profile } }));
    }).catch(() => {});
  }, [drive?.id]);
  const info = drive ? detail[drive.id] : undefined;
  const tracks: Track[] = useMemo(() => drive ? [{ path: info?.path || drive.path, speeds: info?.speeds,
    start: drive.start_lat !== null && drive.start_lon !== null ? [drive.start_lat, drive.start_lon] : null,
    end: drive.end_lat !== null && drive.end_lon !== null ? [drive.end_lat, drive.end_lon] : null }] : [], [drive, info]);
  const km = log.drives.reduce((s, d) => s + d.km, 0);
  const kwh = log.drives.reduce((s, d) => s + (d.kwh ?? 0), 0);
  const kmWithEnergy = log.drives.filter((d) => d.kwh !== null).reduce((s, d) => s + d.km, 0);
  const cost = log.drives.reduce((s, d) => s + (d.cost ?? 0), 0);
  const precise = log.drives.filter((d) => d.source === 'telemetry').length;
  const hasSpeeds = !!info?.speeds.some((v) => v !== null);
  const t = log.telemetry;
  return (
    <section aria-label="Deplasari">
      <div className="tesla-kpis">
        <div><span>Deplasari</span><strong>{log.drives.length}</strong><small>{format(km, 0)} km{precise ? ' · ' + precise + ' cu traseu real' : ''}</small></div>
        <div><span>Consum mediu</span><strong>{kmWithEnergy > 0 ? format(kwh * 1000 / kmWithEnergy, 0) : '--'}<small> Wh/km</small></strong><small>{format(kwh, 1)} kWh</small></div>
        <div><span>Cost</span><strong>{lei(cost)}<small> lei</small></strong><small>{lei(log.cost_per_kwh)} lei/kWh mediu</small></div>
        <div><span>Cost la 100 km</span><strong>{kmWithEnergy > 0 ? lei(cost / kmWithEnergy * 100) : '--'}<small> lei</small></strong><small>din costul incarcarilor</small></div>
      </div>
      <LiveDrive active={log.active.drive} telemetry={t} />
      <p className="battery-note">{t?.live ? <Radio size={14} /> : <Route size={14} />}{
        t?.live ? 'Fleet Telemetry activ: deplasarile noi au traseul real (un punct la 5 s), viteza si consumul din contorul de energie al bateriei.'
        : t?.pushed_at ? 'Fleet Telemetry este configurat; masina trimite date doar cand e treaza. Deplasarile marcate „Citiri rare” sunt aproximative.'
        : 'Traseele marcate „Citiri rare” sunt aproximative (masina e citita rar, fara trezire). Cu Fleet Telemetry activ apar traseul real, viteza si consumul.'}</p>
      {log.drives.length === 0 ? <p className="tesla-empty">Nicio deplasare in perioada aleasa.</p> : <>
        <TeslaMap tracks={tracks} label={drive ? `Traseu ${day(drive.start)} ${clock(drive.start)}, ${format(drive.km, 1)} km` : 'Harta'} />
        {hasSpeeds && <SpeedLegend />}
        <ol className="tesla-list">
          {log.drives.map((d, i) => (
            <li key={d.id} className={i === selected ? 'open' : ''}>
              <button className="tesla-row" onClick={() => setSelected(i)} aria-pressed={i === selected}>
                <span className="when"><b>{day(d.start)}</b><small>{d.approx_start ? '~' : ''}{clock(d.start)} – {clock(d.end)}</small></span>
                <span className="where">{d.source === 'telemetry' && <Activity size={14} className="src-live" aria-label="traseu real" />}{d.start_home ? 'Acasa' : place(false, d.start_lat, d.start_lon)} → {d.end_home ? 'Acasa' : place(false, d.end_lat, d.end_lon)}</span>
                <span className="num"><b>{format(d.km, 1)}</b> km</span>
                <span className="num">{d.kwh === null ? '--' : format(d.kwh, 1)} kWh</span>
                <span className="num">{d.wh_km === null ? '--' : format(d.wh_km, 0)} Wh/km</span>
                <span className="num cost">{ron(d.cost)}</span>
              </button>
              {i === selected && (
                <div className="tesla-detail"><dl>
                  <div><dt><Clock size={14} />Durata</dt><dd>{d.approx_start ? 'cel mult ' : ''}{duration(d.hours)}</dd></div>
                  <div><dt><Gauge size={14} />Viteza medie</dt><dd>{d.approx_start || d.avg_kmh === null ? 'necunoscuta (citiri rare)' : format(d.avg_kmh, 0) + ' km/h'}</dd></div>
                  {d.max_kmh ? <div><dt><Gauge size={14} />Viteza maxima</dt><dd>{format(d.max_kmh, 0)} km/h</dd></div> : null}
                  <div><dt>Baterie</dt><dd>{format(d.start_soc, 0)}% → {format(d.end_soc, 0)}%</dd></div>
                  <div><dt><Zap size={14} />Consum</dt><dd>{d.kwh === null ? '--' : format(d.kwh, 2) + ' kWh'}{d.energy_basis && <small className="dd-note">{d.energy_basis === 'energy' ? 'contor energie baterie' : 'estimat din % baterie'}</small>}</dd></div>
                  <div><dt><Thermometer size={14} />Exterior</dt><dd>{d.outside === null ? '--' : format(d.outside, 1) + ' °C'}</dd></div>
                  <div><dt>{d.source === 'telemetry' ? <Radio size={14} /> : <Route size={14} />}Sursa</dt><dd>{d.source === 'telemetry' ? 'Fleet Telemetry (traseu real)' : 'Citiri rare (aproximativ)'}</dd></div>
                </dl>
                {info && <SpeedProfile profile={info.profile} max={d.max_kmh} />}
                </div>
              )}
            </li>
          ))}
        </ol>
      </>}
    </section>
  );
}

export function Stats({ log }: { log: Log }) {
  const months = useMemo(() => {
    const rows = new Map<string, any>();
    const key = (s: number) => { const d = new Date(s * 1000); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); };
    for (const m of log.monthly_km) { const k = key(m.start / 1000); rows.set(k, { ...(rows.get(k) || { month: month(m.start) }), km: m.km }); }
    for (const c of log.charges) {
      const k = key(c.start), r = rows.get(k) || { month: month(c.start * 1000) };
      const measured = c.solar_kwh + c.battery_kwh + c.grid_kwh;
      if (!c.home) r.away = (r.away || 0) + c.kwh;
      else if (measured > 0) { const f = c.kwh / measured; r.solar = (r.solar || 0) + c.solar_kwh * f; r.battery = (r.battery || 0) + c.battery_kwh * f; r.grid = (r.grid || 0) + c.grid_kwh * f; }
      else r.unmeasured = (r.unmeasured || 0) + c.kwh;
      rows.set(k, r);
    }
    return [...rows.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, v]) => v);
  }, [log]);
  const round = (v: any) => typeof v === 'number' ? format(v, 1) : v;
  const axis = { stroke: 'var(--muted)', fontSize: 11, tickLine: false, axisLine: false };
  return (
    <section aria-label="Statistici" className="tesla-stats">
      <figure className="battery-chart">
        <figcaption><span><i style={{ background: 'var(--energy-load)' }} />Kilometri pe luna</span><small>din kilometraj, statistici HA</small></figcaption>
        <div className="tesla-chart-body"><ResponsiveContainer>
          <BarChart data={months} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="2 4" />
            <XAxis dataKey="month" {...axis} /><YAxis {...axis} width={44} />
            <Tooltip formatter={(v: any) => [round(v) + ' km', 'Distanta']} cursor={{ fill: 'var(--inset)' }} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--edge)', borderRadius: 10, color: 'var(--text)' }} />
            <Bar dataKey="km" fill="var(--energy-load)" radius={[4, 4, 0, 0]} maxBarSize={28} />
          </BarChart>
        </ResponsiveContainer></div>
      </figure>
      <figure className="battery-chart">
        <figcaption><span>Energie incarcata pe luna, dupa sursa</span><small>kWh in bateria masinii</small></figcaption>
        <div className="tesla-chart-body"><ResponsiveContainer>
          <BarChart data={months} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="2 4" />
            <XAxis dataKey="month" {...axis} /><YAxis {...axis} width={44} />
            <Tooltip formatter={(v: any, n: any) => [round(v) + ' kWh', n]} cursor={{ fill: 'var(--inset)' }} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--edge)', borderRadius: 10, color: 'var(--text)' }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="solar" name="Solar" stackId="e" fill="var(--energy-solar)" stroke="var(--surface)" strokeWidth={2} />
            <Bar dataKey="battery" name="Baterie casa" stackId="e" fill="var(--energy-battery)" stroke="var(--surface)" strokeWidth={2} />
            <Bar dataKey="grid" name="Retea" stackId="e" fill="var(--energy-grid)" stroke="var(--surface)" strokeWidth={2} />
            <Bar dataKey="unmeasured" name="Acasa, nemasurat" stackId="e" fill="var(--muted)" stroke="var(--surface)" strokeWidth={2} />
            <Bar dataKey="away" name="Statii externe" stackId="e" fill="var(--energy-export)" stroke="var(--surface)" strokeWidth={2} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer></div>
      </figure>
      <table className="tesla-table">
        <caption>Rezumat pe luni</caption>
        <thead><tr><th>Luna</th><th>km</th><th>Solar</th><th>Baterie</th><th>Retea</th><th>Statii</th></tr></thead>
        <tbody>{months.map((m) => <tr key={m.month}><td>{m.month}</td><td>{round(m.km ?? '--')}</td><td>{round(m.solar ?? 0)}</td><td>{round(m.battery ?? 0)}</td><td>{round((m.grid ?? 0) + (m.unmeasured ?? 0))}</td><td>{round(m.away ?? 0)}</td></tr>)}</tbody>
      </table>
      <p className="battery-note"><CircleAlert size={14} />Kilometrii vin din statisticile HA (din mai 2026); energia pe surse doar din incarcarile inregistrate de jurnal (ultimele 7 zile importate, apoi continuu).</p>
    </section>
  );
}
