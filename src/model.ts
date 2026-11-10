export type State = {
  entity_id: string;
  state: string;
  attributes: Record<string, any>;
  last_updated?: string;
};
export type Snapshot = {
  user: { id: string; name: string; role: "viewer" | "control" | "configure"; local?: boolean; admin?: boolean };
  csrf: string;
  connected: boolean;
  last_update: number;
  states: Record<string, State>;
  bindings: Record<string, string>;
  helpers: Record<string, number[]>;
  entities: any[];
  devices: any[];
  areas: any[];
  floors?: { floor_id: string; name: string; level?: number }[];
  house?: HousePlan;
};
export type HousePlan = {
  floors: { name: string; level: number; icon?: string }[];
  rooms: { key: string; name: string; floor: string; ha_area_id?: string }[];
  items: { id: string; name: string; kind: string; room: string; device_ids?: string[]; primary_entity?: string; manufacturer?: string; note?: string; coverage?: string; external_control?: boolean; rated_power_kw?: number }[];
};
export const bindings: Record<string, string> = {
  solar: "sensor.productie_solara_curenta",
  load: "sensor.consum_total_curent",
  import: "sensor.consum_din_retea",
  export: "sensor.injectie_in_retea",
  soc: "sensor.deye_battery",
  charge: "sensor.baterie_incarcare_putere",
  discharge: "sensor.baterie_descarcare_putere",
  batteryTemp: "sensor.deye_battery_temperature",
  solarToday: "sensor.deye_productie_solara_astazi",
  loadToday: "sensor.deye_today_load_consumption",
  forecast: "sensor.deye_prognoza_solar_maine",
  reserve: "sensor.deye_rezerva_recomandata",
  limit: "sensor.deye_putere_descarcare_recomandata",
  tesla: "sensor.tesla_charging_power",
  boiler: "sensor.ariston_boiler_power_estimated",
  pause: "input_boolean.ha_automation_killswitch",
  manager: "automation.deye_management_baterie_si_prognoza",
};
export const valid = (s?: State) =>
  !!s && !["unknown", "unavailable"].includes(s.state);
export const number = (s?: State) =>
  valid(s) && s!.state.trim() !== "" && Number.isFinite(Number(s!.state))
    ? Number(s!.state)
    : null;
export const format = (n: number | null, digits = 1) =>
  n === null
    ? "--"
    : new Intl.NumberFormat("ro-RO", { maximumFractionDigits: digits }).format(
        n,
      );
export const value = (data: Snapshot | null, key: string) =>
  number(data?.states[data?.bindings?.[key] || bindings[key]]);
export const unit = (s?: State) => s?.attributes.unit_of_measurement || "";
export const name = (s?: State) =>
  s?.attributes.friendly_name || s?.entity_id || "Dispozitiv";
export const label = (s?: State) =>
  !s
    ? "Fara date"
    : {
        on: "Pornit",
        off: "Oprit",
        unavailable: "Indisponibil",
        unknown: "Fara date",
        heat: "Incalzire",
        cool: "Racire",
        idle: "In asteptare",
        charging: "Incarcare",
        discharging: "Descarcare",
        Normal: "Normal",
      }[s.state] ||
      (number(s) !== null ? `${format(number(s))} ${unit(s)}` : s.state);
export const helpers: Record<string, string> = {
  "input_number.deye_battery_min_soc": "Rezerva minima",
  "input_number.deye_battery_max_discharge_kw": "Descarcare maxima",
  "input_number.deye_battery_priority_soc": "Baterie pregatita la",
  "input_number.deye_forecast_confidence_percent":
    "Procent utilizat din prognoza",
  "input_number.deye_forecast_max_reserve_soc": "Rezerva adaptiva maxima",
  "input_number.deye_forecast_fallback_soc": "Rezerva fara prognoza",
  "input_number.deye_baseload_kw": "Consum de baza estimat",
  "input_number.tesla_solar_max_amps": "Curent maxim Tesla",
  "input_number.ariston_normal_temperature": "Temperatura de baza boiler",
  "input_number.hvac_summer_target_c": "Temperatura vara",
  "input_number.hvac_winter_target_c": "Temperatura iarna",
};
export type Device = {
  id: string;
  name: string;
  area: string;
  manufacturer: string;
  entries: State[];
  primary: State;
  floor: string;
  kind: string;
  pending?: boolean;
  external?: boolean;
  note?: string;
  coverage?: string;
  ratedPower?: number;
};
export function houseFloors(data: Snapshot | null): string[] {
  const plan = data?.house?.floors.map(f => f.name) || [];
  if (!data?.floors?.length) return plan;
  return data.floors.map(f => f.name).sort((a, b) => (plan.indexOf(a) < 0 ? 99 : plan.indexOf(a)) - (plan.indexOf(b) < 0 ? 99 : plan.indexOf(b)));
}
const resolvedRoom = (data: Snapshot, room?: HousePlan['rooms'][number]) => {
  const area = data.areas.find(a => a.area_id === room?.ha_area_id || a.name === room?.name);
  return {name: area?.name || room?.name || "Fara camera", floor: data.floors?.find(f => f.floor_id === area?.floor_id)?.name || room?.floor || "Neatribuite"};
};
export function houseRooms(data: Snapshot | null, floor = "all"): string[] {
  const names = (data?.house?.rooms || []).map(r => resolvedRoom(data!, r)).filter(r => floor === "all" || r.floor === floor).map(r => r.name);
  for (const area of data?.areas || []) {
    const f = data?.floors?.find(f => f.floor_id === area.floor_id)?.name;
    if (floor === "all" || f === floor) names.push(area.name);
  }
  return [...new Set(names)];
}
export const inLocation = (d: Device, floor = "all", area = "all") =>
  (floor === "all" || d.floor === floor) && (area === "all" || d.area === area);

export function controllable(d: Device): boolean {
  if (d.pending || d.external) return false;
  const id = d.primary.entity_id, domain = id.split('.')[0];
  if (/polling|firmware|update|access_point/.test(id) || id.startsWith('switch.deye')) return false;
  if (['switch','light','fan'].includes(domain)) return true;
  if (['climate.heat','climate.bedroom_heat'].includes(id)) return false;
  if (['climate','water_heater'].includes(domain)) return true;
  return domain === 'media_player' && (Number(d.primary.attributes.supported_features || 0) & (128|256|1|16384|4|8)) !== 0;
}

export function controlCategory(d: Device): string {
  if (d.kind === 'car' || d.kind === 'charger' || d.manufacturer.toLowerCase()==='tesla') return 'mobility';
  if (d.kind === 'light' || d.primary.entity_id.startsWith('light.')) return 'lights';
  if (d.primary.entity_id.startsWith('climate.')) return 'climate';
  if (d.primary.entity_id.startsWith('water_heater.')) return 'water';
  if (d.primary.entity_id.startsWith('media_player.')) return 'media';
  return 'power';
}
export const deviceReading = (d: Device) => {
  if (d.pending) return d.external ? "Control separat" : "De integrat";
  if (!valid(d.primary)) return label(d.primary);
  if (["door", "window"].includes(d.kind) && ["on", "off"].includes(d.primary.state)) return d.primary.state === "on" ? "Deschis" : "Inchis";
  if (d.kind === "smoke" && ["on", "off"].includes(d.primary.state)) return d.primary.state === "on" ? "Fum detectat" : "Fara fum detectat";
  const words: Record<string, string> = {disarmed: "Dezarmata", armed_away: "Armata - plecat", armed_home: "Armata - acasa", triggered: "Alarma declansata", arming: "Se armeaza", cleaning: "In curatare", docked: "La statie", returning: "Revine la statie", printing: "Imprimare", error: "Eroare"};
  return words[d.primary.state] || label(d.primary);
};
export function devices(data: Snapshot | null): Device[] {
  if (!data) return [];
  const allowed = ["light", "switch", "climate", "water_heater", "fan", "media_player", "alarm_control_panel", "cover", "vacuum"];
  const rank = ["water_heater", "climate", "alarm_control_panel", "vacuum", "media_player", "light", "switch", "cover", "binary_sensor", "sensor"];
  const registry = new Map(data.entities.map((e) => [e.entity_id, e]));
  const usable = (s: State) => {
    const e = registry.get(s.entity_id);
    return !e?.disabled_by && !e?.hidden_by && !e?.entity_category && !s.entity_id.startsWith("switch.deye") && !/polling|firmware|access_point/.test(s.entity_id);
  };
  const sort = (states: State[]) => states.sort((a, b) => {
    const score = (s: State) => { const r = rank.indexOf(s.entity_id.split(".")[0]); return r < 0 ? 99 : r; };
    return score(a) - score(b) || a.entity_id.localeCompare(b.entity_id);
  });
  const assigned = new Set<string>();
  const assignedEntities = new Set<string>();
  const result: Device[] = (data.house?.items || []).map(item => {
    const ids = item.device_ids || [];
    ids.forEach(id => assigned.add(id));
    const auxiliary = item.id === 'boiler' ? ['switch.boiler_ariston_power'] : [];
    auxiliary.forEach(id => assignedEntities.add(id));
    const entries = sort(Object.values(data.states).filter(s => usable(s) && (ids.includes(registry.get(s.entity_id)?.device_id) || s.entity_id === item.primary_entity || auxiliary.includes(s.entity_id)) && rank.includes(s.entity_id.split(".")[0])));
    const preferred = entries.find(s => s.entity_id === item.primary_entity);
    const primary = preferred || entries[0];
    if (item.primary_entity) assignedEntities.add(item.primary_entity);
    const room = resolvedRoom(data, data.house!.rooms.find(r => r.key === item.room));
    const deviceMeta = data.devices.find(d => ids.includes(d.id));
    const areaId = registry.get(primary?.entity_id)?.area_id || deviceMeta?.area_id;
    const nativeArea = data.areas.find(a => a.area_id === areaId);
    const nativeFloor = data.floors?.find(f => f.floor_id === nativeArea?.floor_id);
    return { id: item.id, name: item.name, area: nativeArea?.name || room.name, floor: nativeFloor?.name || room.floor, manufacturer: item.manufacturer || deviceMeta?.manufacturer || "", entries,
      primary: primary || { entity_id: "unconfigured." + item.id, state: "unavailable", attributes: { friendly_name: item.name } },
      pending: !primary, kind: item.kind, external: item.external_control, note: item.note, coverage: item.coverage ? nativeFloor?.name || room.floor : undefined, ratedPower: item.rated_power_kw };
  });
  const groups = new Map<string, State[]>();
  Object.values(data.states).forEach(s => {
    const entry = registry.get(s.entity_id);
    if (!usable(s) || assigned.has(entry?.device_id) || assignedEntities.has(s.entity_id)) return;
    const domain = s.entity_id.split(".")[0];
    const security = domain === "binary_sensor" && ["door", "window", "smoke", "gas", "moisture"].includes(s.attributes.device_class);
    if (!allowed.includes(domain) && !security) return;
    const id = entry?.device_id || s.entity_id;
    groups.set(id, [...(groups.get(id) || []), s]);
  });
  for (const [id, entries] of groups) {
      const d = data.devices.find((d) => d.id === id);
      const primary = sort(entries)[0];
      const areaId = registry.get(primary.entity_id)?.area_id || d?.area_id;
      const area = data.areas.find(a => a.area_id === areaId);
      result.push({
        id,
        entries,
        primary,
        name: d?.name_by_user || d?.name || name(primary),
        manufacturer: d?.manufacturer || "",
        area: area?.name || "Fara camera",
        floor: data.floors?.find(f => f.floor_id === area?.floor_id)?.name || "Neatribuite",
        kind: primary.entity_id.startsWith("binary_sensor.") ? primary.attributes.device_class || "binary_sensor" : primary.entity_id.split(".")[0],
      });
  }
  const floorOrder = houseFloors(data);
  const position = (floor: string) => { const index = floorOrder.indexOf(floor); return index < 0 ? 99 : index; };
  return result.sort((a, b) => position(a.floor) - position(b.floor) || a.area.localeCompare(b.area, "ro") || a.name.localeCompare(b.name, "ro"));
}
