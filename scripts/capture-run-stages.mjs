// Execute only the already-approved fictional presenter script through the
// camera's explicit gates. Never posts directly to Mattermost or approves APIs.
import {readFile,writeFile,rename} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const out=path.resolve(process.argv[2]||path.join(root,'recording/native-take-03'));
const stages=['incident','presence','share_question','approve_cloud','share_cloud_result','approve_app','share_app_result','retry','close'];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const load=async file=>JSON.parse(await readFile(path.join(out,file),'utf8'));
const state=async()=>{const r=await fetch('http://127.0.0.1:4319/api/native/state');if(!r.ok)throw Error('Native state is unavailable');return r.json();};
async function control(value){const c={...value,nonce:randomUUID(),at:Date.now()};await writeFile(path.join(out,'control.json.tmp'),JSON.stringify(c));await rename(path.join(out,'control.json.tmp'),path.join(out,'control.json'));return c;}
async function waitCamera(predicate,timeout=390000){const until=Date.now()+timeout;while(Date.now()<until){const s=await load('status.json');if(['stage_failed','error','framing_failed'].includes(s.camera))throw Error(`Camera stopped: ${s.error||s.camera}`);if(predicate(s))return s;await sleep(300);}throw Error('Camera wait timed out');}
async function frame(room,postId){
 if(!postId)throw Error(`Actual ${room} thread root is missing`);
 const result=await new Promise((resolve,reject)=>{const p=spawn(process.execPath,[path.join(root,'scripts/capture-native-ui.mjs'),room,postId,'--out',out],{stdio:['ignore','pipe','pipe']});let stdout='',stderr='';p.stdout.on('data',b=>stdout+=b);p.stderr.on('data',b=>stderr+=b);p.once('error',reject);p.once('exit',code=>resolve({code,stdout,stderr}));});
 if(result.code!==0){
  // A virtualized post may need actual native permalink navigation first.
  await control({type:'focus',room,postId});await waitCamera(s=>s.camera==='ready'&&s.focusedRoom===room&&s.focusedPostId===postId,22000);
  const retry=await new Promise((resolve,reject)=>{const p=spawn(process.execPath,[path.join(root,'scripts/capture-native-ui.mjs'),room,postId,'--out',out],{stdio:['ignore','pipe','pipe']});let stdout='',stderr='';p.stdout.on('data',b=>stdout+=b);p.stderr.on('data',b=>stderr+=b);p.once('error',reject);p.once('exit',code=>resolve({code,stdout,stderr}));});
  if(retry.code!==0)throw Error(`Native ${room} framing failed: ${retry.stderr.slice(-400)}`);
 }
 console.log(JSON.stringify({framed:room,actualPostId:postId}));
}
try{
 await waitCamera(s=>s.camera==='ready',45000);
 const preflight=await load('preflight.json');if(!preflight.separateRoleBrowserContexts||Object.keys(preflight.rooms).length!==3)throw Error('Three scoped native views have not passed preflight');
 const before=await state();if(Object.keys(before.stages||{}).length||before.humanSources?.length)throw Error('Fresh-stage runner refuses a case that already contains story actions');
 for(const stage of stages){
  const s=await state();
  if(stage==='presence')await frame('shared',s.incidentRoot?.mattermostPostId);
  if(['share_question','approve_app','share_app_result'].includes(stage))await frame('teamchat',s.focus?.teamchat?.postId);
  if(['approve_cloud','share_cloud_result'].includes(stage))await frame('harborcloud',s.focus?.harborcloud?.postId);
  if(stage==='retry')await frame('shared',s.failedCard?.mattermostPostId);
  if(stage==='close'){
   await frame('shared',s.incidentRoot?.mattermostPostId);
   const p=[...(s.cards||[])].reverse().find(p=>p.role==='harborcloud'&&p.kind==='disclosure'&&p.status==='pending');if(p)await frame('harborcloud',p.postId);
  }
  await control({type:'stage',stage});console.log(JSON.stringify({cued:stage}));
  await waitCamera(s=>s.camera==='stage_complete'&&s.stage===stage);
  const marker=(await load('markers.json')).find(m=>m.stage===stage);
  if(stage==='approve_cloud'){
   const v=marker.operationVerification,c=v?.gatewayCanary;
   if(!c||c.status!=='healthy'||c.succeeded!==c.attempted)throw Error('Cloud narrative gate refused: actual provider check did not pass');
   if(v.delivery?.delivered===v.delivery?.attempted)throw Error('Cloud narrative gate refused: app no longer demonstrates a remaining failure');
   console.log(JSON.stringify({milestone:'provider_healthy_app_still_failing',canary:`${c.succeeded}/${c.attempted}`,app:`${v.delivery.delivered}/${v.delivery.attempted}`,marker:stage}));
  }
  if(stage==='approve_app'){
   const d=marker.operationVerification?.delivery;if(d?.status!=='healthy'||d.delivered!==24||d.attempted!==24)throw Error('App narrative gate refused: actual24/24 recovery check not verified');
   console.log(JSON.stringify({milestone:'actual_app24_of24_before_retry',marker:stage}));
  }
  if(stage==='retry'){const r=(await state()).retry;if(!r?.passed)throw Error('Retry narrative gate refused: original-ID delivery and duplicate check did not pass');console.log(JSON.stringify({milestone:'retry_native_result',passed:r.passed,messageId:r.message.id,deliveredRecord:r.record.status,duplicate:r.responses.at(-1).duplicate}));}
 }
 await control({type:'stop'});await waitCamera(s=>s.camera==='stopped',15000);
 console.log(JSON.stringify({capture:'complete',out,stages:stages.length}));
}catch(error){await writeFile(path.join(out,'production-notes.json'),JSON.stringify({at:Date.now(),status:'not_verified_as_final',error:error.message},null,2));await control({type:'stop'}).catch(()=>{});console.error(error.message);process.exitCode=1;}
