import { useState } from 'react';
import { Area, Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Activity, ChartColumn, Table2 } from 'lucide-react';
import { format } from './model';

// Colors follow the entity everywhere in the app (see --energy-* tokens in theme.css).
const SERIES = [
  { key: 'solar', name: 'Productie solara', color: 'var(--energy-solar)' },
  { key: 'load', name: 'Consum casa', color: 'var(--energy-load)' },
  { key: 'battery', name: 'Din baterie', color: 'var(--energy-battery)' },
  { key: 'grid', name: 'Din retea', color: 'var(--energy-grid)' },
] as const;
type Key = typeof SERIES[number]['key'];
const PERIODS = [['day', 'Zi'], ['week', 'Saptamana'], ['month', 'Luna'], ['year', 'An']];
const zone = { timeZone: 'Europe/Bucharest' } as const;
const tickFormat: Record<string, Intl.DateTimeFormatOptions> = {
  day: { hour: '2-digit', minute: '2-digit' },
  week: { weekday: 'short', day: '2-digit' },
  month: { day: '2-digit', month: 'short' },
  year: { month: 'short', year: '2-digit' },
};
const labelFormat: Record<string, Intl.DateTimeFormatOptions> = {
  day: { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' },
  week: { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' },
  month: { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' },
  year: { month: 'long', year: 'numeric' },
};
const when = (time: number, period: string, labels = false) =>
  new Intl.DateTimeFormat('ro-RO', { ...zone, ...(labels ? labelFormat : tickFormat)[period] }).format(new Date(time));
const values = (points: any[], key: Key) => points.map(p => p[key]).filter((n): n is number => typeof n === 'number' && Number.isFinite(n));
const sum = (list: number[]) => list.length ? list.reduce((a, b) => a + b, 0) : null;
const mean = (list: number[]) => list.length ? sum(list)! / list.length : null;
const max = (list: number[]) => list.length ? Math.max(...list) : null;

type Props = {
  authenticated: boolean;
  history: { points: any[]; unit: string; period?: string } | null;
  loading: boolean;
  error: string;
  period: string;
  onPeriod: (period: string) => void;
};

export default function EnergyHistory({ authenticated, history, loading, error, period, onPeriod }: Props) {
  const [hidden, setHidden] = useState<Key[]>([]);
  const [table, setTable] = useState(false);
  const points = history?.points || [];
  const shownPeriod = history?.period || period;
  const unit = history?.unit || (period === 'day' ? 'kW' : 'kWh');
  const power = shownPeriod === 'day';
  const bars = shownPeriod === 'month' || shownPeriod === 'year';
  const visible = SERIES.filter(s => !hidden.includes(s.key));
  const toggle = (key: Key) => setHidden(list => list.includes(key) ? list.filter(k => k !== key) : list.length >= SERIES.length - 1 ? list : [...list, key]);
  const pairs = points.filter(p => typeof p.load === 'number' && typeof p.grid === 'number');
  const loadPaired = sum(pairs.map(p => p.load)), gridPaired = sum(pairs.map(p => p.grid));
  const ownShare = !power && loadPaired !== null && gridPaired !== null && loadPaired > 0 ? Math.max(0, Math.min(100, (1 - gridPaired / loadPaired) * 100)) : null;
  // Day statistics are 5-minute means (kW, power); longer periods are energy changes (kWh).
  const summary: [string, number | null, string, string][] = power ? [
    ['Varf solar', max(values(points, 'solar')), 'kW', 'solar'],
    ['Consum mediu', mean(values(points, 'load')), 'kW', 'load'],
    ['Varf consum', max(values(points, 'load')), 'kW', 'load'],
    ['Din retea, mediu', mean(values(points, 'grid')), 'kW', 'grid'],
  ] : [
    ['Produs solar', sum(values(points, 'solar')), 'kWh', 'solar'],
    ['Consum casa', sum(values(points, 'load')), 'kWh', 'load'],
    ['Din baterie', sum(values(points, 'battery')), 'kWh', 'battery'],
    ['Din retea', sum(values(points, 'grid')), 'kWh', 'grid'],
    ['Fara retea', ownShare, '%', 'share'],
  ];
  const tooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const row = payload[0].payload;
    return <div className="history-tooltip">
      <span className="history-tooltip-time">{when(Number(label), shownPeriod, true)}</span>
      {visible.map(s => <div key={s.key}><i style={{ background: s.color }} /><strong>{typeof row[s.key] === 'number' ? format(row[s.key], 2) : '--'}<small> {unit}</small></strong><span>{s.name}</span></div>)}
    </div>;
  };
  const empty = !authenticated ? 'Istoricul este disponibil dupa autentificare.' : error || (history ? 'Nu exista inca statistici pentru aceasta perioada.' : 'Se incarca istoricul...');
  return <section className="chart-section history-chart" aria-busy={loading}>
    <div className="section-top">
      <div><span className="eyebrow">ANALIZA ENERGETICA</span><h2>{power ? 'Putere in ultimele 24 de ore' : 'Energie in perioada selectata'}</h2></div>
      <div className="segmented" aria-label="Perioada">{PERIODS.map(([key, title]) => <button key={key} className={period === key ? 'selected' : ''} aria-pressed={period === key} onClick={() => onPeriod(key)}>{title}</button>)}</div>
    </div>
    {points.length > 0 && <div className="history-summary">{summary.map(([title, n, u, key]) => <div key={title} className={'history-stat ' + key}><span>{title}</span><strong>{format(n, u === '%' ? 0 : n !== null && Math.abs(n) >= 100 ? 0 : 1)}<small> {u}</small></strong>{key === 'share' && <small>din consum, calculat</small>}</div>)}</div>}
    {points.length > 0 && <div className="history-toolbar">
      <div className="history-legend" role="group" aria-label="Serii afisate">{SERIES.map(s => <button key={s.key} aria-pressed={!hidden.includes(s.key)} title={hidden.includes(s.key) ? 'Afiseaza ' + s.name : 'Ascunde ' + s.name} onClick={() => toggle(s.key)}><i className={bars || s.key === 'solar' ? 'key-fill' : 'key-line'} style={{ background: s.color }} />{s.name}</button>)}</div>
      <div className="history-view" role="group" aria-label="Mod afisare istoric">
        <button aria-pressed={!table} title="Grafic" aria-label="Grafic" onClick={() => setTable(false)}><ChartColumn size={15} /></button>
        <button aria-pressed={table} title="Tabel" aria-label="Tabel" onClick={() => setTable(true)}><Table2 size={15} /></button>
      </div>
    </div>}
    <div className={'chart-container' + (loading && points.length ? ' refreshing' : '') + (table && points.length ? ' as-table' : '')}>
      {!points.length ? <div className="empty-chart"><Activity size={27} /><span>{empty}</span></div>
        : table ? <div className="history-table-wrap"><table className="history-table"><thead><tr><th>Moment</th>{visible.map(s => <th key={s.key}>{s.name} <small>{unit}</small></th>)}</tr></thead>
          <tbody>{[...points].reverse().map(p => <tr key={p.time}><td>{when(p.time, shownPeriod, true)}</td>{visible.map(s => <td key={s.key}>{typeof p[s.key] === 'number' ? format(p[s.key], 2) : '--'}</td>)}</tr>)}</tbody></table></div>
        : <><span className="chart-unit" aria-hidden="true">{unit}</span><ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ left: 0, right: 12, top: 22, bottom: 0 }} barGap={2} barCategoryGap="22%">
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis dataKey="time" tickFormatter={(v: number) => when(v, shownPeriod)} tick={{ fontSize: 11, fill: 'var(--muted)' }} axisLine={{ stroke: 'var(--chart-grid)' }} tickLine={false} minTickGap={36} />
            <YAxis tickFormatter={(v: number) => format(v, 1)} tick={{ fontSize: 11, fill: 'var(--muted)' }} axisLine={false} tickLine={false} width={44} />
            <Tooltip content={tooltip} cursor={bars ? { fill: 'var(--chart-hover)' } : { stroke: 'var(--muted)', strokeWidth: 1 }} isAnimationActive={false} />
            {visible.map(s => bars
              ? <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
              : s.key === 'solar'
                ? <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} fill={s.color} fillOpacity={0.12} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface-solid)' }} connectNulls={false} isAnimationActive={false} />
                : <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} strokeLinecap="round" dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface-solid)' }} connectNulls={false} isAnimationActive={false} />)}
          </ComposedChart>
        </ResponsiveContainer></>}
    </div>
  </section>;
}
