"""Provision independent fictional identities; never alter another project."""
import argparse
import json
from pathlib import Path
import secrets
import time
from .native_setup import _API, _NATIVE, _env, _metadata, _save, BootstrapError


def setup(state_dir: Path) -> dict:
    state_dir = Path(state_dir)
    path = state_dir / 'config.json'
    if path.exists():
        return json.loads(path.read_text())
    ports = json.loads((_NATIVE / 'ports.json').read_text())
    env = _env(_NATIVE / 'native/run/switch-core.env')
    bridge = _metadata('bridge')
    switch = 'http://127.0.0.1:' + str(ports['api'])
    mattermost = 'http://127.0.0.1:' + str(ports['mattermost'])
    checkpoint = state_dir / 'provisioning.json'
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {
        'run_id': secrets.token_hex(3), 'owners': {}, 'agents': {}, 'humans': {}, 'rooms': {}}
    admin, mm = _API(switch), _API(mattermost)
    owners = {}
    try:
        admin.gateway_login(env['GATEWAY_ADMIN_EMAIL'], env['GATEWAY_ADMIN_PASSWORD'])
        connection = bridge['connection_config']
        mm.mm_login(connection['admin_user'], connection['admin_password'])
        team = mm.json('GET', '/api/v4/teams/name/' + connection['team_name'])
        for key, label in [('customer','Customer assistant'), ('provider','Provider assistant'), ('clerk','Incident recorder')]:
            if key not in state['owners']:
                state['owners'][key] = {'name': 'RELAY ' + label,
                    'email': f"relay-incident-{state['run_id']}-{key}@demo.invalid", 'password': secrets.token_urlsafe(28)}
                _save(checkpoint, state)
            owner = state['owners'][key]
            if 'id' not in owner:
                admin.call('POST','/gateway/users', {**owner,'role':'user'}, allow=(409,))
            api = _API(switch); owners[key] = api
            owner['id'] = api.gateway_login(owner['email'], owner['password'])['id']
            _save(checkpoint,state)
            if key not in state['agents']:
                state['agents'][key] = api.json('POST','/gateway/agents/register-other', {
                    'name': f"relay-incident-{state['run_id']}-{key}", 'display_name': 'RELAY · ' + label,
                    'description': 'Fictional support experiment. Scoped application identity.', 'overwrite': False})
                _save(checkpoint,state)
        # A capped local Mattermost team can reuse only explicitly supplied fictional reviewers.
        reviewer_scope = state_dir / 'reviewer-scope.json'
        if reviewer_scope.exists():
            reviewers = json.loads(reviewer_scope.read_text())
            if set(reviewers) != {'customer','provider'}: raise BootstrapError('Invalid reviewer scope.')
            state['humans'] = reviewers
            _save(checkpoint,state)
        for key,label in [('customer','Fictional customer approver'),('provider','Fictional provider approver')]:
            if key not in state['humans']:
                state['humans'][key] = {'username': f"relay-{key}-{state['run_id']}",
                    'email': f"relay-{state['run_id']}-{key}@demo.invalid", 'password': secrets.token_urlsafe(26)}
                _save(checkpoint,state)
            h = state['humans'][key]
            if 'id' not in h:
                h['id'] = mm.json('POST','/api/v4/users', {**h,'first_name':label})['id']
                _save(checkpoint,state)
            r = mm.call('GET', f"/api/v4/teams/{team['id']}/members/{h['id']}", allow=(404,))
            if r.status_code == 404:
                mm.json('POST',f"/api/v4/teams/{team['id']}/members", {'team_id':team['id'],'user_id':h['id']})
            user_api = _API(mattermost)
            try:
                user,h['token'] = user_api.mm_login(h['username'],h['password'])
                if user['id'] != h['id']: raise BootstrapError('Human binding changed.')
            finally: user_api.close()
            _save(checkpoint,state)
        for key,label in [('customer','Customer private'),('provider','Provider private'),('shared','Shared evidence')]:
            if key not in state['rooms']:
                agent_keys = [key] if key != 'shared' else ['customer','provider','clerk']
                human_keys = [key] if key != 'shared' else ['customer','provider']
                state['rooms'][key] = owners[key if key != 'shared' else 'clerk'].json('POST','/gateway/rooms',{
                    'name': f"RELAY · {label} · {state['run_id']}",
                    'description': 'Independent fictional support experiment; explicit owner approval required.',
                    'channel_type':'channel_private','read_visibility':'private','write_visibility':'private',
                    'bridge_id':bridge['bridge_id'],
                    'agent_ids':[state['agents'][k]['id'] for k in agent_keys],
                    'user_names':[state['humans'][k]['username'] for k in human_keys]})
                _save(checkpoint,state)
            room = state['rooms'][key]
            if any(room[k]!='private' for k in ['read_visibility','write_visibility']) or room['channel_type']!='channel_private':
                raise BootstrapError('Room privacy check failed.')
            if mm.json('GET','/api/v4/channels/'+room['external_channel_id'])['type']!='P':
                raise BootstrapError('Mattermost room privacy check failed.')
        for _ in range(40):
            bindings = _metadata('identities',bridge_id=bridge['bridge_id'],
                human_ids=[h['id'] for h in state['humans'].values()], agent_ids=[a['id'] for a in state['agents'].values()])
            if len(bindings['humans'])==2 and len(bindings['agents'])==3: break
            time.sleep(.25)
        else: raise BootstrapError('Switch identity enrollment is incomplete; rerun setup.')
        humans = {h['external_user_id']:h for h in bindings['humans']}
        agents = {a['id']:a for a in bindings['agents']}
        config = {'switch_url':switch, 'mattermost_url':mattermost, 'bridge_id':bridge['bridge_id'],
            'tenant_id':bridge['tenant_id'], 'team_name':team['name'], 'rooms':state['rooms'], 'agents':{},'humans':{}}
        for key,a in state['agents'].items():
            binding = agents[a['id']]
            if binding['owner_id']!=state['owners'][key]['id']: raise BootstrapError('Agent owner check failed.')
            config['agents'][key] = {**a,**binding}
            keys = [key,'shared'] if key!='clerk' else ['shared']
            rules=[]
            for room_key in keys:
                human_keys=[room_key] if room_key!='shared' else ['customer','provider']
                rules.append({'rooms':[state['rooms'][room_key]['id']], 'room_groups':'*',
                    'users':[humans[state['humans'][k]['id']]['external_identity_id'] for k in human_keys],
                    'agents':[other['id'] for other in state['agents'].values() if other['id']!=a['id']],
                    'owner':False,'owner_agents':False,'platform':False})
            owners[key].json('PUT',f"/gateway/agents/{a['id']}/addressing-policy",{'policy':{'rules':rules}})
        for key,h in state['humans'].items(): config['humans'][key] = {**h,**humans[h['id']]}
        _save(path,config)
        return config
    finally:
        admin.close(); mm.close()
        for api in owners.values(): api.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,default=Path(__file__).resolve().parents[1]/'agents/.runtime/switch')
    args=parser.parse_args()
    try:
        setup(args.state_dir)
    except (BootstrapError,OSError,ValueError):
        parser.exit(1,'Relay enrollment failed. Check the installed Switch Console runtime and local room/member capacity; saved partial enrollment is preserved.\n')
    print('Provisioned RELAY: 3 private rooms, 3 scoped agents, 2 fictional people. No credentials printed; approval accounts are fictional and operator-controlled.')

if __name__=='__main__':main()
