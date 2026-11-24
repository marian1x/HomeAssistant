import { useEffect, useState } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Activity, BatteryCharging, BatteryFull, Bluetooth, CircleAlert, Flame, Gauge, HeartPulse, Info, Settings2, ShieldCheck, Snowflake, Thermometer, Zap } from 'lucide-react';
import { type Snapshot, type State, format, number, valid } from './model';
import { Num } from './motion';

type BmsPack = { cells: number[]; cell_temps: number[]; cell_min?: number; cell_max?: number; cell_spread_mv?: number;
  soc?: number; soh?: number; cycles?: number; current?: number; voltage?: number; remaining_ah?: number; mos_temp?: number };
type BmsCtrl = { firmware?: string; heater_on_below?: number; heater_off_above?: number; charge_lowtemp_protect?: number;
  charge_lowtemp_protect_recover?: number; charge_current_limit?: number; discharge_current_limit?: number };
type Bms = { available: boolean; status: string; poll_seconds?: number;
  latest: { ts: number; pack: BmsPack; controller?: BmsCtrl; heater_phase?: string } | null };

function BmsSection({ bms }: { bms: Bms | null }) {
  if (!bms) return null;
  const latest = bms.latest;
  const p = latest?.pack, c = latest?.controller;
  const cells = p?.cells || [];
  const lo = p?.cell_min, hi = p?.cell_max;
  const ago = latest ? Math.round((Date.now() - latest.ts * 1000) / 60000) : null;
  return (
    <section className="chart-section battery-ble" aria-label="Celule prin Bluetooth">
      <header className="battery-history-head">
        <div><span className="eyebrow">CELULE · BLUETOOTH DIRECT</span><h2>Date pe celule de la BMS</h2></div>
        <span className={'tesla-status ' + (bms.available ? 'on' : 'off')}><Bluetooth size={15} />{bms.available ? (ago !== null ? `acum ${ago} min` : 'citit') : 'indisponibil'}</span>
      </header>
      {!bms.available || !p ? <p className="battery-chart-empty" style={{ height: 'auto', padding: '18px' }}>{bms.status || 'Fara citire Bluetooth inca.'} Cat timp aplicatia ENW este conectata pe Bluetooth, citirea casei asteapta.</p> : <>
        <div className="battery-cells" role="img" aria-label={`16 celule intre ${format(lo ?? null, 3)} si ${format(hi ?? null, 3)} volti, diferenta ${format(p.cell_spread_mv ?? null, 0)} milivolti`}>
          {cells.map((v, i) => {
            const frac = hi && lo && hi > lo ? (v - lo) / (hi - lo) : 0.5;
            const tag = v === hi ? 'high' : v === lo ? 'low' : '';
            return <div key={i} className={'battery-cell ' + tag}><span className="cv">{format(v, 3)}</span>
              <div className="cell-bar"><i style={{ height: (40 + frac * 60) + '%' }} /></div><span className="cn">C{String(i + 1).padStart(2, '0')}</span></div>;
          })}
        </div>
        <div className="battery-ble-grid">
          <div className="ble-stat"><span>Diferenta celule</span><strong>{format(p.cell_spread_mv ?? null, 0)}<small> mV</small></strong><small>{format(lo ?? null, 3)}–{format(hi ?? null, 3)} V</small></div>
          <div className="ble-stat"><span>Temperaturi celule</span><strong>{(p.cell_temps || []).map((t) => format(t, 1)).join(' · ') || '--'}<small> °C</small></strong><small>{p.mos_temp !== undefined ? 'placa ' + format(p.mos_temp, 1) + ' °C' : 'pe senzor'}</small></div>
          <div className="ble-stat"><span><Flame size={13} />Incalzire</span><strong className="heater">{latest?.heater_phase || '--'}</strong><small>logica fixa, cere incarcare activa</small></div>
        </div>
        <div className="battery-settings">
          <h3><Settings2 size={15} />Setari BMS (doar citire)</h3>
          <dl>
            {c?.firmware && <div><dt>Firmware</dt><dd>{c.firmware}</dd></div>}
            <div><dt>Incalzire pornita sub</dt><dd>{c?.heater_on_below !== undefined ? format(c.heater_on_below, 0) + ' °C' : '--'}</dd></div>
            <div><dt>Incalzire oprita peste</dt><dd>{c?.heater_off_above !== undefined ? format(c.heater_off_above, 0) + ' °C' : '--'}</dd></div>
            <div><dt>Protectie incarcare la frig</dt><dd>{c?.charge_lowtemp_protect !== undefined ? format(c.charge_lowtemp_protect, 0) + ' °C' : '--'}{c?.charge_lowtemp_protect_recover !== undefined ? ' (revine ' + format(c.charge_lowtemp_protect_recover, 0) + ' °C)' : ''}</dd></div>
            <div><dt>Limita curent incarcare</dt><dd>{c?.charge_current_limit !== undefined ? format(c.charge_current_limit, 0) + ' A' : '--'}</dd></div>
            <div><dt>Limita curent descarcare</dt><dd>{c?.discharge_current_limit !== undefined ? format(Math.abs(c.discharge_current_limit), 0) + ' A' : '--'}</dd></div>
          </dl>
          <p className="battery-note" style={{ marginTop: '8px' }}><Info size={14} />Valorile din „Setari BMS” sunt deduse din citire, nu confirmate de aplicatie. Nimic nu se scrie in baterie.</p>
        </div>
      </>}
    </section>
  );
}

/* Battery panel: everything the BMS forwards through the Deye inverter (Solarman
   attributes of sensor.deye_battery) plus the inverter's own battery readings.
   Read-only. Cell voltages and cell temperatures are NOT forwarded by this battery
   to the inverter (module registers read 0), so they are not shown or invented. */

const BASE = import.meta.env.BASE_URL;
type Point = { time: number; soc?: number | null; temp?: number | null; power?: number | null; charge_limit?: number | null; discharge_limit?: number | null };
const clock = (time: number) => new Intl.DateTimeFormat('ro-RO', { timeZone: 'Europe/Bucharest', hour: '2-digit', minute: '2-digit' }).format(time);

function Spark({ points, field, name, unit, color, digits = 1, domain, step }: { points: Point[]; field: keyof Point; name: string; unit: string; color: string; digits?: number; domain?: [number | string, number | string]; step?: boolean }) {
  const shown = points.some((p) => typeof p[field] === 'number');
  return (
    <figure className="battery-chart">
      <figcaption><span><i style={{ background: color }} />{name}</span><small>{unit}</small></figcaption>
      {shown ? <div className="battery-chart-body"><ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="time" tickFormatter={clock} tick={{ fontSize: 11, fill: 'var(--muted)' }} axisLine={{ stroke: 'var(--chart-grid)' }} tickLine={false} minTickGap={48} />
          <YAxis domain={domain || ['auto', 'auto']} tickFormatter={(v: number) => format(v, digits > 1 ? 1 : 0)} tick={{ fontSize: 11, fill: 'var(--muted)' }} axisLine={false} tickLine={false} width={40} />
          <Tooltip isAnimationActive={false} cursor={{ stroke: 'var(--muted)', strokeWidth: 1 }}
            content={({ active, payload }: any) => active && payload?.length ? <div className="history-tooltip"><span className="history-tooltip-time">{clock(payload[0].payload.time)}</span><div><i style={{ background: color }} /><span>{name}</span><strong>{format(payload[0].value, digits)} <small>{unit}</small></strong></div></div> : null} />
          <Line type={step ? 'stepAfter' : 'monotone'} dataKey={field as string} stroke={color} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer></div> : <p className="battery-chart-empty">Fara date in interval.</p>}
    </figure>
  );
}

export default function Battery({ data }: { data: Snapshot | null }) {
  const [hours, setHours] = useState(24), [points, setPoints] = useState<Point[]>([]), [error, setError] = useState('');
  const [bms, setBms] = useState<Bms | null>(null);
  useEffect(() => {
    if (!data) return;
    let alive = true;
    fetch(BASE + 'api/battery/history?hours=' + hours).then(async (r) => {
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw Error(body.error || 'Istoricul bateriei nu este disponibil.');
      if (alive) { setPoints(body.points || []); setError(''); }
    }).catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [hours, !!data]);
  useEffect(() => {
    if (!data) return;
    let alive = true;
    const load = () => fetch(BASE + 'api/battery/bms').then((r) => r.ok ? r.json() : null).then((b) => alive && b && setBms(b)).catch(() => {});
    load();
    const timer = setInterval(load, 30000);
    return () => { alive = false; clearInterval(timer); };
  }, [!!data]);
  const st = (id: string): State | undefined => data?.states[id];
  const n = (id: string) => number(st(id));
  const main = st('sensor.deye_battery'), a = main?.attributes || {};
  const attr = (key: string) => (typeof a[key] === 'number' && Number.isFinite(a[key]) ? a[key] as number : null);
  const soc = n('sensor.deye_battery'), power = n('sensor.deye_battery_power'), voltage = n('sensor.deye_battery_voltage');
  const current = n('sensor.deye_battery_current'), temp = n('sensor.deye_battery_temperature');
  const chg = attr('BMS Charging Current'), chgMax = attr('BMS Max Charging Current'), dis = attr('BMS Discharging Current'), disMax = attr('BMS Max Discharging Current');
  const chgV = attr('BMS Charging Voltage'), bmsSoc = attr('BMS SOC'), bmsV = attr('BMS Voltage'), bmsA = attr('BMS Current'), symbol = attr('BMS Other Symbol');
  const capacityAh = attr('Corrected Capacity'), nominal = attr('Nominal Voltage'), rating = attr('Life Cycle Rating');
  const cycles = n('sensor.deye_total_battery_life_cycles'), soh = n('sensor.deye_battery_soh');
  const reserve = st('sensor.home_energy_policy_status')?.attributes.battery_reserve_soc;
  const alarm = st('binary_sensor.deye_battery_alarm'), fault = st('binary_sensor.deye_battery_fault');
  // Deye battery power: negative = charging, positive = discharging.
  const mode = power === null ? 'unknown' : power < -50 ? 'charging' : power > 50 ? 'discharging' : 'idle';
  const label = { charging: 'Se incarca', discharging: 'Se descarca', idle: 'In repaus', unknown: 'Fara citire' }[mode];
  const level = soc === null ? 0 : Math.max(0, Math.min(100, soc));
  const limitedCharge = chg !== null && chgMax !== null && chgMax > 0 && chg < chgMax * 0.5;
  const limitedDischarge = dis !== null && disMax !== null && disMax > 0 && dis < disMax * 0.5;
  const kw = (amps: number | null) => (amps === null || voltage === null ? null : (amps * voltage) / 1000);
  const meter = (value: number | null, max: number | null) => (value === null || !max ? 0 : Math.max(0, Math.min(100, (value / max) * 100)));
  const stored = soc !== null && capacityAh !== null && nominal !== null ? (soc / 100) * capacityAh * nominal / 1000 : null;
  return (
    <section className="battery-page" aria-label="Baterie">
      <header className="tesla-head">
        <div><span className="eyebrow">STOCARE</span><h1>Easyway UNIV-16kWh (WP)</h1>
          <p className="tesla-note">Date de la BMS, transmise prin invertorul Deye. Doar citire.</p></div>
        <span className={'tesla-status ' + (mode === 'idle' || mode === 'unknown' ? 'off' : 'on')}><Activity size={15} />{label}</span>
      </header>

      {(limitedCharge || limitedDischarge) && <div className="battery-alert" role="status">
        <Snowflake size={18} />
        <span>BMS-ul limiteaza {limitedCharge ? `incarcarea la ${format(chg, 0)} A (~${format(kw(chg), 1)} kW) din ${format(chgMax, 0)} A` : ''}{limitedCharge && limitedDischarge ? ' si ' : ''}{limitedDischarge ? `descarcarea la ${format(dis, 0)} A din ${format(disMax, 0)} A` : ''}{temp !== null ? `; temperatura bateriei ${format(temp, 1)} °C.` : '.'} Este protectia bateriei, nu o setare a aplicatiei.</span>
      </div>}

      <div className="battery-grid">
        <article className="tesla-card battery-hero">
          <span className="tesla-label"><BatteryFull size={16} />Nivel</span>
          <div className="battery-gauge" role="img" aria-label={soc === null ? 'Nivel necunoscut' : `Nivel ${format(soc, 0)}%` + (typeof reserve === 'number' ? `, rezerva ${format(reserve, 0)}%` : '')}>
            <i className={mode} style={{ height: level + '%' }} />
            {typeof reserve === 'number' && <b style={{ bottom: Math.max(0, Math.min(100, reserve)) + '%' }}><span>rezerva {format(reserve, 0)}%</span></b>}
          </div>
          <strong><Num value={soc} digits={0} /><small> %</small></strong>
          <dl>
            <div><dt>Energie stocata</dt><dd>{format(stored, 1)} kWh</dd></div>
            <div><dt>Putere</dt><dd>{power === null ? '--' : format(Math.abs(power) / 1000, 2) + ' kW'}</dd></div>
          </dl>
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><Zap size={16} />Electric</span>
          <dl>
            <div><dt>Tensiune</dt><dd>{format(voltage, 2)} V</dd></div>
            <div><dt>Curent</dt><dd>{format(current, 1)} A</dd></div>
            <div><dt>Tensiune BMS</dt><dd>{format(bmsV, 2)} V</dd></div>
            <div><dt>Curent BMS</dt><dd>{format(bmsA, 1)} A</dd></div>
            <div><dt>SOC raportat de BMS</dt><dd>{format(bmsSoc, 0)} %</dd></div>
          </dl>
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><Thermometer size={16} />Temperatura</span>
          <strong><Num value={temp} digits={1} /><small> °C</small></strong>
          <span className="tesla-sub">Senzor de pachet (prin invertor). Temperaturile pe celule apar mai jos, prin Bluetooth.</span>
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><Gauge size={16} />Limite cerute de BMS</span>
          <div className="battery-limit"><span>Incarcare</span><strong>{format(chg, 0)} <small>/ {format(chgMax, 0)} A</small></strong><div className={'battery-bar' + (limitedCharge ? ' low' : '')}><i style={{ width: meter(chg, chgMax) + '%' }} /></div></div>
          <div className="battery-limit"><span>Descarcare</span><strong>{format(dis, 0)} <small>/ {format(disMax, 0)} A</small></strong><div className={'battery-bar' + (limitedDischarge ? ' low' : '')}><i style={{ width: meter(dis, disMax) + '%' }} /></div></div>
          <dl><div><dt>Tensiune maxima de incarcare</dt><dd>{format(chgV, 1)} V</dd></div></dl>
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><HeartPulse size={16} />Sanatate</span>
          <strong><Num value={soh} digits={1} /><small> % SOH</small></strong>
          <dl>
            <div><dt>Cicluri complete</dt><dd>{format(cycles, 1)}{rating ? ' din ' + format(rating, 0) : ''}</dd></div>
            <div><dt>Capacitate estimata</dt><dd>{format(capacityAh, 0)} Ah{capacityAh !== null && nominal !== null ? ` · ${format(capacityAh * nominal / 1000, 1)} kWh` : ''}</dd></div>
            <div><dt>Cicluri azi</dt><dd>{format(n('sensor.deye_today_battery_life_cycles'), 2)}</dd></div>
          </dl>
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><BatteryCharging size={16} />Energie</span>
          <dl>
            <div><dt>Incarcat azi</dt><dd>{format(n('sensor.deye_today_battery_charge'), 1)} kWh</dd></div>
            <div><dt>Descarcat azi</dt><dd>{format(n('sensor.deye_today_battery_discharge'), 1)} kWh</dd></div>
            <div><dt>Incarcat total</dt><dd>{format(n('sensor.deye_total_battery_charge'), 0)} kWh</dd></div>
            <div><dt>Descarcat total</dt><dd>{format(n('sensor.deye_total_battery_discharge'), 0)} kWh</dd></div>
          </dl>
        </article>
        <article className="tesla-card">
          <span className="tesla-label"><ShieldCheck size={16} />Protectie</span>
          <dl>
            <div><dt>Alarma baterie</dt><dd className={alarm?.state === 'on' ? 'warn' : ''}>{!valid(alarm) ? '--' : alarm!.state === 'on' ? 'Activa' : 'Nu'}</dd></div>
            <div><dt>Defect baterie</dt><dd className={fault?.state === 'on' ? 'warn' : ''}>{!valid(fault) ? '--' : fault!.state === 'on' ? 'Activ' : 'Nu'}</dd></div>
            <div><dt>Indicatori BMS</dt><dd>{symbol === null ? '--' : symbol === 0 ? 'Niciunul' : 'Cod ' + symbol}</dd></div>
            <div><dt>Rezerva politicii</dt><dd>{typeof reserve === 'number' ? format(reserve, 0) + ' %' : '--'}</dd></div>
          </dl>
        </article>
      </div>

      <section className="chart-section battery-history" aria-label="Istoric baterie">
        <header className="battery-history-head"><div><span className="eyebrow">ISTORIC</span><h2>Ultimele {hours} de ore</h2></div>
          <div className="history-view" role="group" aria-label="Interval">{[24, 48].map((h) => <button key={h} aria-pressed={hours === h} onClick={() => setHours(h)} style={{ width: 'auto', padding: '0 10px' }}>{h} h</button>)}</div></header>
        {error ? <p className="form-error" role="alert">{error}</p> : <div className="battery-charts">
          <Spark points={points} field="temp" name="Temperatura bateriei" unit="°C" color="var(--energy-grid)" />
          <Spark points={points} field="charge_limit" name="Limita BMS de incarcare" unit="A" color="var(--energy-load)" digits={0} domain={[0, 'auto']} step />
          <Spark points={points} field="soc" name="Nivel" unit="%" color="var(--energy-battery)" digits={0} domain={[0, 100]} />
          <Spark points={points.map((p) => ({ ...p, power: typeof p.power === 'number' ? p.power / 1000 : p.power }))} field="power" name="Putere (+ descarcare, − incarcare)" unit="kW" color="var(--energy-solar)" digits={2} />
        </div>}
      </section>

      <BmsSection bms={bms} />

      <p className="battery-note"><Info size={15} />Valorile de pachet (sus) vin prin invertorul Deye. Datele pe celule (tensiuni, temperaturi, incalzire, setari) vin direct de la BMS prin Bluetooth, citite de Home Assistant la cateva minute, fara sa scrie nimic.</p>
      {(alarm?.state === 'on' || fault?.state === 'on') && <p className="form-error" role="alert"><CircleAlert size={15} /> BMS-ul raporteaza o alarma sau un defect. Verifica bateria.</p>}
    </section>
  );
}
