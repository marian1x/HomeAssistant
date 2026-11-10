// Production smoke check: no credentials are entered and no device commands are sent.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({channel:'msedge',args:['--host-resolver-rules=MAP salavat.home.ro 192.168.50.101','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const response=await page.goto('https://salavat.home.ro/casa/');
  assert.equal(response.status(),200);
  await page.locator('.home-command-center').waitFor();
  assert(await page.evaluate(()=>getComputedStyle(document.body,'::before').backgroundImage.includes('/assets/interior-')));
  await page.getByRole('link',{name:'Conectare cu Home Assistant'}).waitFor();
  await page.screenshot({path:'test-results/live-login.png',fullPage:true});
  assert.deepEqual(errors,[]);
  await page.getByRole('link',{name:'Conectare cu Home Assistant'}).click();
  await page.waitForURL(/\/home-assistant\/auth\/authorize/);
  await page.waitForTimeout(2500);
  console.log(JSON.stringify({app:'HTTP 200',interface:'glass control station rendered',auth_url:page.url().split('?')[0],auth_title:await page.title(),auth_text:(await page.locator('body').innerText()).slice(0,650),errors}));
  await page.screenshot({path:'test-results/live-ha-auth.png',fullPage:true});
}finally{await browser.close()}
