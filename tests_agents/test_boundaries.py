"""Fake-model/transport tests; separate from live Switch evidence."""
import asyncio, copy, tempfile, time, unittest
from datetime import datetime, timezone
from pathlib import Path
from agents.bridge import Bridge
from agents.relay import envelope_digest, RelayError, validate_envelope
class FakeRelay:
 def __init__(self):self.deliveries=asyncio.Queue();self.calls=[];self.config=None
 async def prepare(self,side,case,body):return envelope_digest(side,case,body)
 async def release(self,side,case,body,digest,**kwargs):
  if digest!=envelope_digest(side,case,body):raise RelayError('tamper')
  self.calls.append((side,copy.deepcopy(body),kwargs))
  receipt={'side':side,'shared_switch_message_id':'fake-unit-event-'+str(len(self.calls)), 'approval_mode':kwargs['approval_mode'],'approval_switch_message_id':'fake-unit-approval'}
  await self.deliveries.put({'recipient':'provider' if side=='customer' else 'customer','body':copy.deepcopy(body),'receipt':receipt})
  return receipt
class FakeModel:
 def __init__(self):self.payloads=[]
 async def infer(self,role,payload):
  self.payloads.append((role,copy.deepcopy(payload)))
  return {'summary':'Waiting for owner evidence.','action':'wait','content':{'reason':'Unit test'}},{'live':False,'fixture':'unit test only'}
class TestBridge(Bridge):
 async def engine_call(self,role,action=None,args=None,*,apply=False):
  self.engine_calls.append((role,action,args,apply))
  if not action:return {'revision':1,'evidenceId':role+'-private-evidence','privateCanary':role+'-only'}
  if action=='apply_recovery':return {'applied':True,'revision':2}
class Boundaries(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.relay=FakeRelay();self.model=FakeModel()
  self.b=TestBridge(Path(self.temp.name),model=self.model,relay=self.relay);self.b.case_token='unit_incident';self.b.engine_calls=[]
 def tearDown(self):self.temp.cleanup()
 async def stage(self,role='teamchat',operation=False):
  ep={'id':'engine-1','digest':'engine-digest','expectedRevision':1,'expiresAt':datetime.fromtimestamp(time.time()+600,timezone.utc).isoformat(),'target':{'allocationIds':['private-worker-id']},'reason':'Private owner rationale'}
  content={'summary':'Minimal selected fact','operation':ep} if operation else {'summary':'Minimal selected fact'}
  return await self.b.stage(role,'operation' if operation else 'disclosure','Review selected fact',content,'repair_proposal' if operation else 'evidence',ep if operation else None)
 async def test_wrong_owner_cannot_release_or_apply(self):
  p=await self.stage(operation=True)
  with self.assertRaises(ValueError):await self.b.approve(p['id'],'harborcloud')
  self.assertEqual([],self.relay.calls);self.assertEqual([],self.b.engine_calls)
 async def test_expired_review_cannot_release(self):
  p=await self.stage();p['expiresAt']=datetime.fromtimestamp(time.time()-1,timezone.utc).isoformat()
  with self.assertRaises(ValueError):await self.b.approve(p['id'],'teamchat')
  self.assertEqual('expired',p['status']);self.assertFalse(self.relay.calls)
 async def test_body_tamper_cannot_release(self):
  p=await self.stage();p['body']['content']['summary']='Changed after owner preview'
  with self.assertRaises(ValueError):await self.b.approve(p['id'],'teamchat')
  self.assertFalse(self.relay.calls)
 async def test_operation_packet_excludes_private_execution_details(self):
  p=await self.stage(operation=True);wire=str(p['body'])
  self.assertNotIn('private-worker-id',wire);self.assertNotIn('Private owner rationale',wire);self.assertNotIn('engine-digest',wire)
  self.assertNotIn('operation',p['body']['content']);self.assertIn('1 named failed starts',p['body']['content']['change'])
  self.assertEqual(['private-worker-id'],p['engineProposal']['target']['allocationIds'])
 async def test_hidden_fields_and_unobserved_evidence_cannot_bypass_visible_review(self):
  for content in ({'summary':'Visible finding','privateLog':'Hidden raw history'},
                  {'summary':'Visible finding','evidenceIds':['unreviewed private text']},
                  {'summary':'Visible finding','evidenceIds':['event_0123456789']}):
   with self.assertRaises(ValueError):await self.b.stage('teamchat','disclosure','Review finding',content,'evidence')
  self.assertEqual([],self.b.state['proposals'])
  self.b.history['teamchat']=[{'type':'trigger','own_observation':{'events':[{'id':'event_0123456789'}]},'trigger':{'kind':'start'}}]
  p=await self.b.stage('teamchat','disclosure','Review finding',{'summary':'Visible finding','evidenceIds':['event_0123456789']},'evidence')
  self.assertEqual(['event_0123456789'],p['body']['content']['evidenceIds'])
 async def test_private_execution_binding_cannot_change_after_public_plan_review(self):
  p=await self.stage(operation=True);p['engineProposal']['target']['allocationIds']=['other-private-worker']
  with self.assertRaises(ValueError):await self.b.approve(p['id'],'teamchat')
  self.assertFalse(self.relay.calls);self.assertFalse(self.b.engine_calls)
 async def test_no_operation_before_explicit_approval_and_replay_idempotent(self):
  p=await self.stage(operation=True);self.assertFalse(self.b.engine_calls)
  await self.b.approve(p['id'],'teamchat');await self.b.approve(p['id'],'teamchat')
  self.assertEqual(1,len(self.relay.calls));self.assertEqual(1,len(self.b.engine_calls))
  role,action,args,apply=self.b.engine_calls[0]
  self.assertEqual(('teamchat','apply_recovery',True),(role,action,apply));self.assertEqual({'proposalId':'engine-1','digest':'engine-digest'},args)
  self.assertEqual('manual_fictional_owner_click',p['receipt']['approval_mode'])
 async def test_counterpart_queue_requires_transport_delivery(self):
  p=await self.stage();self.assertTrue(self.b.queues['harborcloud'].empty());consumer=asyncio.create_task(self.b.consume())
  try:
   await self.b.approve(p['id'],'teamchat');item=await asyncio.wait_for(self.b.queues['harborcloud'].get(),1)
   self.assertEqual('peer_message',item['kind']);self.assertEqual(p['body']['content'],item['message']['content'])
   self.assertEqual('fake-unit-event-1',item['message']['receipt']['shared_switch_message_id'])
  finally:consumer.cancel();await asyncio.gather(consumer,return_exceptions=True)
 async def test_private_model_histories_do_not_cross(self):
  await self.b.step('teamchat',{'kind':'start','incident':'unit_incident'});await self.b.step('harborcloud',{'kind':'peer_message','incident':'unit_incident','message':{'content':{'summary':'Approved fact only'}}})
  customer=str(self.model.payloads[0][1]);provider=str(self.model.payloads[1][1])
  self.assertIn('teamchat-only',customer);self.assertNotIn('harborcloud-only',customer);self.assertIn('harborcloud-only',provider);self.assertNotIn('teamchat-only',provider)
 async def test_rejected_review_cannot_release(self):
  p=await self.stage();await self.b.reject(p['id'],'teamchat')
  with self.assertRaises(ValueError):await self.b.approve(p['id'],'teamchat')
  self.assertFalse(self.relay.calls)
 async def test_credential_guard_rejects_exact_secret(self):
  self.b.secrets=['unit_private_secret_material']
  with self.assertRaises(ValueError):self.b.safe({'message':'unit_private_secret_material'})
 async def test_call_budget_stops_before_model(self):
  self.b.agent('teamchat')['modelCalls']=self.b.max_calls;await self.b.step('teamchat',{'kind':'peer_message','incident':'unit_incident'});self.assertFalse(self.model.payloads)
 async def test_budget_exhaustion_is_not_a_successful_incident_conclusion(self):
  self.b.state['status']='waiting';self.b.agent('harborcloud')['status']='complete';self.b.agent('teamchat')['modelCalls']=self.b.max_calls
  await self.b.step('teamchat',{'kind':'peer_message','incident':'unit_incident'})
  self.assertEqual('budget_complete',self.b.agent('teamchat')['status']);self.assertNotEqual('complete',self.b.state['status'])
 async def test_reset_cancels_inflight_model_and_invalidates_old_review(self):
  p=await self.stage()
  class WaitingModel:
   async def infer(inner,role,payload):
    await asyncio.Event().wait()
  self.b.model=WaitingModel()
  task=asyncio.create_task(self.b.worker('teamchat'));self.b.worker_tasks={'teamchat':task};self.b.tasks=[task]
  await self.b.queues['teamchat'].put({'kind':'start','incident':'unit_incident'})
  await asyncio.sleep(.01)
  await asyncio.wait_for(self.b.reset(),1)
  self.assertIsNone(self.b.case_token);self.assertEqual([],self.b.state['proposals'])
  with self.assertRaises(ValueError):await self.b.approve(p['id'],'teamchat')
  for task in self.b.worker_tasks.values():task.cancel()
  await asyncio.gather(*self.b.worker_tasks.values(),return_exceptions=True)
 async def test_earlier_case_trigger_cannot_enter_current_context(self):
  await self.b.step('teamchat',{'kind':'peer_message','incident':'old_incident','message':{'summary':'Old context'}})
  self.assertFalse(self.model.payloads);self.assertFalse(self.b.engine_calls);self.assertEqual([],self.b.history['teamchat'])
 def test_envelope_rejects_extra_field_credentials_and_other_case(self):
  for body in ({'ticket':'unit_incident','kind':'evidence','content':{},'extra':1},{'ticket':'other','kind':'evidence','content':{}},{'ticket':'unit_incident','kind':'evidence','content':{'bad':'Bearer private-token'}}):
   with self.assertRaises(RelayError):validate_envelope('unit_incident',body)
if __name__=='__main__':unittest.main()
