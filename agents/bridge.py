"""Local manual owner approval bridge and two event-driven live model contexts.

The local operator can roleplay both fictional owners. Separate scoped credentials
protect model tool boundaries; this is not isolation from the host administrator.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, os, secrets, time
import re
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from engine.http_boundary import permitted_request
from .model import DecisionModel
from .relay import SwitchRelay, canonical, envelope_digest, validate_envelope, APPROVAL_MODE

ROOT=Path(__file__).resolve().parents[1]
ROLES={"teamchat":{"label":"TeamChat","owner":"Maya","engine":"app","wire":"customer"},
       "harborcloud":{"label":"HarborCloud","owner":"Leo","engine":"cloud","wire":"provider"}}
WIRE_ROLES={v["wire"]:k for k,v in ROLES.items()}
REFERENCE=re.compile(r'^(?:event_[a-f0-9]{10}|load_[a-f0-9]{8}|sw_[a-f0-9]{32})$')
def stamp():return datetime.now(timezone.utc).isoformat()
def expiry(value):
 if isinstance(value,(float,int)):return value/1000 if value>1e11 else value
 if isinstance(value,str):
  try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
  except ValueError:return 0
 return 0

async def json_object(request):
 raw=await request.body()
 if len(raw)>64000:raise HTTPException(413,'Request body exceeds 64000 bytes')
 try:value=json.loads(raw or b'{}')
 except (ValueError,UnicodeDecodeError):raise HTTPException(400,'Valid JSON object required') from None
 if not isinstance(value,dict):raise HTTPException(400,'JSON object required')
 return value

def public_change(role,proposal):
 target=proposal['target']
 if role=='harborcloud':return f"Allow up to {target['capacity']} cloud connection requests at once, for this route only."
 return f"Remove {len(target['allocationIds'])} named failed starts, keep working servers, and bring the message service back one server at a time."

def engine_binding(role,proposal):
 return hashlib.sha256(canonical({'role':role,'proposal':proposal}).encode()).hexdigest()

class Bridge:
 def __init__(self, state_dir=None, engine_config=None, *, scripted=False, model=None, relay=None, max_calls=6):
  self.directory=Path(state_dir or ROOT/'agents/.runtime'); self.directory.mkdir(parents=True,exist_ok=True)
  os.chmod(self.directory,0o700)
  self.engine_config_path=Path(engine_config or ROOT/'.runtime/engine.json')
  self.scripted=scripted;self.model=model or DecisionModel();self.relay=relay
  self.max_calls=max_calls;self.http=None;self.tasks=[];self.worker_tasks={};self.queues={r:asyncio.Queue() for r in ROLES}
  self.history={r:[] for r in ROLES};self.secrets=[];self.approval_lock=asyncio.Lock()
  self.state={"mode":"test_operator" if scripted else "manual","status":"starting","roles":ROLES,
   "messages":[],"proposals":[],"investigations":[],"events":[],
   "agents":[{"role":r,"status":"idle","modelCalls":0,"lastSummary":""} for r in ROLES],
   "boundary":"Local fictional owner roleplay. Models have separate scoped tools and histories; host administrator is trusted."}
  self.case_token=None
 def safe(self,value):
  data=canonical(value)
  if any(s in data for s in self.secrets if len(s)>12):raise ValueError('Credential projection refused')
  if len(data.encode())>600000:raise ValueError('Observation exceeds local model boundary')
 def save(self):
  if self.state['status'] not in {'starting','error'}:
   if any(p['status'] in {'pending','approving'} for p in self.state['proposals']):self.state['status']='awaiting_approval'
   elif any(a['status']=='thinking' for a in self.state['agents']):self.state['status']='investigating'
   elif self.case_token and all(a['status']=='complete' for a in self.state['agents']):self.state['status']='complete'
   elif self.case_token:self.state['status']='waiting'
   else:self.state['status']='ready'
  self.safe(self.state)
  temp=self.directory/'coordination.tmp';temp.write_text(json.dumps(self.state,indent=2,ensure_ascii=False));temp.replace(self.directory/'coordination.json')
  for role,rows in self.history.items():
   self.safe(rows);(self.directory/f'{role}-transcript.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False))
 def event(self,kind,role,detail):
  self.state['events'].append({"at":stamp(),"type":kind,"role":role,"detail":detail});self.save()
 def agent(self,role):return next(a for a in self.state['agents'] if a['role']==role)
 def observed_references(self,role):
  refs=set()
  def observation(value):
   if not isinstance(value,dict):return
   for event in value.get('events',[]):
    if isinstance(event,dict):refs.add(event.get('id'))
  for row in self.history[role]:
   if row.get('type')!='trigger':continue
   observation(row.get('own_observation'))
   trigger=row.get('trigger',{})
   if trigger.get('kind')=='own_operation_result':
    result=trigger.get('proposal',{}).get('result',{})
    observation(result.get('observation'));refs.add(result.get('verification',{}).get('id'))
   elif trigger.get('kind')=='peer_message':
    message=trigger.get('message',{});refs.add(message.get('id'))
    refs.update(message.get('content',{}).get('evidenceIds',[]))
  return {r for r in refs if isinstance(r,str) and REFERENCE.fullmatch(r)}
 def reviewed_content(self,role,kind,title,content,wirekind,engine_proposal):
  allowed={'kind','title','summary','evidenceIds'}
  if kind=='operation':allowed.update({'operation','execution','change'})
  if set(content)-allowed:raise ValueError('Disclosure contains fields that were not included in the owner review')
  if content.get('kind',wirekind)!=wirekind:raise ValueError('Disclosure kind differs from the review')
  summary=content.get('summary')
  if not isinstance(title,str) or not 1<=len(title)<=160 or not isinstance(summary,str) or not 1<=len(summary)<=3000:raise ValueError('Bounded, visible title and summary required')
  refs=content.get('evidenceIds',[])
  if not isinstance(refs,list) or len(refs)>24 or any(not isinstance(r,str) for r in refs):raise ValueError('Bounded observed evidence references required')
  known=self.observed_references(role)
  if any(not REFERENCE.fullmatch(r) or r not in known for r in refs):raise ValueError('Disclosure references must come from actual observed evidence')
  projection={'title':title,'summary':summary,'evidenceIds':list(dict.fromkeys(refs))}
  if kind=='operation':
   if not isinstance(engine_proposal,dict):raise ValueError('A locally bound engine proposal is required')
   projection.update(change=public_change(role,engine_proposal),execution='Plan only; execution is not yet verified.')
  return projection
 def verify_engine_binding(self,proposal):
  if proposal['kind']=='operation' and engine_binding(proposal['role'],proposal['engineProposal'])!=proposal.get('engineBinding'):
   raise ValueError('The exact local operation changed after owner review')
 async def start(self):
  self.engine=json.loads(self.engine_config_path.read_text())
  for credentials in self.engine['credentials'].values():self.secrets.extend(credentials.values())
  self.http=httpx.AsyncClient(timeout=35,follow_redirects=False)
  if self.relay is None:self.relay=SwitchRelay(self.directory/'switch',timeout=75)
  await self.relay.__aenter__()
  if self.relay.config:
   for section in ('agents','humans'):
    for value in self.relay.config[section].values():
     self.secrets.extend(v for k,v in value.items() if k in {'api_key','token','password'} and isinstance(v,str))
  self.state['accessChecks']=await self.relay.verify_access()
  if not self.state['accessChecks']['passed']:raise RuntimeError('Scoped Switch access checks failed')
  self.state['status']='ready';self.save()
  self.worker_tasks={r:asyncio.create_task(self.worker(r)) for r in ROLES}
  self.tasks=[asyncio.create_task(self.consume()),*self.worker_tasks.values()]
 async def reset(self):
  async with self.approval_lock:return await self._reset_locked()
 async def _reset_locked(self):
  for task in self.worker_tasks.values():task.cancel()
  await asyncio.gather(*self.worker_tasks.values(),return_exceptions=True)
  if self.case_token:
   archive=self.directory/'archive'/self.case_token;archive.mkdir(parents=True,exist_ok=True)
   for name,value in [('coordination',self.state),*self.history.items()]:
    self.safe(value);(archive/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False))
  self.case_token=None;self.history={r:[] for r in ROLES};self.queues={r:asyncio.Queue() for r in ROLES}
  self.state.update(status='ready',messages=[],proposals=[],investigations=[],events=[])
  for r in ROLES:self.agent(r).update(status='idle',modelCalls=0,lastSummary='')
  self.worker_tasks={r:asyncio.create_task(self.worker(r)) for r in ROLES};self.tasks.extend(self.worker_tasks.values())
  self.event('coordination_reset','operator','Prior review lifecycle archived; Switch source history preserved.')
  return {'status':'ready','mode':self.state['mode']}
 async def close(self):
  for t in self.tasks:t.cancel()
  await asyncio.gather(*self.tasks,return_exceptions=True)
  if self.relay:await self.relay.__aexit__(None,None,None)
  if self.http:await self.http.aclose()
 async def engine_call(self,role,action=None,args=None,*,apply=False):
  spec=ROLES[role];creds=self.engine['credentials'][spec['engine']]
  key='applyToken' if apply else 'readToken'
  url=self.engine.get('apiBase','http://127.0.0.1:4318')+f"/api/role/{spec['engine']}/"+('tool' if action else 'observation')
  kwargs={'headers':{'Authorization':'Bearer '+creds[key]}}
  response=await (self.http.post(url,json={'action':action,'args':args or {}},**kwargs) if action else self.http.get(url,**kwargs))
  if response.status_code>=300:raise RuntimeError(f'Owner engine refused operation (HTTP {response.status_code})')
  value=response.json();self.safe(value);return value
 async def investigate(self):
  async with self.approval_lock:return await self._investigate_locked()
 async def _investigate_locked(self):
  if self.case_token:return {'status':self.state['status'],'incident':self.case_token}
  if any(a['status']=='thinking' for a in self.state['agents']):return {'status':'investigating','incident':self.case_token}
  self.case_token='relay_'+secrets.token_hex(9)
  self.state['investigations'].append({'id':self.case_token,'at':stamp(),'initiator':'teamchat','model':'live authenticated Codex CLI'})
  self.state['status']='investigating'
  for r in ROLES:self.history[r]=[];self.agent(r).update(status='idle',modelCalls=0,lastSummary='')
  self.event('investigation_started','teamchat','Customer investigator is inspecting its own service.')
  await self.queues['teamchat'].put({'kind':'start','incident':self.case_token,
    'request':'Customers cannot reliably send messages. Investigate your own system and seek the cloud owner’s specific evidence where needed.'})
  return {'status':'investigating','incident':self.case_token}
 async def consume(self):
  while True:
   delivered=await self.relay.deliveries.get()
   recipient=WIRE_ROLES[delivered['recipient']];body=delivered['body'];receipt=delivered['receipt']
   # This queue is populated only after captured opposing Switch event + chat readback.
   validate_envelope(body['ticket'],body)
   if body['ticket']!=self.case_token:continue
   sender=WIRE_ROLES[receipt['side']]
   row={'id':receipt['shared_switch_message_id'],'role':sender,'kind':body['kind'],
        'content':body['content'],'at':stamp(),'receipt':receipt}
   if any(m['id']==row['id'] for m in self.state['messages']):continue
   self.safe(row);self.state['messages'].append(row)
   self.event('switch_message_received',recipient,'Authenticated counterpart Switch message received.')
   await self.queues[recipient].put({'kind':'peer_message','incident':body['ticket'],'message':row})
 async def worker(self,role):
  while True:
   trigger=await self.queues[role].get()
   try:await self.step(role,trigger)
   except asyncio.CancelledError:raise
   except Exception as error:
    self.agent(role)['status']='error';self.state['status']='error'
    self.event('agent_error',role,f'{type(error).__name__}: no unapproved action executed.')
   finally:self.queues[role].task_done()
 async def step(self,role,trigger):
  if trigger.get('incident')!=self.case_token:return
  agent=self.agent(role)
  if agent['modelCalls']>=self.max_calls:
   agent.update(status='budget_complete',lastSummary='Decision budget complete; inspect verified measurements and pending owner decisions.');self.save();return
  observation=await self.engine_call(role)
  self.history[role].append({'type':'trigger','at':stamp(),'trigger':trigger,'own_observation':observation})
  agent['status']='thinking';self.save()
  payload={'role':role,'incident':self.case_token,'remaining_calls':self.max_calls-agent['modelCalls'],
    'history':self.history[role], 'pending_own_proposals':[p for p in self.state['proposals'] if p['role']==role and p['status']=='pending']}
  self.safe(payload)
  decision,metadata=await self.model.infer(role,payload)
  self.safe(decision);self.safe(metadata)
  agent['modelCalls']+=1;agent['lastSummary']=decision['summary']
  self.history[role].append({'type':'live_model_decision','at':stamp(),'decision':decision,'metadata':metadata})
  action,content=decision['action'],decision['content']
  if action=='share':
   if content.get('kind') not in {'question','evidence','verification'} or not isinstance(content.get('summary'),str):raise ValueError('Invalid disclosure')
   await self.stage(role,'disclosure',content.get('title','Share incident finding'),content,content['kind'])
  elif action=='propose_recovery':
   if any(p['role']==role and p['kind']=='operation' and p['status'] in {'pending','approving'} for p in self.state['proposals']):
    agent['status']='awaiting_approval';self.save();return
   args={k:content[k] for k in ('reason','expectedRevision','capacity','allocationIds') if k in content}
   engine_proposal=await self.engine_call(role,'propose_recovery',args)
   if 'proposal' in engine_proposal:engine_proposal=engine_proposal['proposal']
   if not all(k in engine_proposal for k in ('id','digest','expectedRevision','expiresAt')):raise ValueError('Engine proposal lacks binding fields')
   shared={'summary':content.get('publicSummary',decision['summary']),'evidenceIds':content.get('evidenceIds',[])}
   await self.stage(role,'operation',content.get('title') or ('Restore the cloud connection' if role=='harborcloud' else 'Restart the message service safely'),shared,'repair_proposal',engine_proposal)
  else:
   agent['status']='complete' if action=='finish' else 'waiting'
   self.event('agent_conclusion' if action=='finish' else 'agent_waiting',role,decision['summary'])
  self.save()
 async def stage(self,role,kind,title,content,wirekind,engine_proposal=None):
  content=self.reviewed_content(role,kind,title,content,wirekind,engine_proposal)
  body={'ticket':self.case_token,'kind':wirekind,'content':content};self.safe(body)
  digest=await self.relay.prepare(ROLES[role]['wire'],self.case_token,body)
  proposal={'id':'review_'+secrets.token_hex(8),'role':role,'kind':kind,'title':title,'body':body,'digest':digest,
   'expectedRevision':engine_proposal.get('expectedRevision') if engine_proposal else None,
   'expiresAt':engine_proposal.get('expiresAt') if engine_proposal else datetime.fromtimestamp(time.time()+900,timezone.utc).isoformat(),
   'status':'pending','createdAt':stamp()}
  if engine_proposal:
   proposal['engineProposal']=json.loads(canonical(engine_proposal));proposal['engineBinding']=engine_binding(role,proposal['engineProposal'])
  self.state['proposals'].append(proposal);self.agent(role)['status']='awaiting_approval';self.state['status']='awaiting_approval'
  self.event('owner_review_requested',role,title)
  if self.scripted:asyncio.create_task(self.scripted_approval(proposal['id'],role))
  return proposal
 async def scripted_approval(self,proposal_id,role):
  try:await self.approve(proposal_id,role,mode='test_operator')
  except Exception as error:self.event('test_operator_review_failed',role,type(error).__name__+'; no automatic retry.')
 def lookup(self,proposal_id,role):
  if role not in ROLES:raise ValueError('Select the enrolled fictional owner role')
  proposal=next((p for p in self.state['proposals'] if p['id']==proposal_id),None)
  if proposal is None:raise ValueError('Unknown proposal')
  if proposal['role']!=role:raise ValueError('Only the proposal’s owner may approve it')
  if proposal['body']['ticket']!=self.case_token:raise ValueError('This proposal belongs to an earlier incident')
  return proposal
 async def approve(self,proposal_id,role,*,mode=APPROVAL_MODE):
  async with self.approval_lock:
   p=self.lookup(proposal_id,role)
   if p['status'] in {'released','executed'}:return p
   if p['status']!='pending':raise ValueError('Proposal is not pending')
   if expiry(p['expiresAt'])<=time.time():p['status']='expired';self.save();raise ValueError('Proposal expired; request a fresh review')
   if envelope_digest(ROLES[role]['wire'],self.case_token,p['body'])!=p['digest']:raise ValueError('Proposal digest changed')
   self.verify_engine_binding(p)
   p['status']='approving';self.save()
   try:
    receipt=await self.relay.release(ROLES[role]['wire'],self.case_token,p['body'],p['digest'],approval_mode=mode)
    p['receipt']=receipt;p['approvedAt']=stamp();p['approvalMode']=mode;p['status']='released'
    if p['kind']=='operation':
     ep=p['engineProposal']
     p['result']=await self.engine_call(role,'apply_recovery',{'proposalId':ep['id'],'digest':ep['digest']},apply=True)
     p['status']='executed'
     self.event('owner_operation_executed',role,'Source-bound owner approval verified; revision-bound owner operation executed.')
     await self.queues[role].put({'kind':'own_operation_result','incident':p['body']['ticket'],'proposal':p})
    else:
     self.event('approved_disclosure_released',role,'Exact owner-approved facts delivered through Switch.')
     if p['body']['kind']=='verification':await self.queues[role].put({'kind':'own_verification_released','incident':p['body']['ticket'],'proposalId':p['id']})
    self.save();return p
   except Exception:
    p['status']='failed';self.save();raise
 async def reject(self,proposal_id,role):
  p=self.lookup(proposal_id,role)
  if p['status']!='pending':raise ValueError('Proposal is not pending')
  p['status']='rejected';self.event('owner_rejected',role,'Owner rejected this exact proposal.');return p


def create_app(bridge):
 @asynccontextmanager
 async def lifespan(app):
  try:
   await bridge.start()
   yield
  finally:
   await bridge.close()
 app=FastAPI(title='RELAY local owner approval bridge',lifespan=lifespan)
 @app.middleware('http')
 async def local_browser_boundary(request:Request,call_next):
  if not permitted_request(request.headers.get('host'),request.headers.get('origin'),method=request.method,fetch_site=request.headers.get('sec-fetch-site')):
   return JSONResponse({'error':'Loopback host and same-origin browser request required'},status_code=403)
  return await call_next(request)
 @app.get('/health')
 async def health():return {'up':True,'mode':bridge.state['mode'],'status':bridge.state['status']}
 @app.get('/api/coordination')
 @app.get('/api/coordination/')
 async def state():return bridge.state
 async def body(request):
  return await json_object(request)
 @app.post('/api/investigate')
 @app.post('/api/coordination/investigate')
 async def investigate(request:Request):
  await body(request)
  return await bridge.investigate()
 @app.post('/api/approve')
 @app.post('/api/coordination/approve')
 async def approve(request:Request):
  args=await body(request)
  try:return await bridge.approve(args.get('proposalId'),args.get('role'))
  except ValueError as e:return error(str(e),400)
  except Exception:return error('Approval or owner operation failed; inspect local audit events. No retry is automatic.',409)
 @app.post('/api/coordination/reset')
 async def reset(request:Request):
  await body(request)
  try:return await bridge.reset()
  except ValueError as e:return error(str(e),409)
 @app.post('/api/reject')
 @app.post('/api/coordination/reject')
 async def reject(request:Request):
  args=await body(request)
  try:return await bridge.reject(args.get('proposalId'),args.get('role'))
  except ValueError as e:return error(str(e),400)
 def error(message,status):
  from fastapi.responses import JSONResponse
  return JSONResponse({'error':message},status_code=status)
 return app

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=4319);parser.add_argument('--engine-config',type=Path);parser.add_argument('--state-dir',type=Path);parser.add_argument('--scripted',action='store_true');parser.add_argument('--max-calls',type=int,default=6)
 args=parser.parse_args()
 import uvicorn
 uvicorn.run(create_app(Bridge(args.state_dir,args.engine_config,scripted=args.scripted,max_calls=args.max_calls)),host='127.0.0.1',port=args.port,log_level='warning')
if __name__=='__main__':main()
