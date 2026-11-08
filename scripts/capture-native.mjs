// Actual native Mattermost camera. Human story posts are issued only by the
// explicitly cued native-stage runner, after verified pre-roll on all views.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir,rename,rm,stat} from 'node:fs/promises';
import {createHash,randomUUID} from 'node:crypto';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2);
const option=(name,fallback)=>{const n=args.indexOf(name);return n<0?fallback:args[n+1];};
const output=path.resolve(option('--out',path.join(ROOT,'recording/native-take')));
const configPath=path.resolve(option('--config',path.join(ROOT,'agents/.runtime/native/browser-session.json')));
const width=1600,height=900;
const interval=Number(option('--interval-ms','200'));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const jsonFile=async file=>JSON.parse(await readFile(file,'utf8'));
async function atomic(file,value){await writeFile(file+'.tmp',JSON.stringify(value,null,2));await rename(file+'.tmp',file);}
const controlFile=path.join(output,'control.json');
const statusFile=path.join(output,'status.json');
if(['cue','stop','focus'].includes(args[0])){
  const status=await jsonFile(statusFile);
  if(args[0]==='cue'&&!['ready','stage_complete'].includes(status.camera))throw new Error(`Camera not ready for a new stage (${status.camera})`);
  const control={type:args[0]==='cue'?'stage':args[0],stage:args[0]==='cue'?args[1]:undefined,room:args[0]==='focus'?args[1]:undefined,postId:args[0]==='focus'?args[2]:undefined,nonce:randomUUID(),at:Date.now()};
  await atomic(controlFile,control);console.log(JSON.stringify({issued:control.type,stage:control.stage,nonce:control.nonce}));
  process.exit(0);
}

class CDP{
  constructor(socket){this.socket=socket;this.id=0;this.calls=new Map();socket.addEventListener('message',event=>{const value=JSON.parse(event.data),call=this.calls.get(value.id);if(!call)return;clearTimeout(call.timer);this.calls.delete(value.id);value.error?call.reject(new Error(value.error.message)):call.resolve(value.result);});socket.addEventListener('close',()=>{for(const call of this.calls.values()){clearTimeout(call.timer);call.reject(new Error('Isolated browser connection closed'));}this.calls.clear();});}
  static async connect(url){const socket=new WebSocket(url);await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});return new CDP(socket);}
  send(method,params={},timeout=10000){return new Promise((resolve,reject)=>{const id=++this.id,timer=setTimeout(()=>{this.calls.delete(id);reject(new Error(`Browser timeout: ${method}`));},timeout);this.calls.set(id,{resolve,reject,timer});this.socket.send(JSON.stringify({id,method,params}));});}
  async evaluate(expression){const result=await this.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},15000);if(result.exceptionDetails)throw new Error('Native page evaluation failed');return result.result.value;}
  close(){this.socket.close();}
}
function jpegDimensions(buffer){
  if(buffer[0]!==0xff||buffer[1]!==0xd8)throw new Error('Camera did not return a JPEG');
  let i=2;
  while(i<buffer.length){while(buffer[i]===0xff)i++;const marker=buffer[i++];if(marker===0xd9||marker===0xda)break;const length=buffer.readUInt16BE(i);if([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker))return {width:buffer.readUInt16BE(i+5),height:buffer.readUInt16BE(i+3)};i+=length;}
  throw new Error('JPEG dimensions not found');
}
function localURL(value){const url=new URL(value);if(url.protocol!=='http:'||!['127.0.0.1','localhost'].includes(url.hostname))throw new Error('Camera configuration must use local services');return url;}
await mkdir(output,{recursive:true});
try{await stat(path.join(output,'markers.json'));throw new Error('Capture directory already contains a take; use a new --out path');}catch(error){if(error.code!=='ENOENT')throw error;}
const config=await jsonFile(configPath);
const mm=localURL(config.mattermostUrl||config.mattermost_url||config.baseUrl);
const observer=config.observer||config.session||{};
const sessions=config.sessions;
if(!sessions?.teamchat?.token||!sessions?.harborcloud?.token)throw new Error('Private scoped Maya and Leo browser sessions are not configured');
const nativeBase=localURL(config.nativeApiBase||'http://127.0.0.1:4319').origin;
const profile=await mkdtemp(path.join(tmpdir(),'relay-native-camera-'));
const browser=spawn(process.env.CHROME_BIN||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',[
  '--headless=new','--no-first-run','--no-default-browser-check','--disable-background-networking',
  '--disable-gpu','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows','--remote-debugging-port=0',`--user-data-dir=${profile}`,
  '--window-size=1600,900','about:blank'],{stdio:'ignore'});
const views={},contexts={},markers=[],visibleEvents=[],seenPosts=new Set(),preflight={at:Date.now(),dimensions:{width,height},userBrowserTouched:false,separateRoleBrowserContexts:true,rooms:{}};
let browserCDP,stopping=false,active=null,lastControl=null,lastFlush=0,totalErrors=0;
let cameraState='starting',flushTail=Promise.resolve();
const secretStrings=[observer.token,...Object.values(sessions).map(s=>s.token)].filter(Boolean);
function safe(value){let text=JSON.stringify(value);for(const secret of secretStrings)if(text.includes(secret))throw new Error('Private capture credential appeared in an export');return value;}
async function status(camera,fields={}){cameraState=camera;await atomic(statusFile,safe({camera,at:Date.now(),dimensions:{width,height},frames:Object.fromEntries(Object.entries(views).map(([key,v])=>[key,v.frames.length])),...fields}));}
function flush(){flushTail=flushTail.then(async()=>{for(const[key,v]of Object.entries(views))await atomic(path.join(output,key,'frames.json'),v.frames);await atomic(path.join(output,'markers.json'),safe(markers));await atomic(path.join(output,'visible-events.json'),safe(visibleEvents));lastFlush=Date.now();});return flushTail;}
async function screenshot(view,save=true){if(view.framing)return null;const posts=save?await view.cdp.evaluate(`(()=>{const rows=new Map();for(const e of document.querySelectorAll('[id]')){const m=e.id.match(/(?:^|_)([a-z0-9]{26})$/),text=e.innerText||'';if(!m||rows.has(m[1])||text.trim().length<12)continue;const r=e.getBoundingClientRect();if(r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight)rows.set(m[1],{id:m[1],excerpt:text.slice(0,500)});}return Array.from(rows.values());})()`):[];const started_at=Date.now();const shot=await view.cdp.send('Page.captureScreenshot',{format:'jpeg',quality:92,fromSurface:true,captureBeyondViewport:false,clip:{x:0,y:0,width,height,scale:1}},12000);const at=Date.now(),bytes=Buffer.from(shot.data,'base64'),size=jpegDimensions(bytes);if(size.width!==width||size.height!==height)throw new Error('Native screenshot bounds changed');if(!save)return {bytes,at,started_at,size};const file=`frame-${String(view.frames.length).padStart(6,'0')}.jpg`;await writeFile(path.join(output,view.key,file),bytes);view.frames.push({file,at,started_at,sha256:hash(bytes),visiblePostIds:posts.map(p=>p.id)});for(const post of posts){const key=view.key+':'+post.id;if(!seenPosts.has(key)){seenPosts.add(key);visibleEvents.push({room:view.key,postId:post.id,firstCapturedAt:at,frame:file,excerpt:post.excerpt});}}return at;}
async function nativeState(){const response=await fetch(nativeBase+'/api/native/state');if(!response.ok)throw new Error(`Native state returned HTTP ${response.status}`);return safe(await response.json());}
function stageRow(state,stage){const rows=state.stages||{};return Array.isArray(rows)?[...rows].reverse().find(row=>(row.stage||row.name)===stage):rows[stage];}
async function runStage(control){
  const marker={label:control.label||control.stage,stage:control.stage,nonce:control.nonce,start:Date.now(),gate_at:null,completed_at:null,end:null,status:'pre_roll'};
  markers.push(marker);const initial=Object.fromEntries(Object.entries(views).map(([key,v])=>[key,v.frames.length]));await flush();await status('stage_running',{stage:marker.stage,phase:'pre_roll'});
  while(!stopping&&(Date.now()-marker.start<3000||Object.entries(views).some(([key,v])=>v.frames.length-initial[key]<8)))await sleep(100);
  if(stopping){marker.status='cancelled_before_cue';marker.end=Date.now();return;}
  marker.gate_at=Date.now();marker.status='running';await flush();
  const response=await fetch(nativeBase+'/api/native/stage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage:control.stage})});
  const result=safe(await response.json());marker.stage_response=result;
  if(!response.ok)throw new Error(`Native stage ${control.stage} refused (HTTP ${response.status})`);
  if(response.status===202){
    const deadline=Date.now()+360000;
    while(Date.now()<deadline){const state=await nativeState();const row=stageRow(state,control.stage);marker.last_stage_status=row?.status||state.status;if(row&&['complete','completed','done','passed'].includes(row.status)){marker.stage_receipt=row;break;}if(row&&['error','failed','refused'].includes(row.status))throw new Error(`Native stage ${control.stage} failed`);await sleep(500);}
    if(!marker.stage_receipt)throw new Error(`Native stage ${control.stage} did not complete within six minutes`);
  }
  marker.completed_at=Date.now();marker.status='complete';
  if(['approve_cloud','approve_app'].includes(control.stage)){
    try{
    const role=control.stage==='approve_cloud'?'harborcloud':'teamchat';const state=await fetch(nativeBase+'/api/coordination').then(r=>r.json());const p=[...(state.proposals||[])].reverse().find(p=>p.role===role&&p.kind==='operation'&&p.status==='executed');
    if(p)marker.operationVerification=safe({role,proposalId:p.id,target:p.engineProposal?.target,gatewayCanary:p.result?.observation?.gatewayCanary,delivery:p.result?.verification});
    }catch{marker.operationVerificationUnavailable=true;}
  }
  await flush();await status('stage_running',{stage:marker.stage,phase:'post_roll'});await sleep(5000);marker.end=Date.now();await flush();await status('stage_complete',{stage:marker.stage});console.log(JSON.stringify({stage:marker.stage,status:'complete',start:marker.start,gate_at:marker.gate_at,completed_at:marker.completed_at,end:marker.end,operationVerification:marker.operationVerification}));
}
async function focusThread(control){
  const view=views[control.room];if(!view||!/^([a-z0-9]{26}|channel)$/.test(control.postId||''))throw new Error('Focus cue must name a captured room and an actual Mattermost post');
  view.framing=true;
  try{
  await status('framing',{room:control.room});
  const url=new URL(view.url);url.pathname=control.postId==='channel'?new URL(view.url).pathname:`/${config.teamName||config.team_name||url.pathname.split('/')[1]}/pl/${control.postId}`;
  await view.cdp.send('Page.navigate',{url:url.href});const until=Date.now()+15000;
  while(Date.now()<until){try{if(await view.cdp.evaluate(`Boolean(document.querySelector('#post_textbox'))`))break;}catch{}await sleep(200);}
  await sleep(800);
  const rhs=await view.cdp.evaluate(`(()=>{const e=document.querySelector('#sidebar-right');if(!e)return null;const r=e.getBoundingClientRect();return {left:r.left,width:r.width,top:r.top,height:r.height};})()`);
  if(rhs&&rhs.width>0&&rhs.width<610){const x=rhs.left+3,y=Math.min(420,rhs.top+100);await view.cdp.send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',buttons:1,clickCount:1});await view.cdp.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:width-650,y,button:'left',buttons:1});await view.cdp.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:width-650,y,button:'left',buttons:0,clickCount:1});}
  await status('ready',{focusedRoom:control.room,focusedPostId:control.postId});console.log(JSON.stringify({framed:control.room,postId:control.postId}));
  }finally{view.framing=false;}
}
process.on('SIGTERM',()=>{stopping=true;});process.on('SIGINT',()=>{stopping=true;});
try{
  let port;
  const deadline=Date.now()+15000;
  while(Date.now()<deadline){try{const lines=(await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n');port=Number(lines[0]);if(port){browserCDP=await CDP.connect(`ws://127.0.0.1:${port}${lines[1]}`);break;}}catch{}if(browser.exitCode!==null)throw new Error('Isolated camera browser exited');await sleep(100);}
  if(!port)throw new Error('Isolated camera browser did not start');
  for(const role of ['teamchat','harborcloud'])contexts[role]=(await browserCDP.send('Target.createBrowserContext',{disposeOnDetach:true})).browserContextId;
  for(const key of ['shared','teamchat','harborcloud']){
    await status('starting',{room:key,phase:'opening_native_room'});
    const entry=config.rooms?.[key];const rawURL=typeof entry==='string'?entry:entry?.url;
    const url=localURL(rawURL);if(url.port!==mm.port)throw new Error('A native room belongs to a different service');url.hostname=mm.hostname;
    const sessionRole=key==='harborcloud'?'harborcloud':'teamchat',session=sessions[sessionRole],token=session.token;
    const target=await browserCDP.send('Target.createTarget',{url:'about:blank',browserContextId:contexts[sessionRole]});
    const tabs=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
    const cdp=await CDP.connect(tabs.find(tab=>tab.id===target.targetId).webSocketDebuggerUrl);
    await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Network.enable');
    await cdp.send('Network.setCookie',{name:'MMAUTHTOKEN',value:token,url:mm.origin+'/',httpOnly:true,secure:false,sameSite:'Lax'});
    const userId=session.userId||session.user_id||session.id;if(userId)await cdp.send('Network.setCookie',{name:'MMUSERID',value:userId,url:mm.origin+'/',httpOnly:false,secure:false,sameSite:'Lax'});
    await cdp.send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await cdp.send('Page.navigate',{url:url.href});
    let ready=false;const until=Date.now()+25000;
    while(Date.now()<until){try{ready=await cdp.evaluate(`(()=>{const browserButton=Array.from(document.querySelectorAll('button,a')).find(e=>e.textContent.trim()==='View in Browser');if(location.pathname==='/landing'&&browserButton){browserButton.click();return false;}return Boolean(document.querySelector('#post_textbox'));})()`);}catch{}if(ready)break;await sleep(300);}
    if(!ready){
      const shot=await cdp.send('Page.captureScreenshot',{format:'jpeg',quality:92,fromSurface:true,captureBeyondViewport:false,clip:{x:0,y:0,width,height,scale:1}},12000);await writeFile(path.join(output,`preflight-error-${key}.jpg`),Buffer.from(shot.data,'base64'));
      const diagnostic=await cdp.evaluate(`({location:location.origin+location.pathname,title:document.title,readyState:document.readyState,loginForm:!!document.querySelector('input[type=password]'),inputIds:Array.from(document.querySelectorAll('input,textarea')).map(e=>e.id)})`);await atomic(path.join(output,`preflight-error-${key}.json`),diagnostic);
      throw new Error(`Native ${key} room did not show a signed-in composer`);
    }
    // Dismiss only the native nonsecurity email-preview banner seen in preflight.
    await cdp.evaluate(`(()=>{const close=Array.from(document.querySelectorAll('a,button')).find(e=>e.textContent.trim()==='×'&&e.getBoundingClientRect().top<45&&e.getBoundingClientRect().right>innerWidth-100);if(close)close.click();})()`);
    const geometry=await cdp.evaluate(`({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,scrollWidth:document.documentElement.scrollWidth,title:document.title,rawTransportVisible:/RELAY\\/1|Exact digest:|\\/relay approve [a-f0-9]{64}/.test(document.body.innerText),composer:document.querySelector('#post_textbox')?.getBoundingClientRect().toJSON()})`);
    if(geometry.width!==width||geometry.height!==height||geometry.rawTransportVisible)throw new Error(`Native ${key} preflight refused: geometry or raw transport presentation`);
    const identity=await cdp.evaluate(`fetch('/api/v4/users/me').then(async r=>({status:r.status,id:(await r.json()).id}))`);if(identity.status!==200||identity.id!==userId)throw new Error(`Native ${key} role session did not match its enrolled account`);
    const view={key,cdp,frames:[],url:url.href};views[key]=view;await mkdir(path.join(output,key),{recursive:true});
    await screenshot(view,false);await sleep(400);
    const shot=await screenshot(view,false);await writeFile(path.join(output,`baseline-${key}.jpg`),shot.bytes);preflight.rooms[key]={url:url.href,role:sessionRole,authenticatedUserId:identity.id,geometry,imageDimensions:shot.size,sha256:hash(shot.bytes)};
  }
  await atomic(path.join(output,'preflight.json'),safe(preflight));await flush();
  try{lastControl=(await jsonFile(controlFile)).nonce;}catch{}
  await status('ready');console.log(JSON.stringify({camera:'ready',output,dimensions:{width,height},rooms:Object.keys(views),storyStagesStarted:0}));
  while(!stopping||active){
    const begin=Date.now();
    const captured=await Promise.allSettled(Object.values(views).map(view=>screenshot(view)));
    for(const result of captured)if(result.status==='rejected'){totalErrors++;console.error('A camera frame failed; the timestamp gap will remain explicit.');if(totalErrors>10)throw new Error('Too many native capture errors');}
    if(Date.now()-lastFlush>1000)await flush();
    let control;try{control=await jsonFile(controlFile);}catch{}
    if(control?.nonce&&control.nonce!==lastControl){lastControl=control.nonce;if(control.type==='stop'){stopping=true;}else if(control.type==='focus'){if(active)console.error('A framing cue was refused during a story stage.');else active=focusThread(control).catch(async error=>{await status('framing_failed',{error:error.message});}).finally(()=>{active=null;});}else if(control.type==='stage'){if(active){console.error('A stage cue was refused while another stage was running.');}else{active=runStage(control).catch(async error=>{const marker=markers.at(-1);marker.status='failed';marker.error=error.message;marker.failed_at=Date.now();await flush();await status('stage_failed',{stage:control.stage,phase:'diagnostic_post_roll',error:error.message});console.error(JSON.stringify({stage:control.stage,status:'failed',error:error.message}));await sleep(5000);marker.end=Date.now();await flush();stopping=true;}).finally(()=>{active=null;});}}}
    await sleep(Math.max(0,interval-(Date.now()-begin)));
  }
  await flush();
  const lastState=await nativeState().catch(()=>null);
  const sharedMessages=await fetch(nativeBase+'/api/coordination').then(r=>r.json()).then(s=>safe((s.messages||[]).map(m=>({id:m.id,role:m.role,kind:m.kind,content:m.content,at:m.at,receipt:m.receipt})))).catch(()=>[]);
  const proof={at:new Date().toISOString(),kind:'Actual full-viewport native Mattermost browser capture',fictionalRoleplay:true,userBrowserTouched:false,dimensions:{width,height},continuousRecordingBetweenStages:true,cameraErrors:totalErrors,frameCounts:Object.fromEntries(Object.entries(views).map(([key,v])=>[key,v.frames.length])),firstFrames:Object.fromEntries(Object.entries(views).map(([key,v])=>[key,v.frames[0]?.at])),markers,finalNativeState:lastState,sharedMessages,visibilityMethod:'Native DOM post and RHS identifiers observed before each actual screenshot; encoded images require independent visual checking.',configExported:false};
  await atomic(path.join(output,'capture-proof.json'),safe(proof));await status('stopped');console.log(JSON.stringify({camera:'stopped',output,frames:proof.frameCounts,markers:markers.length}));
}catch(error){await status('error',{error:error.message}).catch(()=>{});console.error(error.message);process.exitCode=1;}
finally{for(const view of Object.values(views))view.cdp.close();browserCDP?.close();browser.kill('SIGTERM');await new Promise(resolve=>{if(browser.exitCode!==null)return resolve();browser.once('exit',resolve);setTimeout(resolve,3000);});await rm(profile,{recursive:true,force:true}).catch(()=>{});}
