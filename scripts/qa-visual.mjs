// Isolated read-only visual QA. Never posts an approval or starts/reset a scenario.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const evidence = path.join(root,'evidence');
const pending = process.argv.includes('--pending');
const prefix = pending ? 'visual-manual' : 'visual-offline';
const profile = await mkdtemp(path.join(tmpdir(),'relay-visual-'));
const browser = spawn(process.env.CHROME_BIN||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',[
  '--headless=new','--no-first-run','--no-default-browser-check',
  '--disable-background-networking','--disable-gpu','--remote-debugging-port=0',
  `--user-data-dir=${profile}`,'--window-size=1280,800','about:blank'
],{stdio:'ignore'});
let socket;
let nextId = 0;
const calls = new Map();
const posted = [];
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
function command(method,params = {}) {
  return new Promise((resolve,reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => {calls.delete(id);reject(new Error(`CDP timeout: ${method}`));},15000);
    calls.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression) {
  const result = await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'Page evaluation failed');
  return result.result.value;
}
async function waitFor(expression,timeout = 15000) {
  const until = Date.now()+timeout;
  while (Date.now()<until) {if (await evaluate(expression)) return;await sleep(200);}
  throw new Error(`Page condition not reached: ${expression}`);
}
async function snapshot(name) {
  const metrics = await evaluate(`({
    innerWidth,innerHeight,scrollWidth:document.documentElement.scrollWidth,
    horizontalOverflow:document.documentElement.scrollWidth>innerWidth,
    connection:document.querySelector('#connection')?.innerText,
    notice:document.querySelector('#global-notice')?.innerText,
    activeOwner:document.querySelector('[data-role][aria-selected="true"]')?.innerText,
    humanMessages:[...document.querySelectorAll('.message:not(.load-message)')].map(m=>({id:m.dataset.messageId,text:m.querySelector('.message-text')?.innerText,state:m.querySelector('.message-state')?.innerText})),
    failedTestRetryButtons:[...document.querySelectorAll('.load-message [data-retry]')].map(button=>({messageId:button.dataset.retry,label:button.innerText})),
    pendingCards:document.querySelectorAll('[data-review]').length,
    reviewOpen:document.querySelector('#review-dialog')?.open,
    reviewTitle:document.querySelector('#review-title')?.innerText,
    reviewText:document.querySelector('#review-dialog')?.open?document.querySelector('#review-content')?.innerText:null,
    caseStatus:document.querySelector('#case-status')?.innerText
  })`);
  const shot = await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  const output = path.join(evidence,`${prefix}-${name}.png`);
  await writeFile(output,Buffer.from(shot.data,'base64'));
  return {...metrics,path:output};
}
try {
  let port;
  const until=Date.now()+12000;
  while (Date.now()<until) {
    try {port=Number((await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);if(port)break;}catch{}
    if(browser.exitCode !== null)throw new Error(`Isolated Chrome exited: ${browser.exitCode}`);
    await sleep(100);
  }
  if(!port)throw new Error('Isolated Chrome did not expose a local debugging port');
  const tabs=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
  const target=tabs.find(tab=>tab.type==='page');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{
    const value=JSON.parse(event.data);
    if(value.method==='Network.requestWillBeSent' && value.params.request.method==='POST')posted.push({url:value.params.request.url,method:'POST'});
    const call=calls.get(value.id);
    if(!call)return;
    clearTimeout(call.timer);calls.delete(value.id);
    if(value.error)call.reject(new Error(value.error.message));else call.resolve(value.result);
  });
  await command('Page.enable');await command('Runtime.enable');await command('Network.enable');
  await command('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:'http://127.0.0.1:4318/'});
  await waitFor(`document.querySelector('#connection')?.innerText.includes('App')`);
  await mkdir(evidence,{recursive:true});
  const observations=[];
  let coordinationBefore = null;
  const coordinationProjection = `fetch('/api/coordination').then(r=>r.json()).then(s=>({mode:s.mode,status:s.status,sharedMessages:s.messages?.length,proposals:(s.proposals||[]).map(p=>({id:p.id,role:p.role,kind:p.kind,status:p.status,digest:p.digest}))}))`;
  if(pending) {
    await waitFor(`document.querySelector('[data-review]') || document.querySelector('[data-open-role]')`,20000);
    coordinationBefore = await evaluate(coordinationProjection);
    if(coordinationBefore.mode !== 'manual')throw new Error('Visual approval QA requires actual manual mode');
    await evaluate(`document.querySelector('[data-open-role]')?.click()`);
    await waitFor(`document.querySelector('[data-review]')`);
    observations.push(await snapshot('laptop'));
    await evaluate(`document.querySelector('[data-review]').click()`);
    await waitFor(`document.querySelector('#review-dialog')?.open===true`);
    observations.push(await snapshot('review'));
    // Closing a review is local UI only; it neither rejects nor approves the proposal.
    await evaluate(`document.querySelector('[data-cancel-review]').click()`);
  } else observations.push(await snapshot('laptop'));
  await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate('window.scrollTo(0,0)');
  observations.push(await snapshot('mobile'));
  if(pending) {
    await evaluate(`document.querySelector('#owner-title').scrollIntoView({block:'start'})`);
    observations.push(await snapshot('mobile-owner'));
    await evaluate(`document.querySelector('[data-review]').click()`);
    await waitFor(`document.querySelector('#review-dialog')?.open===true`);
    observations.push(await snapshot('mobile-review'));
  }
  const coordinationAfter = pending ? await evaluate(coordinationProjection) : null;
  const report={at:new Date().toISOString(),mode:pending?'actual manual pending proposal':'actual offline-bridge view',userBrowserTouched:false,approvalsClicked:0,postRequests:posted,coordinationBefore,coordinationAfter,observations};
  await writeFile(path.join(evidence,`${prefix}-qa.json`),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
  if(posted.length)throw new Error('Read-only QA unexpectedly emitted a POST request');
  if(observations.some(o=>o.horizontalOverflow))throw new Error('Horizontal overflow observed');
} finally {
  socket?.close();browser.kill('SIGTERM');
  await new Promise(resolve=>{if(browser.exitCode!==null)return resolve();browser.once('exit',resolve);setTimeout(resolve,3000);});
  await rm(profile,{recursive:true,force:true}).catch(()=>{});
}
