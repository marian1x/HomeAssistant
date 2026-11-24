import { useState } from 'react';
import { BatteryCharging, Car, Check, SlidersHorizontal, DoorClosed, ExternalLink, Gauge, LockKeyhole, MapPin, Moon, PlugZap, Radio, ShieldCheck, Thermometer, ThermometerSun, Wifi, WifiOff } from 'lucide-react';
import { type Snapshot, type State, format, number, valid } from './model';
import { Num } from './motion';
import { Charges, Drives, Stats, useTeslaLog } from './TeslaJournal';

/* Tesla page. "Acum" shows what Home Assistant already holds (never wakes the car); the owner
   charge limit is the only command, confirmed, and applied by the HA policy at the next
   no-wake read. The journal tabs read the drive/charge log kept by the policy. */

const CAR = 'salavat_t3';
const when = (iso?: string) => {
  const time = iso ? Date.parse(iso) : NaN;
  return Number.isFinite(time) ? new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(time) : null;
};

const VIEWS = [['now', 'Acum'], ['charges', 'Incarcari'], ['drives', 'Deplasari'], ['stats', 'Statistici']] as const;
type View = typeof VIEWS[number][0];

export default function Tesla({ data }: { data: Snapshot | null }) {
  const [view, setView] = useState<View>('now');
  const [days, setDays] = useState(90);
  const role = data?.user?.role;
  const canControl = role === 'control' || role === 'configure';
  const journal = useTeslaLog(days, view !== 'now' && canControl);
  const tabs = (
    <div className="tesla-tabs">
      <div className="finance-tabs" role="tablist" aria-label="Tesla">{VIEWS.map(([key, title]) => <button key={key} role="tab" aria-selected={view === key} onClick={() => setView(key)}>{title}</button>)}</div>
      {view !== 'now' && <div className="segmented" aria-label="Perioada">{[[30, '30 zile'], [90, '90 zile'], [365, '1 an']].map(([d, t]) => <button key={d} className={days === d ? 'selected' : ''} aria-pressed={days === d} onClick={() => setDays(d as number)}>{t}</button>)}</div>}
    </div>
  );
  if (view !== 'now') {
    return (
      <section className="tesla-page" aria-label="Tesla">
        <header className="tesla-head"><div><span className="eyebrow">MOBILITATE</span><h1>Tesla</h1>
          <p className="tesla-note">Jurnal pastrat in Home Assistant din citirile masinii, fara trezire.</p></div></header>
        {tabs}
        {!canControl ? <p className="tesla-empty" role="status">Istoricul deplasarilor necesita rolul Control.</p>
          : journal.error ? <p className="tesla-empty" role="alert">{journal.error}</p>
          : !journal.log ? <p className="tesla-empty" role="status">Se incarca jurnalul...</p>
          : view === 'charges' ? <Charges log={journal.log} canControl={canControl} csrf={data?.csrf || ''} reload={journal.reload} />
          : view === 'drives' ? <Drives log={journal.log} />
          : <Stats log={journal.log} />}
      </section>
    );
  }
  return <TeslaNow data={data} tabs={tabs} canControl={canControl} />;
}

function LimitCard({ data, native, soc }: { data: Snapshot | null; native: number | null; soc: number | null }) {
  const owner = (data?.states['sensor.home_energy_policy_status']?.attributes?.ev_limit || {}) as { soc?: number; status?: string };
  const current = owner.soc ?? native ?? 80;
  const [value, setValue] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [message, setMessage] = useState('');
  const shown = value ?? current;
  const send = async () => {
    setMessage('Se trimite...');
    const r = await fetch(import.meta.env.BASE_URL + 'api/tesla/limit', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': data?.csrf || '' }, body: JSON.stringify({ soc: shown }) }).catch(() => null);
    setConfirm(false);
    if (r?.ok) { setMessage('Limita ' + shown + '% a fost salvata; se aplica la urmatoarea citire a masinii.'); setValue(null); }
    else setMessage((await r?.json().catch(() => null))?.error || 'Limita nu a fost salvata.');
  };
  return (
    <article className="tesla-card tesla-limit">
      <span className="tesla-label"><SlidersHorizontal size={16} />Limita de incarcare</span>
      <strong>{shown}<small> %</small></strong>
      <input type="range" min={20} max={100} step={1} value={shown} aria-label="Limita de incarcare" onChange={(e) => { setValue(Number(e.target.value)); setConfirm(false); }} />
      <span className="tesla-sub">{shown < 50 ? 'Sub 50%: masina ramane la 50%, iar acasa opresc incarcarea la ' + shown + '% si o reiau sub ' + (shown - 2) + '%.' : 'Se seteaza direct in masina.'}</span>
      <dl>
        <div><dt>In masina</dt><dd>{format(native, 0)} %</dd></div>
        <div><dt>Limita ta</dt><dd>{owner.soc ? owner.soc + ' %' : '--'}</dd></div>
        <div><dt>Stare</dt><dd>{owner.status || '--'}</dd></div>
      </dl>
      {value !== null && value !== current && (!confirm
        ? <button className="button primary" onClick={() => setConfirm(true)}>Seteaza {shown}%</button>
        : <div className="tesla-confirm" role="group" aria-label="Confirmare limita"><span>Trimit limita {shown}%{soc !== null && shown < soc ? ' (masina are deja ' + format(soc, 0) + '%)' : ''}?</span>
            <button className="button primary" onClick={send}><Check size={14} />Confirma</button><button className="button" onClick={() => setConfirm(false)}>Renunta</button></div>)}
      {message && <small role="status">{message}</small>}
    </article>
  );
}

type TelemetryStatus = { live: boolean; status: string; last_message: number | null; signals_day: number; signals_month: number;
  stopped: { reason: string; at: number } | null; config_exp: number | null; cost_month_usd: number; api_month_usd: number;
  stream_allowed_usd: number; trial: boolean };

const ago = (s: number | null) => {
  if (!s) return null;
  const d = Math.max(0, Date.now() / 1000 - s);
  return d < 90 ? 'acum ' + Math.round(d) + ' s' : d < 5400 ? 'acum ' + Math.round(d / 60) + ' min'
    : new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(s * 1000);
};
const usd = (v: number) => '$' + new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v);

function TelemetryCard({ t }: { t: TelemetryStatus | undefined }) {
  if (!t) return null;
  const state = t.stopped ? ['Oprita (buget)', 'off'] : t.live ? ['Live', 'on'] : t.status === 'MQTT neconfigurat in HA' ? ['Neconfigurata', 'off'] : ['In asteptare', 'sleep'];
  const allowed = Math.max(0.01, t.stream_allowed_usd);
  const used = Math.min(100, t.cost_month_usd / allowed * 100);
  return (
    <article className="tesla-card tesla-telemetry">
      <span className="tesla-label"><Radio size={16} />Fleet Telemetry</span>
      <span className={'tesla-status ' + state[1]}><i className={t.live ? 'pulse' : ''} />{state[0]}</span>
      <span className="tesla-sub">{t.live ? 'Masina trimite date acum' : t.stopped ? 'Oprita automat pentru a ramane in buget; citirile fara trezire continua' : t.status}{t.last_message ? ' · ultimul semnal ' + ago(t.last_message) : ''}</span>
      <div className="tesla-budget" role="img" aria-label={`Cost streaming luna aceasta ${usd(t.cost_month_usd)} din ${usd(allowed)} disponibili`}>
        <i style={{ width: used + '%' }} className={used > 80 ? 'warn' : ''} />
      </div>
      <dl>
        <div><dt>Streaming luna</dt><dd>{usd(t.cost_month_usd)} / {usd(allowed)}</dd></div>
        <div><dt>Citiri si comenzi</dt><dd>{usd(t.api_month_usd)}</dd></div>
        <div><dt>Semnale azi / luna</dt><dd>{format(t.signals_day, 0)} / {format(t.signals_month, 0)}</dd></div>
        {t.trial && <div><dt>Primele 2 saptamani</dt><dd>oprire automata peste $2</dd></div>}
      </dl>
      <small className="tesla-sub">Totul ramane in creditul lunar Tesla de $10; rezerva pentru incarcare si citiri e pastrata.</small>
    </article>
  );
}

function TeslaNow({ data, tabs, canControl }: { data: Snapshot | null; tabs: React.ReactNode; canControl: boolean }) {
  const get = (domain: string, key: string): State | undefined => data?.states[`${domain}.${CAR}_${key}`];
  const n = (key: string) => number(get('sensor', key));
  const on = (key: string) => { const state = get('binary_sensor', key); return valid(state) ? state!.state === 'on' : null; };
  const stamp = (key: string) => { const state = get('sensor', key); return when(valid(state) ? state!.state : undefined); };
  const battery = n('battery'), range = n('range'), limit = number(get('number', 'charge_limit'));
  const inside = n('temperature_inside'), outside = n('temperature_outside'), odometer = n('odometer');
  const added = n('energy_added'), power = n('charger_power'), rate = n('charging_rate');
  const charging = on('charging'), plugged = on('charger'), asleep = on('asleep'), online = on('online');
  const tracker = get('device_tracker', 'location_tracker'), located = valid(tracker);
  const lat = located && typeof tracker!.attributes.latitude === 'number' ? tracker!.attributes.latitude as number : null;
  const lon = located && typeof tracker!.attributes.longitude === 'number' ? tracker!.attributes.longitude as number : null;
  const place = !located ? null : tracker!.state === 'home' ? 'Acasa' : tracker!.state === 'not_home' ? 'In deplasare' : tracker!.state;
  const doors = get('lock', 'doors'), sentry = get('switch', 'sentry_mode'), windows = on('windows');
  const seen = stamp('data_last_update_time'), done = charging ? stamp('time_charge_complete') : null;
  const known = [battery, inside, outside, odometer].some((value) => value !== null) || located;
  const telemetry = data?.states['sensor.home_energy_policy_status']?.attributes?.telemetry as TelemetryStatus | undefined;
  const status: [string, string, any] = !data ? ['Neconectat', 'off', WifiOff] : telemetry?.live ? ['Live', 'on', Radio] : !known ? ['Fara date', 'off', WifiOff] : asleep ? ['Adormita', 'sleep', Moon] : online ? ['Online', 'on', Wifi] : ['Stare memorata', 'off', Wifi];
  const StatusIcon = status[2];
  const unit = (state: State | undefined, fallback: string) => state?.attributes.unit_of_measurement || fallback;
  const level = battery === null ? 0 : Math.max(0, Math.min(100, battery));
  return (
    <section className="tesla-page" aria-label="Tesla">
      <header className="tesla-head">
        <div><span className="eyebrow">MOBILITATE</span><h1>Tesla</h1>
          <p className="tesla-note">{telemetry?.live ? 'Date live prin Fleet Telemetry; masina nu este trezita.' : 'Citire din Home Assistant, fara trezirea masinii.'}{seen ? ' Ultimele date: ' + seen + '.' : ''}</p></div>
        <span className={'tesla-status ' + status[1]}><StatusIcon size={15} />{status[0]}</span>
      </header>
      {tabs}
      {!known && data && <p className="tesla-empty" role="status">Integrarea Tesla din Home Assistant nu raporteaza date in acest moment. Valorile apar singure dupa urmatoarea citire.</p>}
      <div className="tesla-grid">
        <article className={'tesla-card tesla-battery' + (charging ? ' charging' : '')}>
          <span className="tesla-label"><BatteryCharging size={16} />Baterie</span>
          <strong><Num value={battery} digits={0} /><small> %</small></strong>
          <div className="tesla-level" role="img" aria-label={battery === null ? 'Nivel baterie necunoscut' : 'Nivel baterie ' + format(battery, 0) + '%' + (limit !== null ? ', limita de incarcare ' + format(limit, 0) + '%' : '')}>
            <i style={{ width: level + '%' }} />{limit !== null && <b style={{ left: Math.max(0, Math.min(100, limit)) + '%' }} />}
          </div>
          <dl><div><dt>Autonomie</dt><dd>{format(range, 0)} {unit(get('sensor', 'range'), 'km')}</dd></div><div><dt>Limita de incarcare</dt><dd>{format(limit, 0)} %</dd></div></dl>
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><PlugZap size={16} />Incarcare</span>
          <strong><Num value={added} digits={1} /><small> kWh</small></strong>
          <span className="tesla-sub">Energie adaugata in ultima sesiune</span>
          <dl>
            <div><dt>Stare</dt><dd>{charging === null && plugged === null ? '--' : charging ? 'Se incarca' : plugged ? 'Conectata, nu incarca' : 'Deconectata'}</dd></div>
            <div><dt>Putere</dt><dd>{format(power, 1)} kW</dd></div>
            <div><dt>Viteza</dt><dd>{format(rate, 0)} {unit(get('sensor', 'charging_rate'), 'km/h')}</dd></div>
            {done && <div><dt>Gata la</dt><dd>{done}</dd></div>}
          </dl>
        </article>
        {canControl && <LimitCard data={data} native={limit} soc={battery} />}
        <TelemetryCard t={telemetry} />
        <article className="tesla-card">
          <span className="tesla-label"><Thermometer size={16} />Temperatura</span>
          <div className="tesla-pair">
            <div><strong><Num value={inside} digits={1} /><small> °C</small></strong><span className="tesla-sub"><Car size={14} />Interior</span></div>
            <div><strong><Num value={outside} digits={1} /><small> °C</small></strong><span className="tesla-sub"><ThermometerSun size={14} />Exterior</span></div>
          </div>
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><Gauge size={16} />Kilometraj</span>
          <strong><Num value={odometer} digits={0} /><small> {unit(get('sensor', 'odometer'), 'km')}</small></strong>
          <span className="tesla-sub">Total parcurs</span>
        </article>
        <article className="tesla-card tesla-place">
          <span className="tesla-label"><MapPin size={16} />Locatie</span>
          <strong className="tesla-where">{place ?? '--'}</strong>
          {lat !== null && lon !== null ? <>
            <span className="tesla-sub">{format(lat, 5)}, {format(lon, 5)}</span>
            <a className="button" href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=16/${lat}/${lon}`} target="_blank" rel="noreferrer"><ExternalLink size={15} />Deschide harta</a>
          </> : <span className="tesla-sub">Fara coordonate in ultima citire</span>}
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><ShieldCheck size={16} />Siguranta</span>
          <dl>
            <div><dt><LockKeyhole size={14} />Usi</dt><dd>{!valid(doors) ? '--' : doors!.state === 'locked' ? 'Incuiate' : 'Descuiate'}</dd></div>
            <div><dt><DoorClosed size={14} />Geamuri</dt><dd>{windows === null ? '--' : windows ? 'Deschise' : 'Inchise'}</dd></div>
            <div><dt><ShieldCheck size={14} />Sentry</dt><dd>{!valid(sentry) ? '--' : sentry!.state === 'on' ? 'Activ' : 'Oprit'}</dd></div>
          </dl>
        </article>
      </div>
    </section>
  );
}
