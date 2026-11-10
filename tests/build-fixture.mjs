// Redacted HA states for isolated browser QA; this file is never served in production.
import {readFile,mkdir,writeFile} from 'node:fs/promises';
const source=JSON.parse(await readFile(process.argv[2],'utf8'));
const allowed=id=>/^(light\.|climate\.|water_heater\.|automation\.|media_player\.|vacuum\.|alarm_control_panel\.)/.test(id)||/^switch\.(living_lights|spots_sonoff|baby_spots|priza_uscator)/.test(id)||/^sensor\.(deye_|productie_solara_|consum_|injectie_|baterie_|tesla_charging_power|ariston_boiler_power_estimated|hvac_|hp_smart_tank|mi_body_composition_scale|mi_smart_scale)/.test(id)||/^input_number\.(deye_|ariston_normal_temperature|tesla_solar_max_amps|hvac_(summer|winter)_target_c)/.test(id)||/^input_boolean\.ha_automation_killswitch$/.test(id);
const states=Object.fromEntries(Object.entries(source.states).filter(([id])=>allowed(id)||id==='binary_sensor.boiler_ariston_is_heating'));
const entities=source.entities.filter(e=>states[e.entity_id]);
const deviceIds=new Set(entities.map(e=>e.device_id));
await mkdir('tests/fixtures',{recursive:true});
await writeFile('tests/fixtures/ha.json',JSON.stringify({user:{id:'test',name:'Cosmin',role:'configure'},csrf:'TEST_ONLY',connected:true,last_update:Date.now()/1000,states,entities,devices:source.devices.filter(d=>deviceIds.has(d.id)),areas:source.areas,floors:source.floors||[],house:JSON.parse(await readFile('server/house.json','utf8')),helpers:{}}));
console.log(`Prepared ${Object.keys(states).length} redacted test states`);
