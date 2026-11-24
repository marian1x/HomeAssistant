// Nova layer on synthetic data (mock server, no HA, no physical commands): aurora canvas,
// live sentence, independence ring, command palette, page and theme transitions.
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const ROOT=fileURLToPath(new URL('..', import.meta.url));
const OUT=process.argv[2]; // optional screenshot folder
const shot=(p,file,opts={})=>OUT?p.screenshot({path:`${OUT}/${file}`,...opts}):null;
const require=createRequire(ROOT+'/package.json');
const {chromium}=require('@playwright/test');
const read=f=>readFile(path.join(ROOT,f),'utf8').then(JSON.parse);
const fixture=await read('tests/fixtures/ha.json');
fixture.house=await read('server/house.json');
fixture.states['sensor.home_energy_policy_status']={entity_id:'sensor.home_energy_policy_status',state:'ready',attributes:{power_valid:true,updated_at:new Date().toISOString(),tesla_quota:{at_home:true,last_poll:Date.now()/1000},
  telemetry:{live:false,status:'Masina adormita sau fara conexiune',last_message:Date.now()/1000-1800,signals_day:1840,signals_month:15200,stopped:null,config_exp:null,cost_month_usd:.12,api_month_usd:.45,stream_allowed_usd:5.5,trial:true}}};
// Synthetic Tesla readings (never production data); the page only reads what HA holds.
const car=(domain,key,state,attributes={})=>{fixture.states[domain+'.salavat_t3_'+key]={entity_id:domain+'.salavat_t3_'+key,state:String(state),attributes};};
car('sensor','battery',64,{unit_of_measurement:'%'});car('sensor','range',312.4,{unit_of_measurement:'km'});car('number','charge_limit',80);
car('sensor','temperature_inside',18.5,{unit_of_measurement:'°C'});car('sensor','temperature_outside',4,{unit_of_measurement:'°C'});
car('sensor','odometer',48213.7,{unit_of_measurement:'km'});car('sensor','energy_added',12.36,{unit_of_measurement:'kWh'});
car('sensor','charger_power',0,{unit_of_measurement:'kW'});car('sensor','charging_rate',0,{unit_of_measurement:'km/h'});
car('binary_sensor','charging','off');car('binary_sensor','charger','on');car('binary_sensor','asleep','on');car('binary_sensor','online','off');car('binary_sensor','windows','off');
car('device_tracker','location_tracker','home',{latitude:44.4,longitude:26.1});car('lock','doors','locked');car('switch','sentry_mode','off');
car('sensor','data_last_update_time','2026-11-10T06:15:00+00:00');
// Synthetic BMS attributes: a cold morning where the BMS allows only 10 A of 30 A.
Object.assign(fixture.states['sensor.deye_battery'].attributes,{'BMS SOC':29,'BMS Voltage':52.1,'BMS Current':-8,'BMS Charging Voltage':57.6,'BMS Charging Current':10,'BMS Max Charging Current':30,'BMS Discharging Current':200,'BMS Max Discharging Current':220,'BMS Other Symbol':0,'Corrected Capacity':317,'Nominal Voltage':48,'Life Cycle Rating':6000});
fixture.states['sensor.deye_battery_temperature'].state='3.1';
const batteryHistory=Array.from({length:289},(_,i)=>({time:Date.now()-(288-i)*300000,soc:20+i/20,temp:2.6+i/40,power:i<150?-400:-3000,charge_limit:i<150?10:157,discharge_limit:200}));
const policy=await read('tests/fixtures/policy.json'), finance=await read('tests/fixtures/finance.json');
const writes=[];
// Synthetic Tesla journal: one home charge with a measured split, one station charge without a
// price, two drives (one with a route).
const T0=Math.floor(Date.now()/1000)-86400;
const teslaLog={days:90,cost_per_kwh:.82,prices:{import:1.11,export:.45},usable_kwh:57.5,active:{drive:null,charge:null},
  monthly_km:[{start:Date.parse('2026-09-01'),km:1210.4},{start:Date.parse('2026-10-01'),km:980.2},{start:Date.parse('2026-11-01'),km:743.9}],
  charges:[{id:2,start:T0+3600,end:T0+3600*3,start_soc:30,end_soc:62,lat:45.7182,lon:21.2653,home:true,kwh:18.4,hours:2,max_kw:11,solar_kwh:6.2,battery_kwh:4.1,grid_kwh:9.9,split_s:7200,price_kwh:null,note:null,cost:15.3},
           {id:1,start:T0-86400,end:T0-86400+2400,start_soc:20,end_soc:70,lat:45.75,lon:21.22,home:false,kwh:30,hours:.67,max_kw:120,solar_kwh:0,battery_kwh:0,grid_kwh:0,split_s:0,price_kwh:null,note:null,cost:null}],
  drives:[{id:5,start:T0+7200*3,end:T0+7200*3+1800,approx_start:false,start_soc:62,end_soc:57,start_lat:45.7182,start_lon:21.2653,end_lat:45.84,end_lon:21.43,start_home:true,end_home:false,km:21.3,kwh:2.9,hours:.5,wh_km:135,avg_kmh:42.6,outside:3.4,cost:2.38,max_kmh:78,source:'telemetry',energy_basis:'energy',path:[[45.7182,21.2653],[45.76,21.3],[45.84,21.43]]},
          {id:4,start:T0-3000,end:T0,approx_start:true,start_soc:70,end_soc:66,start_lat:45.75,start_lon:21.22,end_lat:45.7182,end_lon:21.2653,start_home:false,end_home:true,km:8.1,kwh:2.3,hours:.83,wh_km:284,avg_kmh:9.8,outside:2.1,cost:1.89,path:[[45.75,21.22],[45.7182,21.2653]]}]};
// Layout is a display preference: kept apart from device commands.
let saved={sort:'default',order:[],groups:[]};const saves=[];
const usage={'light.driveway_floodlight':7,'switch.spots_sonoff_1000529656':2};
const server=createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  let raw='';for await(const c of req)raw+=c;
  const json=(b,s=200)=>res.writeHead(s,{'Content-Type':'application/json'}).end(JSON.stringify(b));
  const body={...fixture,user:{...fixture.user,role:'configure',local:false,admin:true}};
  if(url.pathname==='/casa/api/battery/bms')return json({available:true,status:'Citire reusita',poll_seconds:180,latest:{ts:Date.now()/1000-120,
    pack:{cells:[3.185,3.189,3.182,3.176,3.18,3.19,3.19,3.191,3.186,3.184,3.177,3.185,3.187,3.183,3.183,3.179],cell_temps:[3.1,3.2,3.0,3.1],cell_min:3.176,cell_max:3.191,cell_spread_mv:15,soc:29,current:-8,voltage:52.1,mos_temp:4.0},
    controller:{firmware:'V12.05',heater_on_below:0,heater_off_above:10,charge_lowtemp_protect:0,charge_lowtemp_protect_recover:2,charge_current_limit:157,discharge_current_limit:-200},heater_phase:'incalzire in timpul incarcarii'}});
  if(url.pathname==='/casa/api/battery/history')return json({hours:Number(url.searchParams.get('hours')),step:300,points:batteryHistory});
  if(url.pathname==='/casa/api/tesla/log')return json(teslaLog);
  if(url.pathname.startsWith('/casa/api/tesla/drive/'))return json({...teslaLog.drives[0],points:teslaLog.drives[0].path.map((p,i)=>[T0+i*600,...p,[25,78,52][i]])});
  if(url.pathname==='/casa/api/layout'&&req.method==='POST'){saved=JSON.parse(raw);saves.push(saved);return json({saved:true});}
  if(url.pathname==='/casa/api/layout')return json({...saved,usage,usage_days:30});
  if(req.method==='POST'){writes.push(url.pathname);return json({accepted:true});}
  if(url.pathname==='/casa/api/session')return json(body);
  if(url.pathname==='/casa/api/events'){res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify(body)+'\n\n');return;}
  if(url.pathname==='/casa/api/v1/energy-dashboard')return json(finance);
  if(url.pathname==='/casa/api/v1/energy-policy')return json(policy);
  if(url.pathname==='/casa/api/history')return json({points:Array.from({length:8},(_,i)=>({time:Date.now()-(8-i)*3600000,solar:Math.max(0,i-3),load:1+i*.2,battery:.5,grid:.1})),unit:'kW',period:'day'});
  if(url.pathname==='/casa/api/users'||url.pathname==='/casa/api/audit')return json([]);
  try{const file=path.resolve(ROOT,'dist',url.pathname==='/casa/'?'index.html':url.pathname.replace(/^\/casa\//,''));
    const data=await readFile(file);res.writeHead(200,{'Content-Type':file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.woff2')?'font/woff2':'text/html'}).end(data);}catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}/casa/`;
const browser=await chromium.launch({channel:'msedge',args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
if(OUT)await mkdir(OUT,{recursive:true});
const errors=[];
try{
  for(const [w,h] of [[1440,900],[390,844]]){
    writes.length=0;saved={sort:'default',order:[],groups:[]};saves.length=0;
    const context=await browser.newContext({viewport:{width:w,height:h},colorScheme:'dark'});
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base);
    await page.waitForFunction(()=>document.querySelector('.connection.live'));
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark','Without a saved choice the system preference decides');
    await page.locator('canvas.aurora.ready').waitFor();
    assert.equal(await page.evaluate(()=>{const c=document.querySelector('canvas.aurora');return c.width<=640&&c.height<=470;}),true,'Aurora renders at a third of the screen');
    // The sentence and the ring come from the synthetic readings: 1,26 kW from the battery at 29 %.
    assert.equal(await page.locator('.home-brief').innerText(),'Casa merge pe baterie: 1,26 kW, la 29%.');
    await page.getByRole('img',{name:'Independenta energetica azi: 83%'}).waitFor();
    const flux=page.getByRole('button',{name:'Flux energetic',exact:true});
    if(await flux.getAttribute('aria-expanded')==='false')await flux.click();
    assert.equal(await page.locator('.flow-line.house.energized .flow-spark').count(),1,'Sparks only on a wire that carries power');
    assert.equal(await page.locator('.flow-line.solar .flow-spark').count(),0,'No sparks from idle panels');
    await page.waitForTimeout(700);
    await shot(page,`home-dark-${w}.png`);
    // Command palette: keyboard only, never sends by itself.
    await page.keyboard.press('Control+k');
    const palette=page.getByRole('dialog',{name:'Comenzi rapide'});
    await palette.waitFor();
    const field=palette.getByRole('combobox');
    await page.waitForFunction(()=>document.activeElement?.getAttribute('role')==='combobox');
    assert.equal(await palette.getByRole('option').count()>=8,true,'Pages and actions are listed before typing');
    await shot(page,`palette-${w}.png`);
    await field.fill('living');
    await palette.getByRole('option',{name:/Living room lights/}).first().waitFor();
    await shot(page,`palette-search-${w}.png`);
    await field.fill('opreste living');
    await palette.getByRole('option',{name:/Opreste Living room lights/}).waitFor();
    await field.fill('porn');
    assert.equal(await palette.getByRole('option',{name:/^Opreste/}).count(),0);
    await field.fill('opreste liv');
    await page.keyboard.press('Enter');
    // Lights act directly (owner decision); the switch waits for HA, nothing is optimistic.
    await page.waitForFunction(()=>!document.querySelector('[role=dialog]'));
    assert.deepEqual(writes,['/casa/api/command'],'A light command from the palette is sent once, without a dialog');
    await page.keyboard.press('Control+k');
    await palette.getByRole('combobox').fill('opreste priza');
    await palette.getByRole('option',{name:/Opreste Priza uscator rufe/}).waitFor();
    await page.keyboard.press('Enter');
    await page.getByRole('dialog').filter({hasText:'Opresti Priza uscator rufe?'}).waitFor();
    await page.getByRole('button',{name:'Anuleaza',exact:true}).click();
    assert.equal(writes.length,1,'A socket command only opens the confirmation');
    await page.keyboard.press('Control+k');
    await palette.getByRole('combobox').fill('zzzz');
    await palette.getByText('Niciun rezultat').waitFor();
    await page.keyboard.press('Escape');
    await palette.waitFor({state:'detached'});
    // Page change through the palette, with a view transition.
    await page.getByRole('button',{name:'Comenzi rapide',exact:true}).click();
    await palette.getByRole('combobox').fill('energ');
    await page.keyboard.press('Enter');
    await page.waitForFunction(()=>location.hash==='#energie');
    await page.locator('.energy-instruments').waitFor();
    await page.waitForFunction(()=>!document.documentElement.dataset.vt);
    await shot(page,`energy-dark-${w}.png`);
    if(OUT)for(const route of ['costuri','politica','dispozitive','automatizari','setari']){await page.goto(base+'#'+route);await page.waitForTimeout(900);await shot(page,`${route}-dark-${w}.png`);}
    if(OUT){await page.goto(base);await page.locator('.home-device[data-device] .temperature-preset').first().click();await page.getByRole('dialog').waitFor();await page.waitForTimeout(400);await shot(page,`dialog-dark-${w}.png`);await page.getByRole('button',{name:'Anuleaza',exact:true}).click();}
    // Back button after a page change made from the navigation.
    await page.goto(base);await page.locator('.home-command-center').waitFor();
    await page.locator(w<800?'.mobile-nav':'.sidebar nav').getByRole('button',{name:'Energie',exact:true}).click();
    await page.waitForFunction(()=>location.hash==='#energie');await page.locator('.energy-instruments').waitFor();
    await page.goBack();
    await page.locator('.home-command-center').waitFor();
    // Theme reveal keeps the choice.
    await page.getByRole('button',{name:'Aspect luminos',exact:true}).click();
    await page.waitForFunction(()=>document.documentElement.dataset.theme==='light'&&!document.documentElement.dataset.vt);
    assert.equal(await page.evaluate(()=>localStorage.getItem('casa-theme')),'light');
    await page.waitForTimeout(400);
    await shot(page,`home-light-${w}.png`);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal overflow '+w);
    assert.equal(writes.length,1,'Only the one light command was sent');
    // Arrange mode: drag, arrows, groups and most used; controls are inert meanwhile.
    await page.goto(base);await page.locator('.home-command-center').waitFor();
    const names=async(group)=>page.locator('.home-device-group[aria-label="'+group+'"] .home-device-name h3').allInnerTexts();
    const before=await names('Iluminat');
    await page.getByRole('button',{name:'Aranjeaza',exact:true}).click();
    const bar=page.getByRole('region',{name:'Aranjare dispozitive'});await bar.waitFor();
    assert.equal(await page.evaluate(()=>[...document.querySelectorAll('.home-command-center [role=switch]')].every(e=>e.closest('[inert]')&&!e.matches(':focus'))),true,'Device switches are inert while arranging');
    await page.locator('.home-device-group[aria-label="Iluminat"] .home-device').first().click({force:true,position:{x:30,y:60}});
    await page.waitForTimeout(300);
    assert.equal(writes.length,1,'A press on an inert switch sends nothing');
    assert.deepEqual(await names('Iluminat'),before,'Entering arrange mode keeps the order');
    await page.getByRole('button',{name:'Muta '+before[1]+' mai sus',exact:true}).click();
    assert.deepEqual((await names('Iluminat')).slice(0,2),[before[1],before[0]],'Arrow moves one place');
    await page.waitForFunction(()=>true);await page.waitForTimeout(600);
    assert.equal(saves.at(-1).sort,'manual','Moving switches to the manual order');
    // Drag the last light onto the first place with the handle.
    const lights=page.locator('.home-device-group[aria-label="Iluminat"] .sortable');
    const count=await lights.count();
    // Phone: cards are stacked, so drag the second one up onto the first (both on screen).
    const pick=w<800?1:count-1;
    await lights.nth(pick).scrollIntoViewIfNeeded();
    const from=await lights.nth(pick).locator('.arrange-handle').boundingBox(), to=await lights.nth(0).boundingBox();
    const dragged=(await names('Iluminat'))[pick];
    await page.mouse.move(from.x+from.width/2,from.y+from.height/2);await page.mouse.down();
    const tx=to.x+30,ty=to.y+to.height-24;for(let i=1;i<=12;i++)await page.mouse.move(from.x+(tx-from.x)*i/12,from.y+(ty-from.y)*i/12);
    await page.mouse.up();
    assert.equal((await names('Iluminat'))[0],dragged,'Dragged card takes the first place');
    // Keyboard: the handle moves with the arrow keys and keeps focus.
    await lights.nth(0).locator('.arrange-handle').focus();await page.keyboard.press('ArrowDown');
    assert.equal((await names('Iluminat'))[1],dragged,'Arrow key moves the card');
    assert.equal(await page.evaluate(()=>document.activeElement?.closest('.sortable')?.querySelector('h3')?.textContent),dragged,'Focus follows the moved card');
    await page.getByRole('button',{name:'Muta grupul Climatizare mai sus',exact:true}).click();
    assert.deepEqual((await page.locator('.home-device-group').evaluateAll(g=>g.map(x=>x.getAttribute('aria-label')))).slice(0,2),['Climatizare','Iluminat']);
    await page.waitForTimeout(600);
    assert.deepEqual(saves.at(-1).groups.slice(0,2),['climate','lights']);
    await shot(page,`arrange-${w}.png`);
    await bar.getByRole('radio',{name:'Cele mai folosite'}).click();
    assert.equal((await names('Iluminat'))[0],'Driveway','Most used first: 7 commands');
    assert.equal(await page.locator('.home-device-group[aria-label="Iluminat"] .arrange-uses').first().innerText(),'7×');
    await page.waitForTimeout(600);
    assert.equal(saves.at(-1).sort,'usage');
    await bar.getByRole('button',{name:'Gata',exact:true}).click();
    assert.ok(await page.locator('.home-command-center').getByRole('switch').count()>0,'Controls are back after Gata');
    assert.equal(writes.length,1,'Arranging never sent a device command');
    await page.reload();await page.locator('.home-command-center').waitFor();
    assert.equal((await names('Iluminat'))[0],'Driveway','Order survives a reload');
    assert.equal((await page.locator('.home-device-group').first().getAttribute('aria-label')),'Climatizare','Group order survives a reload');
    // Inventory uses the same order and its own arrange button.
    await page.goto(base+'#dispozitive');await page.locator('.device-grid').waitFor();
    await page.getByRole('button',{name:'Aranjeaza',exact:true}).click();
    const first=await page.locator('.device-grid .sortable').first().locator('h3').innerText();
    await page.getByRole('button',{name:'Muta '+first+' mai jos',exact:true}).click();
    assert.equal(await page.locator('.device-grid .sortable').nth(1).locator('h3').innerText(),first);
    await page.getByRole('button',{name:'Gata',exact:true}).click();
    assert.equal(writes.length,1,'Inventory arranging sent no command');
    // Battery panel opens from the battery in the energy flow; read-only.
    await page.goto(base);await page.locator('.home-command-center').waitFor();
    const fluxToggle=page.getByRole('button',{name:'Flux energetic',exact:true});
    if(await fluxToggle.getAttribute('aria-expanded')==='false')await fluxToggle.click();
    await page.getByRole('button',{name:'Baterie · deschide panoul bateriei',exact:true}).click();
    await page.waitForFunction(()=>location.hash==='#baterie');
    const panel=page.locator('.battery-page');
    await panel.getByRole('heading',{name:'Easyway UNIV-16kWh (WP)'}).waitFor();
    await panel.getByRole('status').filter({hasText:'BMS-ul limiteaza incarcarea la 10 A'}).waitFor();
    const text=(await panel.innerText()).replace(/\s+/g,' ');
    for(const part of ['10 / 30 A','200 / 220 A','57,6 V','99,8','317 Ah','Niciunul','3,1'])assert.ok(text.includes(part),'Battery panel shows '+part);
    assert.equal(await panel.locator('.battery-chart .recharts-line').count(),4,'Four single-series charts');
    assert.equal(await panel.getByRole('button',{name:/Confirma|Porneste|Opreste/}).count(),0,'No battery controls');
    await panel.getByRole('button',{name:'48 h'}).click();
    await panel.getByRole('heading',{name:'Ultimele 48 de ore'}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal overflow on battery '+w);
    await page.waitForTimeout(400);
    await shot(page,`battery-${w}.png`,{fullPage:true});
    // Cells over Bluetooth: 16 bars, spread, temps, heater phase, read-only settings.
    const ble=panel.locator('.battery-ble');
    await ble.locator('.battery-cell').first().waitFor();
    assert.equal(await ble.locator('.battery-cell').count(),16,'16 cell bars');
    const bleText=(await ble.innerText()).replace(/\s+/g,' ');
    for(const part of ['15 mV','V12.05','incalzire in timpul incarcarii','10 °C','Incalzire oprita peste','157 A'])assert.ok(bleText.includes(part),'Cells section shows '+part);
    assert.ok(await ble.locator('.battery-cell.low').count()>=1 && await ble.locator('.battery-cell.high').count()>=1,'Min/max cells highlighted');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal overflow on cells '+w);
    await shot(page,`battery-cells-${w}.png`,{fullPage:true});
    assert.equal(writes.length,1,'Battery panel sends nothing');
    // Tesla page: read-only, values from the synthetic readings.
    await page.goto(base+'#tesla');
    const tesla=page.locator('.tesla-page');
    await tesla.getByRole('img',{name:'Nivel baterie 64%, limita de incarcare 80%'}).waitFor();
    for(const text of ['Adormita','312 km','18,5','48.214','12,4','Conectata, nu incarca','Acasa','Incuiate','Inchise','Ultimele date: 10 nov., 08:15','Fleet Telemetry','In asteptare','$0,12 / $5,50','oprire automata peste $2'])
      assert.ok((await tesla.innerText()).replace(/\s+/g,' ').includes(text),'Tesla page shows '+text);
    assert.equal(await tesla.locator('.tesla-grid').getByRole('button').count(),0,'No command button until the limit is moved');
    assert.equal(await tesla.getByRole('link',{name:'Deschide harta'}).getAttribute('rel'),'noreferrer');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal overflow on Tesla '+w);
    await page.waitForTimeout(500);
    await shot(page,`tesla-light-${w}.png`,{fullPage:true});
    assert.equal(writes.length,1,'Viewing Tesla sends nothing');
    // Owner charge limit: below the car's 50% floor, confirmed before it is sent.
    await tesla.getByRole('slider',{name:'Limita de incarcare'}).fill('35');
    await tesla.getByText('Sub 50%: masina ramane la 50%').waitFor();
    await tesla.getByRole('button',{name:'Seteaza 35%'}).click();
    assert.equal(writes.length,1,'Nothing sent before confirmation');
    await tesla.getByRole('group',{name:'Confirmare limita'}).getByRole('button',{name:'Confirma'}).click();
    await tesla.getByText('Limita 35% a fost salvata').waitFor();
    assert.deepEqual(writes.slice(1),['/casa/api/tesla/limit']);
    // Journal tabs.
    await tesla.getByRole('tab',{name:'Incarcari'}).click();
    await tesla.getByText('adauga pret').waitFor();
    const charges=(await tesla.innerText()).replace(/\s+/g,' ');
    for(const text of ['48,4 kWh','18,4 kWh','30→62%','15,30 lei','31 %'])assert.ok(charges.includes(text),'Charges show '+text);
    await tesla.getByRole('button',{name:/45,75, 21,22/}).click();
    await tesla.getByRole('textbox',{name:'Pret pe kWh'}).fill('2,35');
    await tesla.getByRole('button',{name:'Salveaza'}).click();
    await tesla.getByText('Salvat').waitFor();
    assert.deepEqual(writes.slice(2),['/casa/api/tesla/charge-price']);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal overflow on charges '+w);
    await shot(page,`tesla-charges-${w}.png`,{fullPage:true});
    await tesla.getByRole('tab',{name:'Deplasari'}).click();
    await tesla.locator('.tesla-map .leaflet-interactive').first().waitFor();
    const drives=(await tesla.innerText()).replace(/\s+/g,' ');
    for(const text of ['21,3','135 Wh/km','2,38 lei','Acasa →','~','1 cu traseu real'])assert.ok(drives.includes(text),'Drives show '+text);
    await tesla.locator('.speed-legend').waitFor();
    await tesla.locator('.speed-profile .recharts-area').first().waitFor();
    const drive=(await tesla.innerText()).replace(/\s+/g,' ');
    for(const text of ['Viteza maxima','78 km/h','contor energie baterie','Fleet Telemetry (traseu real)'])assert.ok(drive.includes(text),'Drive detail shows '+text);
    assert.ok(await tesla.locator('.tesla-map .leaflet-interactive, .tesla-map path').count()>=3,'Speed-coloured segments drawn');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal overflow on drives '+w);
    await page.waitForTimeout(300);
    await shot(page,`tesla-drives-${w}.png`,{fullPage:true});
    await tesla.getByRole('tab',{name:'Statistici'}).click();
    await tesla.locator('.tesla-stats .recharts-bar-rectangle').first().waitFor();
    assert.ok((await tesla.locator('.tesla-table').innerText()).includes('1.210,4'),'Monthly km table');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal overflow on stats '+w);
    await page.waitForTimeout(300);
    await shot(page,`tesla-stats-${w}.png`,{fullPage:true});
    assert.equal(writes.length,3,'Journal views send nothing');
    await context.close();
  }
  // Reduced motion: same content, no running animation, single aurora frame.
  const calm=await browser.newContext({viewport:{width:1280,height:800},reducedMotion:'reduce'});
  const page=await calm.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  await page.locator('.home-brief').waitFor();
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length),0,'No running animation under reduced motion');
  await page.locator('.sidebar nav').getByRole('button',{name:'Energie',exact:true}).click();
  await page.locator('.energy-instruments').waitFor();
  await calm.close();
  assert.deepEqual(errors,[]);
  console.log('NOVA OK');
}finally{await browser.close();server.closeAllConnections();server.close();}
