// Frame an actual native Mattermost thread in the camera's isolated Chrome.
import {readdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const[room,postId]=process.argv.slice(2);
const outIndex=process.argv.indexOf('--out');const output=path.resolve(outIndex>=0?process.argv[outIndex+1]:path.join(ROOT,'recording/native-take-02'));
if(!['shared','teamchat','harborcloud'].includes(room)||!/^([a-z0-9]{26})$/.test(postId||''))throw Error('Name the room and actual post to frame');
let port;
for(const name of (await readdir(tmpdir())).filter(n=>n.startsWith('relay-native-camera-')).reverse()){
 try{const candidate=Number((await readFile(path.join(tmpdir(),name,'DevToolsActivePort'),'utf8')).split('\n')[0]);const r=await fetch(`http://127.0.0.1:${candidate}/json/list`);if(r.ok){port=candidate;break;}}catch{}
}
if(!port)throw Error('No isolated native camera is running');
const targets=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
const config=JSON.parse(await readFile(path.join(ROOT,'agents/.runtime/native/browser-session.json'),'utf8'));
const channelPath=new URL(config.rooms[room].url).pathname;
const target=targets.find(t=>t.url.includes('/pl/'+postId)||new URL(t.url).pathname===channelPath);
if(!target)throw Error('Frame the actual post permalink with the camera focus cue first');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true});});
let next=0;const calls=new Map();
ws.addEventListener('message',e=>{const d=JSON.parse(e.data),p=calls.get(d.id);if(p){clearTimeout(p.timer);calls.delete(d.id);d.error?p.reject(Error(d.error.message)):p.resolve(d.result);}});
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{calls.delete(id);reject(Error('Camera UI command timed out'));},10000);calls.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('Native UI evaluation failed');return r.result.value;};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
try{
 const rect=await ev(`(()=>{const p=document.getElementById('post_${postId}');if(!p)return null;p.scrollIntoView({block:'center'});const r=p.getBoundingClientRect();return {left:r.left,top:r.top,width:r.width,height:r.height};})()`);
 if(!rect)throw Error('The actual post is not currently rendered');
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:Math.min(1570,rect.left+rect.width-35),y:Math.max(115,Math.min(740,rect.top+25))});await sleep(150);
 const controls=await ev(`(()=>{const p=document.getElementById('post_${postId}');return Array.from(p.querySelectorAll('button,a')).map(e=>({text:e.textContent.trim(),label:e.getAttribute('aria-label'),title:e.getAttribute('title'),id:e.id}));})()`);
 const clicked=await ev(`(()=>{const p=document.getElementById('post_${postId}');const button=Array.from(p.querySelectorAll('button,a')).find(e=>/\\brepl(?:y|ies)\\b/i.test([e.textContent,e.getAttribute('aria-label'),e.getAttribute('title')].join(' ')));if(button){button.click();return true;}return false;})()`);
 if(!clicked){console.log(JSON.stringify({room,postId,controls}));throw Error('The native Reply control was not found');}
 await sleep(500);
 let rhs=await ev(`(()=>{const e=document.querySelector('#sidebar-right');if(!e)return null;const r=e.getBoundingClientRect();return {left:r.left,top:r.top,width:r.width,height:r.height};})()`);
 if(!rhs||!rhs.width)throw Error('The native thread pane did not open');
 const threadControls=await ev(`Array.from(document.querySelector('#sidebar-right').querySelectorAll('button')).map(e=>({text:e.textContent.trim(),label:e.getAttribute('aria-label'),title:e.getAttribute('title'),id:e.id}))`);
 const handles=await ev(`Array.from(document.querySelectorAll('body *')).filter(e=>getComputedStyle(e).cursor==='col-resize').map(e=>{const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:Math.max(150,Math.min(500,r.top+r.height/2)),width:r.width,height:r.height};}).filter(r=>r.width&&r.height)`);
 if(rhs.width<680&&handles.length){const h=handles.find(h=>Math.abs(h.x-rhs.left)<25)||handles[0];await send('Input.dispatchMouseEvent',{type:'mousePressed',x:h.x,y:h.y,button:'left',buttons:1,clickCount:1});for(let n=1;n<=5;n++)await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:h.x+(900-h.x)*n/5,y:h.y,button:'left',buttons:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:900,y:h.y,button:'left',buttons:0,clickCount:1});}
 await sleep(400);
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:1100,y:20});
 rhs=await ev(`(()=>{const r=document.querySelector('#sidebar-right').getBoundingClientRect();return {left:r.left,width:r.width,height:r.height};})()`);
 const shot=await send('Page.captureScreenshot',{format:'jpeg',quality:92,fromSurface:true,captureBeyondViewport:false,clip:{x:0,y:0,width:1600,height:900,scale:1}});
 const file=path.join(output,`focus-${room}-${postId}.jpg`);await writeFile(file,Buffer.from(shot.data,'base64'));
 console.log(JSON.stringify({room,postId,nativeThreadOpened:true,rhs,file,threadControls}));
}finally{ws.close();}
