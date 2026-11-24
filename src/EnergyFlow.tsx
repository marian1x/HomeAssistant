import { useState, type CSSProperties } from 'react';
import { ArrowDownLeft, ArrowUpRight, Battery, Car, ChevronDown, ChevronRight, ChevronUp, Flame, House, Plug, Sun, Wind, Zap } from 'lucide-react';
import { type Device, type Snapshot, format, label, number } from './model';
import { energyFlow } from './energy-flow';
import { Num } from './motion';

const icons:Record<string,any>={solar:Sun,grid:Plug,battery:Battery,house:House,inverter:Zap,tesla:Car,boiler:Flame,ac:Wind,other:Plug};
export default function EnergyFlow({data,devices,navigate}:{data:Snapshot|null;devices:Device[];navigate:(view:string)=>void}) {
  // The viewer's last choice wins; otherwise the diagram opens on wide screens only.
  const [expanded,setOpen]=useState(()=>{try{const saved=localStorage.getItem('casa-flow-expanded');if(saved!==null)return saved==='1';}catch{/* Storage may be disabled. */}return window.matchMedia('(min-width:900px)').matches;});
  const setExpanded=(next:boolean|((v:boolean)=>boolean))=>setOpen(v=>{const value=typeof next==='function'?next(v):next;try{localStorage.setItem('casa-flow-expanded',value?'1':'0');}catch{/* Storage may be disabled. */}return value;});
  const [selected,setSelected]=useState('house');
  const f=energyFlow(data,devices);
  const gridOut=(f.gridExport??0)>(f.gridImport??0);
  const batteryOut=(f.discharge??0)>(f.charge??0);
  const metrics=[['solar','Solar acum',f.pv,Sun],['house','Consum casa',f.house,House],['grid',gridOut?'Export retea':'Import retea',gridOut?f.gridExport:f.gridImport,gridOut?ArrowUpRight:ArrowDownLeft],['battery',batteryOut?'Din baterie':'In baterie',batteryOut?f.discharge:f.charge,Battery]];
  const nodes=[{id:'solar',name:'Panouri',kw:f.pv,x:16,y:20,sub:format(f.solarToday)+' kWh azi'},
    {id:'grid',name:'Retea',kw:gridOut?f.gridExport:f.gridImport,x:16,y:77,sub:gridOut?'Injectie':'Import'},
    {id:'inverter',name:'Deye',kw:null,x:50,y:46,sub:'Invertor hibrid'},
    {id:'house',name:'Casa',kw:f.house,x:84,y:46,sub:'Consum total'},
    {id:'battery',name:'Baterie',kw:batteryOut?f.discharge:f.charge,x:50,y:83,sub:format(f.soc,0)+'% · '+(batteryOut?'Descarcare':'Incarcare')}];
  const selectedLoad=f.loads.find(r=>r.id===selected);
  const heading=selectedLoad?.name || ({solar:'Productie solara',grid:'Schimb cu reteaua',battery:'Stocare',house:'Alimentarea casei',inverter:'Bilant energetic'} as Record<string,string>)[selected];
  const details=selectedLoad ? [[selectedLoad.quality,selectedLoad.kw===null?'-- kW':format(selectedLoad.kw,2)+' kW'],...selectedLoad.devices.flatMap(d=>[[d.name,label(d.primary)+(d.primary.attributes.temperature!=null?' · tinta '+d.primary.attributes.temperature+'°C':'')],...d.entries.filter(s=>s.entity_id.endsWith('_today_energy_consumption')&&s.attributes.unit_of_measurement==='kWh'&&number(s)!==null).map(s=>[d.name+' · energie azi',format(number(s),2)+' kWh'])])] :
    selected==='solar' ? [['Putere',format(f.pv,2)+' kW'],['Produs azi',format(f.solarToday,2)+' kWh'],['Solar spre casa, calculat',format(f.solarHouse,2)+' kW']] :
    selected==='grid' ? [['Import',format(f.gridImport,2)+' kW'],['Export',format(f.gridExport,2)+' kW'],['Cumparare',format(f.importPrice,2)+' lei/kWh'],['Vanzare',format(f.exportPrice,2)+' lei/kWh']] :
    selected==='battery' ? [['Nivel',format(f.soc,0)+'%'],['Incarcare',format(f.charge,2)+' kW'],['Descarcare',format(f.discharge,2)+' kW'],['Rezerva',format(number(data?.states['sensor.deye_rezerva_recomandata']),0)+'%']] :
    selected==='inverter' ? [['Conversie si esantionare',format(f.balance,2)+' kW'],['Solar',format(f.pv,2)+' kW'],['Consum',format(f.house,2)+' kW']] :
    [['Consum',format(f.house,2)+' kW'],['Din solar, calculat',format(f.solarHouse,2)+' kW'],['Din retea',format(f.gridImport,2)+' kW'],['Din baterie',format(f.discharge,2)+' kW']];
  function line(id:string,d:string,kw:number|null,reverse=false) {
    const active=f.live&&kw!==null&&kw>.03;
    const point=({solar:[350,118,90],grid:[330,222,-90],house:[670,166,0],battery:[500,220,90]} as Record<string,number[]>)[id];
    // Sparks travel faster as power grows: about 3,9 s per segment at 0,1 kW, 1,3 s at 5 kW.
    const pace=active?Math.max(1.1,4.2-Math.log10(1+kw*4)*2.2):0;
    return <g key={id} className={'flow-line '+id+(active?' energized':'')+(reverse?' reverse':'')} style={{'--pace':pace+'s'} as CSSProperties}><path d={d} className={'flow-wire '+id+(active?' energized':'')+(reverse?' reverse':'')}/>{active&&<><path d={d} className="flow-glow"/><path d={d} className="flow-tail"/><path d={d} className="flow-spark"/></>}<g transform={`translate(${point[0]} ${point[1]}) rotate(${point[2]+(reverse?180:0)})`} className={'flow-arrow '+(active?'active':'')}><ChevronRight x={-8} y={-8} size={16}/></g></g>;
  }
  return <section className="house-energy" aria-label="Energia intregii case">
    <div className="house-energy-title"><div><span className="eyebrow">ENERGIA INTREGII CASE</span><h2>Productie, stocare si consum</h2></div><span className={'flow-live '+(f.live?'online':'')}><i/>{f.live?'Live':'Fara citire recenta'}</span></div>
    <div className="live-power-strip">{metrics.map(([id,title,kw,Icon]:any)=><button key={id} onClick={()=>{if(id==='battery'){navigate('battery');return;}setSelected(id);setExpanded(true);}} aria-label={id==='battery'?title+' · panoul bateriei':title+' · detalii'}><span><Icon size={17}/>{title}</span><strong><Num value={kw}/><small> kW</small></strong><small>{id==='battery'?format(f.soc,0)+'% SOC':id==='solar'?format(f.solarToday,1)+' kWh azi':id==='house'?'Solar '+format(f.solarHouse,2)+' kW':(gridOut?'Import ':'Export ')+format(gridOut?f.gridImport:f.gridExport,2)+' kW'}</small></button>)}</div>
    <button className="flow-expand" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}><Zap size={16}/>Flux energetic {expanded?<ChevronUp size={17}/>:<ChevronDown size={17}/>}</button>
    {expanded&&<div className="energy-live-workspace">
      <div className="flow-main">
        <div className="flow-diagram" aria-label="Fluxuri de putere">
          <svg className="flow-wires" viewBox="0 0 1000 360" preserveAspectRatio="none" aria-hidden="true">
            {line('solar','M160 72 H330 Q350 72 350 92 V146 Q350 166 370 166 H500',f.pv)}
            {line('grid','M160 277 H310 Q330 277 330 257 V186 Q330 166 350 166 H500',gridOut?f.gridExport:f.gridImport,gridOut)}
            {line('house','M500 166 H840',f.house)}
            {line('battery','M500 166 V299',batteryOut?f.discharge:f.charge,batteryOut)}
          </svg>
          {nodes.map(n=>{const Icon=icons[n.id];return <button key={n.id} className={'flow-node '+n.id+(selected===n.id?' selected':'')+(f.live&&(n.id==='inverter'||(n.kw??0)>.03)?' flowing':'')} style={{left:n.x+'%',top:n.y+'%',...(n.id==='battery'&&f.soc!==null?{'--soc':Math.max(0,Math.min(100,f.soc))+'%'}:{})} as CSSProperties} aria-pressed={selected===n.id} aria-label={n.id==='battery'?'Baterie · deschide panoul bateriei':undefined} onClick={()=>n.id==='battery'?navigate('battery'):setSelected(n.id)}><span className="flow-node-icon"><Icon size={22}/></span><span className="flow-node-name">{n.name}</span>{n.id!=='inverter'&&<strong><Num value={n.kw}/><small> kW</small></strong>}<small>{n.sub}</small></button>;})}
        </div>
        <div className="flow-load-heading"><span>Distributia consumului casei</span><span>kW</span></div>
        <div className="flow-loads">{f.loads.map(r=>{const Icon=icons[r.id];return <button key={r.id} className={'flow-load '+r.id+(selected===r.id?' selected':'')} aria-pressed={selected===r.id} onClick={()=>setSelected(r.id)}><span><Icon size={18}/>{r.name}</span><strong>{r.kw===null&&r.knownKw>0?<>≥ <Num value={r.knownKw}/></>:<Num value={r.kw}/>}<small> kW</small></strong><small>{r.quality}</small><span className="flow-load-track"><i style={{width:r.knownKw&&f.house?Math.min(100,r.knownKw/f.house*100)+'%':'0%'}}/></span></button>;})}</div>
        {f.conflict&&<p className="flow-data-warning" role="status">Citirile consumatorilor nu sunt sincronizate cu totalul casei.</p>}
      </div>
      <aside className="flow-insight" aria-live="polite"><h3>{heading}</h3>{selectedLoad&&<p>{selectedLoad.note}</p>}<dl>{details.map(([name,value])=><div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl><div className="flow-today"><h3>Astazi</h3><dl>{[['Produs',f.solarToday],['Consumat',f.loadToday],['Cumparat',f.importToday],['Injectat',f.exportToday]].map(([title,n]:any)=><div key={title}><dt>{title}</dt><dd>{format(n,2)} kWh</dd></div>)}</dl></div><button className="text-button" onClick={()=>navigate('economics')}>Costuri si prognoza <ArrowUpRight size={16}/></button></aside>
    </div>}
  </section>;
}
