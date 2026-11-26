import { useEffect, useState } from 'react';
import { Battery, Car, House, Flame, Fan, RefreshCw, Save, Search, RotateCcw, ShieldCheck, Clock, AlertTriangle, Snowflake, Trash2 } from 'lucide-react';
import { type Snapshot, format } from './model';
import './energy-policy.css';

type Field = {key: string; label: string; group: string; kind: string; min?: number; max?: number; step?: number; unit?: string; choices?: string[]};
type Policy = {revision: number; config: Record<string, any>; schema: Field[]; status: Record<string, any>};
const BASE = import.meta.env.BASE_URL + 'api/v1/energy-policy';
const groups: Record<string, string> = {general: 'Program si control', prices: 'Tarife energie', planning: 'Estimari consum', safety: 'Protectii si temporizari', battery: 'Baterie si prognoza', tesla: 'Tesla', quota: 'Tesla / buget API', boiler: 'Apa calda', bindings: 'Asociere aparate', tcl: 'Program TCL', comfort: 'Confort', winter: 'Profiluri iarna', summer: 'Profiluri vara', whirlpool: 'Program Whirlpool iarna', fans: 'Trepte ventilatoare', boost: 'Surplus pentru climatizare'};
const deviceMeta = [{key: 'tesla', label: 'Tesla', icon: Car}, {key: 'boiler', label: 'Boiler Ariston', icon: Flame}, {key: 'tcl', label: 'TCL / parter', icon: Fan}, {key: 'whirlpool', label: 'Whirlpool / etaj', icon: Fan}];
const modes: Record<string, string> = {manual: 'Manual', normal: 'Confort', solar: 'Surplus solar', unavailable: 'Neconectat', idle: 'In asteptare'};
const fmt = (n: any, unit: string) => typeof n === 'number' && Number.isFinite(n) ? `${n.toLocaleString('ro-RO', {maximumFractionDigits: 2})} ${unit}` : 'Fara date';

const EV_MODE: Record<string, string> = { driving: 'in mers', charging: 'se incarca', plugged: 'conectata, fara incarcare', home: 'acasa', away: 'parcata departe', unknown: 'necunoscuta' };
const EV_REASON: Record<string, string> = { step_up: 'salt de consum trifazat', step_down: 'scadere de consum trifazat', driving: 'in mers', charging: 'incarcare', plugged: 'conectata', away: 'departe', night: 'verificarea de la miezul noptii', solar: 'incarcare solara', idle: 'verificare de zi' };

/* Energy profiles (owner request 2026-11-25): named presets of policy values kept on the
   server, the same in the APK. Everyone sees them; only Admin mode applies, saves or deletes. */
function Profiles({snapshot, policy, canConfigure, notify}: {snapshot: Snapshot; policy: Policy; canConfigure: boolean; notify: (m: string) => void}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [picked, setPicked] = useState<string[]>(['general']);
  const [busy, setBusy] = useState(false);
  const profiles = snapshot.profiles || [], active = snapshot.active_profile;
  const matches = (values: Record<string, any>) => Object.entries(values).every(([k, v]) => policy.config[k] === v);
  async function call(path: string, body: object = {}) {
    setBusy(true);
    try {
      const r = await fetch(import.meta.env.BASE_URL + 'api/v1/energy-profiles' + path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': snapshot.csrf}, body: JSON.stringify(body)});
      const result = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(result.error || 'Profilul nu a fost salvat.');
      return result;
    } finally {setBusy(false);}
  }
  const usable = policy.schema.filter(f => f.group !== 'bindings' && f.kind !== 'entity');
  async function create() {
    const values = Object.fromEntries(usable.filter(f => picked.includes(f.group)).map(f => [f.key, policy.config[f.key]]));
    try {await call('', {name: name.trim(), icon: 'star', values}); notify('Profil salvat din configuratia actuala.'); setCreating(false); setName('');}
    catch (e: any) {notify(e.message);}
  }
  return <section className="policy-quota policy-profiles" aria-label="Profile"><header><Snowflake size={19}/><strong>Profile</strong><span>{canConfigure ? 'Aplica, salveaza sau sterge' : 'Doar administratorul aplica profile'}</span></header>
    <div className="profile-list">{profiles.map(p => {
      const on = active?.id === p.id, same = matches(p.values);
      return <div key={p.id} className={'profile-chip' + (on ? ' active' : '')}>
        <button className="button" disabled={!canConfigure || busy} title={Object.keys(p.values).join(', ')} onClick={async () => {
          if (!window.confirm(`Aplici profilul "${p.name}"? Se schimba ${Object.keys(p.values).length} parametri; aparatele cu control automat se pot adapta imediat.`)) return;
          try {const r = await call('/' + p.id + '/activate'); notify(`Profilul ${p.name} a fost aplicat (${r.changed.length} modificari).`);} catch (e: any) {notify(e.message);}
        }}>{on && same ? <ShieldCheck size={15}/> : null}{p.name}{on && !same ? ' (modificat)' : ''}<small>{Object.keys(p.values).length}</small></button>
        {canConfigure && <button className="icon-button" title={'Sterge ' + p.name} disabled={busy} onClick={async () => {
          if (!window.confirm(`Stergi profilul "${p.name}"? Configuratia curenta nu se schimba.`)) return;
          try {await call('/' + p.id + '/delete'); notify('Profil sters.');} catch (e: any) {notify(e.message);}
        }}><Trash2 size={14}/></button>}
      </div>;
    })}
    {canConfigure && !creating && <button className="button" onClick={() => setCreating(true)}><Save size={15}/>Salveaza configuratia ca profil</button>}</div>
    {creating && <div className="profile-create"><input aria-label="Nume profil" placeholder="ex. Concediu, Ger, Canicula" maxLength={40} value={name} onChange={e => setName(e.target.value)}/>
      <div className="profile-groups">{Object.entries(groups).filter(([g]) => usable.some(f => f.group === g)).map(([g, title]) => <label key={g}><input type="checkbox" checked={picked.includes(g)} onChange={e => setPicked(p => e.target.checked ? [...p, g] : p.filter(x => x !== g))}/>{title}</label>)}</div>
      <span className="policy-actions"><button className="button" onClick={() => setCreating(false)}>Renunta</button><button className="button primary" disabled={busy || !name.trim() || !picked.length} onClick={create}><Save size={15}/>Salveaza</button></span>
      <small>Profilul retine valorile actuale ale grupurilor bifate; editarea fina se face si din aplicatia Android.</small></div>}
  </section>;
}

export default function EnergyPolicy({snapshot, canConfigure, canControl}: {snapshot: Snapshot; canConfigure: boolean; canControl: boolean}) {
  const [data, setData] = useState<Policy | null>(null);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [revision, setRevision] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [query, setQuery] = useState('');
  async function request(path = '', body?: object) {
    const response = await fetch(BASE + path, body ? {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': snapshot.csrf}, body: JSON.stringify(body)} : {});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.detail || 'Controlul energetic nu raspunde.');
    return result;
  }
  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      try {
        const result = await request();
        if (!alive) return;
        setData(result);
        if (!dirty) {setDraft(result.config); setRevision(result.revision);}
      } catch (error: any) {if (alive) setMessage(error.message);}
    };
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => {alive = false; clearInterval(timer);};
    // policy_stamp: another browser or the APK saved the policy or applied a profile.
  }, [snapshot.connected, dirty, snapshot.policy_stamp]);
  useEffect(() => {
    if (!canConfigure && data) {setDraft(data.config); setRevision(data.revision); setDirty(false);}
  }, [canConfigure]);
  async function save() {
    if (!canConfigure || !dirty || busy) return;
    if (!window.confirm('Aplici noua politica de energie si confort? Schimbarile pot comanda dispozitivele cu control automat activ.')) return;
    setBusy(true); setMessage('');
    try {
      const values = Object.fromEntries(Object.entries(draft).filter(([key,value]) => value !== data?.config[key]));
      const result = await request('', {values, revision});
      setData(result); setDraft(result.config); setRevision(result.revision); setDirty(false); setMessage('Configuratie salvata in Home Assistant.');
    } catch (error: any) {setMessage(error.message);}
    finally {setBusy(false);}
  }
  async function resume(device: string) {
    if (!canControl || busy || !window.confirm('Reiei controlul automat pentru acest aparat?')) return;
    setBusy(true);
    try {setData(await request('/resume', {device})); setMessage('Control automat reluat.');}
    catch (error: any) {setMessage(error.message);}
    finally {setBusy(false);}
  }
  const s = data?.status || {};
  const live = snapshot.states['sensor.home_energy_policy_status']?.attributes;
  const status = live?.updated_at && String(live.updated_at) > String(s.updated_at || '') ? {...s, ...live} : s;
  function edit(key: string, value: any) {setDraft(d => ({...d, [key]: value})); setDirty(true);}
  function control(f: Field) {
    const value = draft[f.key] ?? '';
    const id = 'policy-' + f.key;
    const disabled = !canConfigure || busy;
    if (f.kind === 'boolean') return <input id={id} type="checkbox" role="switch" checked={!!value} disabled={disabled} onChange={e => edit(f.key, e.target.checked)} />;
    if (f.kind === 'select') return <select id={id} value={value} disabled={disabled} onChange={e => edit(f.key, e.target.value)}>{f.choices?.map(c => <option key={c}>{c}</option>)}</select>;
    if (f.kind === 'entity') {
      const domains: Record<string,string> = {tcl_entity:'climate',whirlpool_entity:'climate',boiler_entity:'water_heater',boiler_power:'switch',ev_switch:'switch',ev_amps:'number',ev_limit:'number',ev_connected:'binary_sensor',ev_charging:'binary_sensor',ev_soc:'sensor',ev_power:'sensor',ev_voltage:'sensor',ev_tracker:'device_tracker',ev_home_zone:'zone'};
      const options=Object.values(snapshot.states).filter(s=>s.entity_id.startsWith(domains[f.key]+'.')&&!['climate.heat','climate.bedroom_heat'].includes(s.entity_id)&&(!(f.key==='tcl_entity'||f.key==='whirlpool_entity'||f.key==='boiler_power')||!s.entity_id.includes('salavat_t3')&&!s.entity_id.includes('deye')));
      return <select id={id} value={value} disabled={disabled} onChange={e=>edit(f.key,e.target.value)}><option value="">Neasociat</option>{value&&!options.some(s=>s.entity_id===value)&&<option value={value}>{value} (indisponibil)</option>}{options.map(s=><option key={s.entity_id} value={s.entity_id}>{s.attributes.friendly_name || s.entity_id} · {s.entity_id}</option>)}</select>;
    }
    if (f.kind === 'fan') {
      const key = f.key.startsWith('tcl') ? 'tcl_entity' : 'whirlpool_entity';
      const options = snapshot.states[draft[key]]?.attributes.fan_modes as string[] | undefined;
      if (options?.length) return <select id={id} value={value} disabled={disabled} onChange={e => edit(f.key, e.target.value)}>{!options.includes(value) && <option value={value}>{value} (nesuportat)</option>}{options.map(v => <option key={v}>{v}</option>)}</select>;
    }
    return <span className="policy-input"><input id={id} type={f.kind === 'number' ? 'number' : f.kind === 'time' ? 'time' : f.kind === 'date' ? 'date' : 'text'} value={value} min={f.min} max={f.max} step={f.step} disabled={disabled} maxLength={64} onChange={e => edit(f.key, f.kind === 'number' ? e.target.value === '' ? '' : Number(e.target.value) : e.target.value)} />{f.unit && <small>{f.unit === 'C' ? '°C' : f.unit}</small>}</span>;
  }
  return <div className="policy-page">
    <header className="policy-heading"><div><span className="eyebrow">ENERGIE SI CONFORT</span><h1>Casa, in echilibru</h1></div><span className={'policy-health ' + (status.power_valid ? 'good' : '')}><ShieldCheck size={16}/>{status.phase || 'Conectare la HA'}</span></header>
    <div className="policy-summary">
      <div><span>Surplus disponibil</span><strong>{fmt(status.solar_budget_kw, 'kW')}</strong></div>
      <div><span>Bateria casei</span><strong>{fmt(status.battery_soc, '%')}</strong><small>Rezerva {status.battery_reserve_soc ?? data?.config.base_reserve_soc ?? 20}%</small><small>{status.recharge_lock ? 'Reincarcare prioritara' : 'Sprijin solar disponibil'}</small></div>
      <div><span>Exterior / sezon</span><strong>{fmt(status.outside_c, '°C')}</strong><small>{status.season === 'Winter' ? 'Iarna' : status.season === 'Summer' ? 'Vara' : ''}</small></div>
      <div><span>Prognoza ramasa azi</span><strong>{fmt(status.forecast_remaining_kwh, 'kWh')}</strong><small>{status.updated_at ? new Date(status.updated_at).toLocaleTimeString('ro-RO', {hour: '2-digit', minute: '2-digit'}) : ''}</small></div>
    </div>
    {status.cold_charge?.enabled && <section className="policy-quota" aria-label="Injectie din retea pe frig"><header><Snowflake size={19}/><strong>Incalzire din retea</strong><span>{status.cold_charge.active ? 'Injectie activa' : 'In asteptare'}</span></header><div><span>Baterie <strong>{typeof status.cold_charge.battery_temp === 'number' ? format(status.cold_charge.battery_temp, 1) + ' °C' : '--'}</strong></span><span>Porneste sub <strong>{data?.config.cold_charge_temp_c} °C</strong></span><span>Opreste la <strong>{data?.config.cold_charge_recover_c} °C</strong></span><span>Fereastra <strong>{data?.config.cold_charge_hours_before_sunrise} h inainte de rasarit</strong></span></div><small>{status.cold_charge.reason}{status.cold_charge.grid_charge_switch ? ' · comutator retea: ' + status.cold_charge.grid_charge_switch : ''}</small></section>}
    {status.tesla_quota && <section className="policy-quota" aria-label="Buget Tesla API"><header><Car size={19}/><strong>Tesla API</strong><span>{status.tesla_quota.polling_protected ? 'Polling periodic oprit' : 'Protectie polling neconfirmata'}</span></header><div><span>Citiri azi <strong>{status.tesla_quota.reads_day || 0} / {data?.config.ev_reads_daily}</strong></span><span>Citiri luna <strong>{status.tesla_quota.reads_month || 0} / {data?.config.ev_reads_monthly}</strong></span><span>Comenzi azi <strong>{status.tesla_quota.commands_day || 0} / {data?.config.ev_commands_daily}</strong></span><span>Comenzi luna <strong>{status.tesla_quota.commands_month || 0} / {data?.config.ev_commands_monthly}</strong></span></div><small>{status.tesla_quota.status || 'Fara cerere de actualizare'}{status.tesla_quota.mode ? ' · Masina: ' + (EV_MODE[status.tesla_quota.mode] || status.tesla_quota.mode) : ''}{status.tesla_quota.last_reason ? ' · Ultima citire: ' + (EV_REASON[status.tesla_quota.last_reason] || status.tesla_quota.last_reason) : ''}{' · Salturi de consum azi: ' + (status.tesla_quota.steps_day || 0) + ' / ' + (data?.config.ev_step_daily ?? '-')}</small></section>}
    {data && <Profiles snapshot={snapshot} policy={data} canConfigure={canConfigure} notify={setMessage}/>}
    <ol className="policy-priorities">{[[House, 'Casa'], [Battery, 'Baterie'], [Car, 'Tesla'], [Flame, 'Boiler'], [Fan, 'Climatizare']].map(([Icon, title]: any, i) => <li key={title}><span>{i + 1}</span><Icon size={19}/><strong>{title}</strong></li>)}</ol>
    <p className="policy-reason">{status.reason || 'Se incarca starea controlerului.'}</p>
    <div className="policy-devices">{deviceMeta.map(({key, label, icon: Icon}) => {
      const d = status.devices?.[key] || {};
      const manual = d.manual_until > Date.now()/1000;
      return <article key={key} className={'policy-device ' + (manual ? 'manual' : d.mode || '')}><header><Icon size={23}/><h2>{label}</h2><span>{modes[manual ? 'manual' : d.mode] || 'In asteptare'}</span></header><strong className="policy-setpoint">{d.temperature != null ? fmt(d.temperature, '°C') : d.amps != null ? fmt(d.amps, 'A') : '...'}</strong><p>{d.reason || 'Fara comenzi'}</p>{d.fan && <small>Ventilator: {d.fan}</small>}{manual && <div className="policy-hold"><Clock size={15}/><span>Pana la {new Date(d.manual_until*1000).toLocaleString('ro-RO', {day: '2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'})}</span><button className="icon-button" title={'Reia automat ' + label} disabled={!canControl || busy} onClick={() => resume(key)}><RotateCcw size={17}/></button></div>}</article>;
    })}</div>
    <section className="policy-parameters"><header><div><h2>Parametri de functionare</h2><span className="muted">{canConfigure ? 'Admin' : 'Vizualizare'} · revizia {data?.revision ?? '—'}</span></div><div className="policy-actions"><button className="icon-button" title="Renunta la modificari" disabled={!dirty || busy} onClick={() => {if (data) {setDraft(data.config);setRevision(data.revision);setDirty(false);}}}><RefreshCw size={18}/></button><button className="button primary" disabled={!canConfigure || busy || !dirty} onClick={save}><Save size={16}/>{busy ? 'Se salveaza' : 'Aplica'}</button></div></header>
      {message && <p role="status" className="policy-message"><AlertTriangle size={16}/>{message}</p>}
      {dirty && data?.revision !== revision && <p role="alert" className="policy-message">Configuratie schimbata in alta sesiune. Reincarca inainte de a edita.</p>}
      <label className="policy-search"><Search size={17}/><input type="search" aria-label="Cauta parametri" placeholder="Cauta un parametru" value={query} onChange={e => setQuery(e.target.value)}/></label>
      {Object.entries(groups).map(([key, title]) => {
        const fields = data?.schema.filter(f => f.group === key && (!query || (f.label + ' ' + title).toLocaleLowerCase().includes(query.toLocaleLowerCase()))) || [];
        if (!fields.length) return null;
        return <details className="policy-group" key={key} open={query ? true : undefined}><summary>{title}<small>{fields.length}</small></summary><div className="policy-fields">{fields.map(f => <div className="policy-field" key={f.key}><label htmlFor={'policy-' + f.key}>{f.label}</label>{control(f)}</div>)}</div></details>;
      })}
    </section>
  </div>;
}
