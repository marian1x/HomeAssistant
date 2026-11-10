// Casa-only accounts UI on synthetic data (mock server, no HA, no physical commands).
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
const policy=await read('tests/fixtures/policy.json'), finance=await read('tests/fixtures/finance.json');
let who=null; // null | 'local' | 'admin'
const writes=[], bodies=[];
let accounts=[{id:'local:1',username:'ana',name:'Ana',role:'viewer',enrolled:true,must_change:false,disabled:false,locked:false,last_login:1794200000}];
const user=()=>who==='local'?{id:'local:2',name:'Ion',role:'control',local:true,admin:false}:{...fixture.user,role:'configure',local:false,admin:true};
const server=createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  let raw='';for await(const c of req)raw+=c;
  const json=(b,s=200)=>res.writeHead(s,{'Content-Type':'application/json'}).end(JSON.stringify(b));
  if(req.method==='POST'){writes.push(url.pathname);bodies.push(raw);}
  if(url.pathname==='/casa/auth/local'){assert.equal(req.headers.origin,`http://127.0.0.1:${server.address().port}`);
    const b=JSON.parse(raw);if(b.password!=='temp-pass-1234')return json({error:'Utilizator sau parola gresita.'},401);
    return json({next:'code',must_change:true,name:'Ion',enroll:{secret:'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',uri:'otpauth://totp/Casa%20Salavat%3Aion?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=Casa%20Salavat'}});}
  if(url.pathname==='/casa/auth/local/verify'){const b=JSON.parse(raw);if(b.code!=='123456')return json({error:'Cod incorect sau expirat.'},401);who='local';return json({ok:true});}
  if(url.pathname==='/casa/api/session'||url.pathname==='/casa/api/events'){
    if(!who)return json({error:'Autentificare necesara.'},401);
    const body={...fixture,user:user()};
    if(url.pathname==='/casa/api/session')return json(body);
    res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify(body)+'\n\n');return;}
  if(url.pathname==='/casa/api/v1/energy-dashboard')return json(finance);
  if(url.pathname==='/casa/api/v1/energy-policy')return json(policy);
  if(url.pathname==='/casa/api/history')return json({points:[],unit:'kW',period:'day'});
  if(url.pathname==='/casa/api/local-users'&&req.method==='GET')return json({service:{connected:true,online:true,name:'Casa servicii',admin:true},users:accounts});
  if(url.pathname==='/casa/api/local-users'&&req.method==='POST'){const b=JSON.parse(raw);accounts=[...accounts,{id:'local:3',username:b.username,name:b.name,role:b.role,enrolled:false,must_change:true,disabled:false,locked:false,last_login:null}];return json({id:'local:3',username:b.username,password:'abcd-efgh-jkmn-pqrs'});}
  if(url.pathname==='/casa/api/me/password')return json({saved:true,closed:1});
  if(req.method==='POST')return json({accepted:true});
  if(url.pathname==='/casa/api/users'||url.pathname==='/casa/api/audit')return json([]);
  try{const file=path.resolve(ROOT,'dist',url.pathname==='/casa/'?'index.html':url.pathname.replace(/^\/casa\//,''));
    const body=await readFile(file);res.writeHead(200,{'Content-Type':file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.webp')?'image/webp':'text/html'}).end(body);}catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}/casa/`;
const browser=await chromium.launch({channel:'msedge'});
if(OUT)await mkdir(OUT,{recursive:true});
const errors=[];
try{
  for(const [w,h] of [[1440,1000],[390,844]]){
    who=null;writes.length=0;bodies.length=0;
    const page=await browser.newPage({viewport:{width:w,height:h}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base);
    await page.locator('.auth-band').getByRole('button',{name:'Cont Casa',exact:true}).click();
    const dialog=page.getByRole('dialog',{name:'Conectare cu cont Casa'});
    await dialog.waitFor();
    await page.waitForFunction(()=>document.activeElement?.getAttribute('name')==='username',null,{timeout:2000});
    await dialog.getByLabel('Utilizator').fill('ion');await dialog.getByLabel('Parola').fill('gresit');
    await dialog.getByRole('button',{name:'Continua'}).click();
    await dialog.getByRole('alert').filter({hasText:'Utilizator sau parola gresita.'}).waitFor();
    await dialog.getByLabel('Parola').fill('temp-pass-1234');await dialog.getByRole('button',{name:'Continua'}).click();
    const enroll=page.getByRole('dialog',{name:'Configureaza codul de conectare'});
    await enroll.getByRole('img',{name:'Cod QR pentru aplicatia de autentificare'}).waitFor();
    assert.equal(await enroll.locator('.secret-value').innerText(),'JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP');
    await enroll.getByLabel('Parola noua',{exact:true}).fill('o parola noua lunga');
    await enroll.getByLabel('Repeta parola noua').fill('alta parola lunga');
    await enroll.getByLabel('Cod din aplicatie').fill('123456');
    await enroll.getByRole('button',{name:'Conectare'}).click();
    await enroll.getByRole('alert').filter({hasText:'nu coincid'}).waitFor();
    assert.equal(writes.filter(p=>p.endsWith('/verify')).length,0,'Mismatch is caught before sending');
    await enroll.getByLabel('Repeta parola noua').fill('o parola noua lunga');
    await shot(page,`enroll-${w}.png`);
    await enroll.getByRole('button',{name:'Conectare'}).click();
    await page.locator('.sidebar .account strong',{hasText:'Ion'}).waitFor({state:'attached'});
    assert.deepEqual(JSON.parse(bodies.at(-1)),{code:'123456',new_password:'o parola noua lunga'});
    assert.equal(await page.locator('.ha-link').count(),0,'No HA link for Casa accounts');
    await page.goto(base+'#setari');
    await page.getByText('Cont Casa, parola si cod din aplicatie').waitFor();
    await page.getByRole('heading',{name:'Schimba parola'}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Activeaza modul Admin'}).count(),0,'Control account has no Admin mode');
    await shot(page,`local-settings-${w}.png`,{fullPage:true});
    await page.close();
    // HA administrator manages Casa accounts.
    who='admin';writes.length=0;
    const admin=await browser.newPage({viewport:{width:w,height:h}});
    admin.on('pageerror',e=>errors.push(e.message));
    await admin.goto(base+'#setari');
    await admin.getByRole('button',{name:'Activeaza modul Admin'}).click();
    const section=admin.locator('.local-accounts');
    await section.getByText('Casa servicii · administrator HA').waitFor();
    await section.getByLabel('Utilizator').fill('maria');await section.getByLabel('Nume afisat').fill('Maria');
    await section.getByLabel('Rol cont nou').selectOption('configure');
    await section.getByRole('button',{name:'Adauga cont'}).click();
    await section.locator('.secret-panel').getByText('abcd-efgh-jkmn-pqrs').waitFor();
    assert.deepEqual(JSON.parse(bodies.at(-1)),{username:'maria',name:'Maria',role:'configure'});
    await section.getByRole('button',{name:'Sterge Ana'}).click();
    assert.equal(writes.filter(p=>p.endsWith('/delete')).length,0,'First click only arms the delete');
    await section.scrollIntoViewIfNeeded();
    await shot(admin,`admin-accounts-${w}.png`,{fullPage:true});
    assert.equal(await admin.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal overflow '+w);
    assert.ok(writes.every(p=>p==='/casa/api/local-users'),'Only the account creation was sent: '+writes.join(','));
    await admin.close();
  }
  assert.deepEqual(errors,[]);
  console.log('LOCAL OK');
}finally{await browser.close();server.closeAllConnections();server.close();}
