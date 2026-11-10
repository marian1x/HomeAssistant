import { useEffect, useState } from 'react';
import { Area, Bar, Brush, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowDownLeft, ArrowUpRight, CalendarDays, ChevronLeft, ChevronRight, Cloud, Download, Filter, RefreshCw, Save, SlidersHorizontal, Sun, Thermometer, Wallet } from 'lucide-react';
import type { Snapshot } from './model';
import './energy-economics.css';

const BASE = import.meta.env.BASE_URL + 'api/';
const iso = (d: Date) => new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Bucharest',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);
const today = () => iso(new Date());
const money = (n: any, digits = 2) => typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('ro-RO',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '...';
const short = (d: string) => d ? new Date(d+'T12:00:00').toLocaleDateString('ro-RO',{day:'2-digit',month:'short'}) : '';
const energy = (n: any) => money(n,1);
const hour = (n: number) => new Date(n).toLocaleTimeString('ro-RO',{timeZone:'Europe/Bucharest',hour:'2-digit',minute:'2-digit'});

function Chart({children}: {children: any}) {
  return <div className="finance-chart"><ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer></div>;
}

export default function EnergyEconomics({snapshot, canConfigure, openPolicy}: {snapshot: Snapshot; canConfigure: boolean; openPolicy: () => void}) {
  const [view,setView] = useState('balance');
  const [query,setQuery] = useState({start:today().slice(0,8)+'01',end:today(),mode:'historical'});
  const [draft,setDraft] = useState(query);
  const [data,setData] = useState<any>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const [refresh,setRefresh] = useState(0);
  const [selected,setSelected] = useState('');
  const [detail,setDetail] = useState<any>(null);
  const [price,setPrice] = useState({energy_import_price:1.11,energy_export_price:.45,energy_tariff_from:today()});
  const [priceDirty,setPriceDirty] = useState(false);
  const [saving,setSaving] = useState(false);
  const [page,setPage] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);setError('');setData(null);
    fetch(BASE+'v1/energy-dashboard?'+new URLSearchParams(query),{signal:controller.signal}).then(async r => {
      const body = await r.json();
      if (!r.ok) throw new Error(body.error || 'Raportul nu este disponibil.');
      return body;
    }).then(body => {
      setData(body);setDetail(null);setPage(0);
      setSelected((body.report.days.filter((d:any) => d.load_kwh != null).at(-1) || {}).date || '');
      if (!priceDirty) setPrice({energy_import_price:body.pricing.active.import_price,energy_export_price:body.pricing.active.export_price,energy_tariff_from:today()});
    }).catch(e => {if (e.name !== 'AbortError')setError(e.message);}).finally(() => {if (!controller.signal.aborted)setLoading(false);});
    return () => controller.abort();
  }, [query,refresh,snapshot.connected]);
  useEffect(() => {const timer = setInterval(() => setRefresh(n => n+1),300000);return () => clearInterval(timer);},[]);
  useEffect(() => {
    if (!selected || !data) return;
    setDetail(null);
    if (data.report.hours.some((h:any) => h.date === selected)) return;
    const controller = new AbortController();
    fetch(BASE+'v1/energy-dashboard?'+new URLSearchParams({start:selected,end:selected,mode:query.mode}),{signal:controller.signal})
      .then(async r => {const body = await r.json();if(!r.ok)throw new Error(body.error || 'Zi indisponibila.');return body;})
      .then(body => setDetail(body.report)).catch(e => {if(e.name!=='AbortError')setError(e.message);});
    return () => controller.abort();
  }, [selected,data]);
  useEffect(() => {if (!canConfigure)setPriceDirty(false);},[canConfigure]);
  function preset(kind: string) {
    const end = today();let start = end;
    if(kind==='week'){const d=new Date(end+'T12:00:00');d.setDate(d.getDate()-6);start=iso(d);}
    if(kind==='month')start=end.slice(0,8)+'01';
    if(kind==='year')start=end.slice(0,4)+'-01-01';
    const value={start,end,mode:draft.mode};setDraft(value);setQuery(value);
  }
  async function savePrice() {
    if(!canConfigure || !data || !priceDirty || !window.confirm('Salvezi tariful de la data selectata? Rapoartele pentru acea perioada vor fi recalculate.'))return;
    setSaving(true);setError('');
    try {
      const r=await fetch(BASE+'v1/energy-policy',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':snapshot.csrf},body:JSON.stringify({revision:data.pricing.revision,values:price})});
      const body=await r.json();if(!r.ok)throw new Error(body.error || 'Tariful nu a fost salvat.');
      setPriceDirty(false);setRefresh(n=>n+1);
    }catch(e:any){setError(e.message);}finally{setSaving(false);}
  }
  function download() {
    if(!data)return;
    let fields=['date','solar_kwh','load_kwh','import_kwh','export_kwh','boiler_kwh','import_price','export_price','import_cost_ron','export_income_ron','balance_ron','savings_ron','temperature','clouds','coverage_pct','tariff_assumed','complete','tariff_mode'];
    let records=data.report.days.map((d:any)=>({...d,tariff_mode:data.report.tariff_mode}));
    let filename=`energie_${query.mode}_${query.start}_${query.end}.csv`;
    if(view==='forecast'){
      fields=['date','solar_kwh','load_kwh','load_low_kwh','load_high_kwh','import_kwh','export_kwh','balance_ron','battery_end_soc','temperature_min','temperature_max','clouds','confidence'];
      records=data.outlook.days;filename=`prognoza_${today()}.csv`;
    }else if(view==='consumption'){
      fields=['timestamp_utc','solar_kwh','load_kwh','import_kwh','export_kwh','boiler_kwh'];
      records=hours.map((h:any)=>({...h,timestamp_utc:new Date(h.time).toISOString()}));filename=`consum_orar_${selected}.csv`;
    }
    const quote=(v:any)=>v==null?'':`"${String(v).replaceAll('"','""')}"`;
    const csv='\uFEFF'+[fields.join(','),...records.map((d:any)=>fields.map(k=>quote(typeof d[k]==='number'?Number(d[k].toFixed(4)):d[k])).join(','))].join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  const report=data?.report;
  const totals=report?.totals || {};
  const rows=report?.days || [];
  const plotted=rows.map((r:any)=>({...r,expense:r.import_cost_ron==null?null:-r.import_cost_ron}));
  const dayReport=detail || report;
  const hours=(dayReport?.hours || []).filter((h:any)=>h.date===selected);
  const selectedDay=dayReport?.days.find((d:any)=>d.date===selected);
  const peak=hours.filter((h:any)=>h.load_kwh!=null).reduce((best:any,h:any)=>!best||h.load_kwh>best.load_kwh?h:best,null);
  const night=hours.filter((h:any)=>{const h0=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Bucharest',hour:'2-digit',hourCycle:'h23'}).format(new Date(h.time)));return h0<7||h0>=22;}).reduce((sum:number,h:any)=>sum+(h.load_kwh||0),0);
  const pending=loading || !snapshot.connected;
  return <div className="finance-page">
    <header className="finance-heading"><div><span className="eyebrow">ENERGIA CASEI</span><h1>Costuri si prognoza</h1><small>{report?.data_through ? 'Date pana la '+new Date(report.data_through).toLocaleString('ro-RO',{timeZone:'Europe/Bucharest',dateStyle:'short',timeStyle:'short'}) : 'Contoare Deye'}</small></div><div className="finance-tools"><button className="icon-button" title="Parametri energie si confort" onClick={openPolicy}><SlidersHorizontal size={19}/></button><button className="icon-button" title="Export CSV" disabled={!data||loading} onClick={download}><Download size={19}/></button><button className="icon-button" title="Reincarca raportul" disabled={pending} onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={19} className={loading?'spin':''}/></button></div></header>
    <div className="finance-tabs" role="tablist" aria-label="Analiza energiei">{[['balance','Bilant financiar'],['consumption','Consum pe zile'],['forecast','Prognoza 6 zile']].map(([key,title])=><button key={key} role="tab" aria-selected={view===key} onClick={()=>setView(key)}>{title}</button>)}</div>
    {view!=='forecast' && <form className="finance-period" onSubmit={e=>{e.preventDefault();setQuery({...draft});}}><div className="finance-presets">{[['today','Azi'],['week','7 zile'],['month','Luna'],['year','An']].map(([key,title])=><button type="button" key={key} onClick={()=>preset(key)}>{title}</button>)}</div><label>De la<input type="date" aria-label="Costuri de la" value={draft.start} max={today()} required onChange={e=>setDraft(d=>({...d,start:e.target.value}))}/></label><label>Pana la<input type="date" aria-label="Costuri pana la" value={draft.end} min={draft.start} max={today()} required onChange={e=>setDraft(d=>({...d,end:e.target.value}))}/></label><label>Calcul<select aria-label="Mod calcul tarife" value={draft.mode} onChange={e=>setDraft(d=>({...d,mode:e.target.value}))}><option value="historical">Tarife istorice</option><option value="current">Simulare la pretul actual</option></select></label><button className="icon-button" title="Aplica intervalul" disabled={pending}><Filter size={19}/></button></form>}
    {error && <p className="finance-warning" role="alert">{error}</p>}
    {loading && <p role="status" className="finance-loading">Se incarca datele din Home Assistant...</p>}
    {data && <>
      {view!=='forecast'&&<p className="finance-note">Interval aplicat: {report.start} - {report.end} · {report.tariff_mode==='current'?'Simulare la tariful actual':'Tarife inregistrate'}</p>}
      {view!=='forecast' && <div className="finance-summary"><div><span><Wallet size={16}/>Sold interval</span><strong className={totals.balance_ron>=0?'positive':'negative'}>{money(totals.balance_ron)} <small>lei</small></strong><small>{totals.balance_ron==null?'Fara date':totals.balance_ron>=0?'Credit energetic estimat':'De plata, estimat'}</small></div><div><span><ArrowDownLeft size={16}/>Cumparat</span><strong>{money(totals.import_cost_ron)} <small>lei</small></strong><small>{energy(totals.import_kwh)} kWh din retea</small></div><div><span><ArrowUpRight size={16}/>Injectat</span><strong>{money(totals.export_income_ron)} <small>lei</small></strong><small>{energy(totals.export_kwh)} kWh in retea</small></div><div><span><CalendarDays size={16}/>Luna in curs</span><strong>{money(data.month.totals.balance_ron)} <small>lei</small></strong><small>{short(data.month.start)} - {short(data.month.end)} · pana azi</small></div></div>}
      {view==='balance' && <>
        <div className="finance-savings"><span>Economie estimata fata de alimentarea integrala din retea</span><strong>{money(totals.savings_ron)} lei</strong></div>
        <section className="finance-section"><header><h2>Sold energetic pe zile</h2><span>{report.complete_days}/{report.total_days} zile cu acoperire completa</span></header><Chart><ComposedChart data={plotted} margin={{top:8,right:12,left:0,bottom:0}}><CartesianGrid stroke="var(--chart-grid)" vertical={false}/><XAxis dataKey="date" tickFormatter={short} minTickGap={35}/><YAxis width={55} unit=" lei"/><Tooltip labelFormatter={v=>short(String(v))} formatter={(v:any)=>[money(v)+' lei','Sold']}/><ReferenceLine y={0} stroke="var(--muted)"/><Bar dataKey="balance_ron" name="Venit minus cost" maxBarSize={30} onClick={(entry:any)=>{const day=entry?.date||entry?.payload?.date;if(day){setSelected(day);setView('consumption');}}}>{plotted.map((r:any)=><Cell key={r.date} fill={r.balance_ron>=0?'var(--status-good)':'var(--status-bad)'}/>)}</Bar>{rows.length>45&&<Brush dataKey="date" height={22} startIndex={Math.max(0,rows.length-45)} tickFormatter={short}/>}</ComposedChart></Chart><p className="finance-note">Verde: credit estimat. Rosu: cost net. Calculul nu include alte taxe, regularizari, investitia in panouri sau soldul facturilor furnizorului.</p></section>
        {(report.complete_days<report.total_days||rows.some((r:any)=>r.tariff_assumed))&&<p className="finance-warning">{report.complete_days<report.total_days?'Intervalul contine zile partiale sau fara istoric; lipsurile nu sunt considerate consum zero. ':''}{rows.some((r:any)=>r.tariff_assumed)?'Pentru perioadele fara tarif inregistrat este folosit tariful initial estimat.':''}</p>}
        <section className="finance-section"><header><h2>Productie si consum</h2><span>kWh / zi</span></header><Chart><ComposedChart data={rows} margin={{top:8,right:12,left:0,bottom:0}}><CartesianGrid stroke="var(--chart-grid)" vertical={false}/><XAxis dataKey="date" tickFormatter={short} minTickGap={35}/><YAxis width={50}/><Tooltip labelFormatter={v=>short(String(v))} formatter={(v:any,n:any)=>[energy(v)+' kWh',n]}/><Legend/><Bar dataKey="import_kwh" name="Din retea" fill="var(--energy-grid)" maxBarSize={18}/><Bar dataKey="export_kwh" name="Injectie" fill="var(--energy-export)" maxBarSize={18}/><Line dataKey="solar_kwh" name="Solar" stroke="var(--energy-solar)" dot={false} strokeWidth={2} connectNulls={false}/><Line dataKey="load_kwh" name="Consum casa" stroke="var(--energy-load)" dot={false} strokeWidth={2} connectNulls={false}/>{rows.length>45&&<Brush dataKey="date" height={22} startIndex={Math.max(0,rows.length-45)} tickFormatter={short}/>}</ComposedChart></Chart></section>
        <section className="finance-section"><header><h2>Registru zilnic</h2><div className="finance-tools"><small>{page*30+1}-{Math.min(rows.length,(page+1)*30)} / {rows.length}</small><button className="icon-button" title="Zile precedente" disabled={page===0} onClick={()=>setPage(p=>p-1)}><ChevronLeft size={18}/></button><button className="icon-button" title="Zile urmatoare" disabled={(page+1)*30>=rows.length} onClick={()=>setPage(p=>p+1)}><ChevronRight size={18}/></button></div></header><div className="finance-table-wrap"><table className="finance-table"><thead><tr>{['Data','Solar kWh','Consum kWh','Import kWh','Export kWh','Cost lei','Venit lei','Sold lei'].map(t=><th key={t}>{t}</th>)}</tr></thead><tbody>{rows.slice(page*30,(page+1)*30).map((r:any)=><tr key={r.date}><td><button onClick={()=>{setSelected(r.date);setView('consumption');}}>{short(r.date)}</button></td>{['solar_kwh','load_kwh','import_kwh','export_kwh','import_cost_ron','export_income_ron','balance_ron'].map(k=><td key={k} className={k==='balance_ron'?(r[k]>=0?'positive':'negative'):''}>{money(r[k],k.endsWith('kwh')?1:2)}</td>)}</tr>)}</tbody></table></div></section>
        <details className="finance-prices"><summary>Tarife si istoric <span>{money(data.pricing.active.import_price)} / {money(data.pricing.active.export_price)} lei/kWh</span></summary><div className="finance-price-fields"><label>Cumparare (lei/kWh)<input type="number" aria-label="Pret cumparare energie" min="0" max="5" step="0.01" value={price.energy_import_price} disabled={!canConfigure||saving} onChange={e=>{setPrice(p=>({...p,energy_import_price:e.target.valueAsNumber}));setPriceDirty(true);}}/></label><label>Vanzare (lei/kWh)<input type="number" aria-label="Pret vanzare energie" min="0" max="5" step="0.01" value={price.energy_export_price} disabled={!canConfigure||saving} onChange={e=>{setPrice(p=>({...p,energy_export_price:e.target.valueAsNumber}));setPriceDirty(true);}}/></label><label>Valabil din<input type="date" aria-label="Tarif energie valabil din" value={price.energy_tariff_from} disabled={!canConfigure||saving} onChange={e=>{setPrice(p=>({...p,energy_tariff_from:e.target.value}));setPriceDirty(true);}}/></label><button className="button" disabled={!canConfigure||saving||!priceDirty||!Number.isFinite(price.energy_import_price)||!Number.isFinite(price.energy_export_price)} onClick={savePrice}><Save size={16}/>Salveaza tariful</button></div><div className="finance-tariff-history">{[...data.pricing.history].reverse().map((r:any)=><div key={r.from}><span>{r.assumed?'Inainte de primul tarif inregistrat':r.from}</span><strong>{money(r.import_price)} / {money(r.export_price)} lei/kWh</strong></div>)}</div></details>
      </>}
      {view==='consumption' && <section className="finance-section"><header><h2>Consumul unei zile</h2><select aria-label="Zi analizata" value={selected} onChange={e=>setSelected(e.target.value)}>{rows.filter((r:any)=>r.load_kwh!=null).map((r:any)=><option key={r.date} value={r.date}>{short(r.date)}</option>)}</select></header><div className="finance-day-metrics"><span>Consum total<strong>{energy(selectedDay?.load_kwh)} kWh</strong></span><span>Varf intr-o ora<strong>{peak?hour(peak.time)+' / '+energy(peak.load_kwh)+' kWh':'Fara date'}</strong></span><span>Noaptea, 22:00-07:00<strong>{energy(hours.length?night:null)} kWh</strong></span><span>Boiler, estimat<strong>{energy(selectedDay?.boiler_kwh)} kWh</strong></span></div><Chart><ComposedChart data={hours} margin={{top:8,right:12,left:0,bottom:0}}><CartesianGrid stroke="var(--chart-grid)" vertical={false}/><XAxis dataKey="time" tickFormatter={hour} minTickGap={35}/><YAxis width={50}/><Tooltip labelFormatter={v=>hour(Number(v))} formatter={(v:any,n:any)=>[energy(v)+' kWh',n]}/><Legend/><Bar dataKey="load_kwh" name="Consum casa" fill="var(--energy-load)" maxBarSize={24}/><Area dataKey="solar_kwh" name="Solar" stroke="var(--energy-solar)" fill="var(--energy-solar)" fillOpacity={.12} connectNulls={false}/><Line dataKey="import_kwh" name="Din retea" stroke="var(--energy-grid)" dot={false} strokeWidth={2}/><Line dataKey="boiler_kwh" name="Boiler estimat" stroke="var(--energy-load)" strokeDasharray="5 4" strokeWidth={2} dot={false}/></ComposedChart></Chart><div className="finance-weather-observed"><Thermometer size={17}/><span>Temperatura medie: {energy(selectedDay?.temperature)} °C</span><Cloud size={17}/><span>Nori: {money(selectedDay?.clouds,0)}%</span></div><p className="finance-note">Valorile graficului sunt energii pe ora. Boilerul este inclus in consumul casei; estimarea lui foloseste rezistenta de 1,8 kW. Datele meteo lipsa nu sunt reconstruite artificial.</p></section>}
      {view==='forecast' && <>
        <div className="finance-forecast-meta"><span>{data.outlook.model} · incredere {data.outlook.days[0]?.confidence || 'redusa'}</span><small>Rezerva baterie {data.outlook.assumptions.battery_reserve_soc}% · fara incarcari Tesla suplimentare</small></div>
        {data.outlook.weather_error&&<p className="finance-warning">{data.outlook.weather_error}</p>}
        <div className="finance-forecast-days">{data.outlook.days.map((r:any)=><article key={r.date}><header><h2>{r.date===today()?'Azi':short(r.date)}</h2><span>{money(r.temperature_min,0)} - {money(r.temperature_max,0)} °C</span></header><div className="forecast-sky"><Cloud size={19}/><span>Nori {money(r.clouds,0)}%</span><Sun size={19}/><strong>{energy(r.solar_kwh)} kWh</strong></div><dl><div><dt>Consum estimat</dt><dd>{energy(r.load_kwh)} kWh</dd></div><div><dt>Interval orientativ</dt><dd>{energy(r.load_low_kwh)} - {energy(r.load_high_kwh)} kWh</dd></div><div><dt>Import estimat</dt><dd>{energy(r.import_kwh)} kWh</dd></div><div><dt>Injectie estimata</dt><dd>{energy(r.export_kwh)} kWh</dd></div><div><dt>Baterie la final</dt><dd>{money(r.battery_end_soc,0)}%</dd></div><div><dt>Sold estimat</dt><dd className={r.balance_ron>=0?'positive':'negative'}>{money(r.balance_ron)} lei</dd></div></dl>{r.best_window?.surplus_kwh>0&&<footer>Surplus maxim in jur de {hour(r.best_window.time)}</footer>}</article>)}</div>
        <section className="finance-section"><header><h2>Urmatoarele zile, in energie</h2><span>Estimari kWh</span></header><Chart><ComposedChart data={data.outlook.days}><CartesianGrid stroke="var(--chart-grid)" vertical={false}/><XAxis dataKey="date" tickFormatter={short}/><YAxis width={50}/><Tooltip labelFormatter={v=>short(String(v))} formatter={(v:any,n:any)=>[energy(v)+' kWh',n]}/><Legend/><Bar dataKey="solar_kwh" name="Productie solara" fill="var(--energy-solar)" maxBarSize={25}/><Bar dataKey="load_kwh" name="Consum estimat" fill="var(--energy-load)" maxBarSize={25}/><Line dataKey="import_kwh" name="Import estimat" stroke="var(--energy-grid)" dot={false} strokeWidth={2}/></ComposedChart></Chart></section>
        <section className="finance-advice"><h2>Masuri propuse</h2>{data.outlook.recommendations.map((r:any)=><article key={r.title} className={r.level}><h3>{r.title}</h3><p>{r.text}</p></article>)}</section><p className="finance-note">Estimari, nu comenzi automate. Prognoza solara foloseste configuratia panourilor din HA, cu inclinatia acoperisului estimata. Meteo: <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a>. Randamentul bateriei si profilul termic sunt ipoteze reglabile.</p>
      </>}
    </>}
  </div>;
}
