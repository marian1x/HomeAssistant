import { useEffect, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, ArrowUpRight, Car, Check, CloudSun, Flame, House, LayoutGrid, Lightbulb, Plug, Search, SlidersHorizontal, Star, Sun, Thermometer, Volume2, Wind, X } from 'lucide-react';
import { type Device, type Snapshot, type State, controllable, controlCategory, deviceReading, format, houseFloors, houseRooms, inLocation, valid } from './model';
import EnergyFlow from './EnergyFlow';
import { energyFlow } from './energy-flow';
import { brief } from './brief';
import { Num } from './motion';
import { type Layout, arrange, groupOrder, move, moveGroup, pick, uses } from './arrange';
import { ArrangeBar, Sortable, useSortable } from './ArrangeMode';
import './home-control.css';

type Props={data:Snapshot|null;devices:Device[];history:any;canControl:boolean;control:(state:State)=>ReactNode;
  temperature:(state:State,target:number)=>void;brightness:(state:State,percent:number)=>void;navigate:(tab:string,area?:string,floor?:string)=>void;
  room:string;floor:string;onLocation:(floor:string,room:string)=>void;
  layout:Layout;onLayout:(change:Partial<Layout>)=>void;onArrange:()=>void};
const groups=[{id:'lights',name:'Iluminat',icon:Lightbulb},{id:'climate',name:'Climatizare',icon:Wind},{id:'water',name:'Apa calda',icon:Flame},
  {id:'power',name:'Prize si relee',icon:Plug},{id:'media',name:'Media',icon:Volume2},{id:'mobility',name:'Mobilitate',icon:Car}];

function DeviceCommand({device:d,control,canControl,temperature,brightness,favorite,onFavorite}:{device:Device;control:Props['control'];canControl:boolean;temperature:Props['temperature'];brightness:Props['brightness'];favorite:boolean;onFavorite:()=>void}) {
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
    <div className="home-device-top"><span className="home-device-icon"><Icon size={20}/></span><div className="home-device-name"><h3>{d.name}</h3><span>{d.floor} / {d.area}</span></div><button type="button" className={'favorite-toggle'+(favorite?' on':'')} aria-pressed={favorite} title={favorite?'Scoate din favorite':'Adauga la favorite'} aria-label={(favorite?'Scoate din favorite ':'Adauga la favorite ')+d.name} onClick={onFavorite}><Star size={15} fill={favorite?'currentColor':'none'}/></button>{toggle?control(state):<span className={'state-chip '+tone}>{deviceReading(d)}</span>}</div>
    {toggle?<div className="home-device-meta"><span className={'state-chip '+tone}>{deviceReading(d)}</span><span>{reading}</span></div>
      :<div className="home-device-bottom"><div className="home-device-reading">{thermal?<><strong>{temp(state.attributes.current_temperature)}<small> °C</small></strong><span>Tinta {temp(state.attributes.temperature)}°{state.attributes.fan_mode?' · Ventilator '+state.attributes.fan_mode:''}</span></>:<span>{reading}</span>}</div>{control(state)}</div>}
    {adjustable&&<div className="home-brightness"><Sun size={16}/><input type="range" aria-label={'Luminozitate '+d.name} min="1" max="100" value={lightDraft??actual??1} disabled={!canControl||!valid(state)} onChange={e=>setLightDraft(Number(e.target.value))}/><output>{lightDraft??actual??'--'}%</output><button className="apply-button" title={'Aplica luminozitatea '+d.name} aria-label={'Aplica luminozitatea '+d.name} disabled={!canControl||!valid(state)||lightDraft===null||lightDraft===actual} onClick={()=>lightDraft!==null&&brightness(state,lightDraft)}><Check size={15}/>Aplica</button></div>}
    {thermal&&<div className="home-temperature-preset" role="group" aria-label={'Temperaturi rapide '+d.name}>{(category==='water'?[43,47,80]:[21,23,25]).filter(n=>n>=(state.attributes.min_temp??0)&&n<=(state.attributes.max_temp??100)).map(n=><button key={n} className={'temperature-preset '+(state.attributes.temperature===n?'current':'')} aria-pressed={state.attributes.temperature===n} disabled={!canControl||!valid(state)} onClick={()=>temperature(state,n)} aria-label={d.name+' · seteaza '+n+' grade'}><Thermometer size={13}/>{n}°</button>)}</div>}
  </article>;
}

export default function HomeDashboard({data,devices,canControl,control,temperature,brightness,navigate,room,floor,onLocation,layout,onLayout,onArrange}:Props) {
  const [arranging,setArranging]=useState(false);
  // Favorites and named views are shared with the APK through the server layout.
  const [collection,setCollection]=useState(()=>layout.favorites?.length?'fav':'all');
  const view=layout.views?.find(v=>v.id===collection);
  const picked=collection==='fav'?pick(devices,layout.favorites||[]):view?pick(devices,view.items):null;
  const isFavorite=(d:Device)=>(layout.favorites||[]).includes(d.id);
  const toggleFavorite=(d:Device)=>onLayout({favorites:isFavorite(d)?layout.favorites.filter(id=>id!==d.id):[...(layout.favorites||[]),d.id].slice(0,100)});
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
  // The user's order (manual, most used or default) applies to groups and to cards.
  const ordered=groupOrder(layout).map(id=>groups.find(g=>g.id===id)!).filter(Boolean);
  const sorted=arrange(shown,layout);
  const sorter=useSortable((ids,id,to)=>onLayout({sort:'manual',order:move(layout.sort==='manual'?layout.order:arrange(devices,layout).map(d=>d.id),ids,id,to)}));
  const toggleArrange=()=>{if(!arranging)onArrange();setArranging(!arranging);};
  // "Casa acum": a sentence and a few facts computed from live readings only.
  const flow=energyFlow(data,devices), summary=brief(flow);
  const working=(id:string)=>devices.filter(d=>controllable(d)&&valid(d.primary)&&controlCategory(d)===id&&!['off','idle','standby','paused'].includes(d.primary.state)).length;
  const lit=working('lights'), cooling=working('climate'), ring=2*Math.PI*30;
  return <section className="home-command-center">
    <header className={'home-welcome tone-'+summary.tone}><div className="home-hello"><span className="eyebrow">CASA SALAVAT</span><h1>{data?'Buna, '+data.user.name.split(' ')[0]+'.':'Bine ai venit acasa.'}</h1>
      {data&&<p className="home-brief" key={summary.headline}><i aria-hidden="true"/>{summary.headline}</p>}
      {data&&<div className="home-facts">{lit>0&&<span><Lightbulb size={14}/>{lit} {lit===1?'lumina aprinsa':'lumini aprinse'}</span>}{cooling>0&&<span><Wind size={14}/>{cooling} {cooling===1?'climatizare activa':'climatizari active'}</span>}{flow.solarToday!==null&&<span><Sun size={14}/>Solar azi {format(flow.solarToday,1)} kWh</span>}</div>}
    </div><div className="home-side">{data&&summary.autarky!==null&&<div className="autarky" role="img" aria-label={'Independenta energetica azi: '+summary.autarky+'%'}><svg viewBox="0 0 72 72" aria-hidden="true"><defs><linearGradient id="autarky-stroke" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stopColor="var(--energy-load)"/><stop offset="1" stopColor="var(--energy-solar)"/></linearGradient></defs><circle cx="36" cy="36" r="30" className="autarky-track"/><circle cx="36" cy="36" r="30" className="autarky-value" strokeDasharray={ring} strokeDashoffset={ring*(1-summary.autarky/100)}/></svg><strong><Num value={summary.autarky} digits={0}/><small>%</small></strong><span>independenta<br/>energetica azi</span></div>}<div className="home-context"><span>{date}</span><span><CloudSun size={19}/>{format(typeof weather?.attributes.temperature==='number'?weather.attributes.temperature:null)} {weather?.attributes.temperature_unit||'°C'}</span><button className="icon-button" title="Setarile casei" onClick={()=>navigate('settings')}><SlidersHorizontal size={19}/></button></div></div></header>
    <EnergyFlow data={data} devices={devices} navigate={navigate}/>
    <section className="room-command-center" aria-label="Controlul camerelor">
      <header className="room-command-heading"><div><span className="eyebrow">CONTROL DIRECT</span><h2>{room==='all'?(floor==='all'?'Dispozitivele casei':floor):room}</h2><span className="room-device-count">{scoped.length} dispozitive integrate pentru control</span></div><div className="room-command-actions">{data&&<button className={'button arrange-toggle'+(arranging?' selected':'')} aria-pressed={arranging} onClick={toggleArrange}><ArrowUpDown size={16}/>Aranjeaza</button>}<button className="text-button" onClick={()=>navigate('devices',room,floor)}>Inventar dispozitive <ArrowUpRight size={16}/></button></div></header>
      {arranging&&<ArrangeBar sort={layout.sort} days={layout.usage_days||30} onSort={sort=>onLayout({sort})} onDone={()=>setArranging(false)}/>}
      {data&&<div className="room-tabs collection-tabs" role="tablist" aria-label="Colectii">{[{id:'all',name:'Toate'},{id:'fav',name:'Favorite'},...(layout.views||[])].map(c=><button role="tab" key={c.id} aria-selected={collection===c.id} onClick={()=>{setCollection(c.id);setArranging(false);}}>{c.id==='fav'&&<Star size={14}/>}{c.name}<small className="tab-count" aria-hidden="true">{c.id==='all'?devices.filter(controllable).length:c.id==='fav'?(layout.favorites||[]).length:(c as any).items.length}</small></button>)}</div>}
      {picked&&<section className="home-device-group" aria-label={view?view.name:'Favorite'}><header><h3><Star size={17}/>{view?view.name:'Favorite'}</h3><small>{picked.length} dispozitive{view?' · vederea se editeaza din aplicatia Android':''}</small></header>
        {picked.length?<div className="home-device-grid">{picked.map(d=><DeviceCommand key={d.id} device={d} control={control} canControl={canControl} temperature={temperature} brightness={brightness} favorite={isFavorite(d)} onFavorite={()=>toggleFavorite(d)}/>)}</div>
          :<div className="home-control-empty"><Star size={24}/><span>{view?'Vederea este goala.':'Nicio favorita inca. Atinge steaua unui dispozitiv.'}</span></div>}</section>}
      {!picked&&<>
      <div className="floor-tabs" role="tablist" aria-label="Nivel">{['all',...houseFloors(data)].map(f=><button role="tab" key={f} aria-label={f==='all'?'Toata casa':f} aria-selected={floor===f} onClick={()=>{onLocation(f,'all');setQuery('');}}>{f==='all'?<><House size={15}/>Toata casa</>:f}<small className="tab-count" aria-hidden="true">{placeCount(f,'all')}</small></button>)}</div>
      <div className="room-tabs" role="tablist" aria-label="Camere">{roomTabs.map(r=><button role="tab" key={r} aria-label={r==='all'?'Toate camerele':r} aria-selected={room===r} onClick={()=>{onLocation(floor,r);setQuery('');}}>{r==='all'?'Toate camerele':r}<small className="tab-count" aria-hidden="true">{placeCount(floor,r)}</small></button>)}</div>
      <label className="home-category-select"><LayoutGrid size={17}/><select aria-label="Tip dispozitiv" value={category} onChange={e=>setCategory(e.target.value)}>{[{id:'all',name:'Toate dispozitivele'},...ordered].map(g=><option key={g.id} value={g.id}>{g.name} ({g.id==='all'?scoped.length:counts(g.id)})</option>)}</select></label>
      <div className="home-control-toolbar"><div className="control-categories" role="tablist" aria-label="Tip dispozitiv">{[{id:'all',name:'Toate',icon:LayoutGrid},...ordered].map(g=><button key={g.id} role="tab" aria-selected={category===g.id} onClick={()=>setCategory(g.id)}><g.icon size={16}/>{g.name}<small>{g.id==='all'?scoped.length:counts(g.id)}</small></button>)}</div><div className="home-device-options"><label className="offline-option"><input type="checkbox" checked={showOffline} onChange={e=>setShowOffline(e.target.checked)}/>Indisponibile</label><label className="home-device-search"><Search size={17}/><input type="search" aria-label="Cauta in camera" placeholder="Cauta dispozitiv" value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<button title="Sterge cautarea" onClick={()=>setQuery('')}><X size={15}/></button>}</label></div></div>
      {ordered.filter(g=>category==='all'||g.id===category).map((g,gi,visibleGroups)=>{const items=sorted.filter(d=>controlCategory(d)===g.id);if(!items.length)return null;
        const card=(d:Device)=><DeviceCommand key={d.id} device={d} control={control} canControl={canControl&&!arranging} temperature={temperature} brightness={brightness} favorite={isFavorite(d)} onFavorite={()=>toggleFavorite(d)}/>;
        const ids=items.map(d=>d.id), view=arranging?sorter.preview(g.id,ids):ids, byId=new Map(items.map(d=>[d.id,d]));
        return <section className={'home-device-group'+(arranging?' arranging':'')} key={g.id} aria-label={g.name}><header><h3><g.icon size={17}/>{g.name}</h3>
          {arranging&&category==='all'&&<span className="group-steps"><button type="button" aria-label={'Muta grupul '+g.name+' mai sus'} disabled={gi===0} onClick={()=>onLayout({groups:moveGroup(layout,g.id,-1)})}><ArrowUp size={15}/></button><button type="button" aria-label={'Muta grupul '+g.name+' mai jos'} disabled={gi===visibleGroups.length-1} onClick={()=>onLayout({groups:moveGroup(layout,g.id,1)})}><ArrowDown size={15}/></button></span>}
          <small>{items.length} dispozitive</small></header>
          <div className="home-device-grid">{arranging?view.map(id=>{const d=byId.get(id)!;return <Sortable key={id} sorter={sorter} scope={g.id} ids={ids} id={id} name={d.name} uses={layout.sort==='usage'?uses(d,layout.usage):null}>{card(d)}</Sortable>;}):items.map(card)}</div></section>;})}
      {!shown.length&&<div className="home-control-empty"><Plug size={24}/><span>{data?'Niciun dispozitiv de control pentru aceasta selectie.':'Autentifica-te pentru dispozitivele casei.'}</span></div>}
      </>}
    </section>
  </section>;
}
