"""Explicit scripted-operator live verification, never used in manual mode.

Requires the stable running engine. Runs actual authenticated model inference and
actual Switch delivery; outputs remain separate from fixture unit tests.
"""
from __future__ import annotations
import argparse,asyncio,json,time,sqlite3
from pathlib import Path
from .bridge import Bridge,ROOT,stamp

async def run(args):
 bridge=Bridge(args.state_dir,args.engine_config,scripted=True,max_calls=args.max_calls)
 await bridge.start()
 report={'at':stamp(),'mode':'test_operator','model':'live authenticated Codex CLI','transport':'actual Switch + Mattermost','approval':'explicit scripted verification; no independent humans'}
 try:
  base=bridge.engine.get('apiBase','http://127.0.0.1:4318')
  if not args.no_burst:
   response=await bridge.http.post(base+'/api/demo/burst',json={})
   if response.status_code!=202:raise RuntimeError('Engine did not accept incident load burst')
   end=time.monotonic()+60
   while time.monotonic()<end:
    value=(await bridge.http.get(base+'/api/state')).json()
    if not value['burst']['running']:break
    await asyncio.sleep(.25)
   else:raise RuntimeError('Incident load did not finish')
  report['before']=(await bridge.http.get(base+'/api/state')).json()
  await bridge.investigate()
  end=time.monotonic()+args.timeout
  last=None
  while time.monotonic()<end:
   current=tuple((a['role'],a['status'],a['modelCalls']) for a in bridge.state['agents'])
   if current!=last:
    print(json.dumps({'agents':current,'messages':len(bridge.state['messages']),'reviews':len(bridge.state['proposals'])}),flush=True);last=current
   pending=any(p['status'] in {'pending','approving'} for p in bridge.state['proposals'])
   active=any(a['status']=='thinking' for a in bridge.state['agents']) or any(not q.empty() for q in bridge.queues.values())
   if bridge.state['status']=='complete' and not active and not pending:break
   if bridge.state['status']=='error' and not active and not pending:break
   await asyncio.sleep(.5)
  report['after']=(await bridge.http.get(base+'/api/state')).json()
  report['coordination']=bridge.state
  report['checks']={
   'both_owner_operations_executed':all(any(p['role']==r and p['kind']=='operation' and p['status']=='executed' for p in bridge.state['proposals']) for r in ('teamchat','harborcloud')),
   'both_roles_live_model_calls':all(any(row['type']=='live_model_decision' and row['metadata'].get('live') for row in bridge.history[r]) for r in ('teamchat','harborcloud')),
   'all_releases_actual_switch':all(m['receipt']['shared_switch_message_id'].startswith('sw_') and m['receipt']['approval_switch_message_id'].startswith('sw_') for m in bridge.state['messages']) and len(bridge.state['messages'])>=3,
   'all_approvals_test_label':all(p.get('approvalMode')=='test_operator' for p in bridge.state['proposals'] if p.get('receipt')),
   'both_roles_closed':all(a['status']=='complete' for a in bridge.state['agents']),
   'engine_measured_recovery':report['after'].get('health',{}).get('successRate')==1 and report['after'].get('health',{}).get('status')=='healthy',
   'room_scope_checks':bridge.state['accessChecks']['passed']}
  # Bind every published receipt to our persisted actual observer event.
  with sqlite3.connect(bridge.relay.db_path) as db:
   report['checks']['receipts_match_captured_events']=all(db.execute('SELECT COUNT(*) FROM events WHERE message_id=?',(m['receipt']['shared_switch_message_id'],)).fetchone()[0]>0 and db.execute('SELECT COUNT(*) FROM events WHERE message_id=?',(m['receipt']['approval_switch_message_id'],)).fetchone()[0]>0 for m in bridge.state['messages'])
  report['passed']=all(report['checks'].values());bridge.safe(report)
  output=bridge.directory/'live-verification.json';output.write_text(json.dumps(report,indent=2,ensure_ascii=False))
  print(json.dumps({'passed':report['passed'],'checks':report['checks'],'artifact':str(output)}),flush=True)
  return report['passed']
 finally:await bridge.close()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--engine-config',type=Path);parser.add_argument('--state-dir',type=Path);parser.add_argument('--max-calls',type=int,default=6);parser.add_argument('--timeout',type=float,default=420);parser.add_argument('--no-burst',action='store_true');args=parser.parse_args()
 raise SystemExit(0 if asyncio.run(run(args)) else 1)
if __name__=='__main__':main()
