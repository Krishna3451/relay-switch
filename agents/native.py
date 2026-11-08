"""Native Mattermost decisions: original owner replies authorize exact thread cards."""
from __future__ import annotations
import asyncio,json,re,secrets,time
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse
from .bridge import Bridge,ROOT,ROLES,WIRE_ROLES,stamp,expiry,create_app,json_object
from .relay import canonical,envelope_digest,RelayError
from .native_transport import NativeRelay

STAGES=('incident','presence','share_question','approve_cloud','share_cloud_result','approve_app','share_app_result','retry','close')
def cloud_check_passed(result):
 canary=result.get('observation',{}).get('gatewayCanary',{})
 attempted=canary.get('attempted');rows=canary.get('results')
 return (canary.get('status')=='healthy' and type(attempted) is int and attempted>0
         and canary.get('succeeded')==attempted and isinstance(rows,list) and len(rows)==attempted
         and all(isinstance(row,dict) and row.get('passed') is True for row in rows))
def delivery_check_passed(check):
 return (check.get('status')=='healthy' and check.get('attempted')==24 and check.get('delivered')==24 and check.get('fresh',True) is True)
class NativeBridge(Bridge):
 def __init__(self,directory=None,engine_config=None,**kwargs):
  directory=Path(directory or ROOT/'agents/.runtime/native')
  prior=directory/'native-state.json'
  if prior.exists():
   try:previous=json.loads(prior.read_text())
   except (OSError,ValueError):raise ValueError('Existing native take is unreadable; preserve it and choose a fresh --state-dir') from None
   if previous.get('case'):raise ValueError('Existing native incident is preserved. Enroll fresh rooms with a fresh --state-dir for a new take.')
  kwargs.pop('scripted',None)
  relay=kwargs.pop('relay',None) or NativeRelay(directory/'switch',timeout=75)
  super().__init__(directory,engine_config,scripted=False,relay=relay,**kwargs)
  self.state['mode']='native_owner_reply'
  self.native={'mode':'native_enrolled_owner_reply','participation':'One presenter roleplays two fictional owners using their enrolled accounts.',
   'status':'starting','stages':{},'cards':[],'focus':{},'posts':[],'humanSources':[],'retry':None,'freshCheck':None}
  self.native_seen=set();self.stage_lock=asyncio.Lock();self.stage_tasks=set();self.fixture=None
 def save(self):
  super().save()
  if hasattr(self,'native'):
   self.native['status']=self.state['status'];self.native['case']=self.case_token
   self.native['cards']=[{'id':p['id'],'role':p['role'],'kind':p['kind'],'wireKind':p['body']['kind'],'title':p['title'],
     'status':p['status'],'postId':p.get('card',{}).get('mattermostPostId'),'threadRootId':p.get('card',{}).get('mattermostPostId'),
     'switchThreadId':p.get('card',{}).get('switchMessageId'),'digest':p['digest']} for p in self.state['proposals']]
   for role in ROLES:
    pending=[p for p in self.state['proposals'] if p['role']==role and p['status']=='pending' and p.get('card')]
    if pending:self.native['focus'][role]={'postId':pending[-1]['card']['mattermostPostId'],'threadRootId':pending[-1]['card']['mattermostPostId']}
   self.safe(self.native);tmp=self.directory/'native-state.tmp';tmp.write_text(json.dumps(self.native,indent=2,ensure_ascii=False));tmp.replace(self.directory/'native-state.json')
 async def start(self):
  browser_path=self.directory/'browser-session.json'
  if not browser_path.exists() or not (self.directory/'switch/config.json').exists():
   raise ValueError('Run python -m agents.native_enroll with this --state-dir before starting native mode')
  browser=json.loads(browser_path.read_text())
  await super().start()
  self.native['rooms']=browser['rooms'];self.native['mattermostUrl']=browser['mattermostUrl']
  self.tasks.append(asyncio.create_task(self.native_consume()));self.save()
 async def investigate(self):raise ValueError('Start this incident with an actual enrolled owner message in Mattermost')
 async def approve(self,*args,**kwargs):raise ValueError('Reply from the enrolled owner account in this exact Mattermost review thread')
 async def reset(self):raise ValueError('Native incident history is preserved; use a fresh --state-dir and enroll fresh rooms for a new take')
 async def close(self):
  for task in self.stage_tasks:task.cancel()
  await asyncio.gather(*self.stage_tasks,return_exceptions=True)
  await super().close()
 async def post(self,role,room,text,*,thread_id=None,kind='agent_notice'):
  receipt=await self.relay.post_readable(ROLES[role]['wire'],room,text,thread_id=thread_id,marker='relay-card:'+secrets.token_hex(8))
  self.native['posts'].append({'role':role,'kind':kind,'at':stamp(),**receipt});self.save();return receipt
 async def step(self,role,trigger):
  if trigger.get('incident')!=self.case_token:return
  if trigger['kind']=='start':
   trigger['native_source']=self.native.get('initiatorSource')
   await self.post(role,ROLES[role]['wire'],"Maya, I’m checking TeamChat’s message service now. I’ll explain what I find and ask before sharing findings or changing anything.",kind='working')
  elif trigger['kind']=='peer_message' and trigger['message']['kind']=='question':
   await self.post(role,'shared',"I’ve received TeamChat’s question through Switch. I’m checking HarborCloud’s connection now; Leo will review any change.",thread_id=self.native['incidentRoot']['switchMessageId'],kind='working')
  elif trigger['kind']=='own_operation_result':
   result=trigger['proposal']['result'];verification=result.get('verification',{});observation=result.get('observation',{})
   if role=='harborcloud':
    canary=observation.get('gatewayCanary') or {};line=f"The approved cloud change ran. The connection check passed {canary.get('succeeded','?')} of {canary.get('attempted','?')} requests. A fresh message check delivered {verification.get('delivered','?')} of {verification.get('attempted','?')}. I’m preparing the result for your review."
   else:line=f"The approved message-service recovery ran. A fresh check delivered {verification.get('delivered','?')} of {verification.get('attempted','?')} messages. I’m preparing the result for your review."
   await self.post(role,ROLES[role]['wire'],line,thread_id=trigger['proposal']['card']['switchMessageId'],kind='operation_result')
  await super().step(role,trigger)
  if self.agent(role)['status']=='complete':
   await self.post(role,ROLES[role]['wire'],self.agent(role)['lastSummary'],kind='agent_conclusion')
 async def stage(self,role,kind,title,content,wirekind,engine_proposal=None):
  p=await super().stage(role,kind,title,content,wirekind,engine_proposal)
  owner=ROLES[role]['owner'];text=f"### {title}\n\n{content.get('summary','')}\n\n"
  if kind=='operation':
   change=p['body']['content']['change']
   text+=f"**Change for {owner} to review:** {change}\n\nApproval also shares this summary and change description with the other team; internal resource IDs and authorization fields stay local.\n\nNo change has run yet. Reply **Approve this change** in this message’s thread to authorize this exact plan, or **Do not approve**."
  else:
   command='Share with HarborCloud' if wirekind=='question' and role=='teamchat' else 'Share this result'
   text+=f"**{owner}: may I share exactly this finding in the incident thread?** Reply **{command}** in this message’s thread, or **Do not share**."
  p['card']=await self.post(role,ROLES[role]['wire'],text,kind='owner_review');self.save();return p
 async def native_consume(self):
  while True:
   row=await self.relay.native_events.get();frame=row['frame'];data=frame['data'];payload=data.get('payload',{})
   room=next((k for k,v in self.relay.config['rooms'].items() if v['id']==data.get('room_id')),None)
   if room is None:continue
   primary='customer' if room=='shared' else room
   if row['observer']!=primary:continue
   side=next((k for k,v in self.relay.config['humans'].items() if v['actor_id']==payload.get('sender')),None)
   if side is None or (room!='shared' and side!=room):continue
   mid=payload.get('message_id')
   if mid in self.native_seen:continue
   try:
    source=await self.relay.verify_source(side,room,payload)
    if source is None:continue
    self.native_seen.add(mid);self.native['humanSources'].append(source);self.save()
    await self.handle_native(source)
   except asyncio.CancelledError:raise
   except Exception as error:
    self.event('native_input_refused',WIRE_ROLES[side],type(error).__name__+'; no unapproved action executed.')
    self.native['lastError']=type(error).__name__;self.save()
 def command(self,text):
  text=re.sub(r'^(?:Maya · TeamChat|Leo · HarborCloud)\s*\n+', '',text).strip()
  return text.rstrip('.!').strip().lower()
 async def handle_native(self,source):
  role=WIRE_ROLES[source['side']];command=self.command(source['body'])
  if source['room']=='shared' and role=='teamchat' and 'investigate' in command:
   if self.case_token:return
   self.native['incidentRoot']={'switchMessageId':source['threadId'] or source['switchMessageId'],'mattermostPostId':source['rootPostId'] or source['postId']}
   self.native['initiatorSource']=source
   await self.post(role,'shared',"I’ve received the report. I’m checking TeamChat’s own service first. I’ll keep the two teams’ findings and decisions together in this thread.",thread_id=self.native['incidentRoot']['switchMessageId'],kind='acknowledgment')
   if self.fixture:
    failed=next((m for m in self.fixture['messages'] if m['status']=='failed'),None)
    if failed:
     message={k:failed[k] for k in ('id','text','author')};self.native['failedMessage']=message
     self.native['failedCard']=await self.post(role,'shared',f"### An actual failed delivery check\n\n**{message['text']}**\n\nThis message did not arrive during the busy-morning check. I’ve kept its original identity and text for a later retry. This is a failed test request, not a failed Mattermost post.\n\nAfter service recovery, Maya can reply **Retry this message** here.",kind='failed_message')
   await super().investigate();return
  if command=='retry this message':
   card=self.native.get('failedCard')
   if role!='teamchat' or source['room']!='shared' or not card or source['rootPostId']!=card['mattermostPostId'] or source['threadId']!=card['switchMessageId']:raise ValueError('Retry must be in the original failed-message thread')
   await self.retry_message(source);return
  if command in {'share with harborcloud','share this result','approve this change','do not approve','do not share'}:
   p=next((p for p in self.state['proposals'] if p['role']==role and p.get('card',{}).get('mattermostPostId')==source['rootPostId']),None)
   if not p or source['room']!=ROLES[role]['wire'] or source['threadId']!=p['card']['switchMessageId']:raise ValueError('Decision must reply to the exact owner review card')
   if command.startswith('do not'):
    await self.reject(p['id'],role);await self.post(role,source['room'],'I’ve recorded your decision. Nothing from this card will be applied or shared.',thread_id=p['card']['switchMessageId']);return
   if (p['kind']=='operation')!=(command=='approve this change'):raise ValueError('Reply must match this card’s decision')
   await self.approve_source(p,role,source)
 async def approve_source(self,p,role,source):
  async with self.approval_lock:
   self.lookup(p['id'],role)
   human=self.relay.config['humans'][ROLES[role]['wire']]
   if source['side']!=ROLES[role]['wire'] or source['room']!=ROLES[role]['wire'] or source['actorId']!=human['actor_id'] or source['rootPostId']!=p['card']['mattermostPostId'] or source['threadId']!=p['card']['switchMessageId']:raise ValueError('Native owner, room or exact review thread differs')
   if p['status'] in {'released','executed'}:return
   if p['status']!='pending' or expiry(p['expiresAt'])<=time.time():raise ValueError('Review is no longer current')
   if envelope_digest(ROLES[role]['wire'],self.case_token,p['body'])!=p['digest']:raise ValueError('Exact approved finding changed')
   self.verify_engine_binding(p)
   p['status']='approving';p['nativeApproval']=source;self.save()
   try:
    receipt=await self.relay.publish_approved(ROLES[role]['wire'],self.case_token,p['body'],p['digest'],source,thread_id=self.native['incidentRoot']['switchMessageId'])
    p.update(receipt=receipt,approvedAt=stamp(),approvalMode='native_enrolled_owner_reply',status='released')
    if p['kind']=='operation':
     ep=p['engineProposal'];p['result']=await self.engine_call(role,'apply_recovery',{'proposalId':ep['id'],'digest':ep['digest']},apply=True);p['status']='executed'
     await self.queues[role].put({'kind':'own_operation_result','incident':self.case_token,'proposal':p})
    elif p['body']['kind']=='verification':await self.queues[role].put({'kind':'own_verification_released','incident':self.case_token,'proposalId':p['id']})
    await self.post(role,source['room'],'Your approval is verified. '+('The recovery ran; I’m checking its result.' if p['kind']=='operation' else 'The reviewed finding has reached the other agent through Switch.'),thread_id=p['card']['switchMessageId'],kind='owner_decision_receipt')
    self.save()
   except Exception:p['status']='failed';self.save();raise
 async def retry_message(self,source):
  if self.native['retry'] and self.native['retry'].get('passed'):return
  if not all(any(p['role']==r and p['kind']=='operation' and p['status']=='executed' for p in self.state['proposals']) for r in ROLES):raise ValueError('Both owner recoveries must be verified before the selected retry')
  message=self.native['failedMessage'];base=self.engine['apiBase'];responses=[]
  for _ in range(2):
   response=await self.http.post(base+'/api/messages',json=message);value=response.json();self.safe(value);responses.append(value)
  state=(await self.http.get(base+'/api/state')).json();record=next((m for m in state['messages'] if m['id']==message['id']),None)
  passed=all(r.get('ok') for r in responses) and responses[-1].get('duplicate') is True and record is not None and record['status']=='delivered'
  self.native['retry']={'source':source,'message':message,'responses':responses,'record':record,'passed':passed,'at':stamp()}
  self.native.setdefault('retryAttempts',[]).append(self.native['retry'])
  self.history['teamchat'].append({'type':'native_customer_tool_result','at':stamp(),'action':'retry_original_failed_message','source':source,'result':self.native['retry']})
  text=('The same earlier failed message has now arrived. Its original identity and text were preserved. A repeated identical request was recognized as a duplicate, so it did not create a second message.' if passed else 'The retry did not verify both delivery and duplicate suppression. I’m keeping the case open; inspect the measured result before trying again.')
  self.native['retryPost']=await self.post('teamchat','shared',text,thread_id=self.native['failedCard']['switchMessageId'],kind='retry_result');self.save()
 def pending(self,role,kind=None,wirekind=None):
  return next((p for p in self.state['proposals'] if p['role']==role and p['status']=='pending' and p.get('card') and (kind is None or p['kind']==kind) and (wirekind is None or p['body']['kind']==wirekind)),None)
 async def wait_for(self,predicate,timeout=150):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   result=predicate()
   if result:return result
   if any(a['status']=='error' for a in self.state['agents']):raise RuntimeError('Native agent needs operator attention')
   await asyncio.sleep(.15)
  raise TimeoutError('Native stage did not reach its verified condition')
 async def human_post(self,role,roomkey,text,*,root=None):
  side=ROLES[role]['wire'];h=self.relay.config['humans'][side];payload={'channel_id':self.relay.config['rooms'][roomkey]['external_channel_id'],'message':ROLES[role]['owner']+' · '+ROLES[role]['label']+'\n\n'+text}
  if root:payload['root_id']=root
  response=await self.http.post(self.relay.config['mattermost_url']+'/api/v4/posts',headers={'Authorization':'Bearer '+h['token']},json=payload)
  if response.status_code!=201:raise RuntimeError('Presenter roleplay post refused')
  post=response.json();self.native['posts'].append({'role':role,'kind':'presenter_roleplay','at':stamp(),'mattermostPostId':post['id'],'room':roomkey,'text':payload['message']});self.save();return post
 async def stage_action(self,name):
  async with self.stage_lock:
   row=self.native['stages'][name];row.update(status='running',startedAt=stamp());self.save()
   try:
    if name=='incident':
     base=self.engine['apiBase'];response=await self.http.post(base+'/api/demo/burst',json={})
     if response.status_code!=202:raise RuntimeError('Actual incident load was refused')
     for _ in range(200):
      self.fixture=(await self.http.get(base+'/api/state')).json()
      if not self.fixture['burst']['running']:break
      await asyncio.sleep(.1)
     self.native['initialHealth']=self.fixture['health']
     (self.directory/'initial-engine.json').write_text(json.dumps(self.fixture,indent=2))
     await self.human_post('teamchat','shared','Customers are reporting failed TeamChat messages. TeamChat Agent, can you investigate?')
     await self.wait_for(lambda:self.pending('teamchat','disclosure','question'))
    elif name=='presence':
     await self.wait_for(lambda:any(p['kind']=='acknowledgment' for p in self.native['posts']))
     await self.human_post('harborcloud','shared','We’re here from HarborCloud.',root=self.native['incidentRoot']['mattermostPostId'])
     await self.wait_for(lambda:any(s['side']=='provider' and 'here from HarborCloud' in s['body'] for s in self.native['humanSources']))
    elif name=='retry':
     card=self.native['failedCard'];await self.human_post('teamchat','shared','Retry this message',root=card['mattermostPostId']);await self.wait_for(lambda:self.native['retry'])
     if not self.native['retry'].get('passed'):raise RuntimeError('The actual original-message retry did not pass')
    elif name=='close':
     p=await self.wait_for(lambda:self.pending('harborcloud','disclosure','verification') or all(a['status']=='complete' for a in self.state['agents']))
     if isinstance(p,dict):
      await self.human_post('harborcloud','provider','Share this result',root=p['card']['mattermostPostId'])
     await self.wait_for(lambda:all(a['status']=='complete' for a in self.state['agents']))
     base=self.engine['apiBase'];r=await self.http.post(base+'/api/demo/probe',json={})
     if r.status_code!=202:raise RuntimeError('Final actual delivery check refused')
     for _ in range(200):
      value=(await self.http.get(base+'/api/state')).json()
      if not value['burst']['running']:break
      await asyncio.sleep(.1)
     self.native['freshCheck']=value['health'];self.native['finalCheckPost']=await self.post('teamchat','shared',f"### Latest delivery check\n\n{value['health']['delivered']} of {value['health']['attempted']} messages arrived. "+('The measured response-time target was met.' if value['health']['status']=='healthy' else 'The measured response-time target was not met.')+' Earlier messages are only confirmed where explicitly checked.',thread_id=self.native['incidentRoot']['switchMessageId'],kind='fresh_check')
     if not delivery_check_passed(value['health']):raise RuntimeError('The actual closing delivery check did not pass')
    else:
     specs={'share_question':('teamchat','disclosure','question','Share with HarborCloud'),
      'approve_cloud':('harborcloud','operation',None,'Approve this change'),
      'share_cloud_result':('harborcloud','disclosure','verification','Share this result'),
      'approve_app':('teamchat','operation',None,'Approve this change'),
      'share_app_result':('teamchat','disclosure','verification','Share this result')}
     role,kind,wirekind,text=specs[name];p=await self.wait_for(lambda:self.pending(role,kind,wirekind))
     await self.human_post(role,ROLES[role]['wire'],text,root=p['card']['mattermostPostId'])
     await self.wait_for(lambda:p['status'] in {'released','executed','failed'})
     if p['status']=='failed':raise RuntimeError('Approved native stage failed')
     if name=='share_question':await self.wait_for(lambda:self.pending('harborcloud','operation'))
     elif name=='approve_cloud':
      await self.wait_for(lambda:self.pending('harborcloud','disclosure','verification'))
      if not cloud_check_passed(p.get('result',{})):raise RuntimeError('Actual cloud connection check did not pass; do not claim connection recovery')
     elif name=='share_cloud_result':await self.wait_for(lambda:self.pending('teamchat','operation'))
     elif name=='approve_app':
      await self.wait_for(lambda:self.pending('teamchat','disclosure','verification'))
      if not delivery_check_passed(p.get('result',{}).get('verification',{})):raise RuntimeError('Actual app recovery did not pass the delivery check')
     elif name=='share_app_result':await self.wait_for(lambda:self.pending('harborcloud','disclosure','verification') or all(a['status']=='complete' for a in self.state['agents']))
    row.update(status='complete',completedAt=stamp());self.save()
   except Exception as error:row.update(status='failed',error=type(error).__name__,completedAt=stamp());self.save()
 def queue_stage(self,name):
  if name not in STAGES:raise ValueError('Unknown native camera stage')
  if name in self.native['stages']:return self.native['stages'][name]
  index=STAGES.index(name)
  if index and self.native['stages'].get(STAGES[index-1],{}).get('status')!='complete':raise ValueError('Complete the preceding camera stage first')
  row={'name':name,'status':'queued','requestedAt':stamp(),'participation':'scripted_presenter_roleplay'};self.native['stages'][name]=row
  task=asyncio.create_task(self.stage_action(name));self.stage_tasks.add(task);task.add_done_callback(self.stage_tasks.discard);self.save();return row

def native_app(bridge):
 app=create_app(bridge)
 @app.get('/api/native/state')
 async def native_state():return bridge.native
 @app.post('/api/native/stage')
 async def stage(request:Request):
  body=await json_object(request)
  try:return JSONResponse(bridge.queue_stage(body.get('stage')),status_code=202)
  except ValueError as error:return JSONResponse({'error':str(error)},status_code=409)
 return app

def main():
 import argparse,uvicorn
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=4319);p.add_argument('--state-dir',type=Path);p.add_argument('--engine-config',type=Path);p.add_argument('--max-calls',type=int,default=6);a=p.parse_args()
 uvicorn.run(native_app(NativeBridge(a.state_dir,a.engine_config,max_calls=a.max_calls)),host='127.0.0.1',port=a.port,log_level='warning')
if __name__=='__main__':main()
