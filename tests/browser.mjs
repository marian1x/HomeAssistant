import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from '@playwright/test';
import {PNG} from 'pngjs';
const fixture=JSON.parse(await readFile('tests/fixtures/ha.json','utf8'));
// Synthetic TCL state exercises the newly bound device without any cloud requests.
const tclFixture=JSON.parse(await readFile('tests/fixtures/tcl.json','utf8'));
fixture.states[tclFixture.entity_id]=tclFixture;
fixture.entities.push({entity_id:tclFixture.entity_id,device_id:'64f01c0359ebb3569a50e8eb51041183',platform:'tcl_home_unofficial'});
fixture.house=JSON.parse(await readFile('server/house.json','utf8'));
const policyFixture=JSON.parse(await readFile('tests/fixtures/policy.json','utf8'));
const financeFixture=JSON.parse(await readFile('tests/fixtures/finance.json','utf8'));
fixture.states['sensor.home_energy_policy_status']={entity_id:'sensor.home_energy_policy_status',state:'ready',attributes:{power_valid:true,updated_at:new Date().toISOString(),tesla_quota:{at_home:true,last_poll:Date.now()/1000}}};
fixture.states['sensor.salavat_t3_charger_power']={entity_id:'sensor.salavat_t3_charger_power',state:'0',last_updated:new Date().toISOString(),attributes:{unit_of_measurement:'kW'}};
// Isolated switch input for testing the boiler's power control, never production data.
fixture.states['switch.boiler_ariston_power'] ??= {entity_id:'switch.boiler_ariston_power',state:'on',attributes:{friendly_name:'Boiler power test'}};
const writes=[];
const connections=new Set();
const server=createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const role=req.headers['x-test-role']||'configure';
  if(url.pathname==='/casa/api/v1/energy-dashboard'&&req.method==='GET'){
    const start=url.searchParams.get('start'),end=url.searchParams.get('end');
    const report={...financeFixture.report,tariff_mode:url.searchParams.get('mode')||'historical'};
    if(start&&end){report.start=start;report.end=end;report.days=report.days.filter(r=>r.date>=start&&r.date<=end);report.hours=report.hours.filter(r=>r.date>=start&&r.date<=end);}
    res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify({...financeFixture,report}));return;
  }
  if(url.pathname==='/casa/api/v1/energy-policy' && req.method==='GET'){
    res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(policyFixture));return;
  }
  if(url.pathname==='/casa/api/session'){
    if(role==='anonymous'){res.writeHead(401,{'Content-Type':'application/json'}).end('{"error":"Autentificare necesara"}');return}
    fixture.states['sensor.home_energy_policy_status'].attributes.updated_at=new Date().toISOString();
    res.setHeader('Content-Type','application/json');res.end(JSON.stringify({...fixture,user:{...fixture.user,role}}));return;
  }
  if(url.pathname==='/casa/api/events'){
    res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','Connection':'keep-alive'});
    res.write('data: '+JSON.stringify({...fixture,user:{...fixture.user,role}})+'\n\n');
    connections.add(res);const timer=setInterval(()=>res.write(': ping\n\n'),5000);
    req.on('close',()=>{clearInterval(timer);connections.delete(res)});return;
  }
  if(url.pathname==='/casa/api/history'){
    // Synthetic chart samples are isolated test inputs, not production telemetry.
    const points=Array.from({length:8},(_,i)=>({time:Date.now()-(8-i)*3600000,solar:Math.max(0,i-3),load:1+i*.2,battery:.5,grid:.1}));
    res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify({points,unit:url.searchParams.get('period')==='day'?'kW':'kWh'}));return;
  }
  if(req.method==='POST'){
    let text='';for await(const chunk of req)text+=chunk;
    writes.push({path:url.pathname,data:JSON.parse(text||'{}')});
    res.writeHead(200,{'Content-Type':'application/json'}).end('{"accepted":true,"enabled":false}');return;
  }
  if(url.pathname==='/casa/api/users'){
    res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify([
      {id:'test',name:'Cosmin',role:'configure',is_admin:true},
      {id:'family',name:'Family test',role:'viewer',is_admin:false},
      {id:'admin2',name:'Other admin test',role:'configure',is_admin:true},
    ]));return;
  }
  if(url.pathname==='/casa/api/audit'){res.writeHead(200,{'Content-Type':'application/json'}).end('[]');return}
  try{
    const file=path.resolve('dist',url.pathname==='/casa/'?'index.html':url.pathname.replace(/^\/casa\//,''));
    if(!file.startsWith(path.resolve('dist')+path.sep)){res.writeHead(403).end();return}
    const content=await readFile(file);res.writeHead(200,{'Content-Type':file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.webp')?'image/webp':'text/html'}).end(content);
  }catch{res.writeHead(404).end()}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({channel:'msedge',args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
await mkdir('test-results',{recursive:true});
const errors=[];
try{
  for(const width of [1440,1024,768,390,360]){
    const page=await browser.newPage({viewport:{width,height:width===1440?1000:844}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/casa/`);
    await page.waitForFunction(()=>document.querySelector('.connection.live'));
    await page.locator('.home-command-center').waitFor();
    await page.waitForTimeout(500);
    await page.screenshot({path:`test-results/overview-${width}.png`,fullPage:true});
    await page.screenshot({path:`test-results/overview-viewport-${width}.png`});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`No overflow ${width}`);
    assert.equal(writes.length,0,'Viewing never sends control commands');
    assert.equal(await page.locator('canvas').count(),0,'No house model or WebGL rendering');
    assert.equal(await page.locator('.pendant-art').count(),0,'No oversized lighting illustration');
    assert(await page.evaluate(()=>getComputedStyle(document.body,'::before').backgroundImage.includes('/assets/interior-')),'Existing bitmap background retained');
    const overlaps=await page.locator('.home-device').evaluateAll(tiles=>tiles.flatMap((t,i)=>tiles.slice(i+1).filter(o=>{const a=t.getBoundingClientRect(),b=o.getBoundingClientRect();return a.left<b.right-1&&a.right>b.left+1&&a.top<b.bottom-1&&a.bottom>b.top+1}).map(()=>i)));
    assert.deepEqual(overlaps,[],`No tile overlap ${width}`);
    await page.getByRole('button',{name:'Aspect intunecat',exact:true}).click();
    await page.screenshot({path:`test-results/overview-dark-${width}.png`,fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark');
    await page.reload();await page.waitForFunction(()=>document.querySelector('.connection.live'));
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark','Theme persisted');
    await page.getByRole('button',{name:'Aspect luminos',exact:true}).click();
    const energyToggle=page.getByRole('button',{name:'Flux energetic',exact:true});
    if(await energyToggle.getAttribute('aria-expanded')==='false')await energyToggle.click();
    assert.equal(await page.locator('.flow-node').count(),5);
    assert.equal(await page.locator('.flow-load').count(),4);
    const flowOverlaps=await page.locator('.flow-node').evaluateAll(nodes=>nodes.flatMap((n,i)=>nodes.slice(i+1).filter(o=>{const a=n.getBoundingClientRect(),b=o.getBoundingClientRect();return a.left<b.right-1&&a.right>b.left+1&&a.top<b.bottom-1&&a.bottom>b.top+1}).map(()=>i)));
    assert.deepEqual(flowOverlaps,[],`Energy nodes do not overlap ${width}`);
    await page.locator('.flow-load.ac').click();
    await page.locator('.flow-insight').getByRole('heading',{name:'Climatizare',exact:true}).waitFor();
    assert.equal(writes.length,0,'Interactive flow never commands devices');
    await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`test-results/flow-${width}.png`,fullPage:true});
    const chooseCategory=async(id,title)=>width<=600?page.getByRole('combobox',{name:'Tip dispozitiv',exact:true}).selectOption(id):page.getByRole('tablist',{name:'Tip dispozitiv'}).getByRole('tab',{name:new RegExp('^'+title)}).click();
    assert.equal(await page.locator('.home-device.offline').count(),0,'Offline devices hidden by default');
    await page.getByRole('checkbox',{name:'Indisponibile',exact:true}).check();
    assert(await page.locator('.home-device.offline').count()>0,'Offline inventory can be inspected without enabling controls');
    await page.getByRole('checkbox',{name:'Indisponibile',exact:true}).uncheck();
    await chooseCategory('lights','Iluminat');
    const allLights=await page.locator('.home-device').count();assert(allLights>1,'All rooms lists all integrated lights');
    await page.getByRole('tablist',{name:'Nivel',exact:true}).getByRole('tab',{name:'Etaj',exact:true}).click();
    await page.getByRole('tablist',{name:'Camere',exact:true}).getByRole('tab',{name:'Dormitor Mic',exact:true}).click();
    assert.equal(await page.locator('.home-device').count(),1);
    assert.equal(await page.locator('.home-device').getAttribute('data-device'),'baby-spots');
    await chooseCategory('climate','Climatizare');
    assert.equal(await page.locator('.home-device').count(),0,'No upstairs hall AC in the small bedroom');
    await page.getByRole('tablist',{name:'Camere',exact:true}).getByRole('tab',{name:'Toate camerele',exact:true}).click();
    assert.equal(await page.locator('.home-device').count(),1,'All upstairs rooms contains Whirlpool');
    await page.getByRole('tablist',{name:'Nivel',exact:true}).getByRole('tab',{name:'Toata casa',exact:true}).click();
    assert.equal(await page.locator('.home-device').count(),2,'All rooms contains house ACs, not the Tesla HVAC or raw Tuya thermostats');
    const tclTile=page.locator('.home-device[data-device="tcl"]');
    await tclTile.getByRole('button',{name:'TCL FreshIN · seteaza 25 grade',exact:true}).click();
    await page.getByRole('dialog').waitFor();assert.equal(writes.length,0);
    await page.getByRole('button',{name:'Anuleaza',exact:true}).click();
    await page.getByRole('tablist',{name:'Nivel',exact:true}).getByRole('tab',{name:'Etaj',exact:true}).click();
    await page.getByRole('tablist',{name:'Camere',exact:true}).getByRole('tab',{name:'Dormitor Mare',exact:true}).click();
    await page.getByRole('button',{name:'Inventar dispozitive',exact:true}).click();
    await page.getByRole('heading',{name:'Reading lights',exact:true}).waitFor();
    const reading=page.locator('.device-card').filter({has:page.getByRole('heading',{name:'Reading lights',exact:true})});
    assert.equal(await reading.getByRole('switch').count(),0,'Unintegrated Hue has no fake control');
    await page.getByRole('tablist',{name:'Nivel dispozitive',exact:true}).getByRole('tab',{name:'Parter',exact:true}).click();
    await page.getByRole('combobox',{name:'Camera',exact:true}).selectOption({label:'Living'});
    await page.getByRole('heading',{name:'TCL FreshIN',exact:true}).waitFor();
    await page.getByRole('button',{name:'Temperatura TCL FreshIN',exact:true}).click();
    assert.equal(await page.getByRole('combobox',{name:'Treapta ventilator',exact:true}).inputValue(),'3');
    await page.screenshot({path:`test-results/tcl-controls-${width}.png`});
    await page.getByRole('combobox',{name:'Treapta ventilator',exact:true}).selectOption('6');
    await page.getByRole('dialog').getByText('Setezi ventilatorul TCL FreshIN pe 6?',{exact:true}).waitFor();
    assert.equal(writes.length,0,'TCL fan change requires confirmation');
    await page.getByRole('button',{name:'Anuleaza',exact:true}).click();
    assert.equal(writes.length,0,'Cancelled TCL fan change does not command the device');
    await page.getByRole('combobox',{name:'Camera',exact:true}).selectOption({label:'Camera tehnica'});
    assert.equal(await page.locator('.device-card').count(),1,'Technical room contains only its own boiler');
    await page.getByRole('heading',{name:'Boiler Ariston',exact:true}).waitFor();
    await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(250);
    await page.screenshot({path:`test-results/room-boiler-${width}.png`,fullPage:true});
    await page.getByRole('tablist',{name:'Nivel dispozitive',exact:true}).getByRole('tab',{name:'Toate nivelurile',exact:true}).click();
    await page.locator(width<800?'.mobile-nav':'.sidebar nav').getByRole('button',{name:'Dispozitive',exact:true}).click();
    await page.getByRole('searchbox',{name:'Cauta dispozitive'}).fill('zzzz_not_found');
    await page.getByText('Niciun dispozitiv pentru filtrele alese.').waitFor();
    if(width<800){await page.getByRole('button',{name:'Meniu',exact:true}).click()}
    await page.getByRole('button',{name:'Setari',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'Modifica Descarcare maxima',exact:true}).count(),0,'User view hides configuration');
    await page.getByRole('button',{name:'Activeaza modul Admin'}).click();
    await page.getByRole('button',{name:'Modifica Descarcare maxima',exact:true}).click();
    await page.getByRole('dialog').waitFor();
    const bound=await page.getByRole('dialog').boundingBox();assert(bound.x>=0&&bound.x+bound.width<=width);
    await page.screenshot({path:`test-results/settings-${width}.png`});
    await page.getByRole('button',{name:'Anuleaza',exact:true}).click();
    assert.equal(writes.length,0,'Cancelled dialog never sends commands');
    await page.locator(width<800?'.mobile-nav':'.sidebar nav').getByRole('button',{name:'Energie',exact:true}).click();
    await page.getByRole('heading',{name:'Fluxuri energetice',exact:true}).waitFor();
    await page.getByRole('button',{name:/^Import /}).click();
    await page.getByRole('heading',{name:'Reteaua electrica',exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Energy layout ${width}`);
    await page.screenshot({path:`test-results/energy-${width}.png`,fullPage:true});
    await page.locator(width<800?'.mobile-nav':'.sidebar nav').getByRole('button',{name:'Automatizari',exact:true}).click();
    await page.getByRole('heading',{name:'Regulile casei',exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Rules layout ${width}`);
    assert.equal(writes.length,0,'Navigation never writes to HA');
    if(width<800)await page.getByRole('button',{name:'Meniu',exact:true}).click();
    await page.getByRole('button',{name:'Politica Energie',exact:true}).click();
    await page.getByRole('heading',{name:'Casa, in echilibru',exact:true}).waitFor();
    await page.getByText('Reincarcare prioritara',{exact:true}).waitFor({state:'hidden'});
    await page.locator('.policy-device').first().waitFor();
    await page.locator('.policy-group').filter({hasText:'Profiluri iarna'}).locator('summary').click();
    assert.equal(await page.getByLabel('Prag frig sever').inputValue(),'-15');
    assert(await page.getByLabel('Prag frig sever').isEnabled());
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Policy layout ${width}`);
    await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(300);
    await page.screenshot({path:`test-results/policy-${width}.png`,fullPage:true});
    await page.screenshot({path:`test-results/policy-viewport-${width}.png`});
    await page.getByLabel('Prag frig sever').fill('-16');
    assert.equal(writes.length,0,'Policy drafts never send commands');
    await page.getByRole('button',{name:'Renunta la modificari',exact:true}).click();
    assert.equal(writes.length,0,'Reset policy is local only');
    if(width<800)await page.getByRole('button',{name:'Meniu',exact:true}).click();
    await page.getByRole('button',{name:'Costuri si prognoza',exact:true}).click();
    await page.getByRole('heading',{name:'Sold energetic pe zile',exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Finance layout ${width}`);
    await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(300);
    await page.screenshot({path:`test-results/finance-${width}.png`,fullPage:true});
    await page.screenshot({path:`test-results/finance-viewport-${width}.png`});
    await page.getByRole('tab',{name:'Consum pe zile',exact:true}).click();
    await page.getByRole('heading',{name:'Consumul unei zile',exact:true}).waitFor();
    assert(await page.getByRole('combobox',{name:'Zi analizata',exact:true}).inputValue());
    await page.getByRole('tab',{name:'Prognoza 6 zile',exact:true}).click();
    assert.equal(await page.locator('.finance-forecast-days > article').count(),6);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Forecast layout ${width}`);
    await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(200);
    await page.screenshot({path:`test-results/forecast-${width}.png`,fullPage:true});
    await page.getByRole('tab',{name:'Bilant financiar',exact:true}).click();
    await page.locator('.finance-prices summary').click();
    await page.getByRole('spinbutton',{name:'Pret cumparare energie',exact:true}).fill('1.12');
    assert.equal(writes.length,0,'Price drafts do not write to HA');
    const downloadPromise=page.waitForEvent('download');
    await page.getByRole('button',{name:'Export CSV',exact:true}).click();
    assert((await downloadPromise).suggestedFilename().endsWith('.csv'));
    assert.equal(writes.length,0,'CSV is generated locally with no HA mutation');
    await page.close();
    console.log(`PASS ${width}: tactile menus, assets, themes, rooms, local draft controls, responsive, no automatic writes`);
  }
  for(const role of ['viewer','control','anonymous']){
    const page=await browser.newPage({viewport:{width:390,height:844},extraHTTPHeaders:{'X-Test-Role':role}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/casa/`);
    if(role==='anonymous')await page.getByRole('link',{name:'Conectare cu Home Assistant'}).waitFor();
    await page.locator('.home-command-center').waitFor();
    assert.equal(await page.getByRole('button',{name:'Activeaza modul Admin'}).count(),0);
    if(role==='viewer'||role==='anonymous')assert(await page.getByRole('button',{name:/Opreste toate automatizarile|Dezactiveaza pauza globala/}).isDisabled());
    if(role !== 'anonymous'){
      await page.getByRole('button',{name:'Meniu',exact:true}).click();
      await page.getByRole('button',{name:'Setari',exact:true}).click();
      await page.locator('.account-settings').waitFor();
      assert.equal(await page.getByText('Acces utilizatori',{exact:true}).count(),0);
      assert.equal(await page.getByRole('button',{name:/Modifica /}).count(),0);
      await page.screenshot({path:`test-results/account-${role}-390.png`});
    }
    await page.close();console.log(`PASS ${role} role`);
  }
  const manual=await browser.newPage({viewport:{width:1440,height:1000}});
  await manual.goto(`http://127.0.0.1:${server.address().port}/casa/`);
  await manual.waitForFunction(()=>document.querySelector('.connection.live'));
  const lightToggle=manual.locator('.home-device.lights').first().getByRole('switch');
  assert(await lightToggle.isEnabled());
  await lightToggle.click();assert.equal(writes.length,0,'Toggle requires confirmation');
  await manual.getByRole('dialog').getByRole('button',{name:'Confirma',exact:true}).click();
  await manual.getByRole('dialog').waitFor({state:'hidden'});
  assert.equal(writes.length,1,'Exactly one explicit mock command');
  assert.equal(writes[0].path,'/casa/api/command');
  assert(['turn_on','turn_off'].includes(writes[0].data.action));
  assert(await lightToggle.getAttribute('aria-checked')==='true','No optimistic physical state mutation');
  await manual.getByRole('searchbox',{name:'Cautare rapida'}).fill('zzzz_not_found');
  await manual.getByRole('searchbox',{name:'Cautare rapida'}).press('Enter');
  await manual.getByText('Niciun dispozitiv pentru filtrele alese.').waitFor();
  await manual.getByRole('button',{name:'Setari',exact:true}).click();
  assert.equal(await manual.getByText('Acces utilizatori',{exact:true}).count(),0,'User view hides administration');
  await manual.getByRole('button',{name:'Activeaza modul Admin',exact:true}).click();
  await manual.getByText('Acces utilizatori',{exact:true}).waitFor();
  const familyRole=manual.getByRole('combobox',{name:'Acces Family test',exact:true});
  await familyRole.selectOption('control');
  await manual.getByRole('status').getByText('Acces actualizat.').waitFor();
  assert.equal(writes.length,2);
  assert.deepEqual(writes[1],{path:'/casa/api/users/family',data:{role:'control'}});
  assert.equal(await manual.getByRole('combobox',{name:'Acces Cosmin',exact:true}).count(),0);
  assert.equal(await manual.getByRole('combobox',{name:'Acces Other admin test',exact:true}).count(),0);
  await manual.screenshot({path:'test-results/admin-users-1440.png',fullPage:true});
  await manual.getByRole('button',{name:'Revino la modul User',exact:true}).click();
  assert.equal(await manual.getByText('Acces utilizatori',{exact:true}).count(),0);
  assert.equal(await manual.getByRole('button',{name:'Jurnal',exact:true}).count(),0);
  await manual.getByRole('button',{name:'Dispozitive',exact:true}).click();
  await manual.getByRole('searchbox',{name:'Cauta dispozitive',exact:true}).fill('Bedroom Speaker');
  await manual.getByRole('button',{name:'Volum Bedroom speaker',exact:true}).click();
  const volumeSlider=manual.getByRole('slider',{name:'Volum media',exact:true});
  await volumeSlider.press('Home');
  for(let i=0;i<35;i++)await volumeSlider.press('ArrowRight');
  await manual.getByRole('dialog').getByText('35%',{exact:true}).waitFor();
  assert.equal(writes.length,2,'Volume edits require explicit confirmation');
  await manual.getByRole('dialog').getByRole('button',{name:'Confirma',exact:true}).click();
  await manual.getByRole('dialog').waitFor({state:'hidden'});
  assert.equal(writes.length,3);
  assert.equal(writes[2].data.action,'set_volume');
  assert.equal(writes[2].data.value,35);
  await manual.getByRole('searchbox',{name:'Cauta dispozitive',exact:true}).fill('Boiler Ariston');
  assert(await manual.getByRole('switch',{name:'Boiler power test',exact:true}).isEnabled());
  await manual.getByRole('button',{name:'Temperatura Boiler',exact:true}).click();
  await manual.getByRole('combobox',{name:'Mod boiler',exact:true}).selectOption('BOOST');
  await manual.getByRole('button',{name:'Anuleaza',exact:true}).click();
  assert.equal(writes.length,3,'Cancelled boiler Boost never sends a command');
  await manual.close();console.log('PASS explicit mock command, confirmation, no optimistic state, quick search');
  assert.deepEqual(errors,[]);
}finally{await browser.close();for(const response of connections)response.end();server.closeAllConnections();await new Promise(resolve=>server.close(resolve))}
