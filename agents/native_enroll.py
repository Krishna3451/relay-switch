"""Enroll demo identities once, then create clean native rooms reusing them."""
from __future__ import annotations
import argparse,json,secrets
from pathlib import Path
from .native_setup import _API,_metadata,_save,BootstrapError
from .bootstrap import setup
ROOT=Path(__file__).resolve().parents[1]
def load_base(directory:Path,base_state_dir=None):
 base=Path(base_state_dir) if base_state_dir is not None else Path(directory).parent/'switch'
 if not (base/'config.json').exists():setup(base)
 try:
  return json.loads((base/'config.json').read_text()),json.loads((base/'provisioning.json').read_text())
 except (OSError,ValueError):
  raise BootstrapError('Base enrollment is incomplete. Preserve this state and rerun agents.bootstrap with the same --state-dir.') from None
def prepare(directory:Path,base_state_dir=None):
 directory=Path(directory);target=directory/'switch/config.json'
 if target.exists() and (directory/'browser-session.json').exists():return json.loads(target.read_text())
 config,state=load_base(directory,base_state_dir)
 bridge=_metadata('bridge',bridge_id=config['bridge_id']);connection=bridge['connection_config'];mm=_API(config['mattermost_url']);owners={}
 try:
  observer,observer_token=mm.mm_login(connection['admin_user'],connection['admin_password'])
  checkpoint=directory/'enrollment.json';saved=json.loads(checkpoint.read_text()) if checkpoint.exists() else {'tag':secrets.token_hex(3),'rooms':{}}
  for side in ('customer','provider','clerk'):
   api=_API(config['switch_url']);o=state['owners'][side];api.gateway_login(o['email'],o['password']);owners[side]=api
  labels={'customer':'TeamChat · Maya review','provider':'HarborCloud · Leo review','shared':'RELAY · Incident'}
  for side,label in labels.items():
   if side not in saved['rooms']:
    agents=[side] if side!='shared' else ['customer','provider'];humans=[side] if side!='shared' else ['customer','provider']
    room=owners[side if side!='shared' else 'clerk'].json('POST','/gateway/rooms',{
     'name':label+' · '+saved['tag'],'description':'Fictional local incident. Presenter roleplays Maya (TeamChat) and Leo (HarborCloud). Owner decisions are actual enrolled-account replies.',
     'channel_type':'channel_private','read_visibility':'private','write_visibility':'private','bridge_id':config['bridge_id'],
     'agent_ids':[config['agents'][a]['id'] for a in agents],'user_names':[config['humans'][h]['username'] for h in humans]})
    saved['rooms'][side]=room;_save(checkpoint,saved)
   room=saved['rooms'][side]
   mm.json('PUT',f"/api/v4/channels/{room['external_channel_id']}/patch",{'display_name':label,'header':'Fictional local demonstration · One presenter plays Maya and Leo · Real agents, Switch messages and service checks.'})
  native={**config,'agents':{k:v for k,v in config['agents'].items() if k in ('customer','provider')},'rooms':saved['rooms']}
  for side,name in [('customer','TeamChat Agent'),('provider','HarborCloud Agent')]:
   owners[side].json('PUT',f"/gateway/agents/{config['agents'][side]['id']}/display-name",{'display_name':name})
   rules=[]
   for roomkey in (side,'shared'):
    humans=[side] if roomkey!='shared' else ['customer','provider']
    rules.append({'rooms':[native['rooms'][roomkey]['id']],'room_groups':'*',
      'users':[config['humans'][h]['external_identity_id'] for h in humans],
      'agents':[config['agents'][a]['id'] for a in ('customer','provider') if a!=side],
      'owner':False,'owner_agents':False,'platform':False})
   owners[side].json('PUT',f"/gateway/agents/{native['agents'][side]['id']}/addressing-policy",{'policy':{'rules':rules}})
  browser_base=mm.json('GET','/api/v4/config').get('ServiceSettings',{}).get('SiteURL') or config['mattermost_url'].replace('127.0.0.1','localhost')
  urls={}
  for side,room in native['rooms'].items():
   channel=mm.json('GET','/api/v4/channels/'+room['external_channel_id']);urls[{'customer':'teamchat','provider':'harborcloud'}.get(side,side)]={'url':browser_base+'/'+config['team_name']+'/channels/'+channel['name'],'channelId':channel['id'],'switchRoomId':room['id']}
  _save(directory/'browser-session.json',{'mattermostUrl':browser_base,'observer':{'token':observer_token,'userId':observer['id']},'rooms':urls,'nativeApiBase':'http://127.0.0.1:4319','sessions':{'teamchat':{'token':config['humans']['customer']['token'],'userId':config['humans']['customer']['id']},'harborcloud':{'token':config['humans']['provider']['token'],'userId':config['humans']['provider']['id']}}})
  _save(target,native)
  return native
 finally:
  mm.close()
  for a in owners.values():a.close()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--state-dir',type=Path,default=ROOT/'agents/.runtime/native')
 p.add_argument('--base-state-dir',type=Path,help='Existing or new base enrollment; defaults to the sibling switch directory')
 args=p.parse_args()
 try:c=prepare(args.state_dir,args.base_state_dir)
 except (BootstrapError,OSError,ValueError,KeyError):
  p.exit(1,'Native enrollment failed. Check Switch Console, its Mattermost bridge and enrollment state; no saved resources were deleted.\n')
 print({'nativeRooms':len(c['rooms']),'agents':len(c['agents']),'identitiesReused':True,'humanProfilesRenamed':False})
if __name__=='__main__':main()
