"""Read-only measurement/source audit of the actual native take, after capture."""
from __future__ import annotations
import argparse,hashlib,json,sqlite3
from pathlib import Path
from .bridge import ROOT

def audit(directory):
 directory=Path(directory);native=json.loads((directory/'native-state.json').read_text());coord=json.loads((directory/'coordination.json').read_text());cfg=json.loads((directory/'switch/config.json').read_text());engine=json.loads((ROOT/'.runtime/engine.json').read_text());initial=json.loads((directory/'initial-engine.json').read_text());calls=[]
 for role in ['teamchat','harborcloud']:
  calls.extend({'role':role,**r['metadata']} for r in json.loads((directory/(role+'-transcript.json')).read_text()) if r['type']=='live_model_decision')
 app=next((p for p in coord['proposals'] if p['role']=='teamchat' and p['kind']=='operation' and p['status']=='executed'),{})
 app_recovery=app.get('result',{}).get('verification',{})
 cloud=next((p for p in coord['proposals'] if p['role']=='harborcloud' and p['kind']=='operation' and p['status']=='executed'),{})
 partial=cloud.get('result',{}).get('verification',{});canary=cloud.get('result',{}).get('observation',{}).get('gatewayCanary',{})
 retry=native.get('retry') or {};message=retry.get('message',{});mid=message.get('id');rows=0
 if mid:
  with sqlite3.connect(f"file:{ROOT/'.runtime/messages.sqlite3'}?mode=ro",uri=True) as db:rows=db.execute('SELECT COUNT(*) FROM messages WHERE id=?',(mid,)).fetchone()[0]
 original=next((m for m in initial['messages'] if m['id']==mid),None);final=native.get('freshCheck') or {};bound=[]
 with sqlite3.connect(directory/'switch/transport.db') as db:
  for p in coord['proposals']:
   if not p.get('receipt'):continue
   r=p['receipt'];source=p['nativeApproval'];card=p['card'];side='customer' if p['role']=='teamchat' else 'provider'
   count=db.execute('SELECT COUNT(*) FROM events WHERE message_id=?',(r['approval_switch_message_id'],)).fetchone()[0]
   shared=db.execute('SELECT COUNT(*) FROM events WHERE message_id=?',(r['shared_switch_message_id'],)).fetchone()[0]
   bound.append(count>0 and shared>0 and source['actorId']==cfg['humans'][side]['actor_id'] and source['rootPostId']==card['mattermostPostId'] and source['threadId']==card['switchMessageId'] and r['approval_mode']=='native_enrolled_owner_reply')
 secretvalues=[v for c in engine['credentials'].values() for v in c.values()]+[v for group in ['agents','humans'] for c in cfg[group].values() for k,v in c.items() if k in ['api_key','password','token'] and isinstance(v,str)]
 files=[directory/f for f in ['native-state.json','coordination.json','teamchat-transcript.json','harborcloud-transcript.json']]
 checks={'allNativeStagesComplete':all(native.get('stages',{}).get(s,{}).get('status')=='complete' for s in ['incident','presence','share_question','approve_cloud','share_cloud_result','approve_app','share_app_result','retry','close']),
  'sourceAndExactReviewThreadsBound':bool(bound) and all(bound),'bothOwnersExecuted':all(any(p['role']==r and p['kind']=='operation' and p['status']=='executed' for p in coord['proposals']) for r in ['teamchat','harborcloud']),
  'actualSeparateLiveModelContexts':all(any(c['role']==r and c.get('live') for c in calls) for r in ['teamchat','harborcloud']),
  'gatewayHealthyWhileFreshChatDegraded':canary.get('status')=='healthy' and partial.get('delivered',0)<partial.get('attempted',0),
  'appRecovery24of24BeforeRetry':app_recovery.get('attempted')==24 and app_recovery.get('delivered')==24 and app_recovery.get('status')=='healthy' and str(app_recovery.get('testedAt',''))<str(retry.get('at','')),
  'fresh24of24AndSLO':final.get('attempted')==24 and final.get('delivered')==24 and final.get('status')=='healthy',
  'originalFailedMessageSameIdBodyRetry':bool(original and original['status']=='failed' and all(original.get(k)==message.get(k) for k in ['id','text','author']) and retry.get('passed') and rows==1),
  'bothRolesClosed':all(a['status']=='complete' for a in coord['agents']), 'roomScopes':coord['accessChecks']['passed'],
  'knownCredentialOccurrencesZero':sum(p.read_text().count(v) for p in files for v in secretvalues if len(v)>12)==0}
 result={'passed':all(checks.values()),'checks':checks,'participation':'Scripted presenter roleplay in two actual enrolled human accounts; actual scoped live agents and Switch events.',
  'before':native['initialHealth'],'partial':partial,'gatewayCanary':canary,'appRecovery':app_recovery,'final':final,
  'retry':{'originalFailed':bool(original and original['status']=='failed'),'id':mid,'delivered':bool(retry.get('passed')),'persistedRows':rows,'sameIdAndBody':bool(original and all(original.get(k)==message.get(k) for k in ['id','text','author'])),'responses':retry.get('responses')},
  'modelCalls':len(calls),'distinctThreads':len({t for c in calls for t in c.get('thread_ids',[])}),'summedInferenceSeconds':round(sum(c.get('seconds',0) for c in calls),3),
  'usage':{k:sum(c.get('usage',{}).get(k,0) for c in calls) for k in ['input_tokens','cached_input_tokens','output_tokens']},
  'actualReleases':len(coord['messages']),'nativeSourceReplies':len(native['humanSources']),'sourceHashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'agents').glob('*.py'))},'native':native,'coordination':coord}
 (directory/'native-verification.json').write_text(json.dumps(result,indent=2,ensure_ascii=False));print(json.dumps({k:result[k] for k in ['passed','checks','modelCalls','actualReleases','retry','final']},indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--state-dir',type=Path,default=ROOT/'agents/.runtime/native');a=p.parse_args();raise SystemExit(0 if audit(a.state_dir)['passed'] else 1)
