"""Native boundary tests use explicit fake transport; live recording has separate proof."""
import asyncio,hashlib,json,tempfile,time,unittest
from pathlib import Path
from agents.native import NativeBridge
from agents.native_transport import NativeRelay,machine_post,read_machine_post
from agents.relay import envelope_digest,RelayError

class FakeNativeRelay:
 def __init__(self):
  self.deliveries=asyncio.Queue();self.native_events=asyncio.Queue();self.calls=[];self.posts=[]
  self.config={'humans':{'customer':{'actor_id':'maya-actor'},'provider':{'actor_id':'leo-actor'}}}
 async def prepare(self,side,case,body):return envelope_digest(side,case,body)
 async def post_readable(self,side,room,text,**kwargs):
  self.posts.append((side,room,text,kwargs));n=len(self.posts)
  return {'switchMessageId':'sw_card_'+str(n),'mattermostPostId':'mm_card_'+str(n),'room':room,'text':text}
 async def publish_approved(self,side,case,body,digest,source,**kwargs):
  self.calls.append((side,source));return {'approval_mode':'native_enrolled_owner_reply','approval_switch_message_id':source['switchMessageId']}
 async def release(self,*args,**kwargs):raise AssertionError('Native must not manufacture owner posts')
class FakeNativeBridge(NativeBridge):
 async def engine_call(self,role,action=None,args=None,*,apply=False):
  self.engine_calls.append((role,action,args,apply));return {'applied':True,'verification':{'delivered':24,'attempted':24}}
class NativeBoundaries(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.relay=FakeNativeRelay();self.b=FakeNativeBridge(Path(self.temp.name),relay=self.relay);self.b.case_token='native-unit';self.b.engine_calls=[];self.b.native['incidentRoot']={'switchMessageId':'sw_incident','mattermostPostId':'mm_incident'}
 def tearDown(self):self.temp.cleanup()
 async def make_card(self):
  ep={'id':'engine-native','digest':'exact-engine-digest','expectedRevision':7,'expiresAt':time.time()+600,'target':{'allocationIds':['failed-1']}}
  return await self.b.stage('teamchat','operation','Restart the message service safely',{'summary':'One server failed to start.','operation':ep},'repair_proposal',ep)
 def source(self,p,**changes):
  s={'side':'customer','room':'customer','actorId':'maya-actor','body':'Maya · TeamChat\n\nApprove this change','postId':'mm_human','rootPostId':p['card']['mattermostPostId'],'switchMessageId':'sw_human','threadId':p['card']['switchMessageId'],'createdAt':time.time()};s.update(changes);return s
 async def test_native_web_paths_cannot_start_or_approve(self):
  with self.assertRaises(ValueError):await self.b.investigate()
  with self.assertRaises(ValueError):await self.b.approve('anything','teamchat')
  self.assertFalse(self.relay.calls);self.assertFalse(self.b.engine_calls)
 async def test_native_wrong_actor_room_or_either_thread_cannot_apply(self):
  p=await self.make_card()
  for changes in ({'actorId':'leo-actor'},{'side':'provider'},{'room':'shared'},{'rootPostId':'other-mm-card'},{'threadId':'other-sw-card'}):
   with self.assertRaises(ValueError):await self.b.approve_source(p,'teamchat',self.source(p,**changes))
  self.assertFalse(self.relay.calls);self.assertFalse(self.b.engine_calls);self.assertEqual('pending',p['status'])
 async def test_native_exact_original_reply_authorizes_only_owner_operation(self):
  p=await self.make_card();source=self.source(p)
  await self.b.approve_source(p,'teamchat',source);await self.b.approve_source(p,'teamchat',source)
  self.assertEqual(1,len(self.b.engine_calls));self.assertEqual(('teamchat','apply_recovery',{'proposalId':'engine-native','digest':'exact-engine-digest'},True),self.b.engine_calls[0]);self.assertEqual(1,len(self.relay.calls));self.assertEqual('executed',p['status'])
 async def test_native_changed_digest_or_expiry_refuses(self):
  p=await self.make_card();p['body']['content']['summary']='Changed after review'
  with self.assertRaises(ValueError):await self.b.approve_source(p,'teamchat',self.source(p))
  self.assertFalse(self.relay.calls)
 async def test_native_private_execution_binding_cannot_be_swapped(self):
  p=await self.make_card();p['engineProposal']['target']['allocationIds']=['other-failed-id']
  with self.assertRaises(ValueError):await self.b.approve_source(p,'teamchat',self.source(p))
  self.assertFalse(self.relay.calls);self.assertFalse(self.b.engine_calls)
 async def test_native_wrong_human_reply_thread_does_not_select_any_card(self):
  p=await self.make_card()
  with self.assertRaises(ValueError):await self.b.handle_native(self.source(p,rootPostId='unrelated',threadId='unrelated'))
  self.assertFalse(self.b.engine_calls)
 async def test_native_retry_requires_same_failed_message_thread(self):
  p=await self.make_card();self.b.native['failedCard']={'mattermostPostId':'failed-mm','switchMessageId':'failed-sw'}
  with self.assertRaises(ValueError):await self.b.handle_native(self.source(p,body='Retry this message',room='shared'))
  self.assertIsNone(self.b.native['retry'])
 def test_actual_machine_text_retains_complete_peer_evidence(self):
  body={'ticket':'native-unit','kind':'verification','content':{'title':'Cloud connection check','summary':'The connection works; messages still fail.','facts':{'measured':14,'total':24}}}
  digest=envelope_digest('provider','native-unit',body);text=machine_post('provider','native-unit',body,digest);wire=read_machine_post(text)
  self.assertEqual(body,wire['body']);self.assertNotIn('RELAY/1',text);self.assertTrue(text.startswith('### Cloud connection check'))
  with self.assertRaises(RelayError):read_machine_post(text.replace('messages still fail','all messages arrived'))
 async def test_native_transport_original_source_proof_rejects_edits_and_actor_spoof(self):
  relay=NativeRelay(Path(self.temp.name)/'source');h={'id':'mm-maya','client_id':'client-maya','actor_id':'actor-maya'};relay.config={'bridge_id':'bridge','humans':{'customer':h},'rooms':{'customer':{'external_channel_id':'channel'}}}
  post={'id':'original','user_id':h['id'],'channel_id':'channel','message':'Approve this change','root_id':'review-root','create_at':int(time.time()*1000),'props':{},'type':''}
  mid='sw_'+hashlib.sha256('\x1f'.join([h['client_id'],'bridge','channel','original','0']).encode()).hexdigest()[:32]
  async def posts(*args):return [post]
  relay._posts=posts;payload={'sender':h['actor_id'],'message_id':mid,'body':post['message'],'thread_id':'sw-root'}
  ctx=await relay.verify_source('customer','customer',payload);self.assertEqual('review-root',ctx['rootPostId'])
  post['edit_at']=1;self.assertIsNone(await relay.verify_source('customer','customer',payload));post.pop('edit_at')
  self.assertIsNone(await relay.verify_source('customer','customer',{**payload,'sender':'actor-other'}))
 async def test_presence_camera_gate_is_required_before_sharing_question(self):
  self.b.native['stages']['incident']={'status':'complete'}
  with self.assertRaises(ValueError):self.b.queue_stage('share_question')
  self.assertFalse(self.relay.calls);self.assertFalse(self.b.engine_calls)
 async def test_native_transport_never_posts_manufactured_approval(self):
  relay=NativeRelay(Path(self.temp.name)/'reject')
  with self.assertRaises(RelayError):await relay.release('customer','native-unit',{},'digest')

class DeclaredCloudValidation(unittest.TestCase):
 def test_provider_contract_precedes_plan_and_matches_actual_http_check(self):
  from engine.server import Engine
  from agents.native import cloud_check_passed
  with tempfile.TemporaryDirectory(prefix='relay-declared-cloud-contract-') as directory:
   engine=Engine(directory,port=0).start()
   try:
    before=engine.observation('cloud');contract=before['validationContract']['gatewayConnectionCheck']
    self.assertEqual('unmeasured',before['gatewayCanary']['status'])
    self.assertGreater(contract['simultaneousRequests'],0);self.assertEqual(contract['simultaneousRequests'],contract['requiredSuccesses'])
    self.assertNotIn('validationContract',engine.observation('app'))
    first=engine.gateway_canary();self.assertEqual(contract['simultaneousRequests'],first['attempted']);self.assertLess(first['succeeded'],first['attempted'])
    self.assertFalse(cloud_check_passed({'observation':{'gatewayCanary':first}}))
    code,proposal=engine.propose('cloud',{'expectedRevision':before['revision'],'reason':'Size this owned route to its declared simultaneous check demand.','capacity':contract['simultaneousRequests']})
    self.assertEqual(200,code);code,result=engine.apply('cloud',{'proposalId':proposal['id'],'digest':proposal['digest']})
    self.assertEqual(200,code);self.assertTrue(cloud_check_passed(result));self.assertEqual(contract['requiredSuccesses'],result['observation']['gatewayCanary']['succeeded'])
   finally:engine.stop()
 def test_four_of_six_cannot_be_a_passing_cloud_stage(self):
  from agents.native import cloud_check_passed
  self.assertFalse(cloud_check_passed({'observation':{'gatewayCanary':{'status':'degraded','attempted':6,'succeeded':4,'results':[{'passed':True}]*4+[{'passed':False}]*2}}}))

if __name__=='__main__':unittest.main()
