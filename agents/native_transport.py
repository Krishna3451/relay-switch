"""Readable native chat, with the complete peer envelope retained in Switch text."""
from __future__ import annotations
import asyncio,base64,hashlib,json,re,time
from datetime import datetime,timezone
from .relay import SwitchRelay,RelayError,canonical,envelope_digest,validate_envelope
MARKER=re.compile(r'\[\u2060\]\(# "relay-native:([A-Za-z0-9_-]+)"\)')
def machine_post(side,case,body,digest):
 wire={'side':side,'case_token':case,'body':body,'digest':digest}
 payload=base64.urlsafe_b64encode(canonical(wire).encode()).decode().rstrip('=')
 title=body['content'].get('title') or {'question':'Question for the other team','evidence':'Finding shared by the owner','repair_proposal':'Owner-approved recovery plan','verification':'Verified result shared by the owner'}[body['kind']]
 caption=f"### {title}\n\n{body['content'].get('summary','')}"
 if body['kind']=='repair_proposal':
  if isinstance(body['content'].get('change'),str):caption+='\n\n**Approved change:** '+body['content']['change']
  caption+='\n\n**Approved plan. Execution has not yet been verified.**'
 text=caption+'\n\n[\u2060](# "relay-native:'+payload+'")'
 if len(text.encode())>16000:raise RelayError('Native post exceeds the bounded chat envelope')
 return text

def read_machine_post(text):
 found=MARKER.search(text)
 if not found:return None
 try:
  raw=found.group(1);wire=json.loads(base64.urlsafe_b64decode(raw+'='*((-len(raw))%4)))
  if set(wire)!={'side','case_token','body','digest'}:raise ValueError()
  if envelope_digest(wire['side'],wire['case_token'],wire['body'])!=wire['digest']:raise ValueError()
  if machine_post(wire['side'],wire['case_token'],wire['body'],wire['digest'])!=text:raise ValueError()
  return wire
 except (ValueError,TypeError,KeyError):raise RelayError('Invalid native machine envelope') from None

class NativeRelay(SwitchRelay):
 agent_keys=('customer','provider')
 def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.native_events=asyncio.Queue()
 async def _capture(self,observer,client):
  async for frame in client.events():
   if frame.get('event')=='message':
    mid=frame['data'].get('payload',{}).get('message_id')
    if mid:
     with self._db() as con:con.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?)',(observer,mid,canonical(frame),time.time()))
     await self.native_events.put({'observer':observer,'frame':frame})
   await client.ack(frame)
 async def release(self,*args,**kwargs):raise RelayError('Native mode accepts only original enrolled-owner reply events')
 async def prepare(self,side,case_token,body):
  digest=envelope_digest(side,case_token,body)
  with self._db() as con:con.execute('INSERT OR IGNORE INTO proposals(digest,side,case_token,body,created_at) VALUES(?,?,?,?,?)',(digest,side,case_token,canonical(body),time.time()))
  return digest
 async def post_readable(self,side,roomkey,text,*,thread_id=None,marker=None):
  if marker:text+='\n\n[\u2060](# "'+marker+'")'
  result=await self.clients[side].post_message(self.config['rooms'][roomkey]['id'],text,thread_id=thread_id)
  if not isinstance(result,dict) or not isinstance(result.get('event_id'),str):raise RelayError('Switch did not return an authoritative post ID')
  post=None
  for _ in range(150):
   post=await self._find_post(side,roomkey,text)
   if post:break
   await asyncio.sleep(.1)
  if not post:raise RelayError('Native agent post was not read back from Mattermost')
  return {'switchMessageId':result['event_id'],'mattermostPostId':post['id'],'room':roomkey,'text':text,'postedAt':datetime.now(timezone.utc).isoformat()}
 async def verify_source(self,side,roomkey,payload):
  human=self.config['humans'][side];room=self.config['rooms'][roomkey]
  if payload.get('sender')!=human['actor_id'] or payload.get('on_behalf_of') or payload.get('sender_kind') in {'agent','platform'}:return None
  # Search bounded native-room history and bind immutable original account+post.
  for post in await self._posts(side,roomkey):
   source='\x1f'.join([human['client_id'],self.config['bridge_id'],room['external_channel_id'],post['id'],'0'])
   mid='sw_'+hashlib.sha256(source.encode()).hexdigest()[:32]
   if mid!=payload.get('message_id'):continue
   if post.get('user_id')!=human['id'] or post.get('message')!=payload.get('body') or post.get('channel_id')!=room['external_channel_id']:return None
   if post.get('edit_at') or post.get('delete_at') or post.get('type') or post.get('props',{}).get('from_webhook') or post.get('props',{}).get('from_bot'):return None
   return {'side':side,'room':roomkey,'body':post['message'],'postId':post['id'],'rootPostId':post.get('root_id') or None,
    'switchMessageId':mid,'threadId':payload.get('thread_id'),'actorId':human['actor_id'],'createdAt':post['create_at']/1000}
  raise RelayError('Native human source post could not be independently bound')
 async def publish_approved(self,side,case,body,digest,source,*,thread_id):
  if digest!=envelope_digest(side,case,body):raise RelayError('Exact native disclosure digest changed')
  with self._db() as con:row=con.execute('SELECT * FROM proposals WHERE digest=?',(digest,)).fetchone()
  if not row or source['createdAt']<row['created_at']:raise RelayError('Native approval predates the exact proposal')
  if row['receipt']:return json.loads(row['receipt'])
  text=machine_post(side,case,body,digest)
  posted=await self.post_readable(side,'shared',text,thread_id=thread_id)
  opposite='provider' if side=='customer' else 'customer'
  frame=await self._wait(lambda:self._event(opposite,room=self.config['rooms']['shared']['id'],sender=self.config['agents'][side]['actor_id'],body=text))
  wire=read_machine_post(frame['data']['payload']['body'])
  if not wire or wire['digest']!=digest:raise RelayError('Opposing event did not retain the approved evidence')
  receipt={'case_token':case,'side':side,'kind':body['kind'],'digest':digest,'approval_mode':'native_enrolled_owner_reply',
   'participation':'fictional_presenter_roleplay','approval_mattermost_post_id':source['postId'],
   'approval_switch_message_id':source['switchMessageId'],'approval_root_mattermost_post_id':source['rootPostId'],
   'approval_thread_switch_id':source['threadId'],'shared_mattermost_post_id':posted['mattermostPostId'],
   'shared_switch_message_id':frame['data']['payload']['message_id'],'counterpart':opposite,
   'counterpart_switch_event_id':frame.get('id'),'counterpart_observed_at':datetime.now(timezone.utc).isoformat(),
   'transport':'Original enrolled human reply → captured Switch event → readable agent post with complete peer envelope → opposing Switch event + Mattermost readback'}
  with self._db() as con:con.execute('UPDATE proposals SET approval_post_id=?,approval_event_id=?,shared_event_id=?,receipt=? WHERE digest=?',(source['postId'],source['switchMessageId'],receipt['shared_switch_message_id'],canonical(receipt),digest))
  await self.deliveries.put({'recipient':opposite,'body':wire['body'],'receipt':receipt})
  return receipt
