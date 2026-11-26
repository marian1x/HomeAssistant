import { useState } from 'react';
import { BellRing, Fan, Flashlight, Gauge, Lock, LockOpen, Power, PlugZap, Shield, Timer } from 'lucide-react';
import { type Snapshot, type State, format, valid } from './model';

/* Full car control (owner decision 2026-11-25), same narrow server commands as the APK:
   /api/command on the car's own entities, each confirmed and audited. A command may wake
   the car and costs Tesla API budget, so nothing here repeats or retries by itself. */

const CAR = 'salavat_t3';
const WAKE = 'Comanda poate trezi masina si consuma din bugetul API Tesla.';

export default function TeslaControls({ data }: { data: Snapshot }) {
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [amps, setAmps] = useState<number | null>(null);
  const [temp, setTemp] = useState<number | null>(null);
  const get = (domain: string, key: string): State | undefined => data.states[`${domain}.${CAR}_${key}`];
  const all = (domain: string) => Object.values(data.states).filter((s) => s.entity_id.startsWith(`${domain}.${CAR}_`));
  const short = (s: State) => String(s.attributes.friendly_name || s.entity_id).replace(/^Salavat T3\s*/i, '');
  async function send(entity: string, action: string, value: unknown, question: string) {
    if (busy || !window.confirm(question + '\n\n' + WAKE)) return;
    setBusy(entity); setMessage('Se trimite...');
    try {
      const r = await fetch(import.meta.env.BASE_URL + 'api/command', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': data.csrf },
        body: JSON.stringify({ entity_id: entity, action, ...(value === undefined ? {} : { value }) }) });
      const body = await r.json().catch(() => ({}));
      setMessage(r.ok ? 'Comanda acceptata; starea se schimba cand masina confirma.' : body.error || 'Comanda nu a fost acceptata.');
    } catch { setMessage('Serverul nu raspunde.'); } finally { setBusy(''); }
  }
  const charger = get('switch', 'charger'), doors = get('lock', 'doors'), sentry = get('switch', 'sentry_mode');
  const current = get('number', 'charging_amps'), climate = all('climate')[0];
  const shownAmps = amps ?? (valid(current) ? Number(current!.state) : null);
  const target = typeof climate?.attributes.temperature === 'number' ? climate.attributes.temperature as number : null;
  const shownTemp = temp ?? target;
  const button = (entity: State | undefined, label: string, Icon: any, action: string, question: string, value?: unknown) => entity &&
    <button className="button" disabled={!!busy || entity.state === 'unavailable'} onClick={() => send(entity.entity_id, action, value, question)}><Icon size={15} />{label}</button>;
  return (
    <article className="tesla-card tesla-controls">
      <span className="tesla-label"><Power size={16} />Comenzi</span>
      <div className="tesla-actions">
        {charger && button(charger, charger.state === 'on' ? 'Opreste incarcarea' : 'Porneste incarcarea', PlugZap, charger.state === 'on' ? 'turn_off' : 'turn_on',
          (charger.state === 'on' ? 'Opresti' : 'Pornesti') + ' incarcarea? Politica trece Tesla pe control manual pana a doua zi.')}
        {doors && button(doors, doors.state === 'locked' ? 'Descuie' : 'Incuie', doors.state === 'locked' ? LockOpen : Lock, doors.state === 'locked' ? 'unlock' : 'lock',
          doors.state === 'locked' ? 'Descui masina?' : 'Incui masina?')}
        {sentry && button(sentry, sentry.state === 'on' ? 'Opreste Sentry' : 'Porneste Sentry', Shield, sentry.state === 'on' ? 'turn_off' : 'turn_on', 'Schimbi Sentry?')}
        {button(get('button', 'flash_lights'), 'Semnalizeaza', Flashlight, 'press', 'Aprinzi farurile scurt?')}
        {button(get('button', 'horn'), 'Claxon', BellRing, 'press', 'Claxonezi?')}
        {button(get('button', 'wake_up'), 'Trezeste', Power, 'press', 'Trezesti masina?')}
      </div>
      {current && shownAmps !== null && <div className="tesla-row-control">
        <span><Gauge size={14} />Curent incarcare <strong>{shownAmps} A</strong> <small>~{format(shownAmps * 0.69, 1)} kW</small></span>
        <input type="range" min={current.attributes.min ?? 0} max={Math.min(48, current.attributes.max ?? 16)} step={1} value={shownAmps} aria-label="Curent incarcare" onChange={(e) => setAmps(Number(e.target.value))} />
        {amps !== null && amps !== Number(current.state) && <button className="button primary" disabled={!!busy} onClick={() => send(current.entity_id, 'set_value', amps, `Setezi ${amps} A?`).then(() => setAmps(null))}>Aplica</button>}
      </div>}
      {climate && <div className="tesla-row-control">
        <span><Fan size={14} />Climatizare <strong>{climate.state === 'off' ? 'oprita' : 'pornita'}</strong> <small>interior {format(typeof climate.attributes.current_temperature === 'number' ? climate.attributes.current_temperature : null, 1)} °C</small></span>
        <span className="tesla-steps">
          <button className="button" disabled={!!busy || shownTemp === null} onClick={() => setTemp((shownTemp ?? 21) - 0.5)}>−</button>
          <strong>{format(shownTemp, 1)}°</strong>
          <button className="button" disabled={!!busy || shownTemp === null} onClick={() => setTemp((shownTemp ?? 21) + 0.5)}>+</button>
          {temp !== null && temp !== target && <button className="button primary" disabled={!!busy} onClick={() => send(climate.entity_id, 'set_temperature', temp, `Setezi ${format(temp, 1)}° in masina?`).then(() => setTemp(null))}>Aplica</button>}
          <button className="button" disabled={!!busy} onClick={() => send(climate.entity_id, climate.state === 'off' ? 'turn_on' : 'turn_off', undefined, climate.state === 'off' ? 'Pornesti climatizarea?' : 'Opresti climatizarea?')}>{climate.state === 'off' ? 'Porneste' : 'Opreste'}</button>
        </span>
      </div>}
      {all('cover').map((c) => <div className="tesla-row-control" key={c.entity_id}><span>{short(c)} <small>{c.state === 'open' ? 'deschis' : c.state === 'closed' ? 'inchis' : c.state}</small></span>
        <span className="tesla-steps">{button(c, 'Deschide', LockOpen, 'open_cover', `Deschizi ${short(c)}?`)}{button(c, 'Inchide', Lock, 'close_cover', `Inchizi ${short(c)}?`)}</span></div>)}
      {all('select').map((s) => <div className="tesla-row-control" key={s.entity_id}><span>{short(s)}</span>
        <span className="tesla-steps">{(s.attributes.options as string[] || []).map((o) => <button key={o} className={'button' + (s.state === o ? ' primary' : '')} disabled={!!busy || s.state === o} onClick={() => send(s.entity_id, 'select_option', o, `${short(s)}: ${o}?`)}>{o}</button>)}</span></div>)}
      {all('time').map((t) => <div className="tesla-row-control" key={t.entity_id}><span><Timer size={14} />{short(t)} <strong>{valid(t) ? t.state.slice(0, 5) : '--'}</strong></span>
        <input type="time" aria-label={short(t)} defaultValue={valid(t) ? t.state.slice(0, 5) : ''} onBlur={(e) => e.target.value && e.target.value !== t.state.slice(0, 5) && send(t.entity_id, 'set_value', e.target.value, `${short(t)} la ${e.target.value}?`)} /></div>)}
      {message && <small role="status">{message}</small>}
      <small className="tesla-sub">{WAKE} Fiecare comanda apare in jurnal.</small>
    </article>
  );
}
