import { useEffect, useState, type ReactNode } from 'react';
import { ArrowUpRight, Car, Check, CloudSun, Flame, House, LayoutGrid, Lightbulb, Plug, Search, SlidersHorizontal, Sun, Thermometer, Volume2, Wind, X } from 'lucide-react';
import { type Device, type Snapshot, type State, controllable, controlCategory, deviceReading, format, houseFloors, houseRooms, inLocation, valid } from './model';
import EnergyFlow from './EnergyFlow';
import './home-control.css';

type Props={data:Snapshot|null;devices:Device[];history:any;canControl:boolean;control:(state:State)=>ReactNode;
  temperature:(state:State,target:number)=>void;brightness:(state:State,percent:number)=>void;navigate:(tab:string,area?:string,floor?:string)=>void;
  room:string;floor:string;onLocation:(floor:string,room:string)=>void};
const groups=[{id:'lights',name:'Iluminat',icon:Lightbulb},{id:'climate',name:'Climatizare',icon:Wind},{id:'water',name:'Apa calda',icon:Flame},
  {id:'power',name:'Prize si relee',icon:Plug},{id:'media',name:'Media',icon:Volume2},{id:'mobility',name:'Mobilitate',icon:Car}];

function DeviceCommand({device:d,control,canControl,temperature,brightness}:{device:Device;control:Props['control'];canControl:boolean;temperature:Props['temperature'];brightness:Props['brightness']}) {
  const state=d.primary, category=controlCategory(d), Icon=groups.find(g=>g.id===category)?.icon || Plug;
  const [lightDraft,setLightDraft]=useState<number|null>(null);
  const actual=state.state==='off'?0:typeof state.attributes.brightness==='number'?Math.round(state.attributes.brightness/255*100):null;
  const adjustable=state.entity_id.startsWith('light.')&&(state.attributes.supported_color_modes||[]).some((m:string)=>!['onoff','unknown'].includes(m));
  useEffect(()=>setLightDraft(null),[state.entity_id,actual]);
  // A boiler mode (e.g. MANUAL) is not proof that the element heats, so it stays neutral.
  const on=['on','heat','cool','heat_cool','auto','dry','fan_only','playing'].includes(state.state);
  const tone=!valid(state)?'offline':on?'on':'off';
  const toggle=['switch.','light.','fan.'].some(p=>state.entity_id.startsWith(p));
  const thermal=category==='climate'||category==='water';
  const temp=(n:any)=>format(typeof n==='number'?n:null);
  const reading=category==='lights'&&actual!==null?'Luminozitate '+actual+'%':category==='media'&&state.attributes.volume_level!=null?'Volum '+Math.round(state.attributes.volume_level*100)+'%':d.manufacturer || 'Home Assistant';
  return <article className={'home-device '+category+(!valid(state)?' offline':'')+(on?' active':'')} data-device={d.id} data-room={d.area}>
    <div className="home-device-top"><span className="home-device-icon"><Icon size={20}/></span><div className="home-device-name"><h3>{d.name}</h3><span>{d.floor} / {d.area}</span></div>{toggle?control(state):<span className={'state-chip '+tone}>{deviceReading(d)}</span>}</div>
    {toggle?<div className="home-device-meta"><span className={'state-chip '+tone}>{deviceReading(d)}</span><span>{reading}</span></div>
      :<div className="home-device-bottom"><div className="home-device-reading">{thermal?<><strong>{temp(state.attributes.current_temperature)}<small> °C</small></strong><span>Tinta {temp(state.attributes.temperature)}°{state.attributes.fan_mode?' · Ventilator '+state.attributes.fan_mode:''}</span></>:<span>{reading}</span>}</div>{control(state)}</div>}
    {adjustable&&<div className="home-brightness"><Sun size={16}/><input type="range" aria-label={'Luminozitate '+d.name} min="1" max="100" value={lightDraft??actual??1} disabled={!canControl||!valid(state)} onChange={e=>setLightDraft(Number(e.target.value))}/><output>{lightDraft??actual??'--'}%</output><button className="apply-button" title={'Aplica luminozitatea '+d.name} aria-label={'Aplica luminozitatea '+d.name} disabled={!canControl||!valid(state)||lightDraft===null||lightDraft===actual} onClick={()=>lightDraft!==null&&brightness(state,lightDraft)}><Check size={15}/>Aplica</button></div>}
    {thermal&&<div className="home-temperature-preset" role="group" aria-label={'Temperaturi rapide '+d.name}>{(category==='water'?[43,47,80]:[21,23,25]).filter(n=>n>=(state.attributes.min_temp??0)&&n<=(state.attributes.max_temp??100)).map(n=><button key={n} className={'temperature-preset '+(state.attributes.temperature===n?'current':'')} aria-pressed={state.attributes.temperature===n} disabled={!canControl||!valid(state)} onClick={()=>temperature(state,n)} aria-label={d.name+' · seteaza '+n+' grade'}><Thermometer size={13}/>{n}°</button>)}</div>}
  </article>;
}

export default function HomeDashboard({data,devices,canControl,control,temperature,brightness,navigate,room,floor,onLocation}:Props) {
  const [category,setCategory]=useState('all'),[query,setQuery]=useState('');
  const [showOffline,setShowOffline]=useState(false);
  const [now,setNow]=useState(()=>new Date());
  useEffect(()=>{const timer=setInterval(()=>setNow(new Date()),30000);return()=>clearInterval(timer);},[]);
  const rooms=[...new Set([...houseRooms(data,floor),...devices.filter(d=>floor==='all'||d.floor===floor).map(d=>d.area)])].filter(r=>r!=='Fara camera');
  const scoped=devices.filter(d=>inLocation(d,floor,room)&&controllable(d)&&(showOffline||valid(d.primary)));
  const shown=scoped.filter(d=>(category==='all'||controlCategory(d)===category)&&`${d.name} ${d.area} ${d.manufacturer}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const weather=Object.values(data?.states||{}).find(s=>s.entity_id.startsWith('weather.')&&valid(s));
  const date=new Intl.DateTimeFormat('ro-RO',{day:'numeric',month:'long',timeZone:'Europe/Bucharest'}).format(now);
  const counts=(id:string)=>scoped.filter(d=>controlCategory(d)===id).length;
  // Counts ignore the type filter so a room never disappears while a category is selected.
  const placeCount=(f:string,r:string)=>devices.filter(d=>inLocation(d,f,r)&&controllable(d)&&(showOffline||valid(d.primary))).length;
  const roomTabs=['all',...rooms.filter(r=>r===room||placeCount(floor,r)>0)];
  return <section className="home-command-center">
    <header className="home-welcome"><div><span className="eyebrow">CASA SALAVAT</span><h1>{data?'Buna, '+data.user.name.split(' ')[0]+'.':'Bine ai venit acasa.'}</h1></div><div className="home-context"><span>{date}</span><span><CloudSun size={19}/>{format(typeof weather?.attributes.temperature==='number'?weather.attributes.temperature:null)} {weather?.attributes.temperature_unit||'°C'}</span><button className="icon-button" title="Setarile casei" onClick={()=>navigate('settings')}><SlidersHorizontal size={19}/></button></div></header>
    <EnergyFlow data={data} devices={devices} navigate={navigate}/>
    <section className="room-command-center" aria-label="Controlul camerelor">
      <header className="room-command-heading"><div><span className="eyebrow">CONTROL DIRECT</span><h2>{room==='all'?(floor==='all'?'Dispozitivele casei':floor):room}</h2><span className="room-device-count">{scoped.length} dispozitive integrate pentru control</span></div><button className="text-button" onClick={()=>navigate('devices',room,floor)}>Inventar dispozitive <ArrowUpRight size={16}/></button></header>
      <div className="floor-tabs" role="tablist" aria-label="Nivel">{['all',...houseFloors(data)].map(f=><button role="tab" key={f} aria-label={f==='all'?'Toata casa':f} aria-selected={floor===f} onClick={()=>{onLocation(f,'all');setQuery('');}}>{f==='all'?<><House size={15}/>Toata casa</>:f}<small className="tab-count" aria-hidden="true">{placeCount(f,'all')}</small></button>)}</div>
      <div className="room-tabs" role="tablist" aria-label="Camere">{roomTabs.map(r=><button role="tab" key={r} aria-label={r==='all'?'Toate camerele':r} aria-selected={room===r} onClick={()=>{onLocation(floor,r);setQuery('');}}>{r==='all'?'Toate camerele':r}<small className="tab-count" aria-hidden="true">{placeCount(floor,r)}</small></button>)}</div>
      <label className="home-category-select"><LayoutGrid size={17}/><select aria-label="Tip dispozitiv" value={category} onChange={e=>setCategory(e.target.value)}>{[{id:'all',name:'Toate dispozitivele'},...groups].map(g=><option key={g.id} value={g.id}>{g.name} ({g.id==='all'?scoped.length:counts(g.id)})</option>)}</select></label>
      <div className="home-control-toolbar"><div className="control-categories" role="tablist" aria-label="Tip dispozitiv">{[{id:'all',name:'Toate',icon:LayoutGrid},...groups].map(g=><button key={g.id} role="tab" aria-selected={category===g.id} onClick={()=>setCategory(g.id)}><g.icon size={16}/>{g.name}<small>{g.id==='all'?scoped.length:counts(g.id)}</small></button>)}</div><div className="home-device-options"><label className="offline-option"><input type="checkbox" checked={showOffline} onChange={e=>setShowOffline(e.target.checked)}/>Indisponibile</label><label className="home-device-search"><Search size={17}/><input type="search" aria-label="Cauta in camera" placeholder="Cauta dispozitiv" value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<button title="Sterge cautarea" onClick={()=>setQuery('')}><X size={15}/></button>}</label></div></div>
      {groups.filter(g=>category==='all'||g.id===category).map(g=>{const items=shown.filter(d=>controlCategory(d)===g.id);return items.length?<section className="home-device-group" key={g.id} aria-label={g.name}><header><h3><g.icon size={17}/>{g.name}</h3><small>{items.length} dispozitive</small></header><div className="home-device-grid">{items.map(d=><DeviceCommand key={d.id} device={d} control={control} canControl={canControl} temperature={temperature} brightness={brightness}/>)}</div></section>:null;})}
      {!shown.length&&<div className="home-control-empty"><Plug size={24}/><span>{data?'Niciun dispozitiv de control pentru aceasta selectie.':'Autentifica-te pentru dispozitivele casei.'}</span></div>}
    </section>
  </section>;
}
