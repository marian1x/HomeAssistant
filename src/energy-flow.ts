import { type Device, type Snapshot, type State, bindings, number, valid } from './model.ts';

export type LoadReading = {id:string; name:string; kw:number|null; knownKw:number; quality:string; note:string; devices:Device[]};
export function power(state?:State):number|null {
  const n=number(state), unit=state?.attributes.unit_of_measurement;
  return n!==null && n>=0 && ['W','kW'].includes(unit) ? n/(unit==='W'?1000:1) : null;
}
const recent=(stamp:any,now:number,seconds:number)=>typeof stamp==='string'&&Number.isFinite(Date.parse(stamp))&&now-Date.parse(stamp)>=-60000&&now-Date.parse(stamp)<=seconds*1000;

function metered(d:Device):number|null {
  const candidates=d.entries.filter(s=>s.attributes.device_class==='power' && !/max|min|limit|rated|nominal|phase|l[123]_/.test(s.entity_id) && power(s)!==null);
  return candidates.length===1 ? power(candidates[0]) : null;
}

export function energyFlow(data:Snapshot|null, devices:Device[], now=Date.now()) {
  const states=data?.states||{}, status=states['sensor.home_energy_policy_status']?.attributes;
  const source=(key:string)=>states[data?.bindings?.[key] || bindings[key]];
  const sourceFresh=status ? status.power_valid===true && recent(status.updated_at,now,120) : ['solar','load'].every(k=>recent(source(k)?.last_updated,now,120));
  const live=!!data?.connected && sourceFresh;
  const read=(key:string)=>live?power(source(key)):null;
  const pv=read('solar'), house=read('load'), gridImport=read('import'), gridExport=read('export'), charge=read('charge'), discharge=read('discharge');
  const solarHouse=pv!==null&&house!==null&&gridExport!==null&&charge!==null ? Math.min(house,Math.max(0,pv-gridExport-charge)) : null;
  const climates=devices.filter(d=>!d.pending && d.kind!=='car' && d.primary.entity_id.startsWith('climate.') && !['climate.heat','climate.bedroom_heat'].includes(d.primary.entity_id) && !d.primary.entity_id.includes('salavat_t3'));
  const acReadings=climates.map(d=>{
    if (!data?.connected || !valid(d.primary) || d.entries.some(s=>s.entity_id.endsWith('_is_online')&&s.state==='off')) return null;
    return metered(d) ?? (d.primary.state==='off'?0:null);
  });
  const acKnown=acReadings.reduce<number>((sum,n)=>sum+(n??0),0);
  const acComplete=climates.length>0&&acReadings.every(n=>n!==null);
  const boiler=devices.filter(d=>d.primary.entity_id.startsWith('water_heater.'));
  const boilerKw=data?.connected && boiler.some(d=>valid(d.primary)) ? power(source('boiler')) : null;
  const rawTesla=states['sensor.salavat_t3_charger_power'];
  const quota=status?.tesla_quota;
  const pollFresh=typeof quota?.last_poll==='number' && now-quota.last_poll*1000>=-60000 && now-quota.last_poll*1000<=900000;
  const teslaFresh=!!data?.connected && (pollFresh || recent(rawTesla?.last_updated,now,900));
  // Vehicle power away from home is never attributed to the house meter.
  const teslaKw=teslaFresh && quota?.at_home===false ? 0 : teslaFresh && quota?.at_home===true ? power(rawTesla) : null;
  const loads:LoadReading[]=[
    {id:'tesla',name:'Tesla',kw:teslaKw,knownKw:teslaKw??0,quality:teslaKw===null?'Stare memorata':'Citire Tesla',note:teslaKw===null?'Fara citire recenta; masina nu este trezita':quota?.at_home===false?'In afara casei':'Incarcare la domiciliu',devices:devices.filter(d=>d.kind==='car')},
    {id:'boiler',name:'Boiler',kw:boilerKw,knownKw:boilerKw??0,quality:'Estimat',note:'Rezistenta de 1,8 kW; numai cand incalzeste',devices:boiler},
    {id:'ac',name:'Climatizare',kw:acComplete?acKnown:null,knownKw:acKnown,quality:acComplete?(acKnown===0?'Aparate oprite':'Masurat'):'Fara contorizare completa',note:acComplete?'Putere cumulata AC':'Energia zilnica nu indica puterea instantanee',devices:climates},
  ];
  const known=loads.reduce((sum,r)=>sum+r.knownKw,0);
  const conflict=live&&house!==null&&known>house+.1;
  const unassigned=house===null||conflict?null:Math.max(0,house-known);
  const unknown=loads.filter(r=>r.kw===null).map(r=>r.name);
  loads.push({id:'other',name:'Consum neatribuit',kw:unassigned,knownKw:unassigned??0,quality:'Rezidual',note:unknown.length?'Include si consumul necontorizat: '+unknown.join(', '):'Iluminat, prize si restul consumatorilor',devices:[]});
  const balance=pv!==null&&house!==null&&gridImport!==null&&gridExport!==null&&charge!==null&&discharge!==null ? pv+gridImport+discharge-house-gridExport-charge : null;
  return {live,pv,house,gridImport,gridExport,charge,discharge,solarHouse,loads,conflict,balance,
    soc:data?.connected?number(source('soc')):null,
    solarToday:number(source('solarToday')),loadToday:number(source('loadToday')),
    importToday:number(states['sensor.deye_today_energy_import']),exportToday:number(states['sensor.deye_today_energy_export']),
    importPrice:number(states['sensor.home_energy_import_price']),exportPrice:number(states['sensor.home_energy_export_price']),
    lastUpdate:typeof status?.updated_at==='string'?status.updated_at:null};
}
