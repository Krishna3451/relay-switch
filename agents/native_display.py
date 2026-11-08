"""Reversible display-only changes to the two fictional reviewers and observer preference."""
import json,sys
from pathlib import Path
from .native_setup import _API,_metadata,_save
ROOT=Path(__file__).resolve().parents[1]
def run(restore=False):
 directory=ROOT/'agents/.runtime/native';config=json.loads((directory/'switch/config.json').read_text());browser=json.loads((directory/'browser-session.json').read_text());bridge=_metadata('bridge',bridge_id=config['bridge_id']);mm=_API(config['mattermost_url']);c=bridge['connection_config'];mm.mm_login(c['admin_user'],c['admin_password']);path=directory/'profile-display-audit.json';audit=json.loads(path.read_text()) if path.exists() else {'users':{},'observer':{},'scope':'Display fields only for two fictional roleplay reviewers; immutable identities/credentials/permissions unchanged.'}
 try:
  for side,name,company in [('customer','Maya','TeamChat'),('provider','Leo','HarborCloud')]:
   user_id=config['humans'][side]['id'];user=mm.json('GET','/api/v4/users/'+user_id)
   if side not in audit['users']:audit['users'][side]={'userId':user_id,'before':{k:user.get(k,'') for k in ['first_name','last_name','nickname']}}
   value=audit['users'][side]['before'] if restore else {'first_name':name,'last_name':company,'nickname':name+' · '+company}
   mm.json('PUT','/api/v4/users/'+user_id+'/patch',value);audit['users'][side]['restored' if restore else 'during']=value
  oid=browser['observer']['userId'];prefs=mm.json('GET',f'/api/v4/users/{oid}/preferences')
  if not audit['observer']:audit['observer']={'userId':oid,'before':next((p for p in prefs if p['category']=='display_settings' and p['name']=='name_format'),None)}
  pref=audit['observer']['before'] if restore else {'user_id':oid,'category':'display_settings','name':'name_format','value':'nickname_full_name'}
  if pref:mm.json('PUT',f'/api/v4/users/{oid}/preferences',[pref])
  elif restore:mm.call('POST',f'/api/v4/users/{oid}/preferences/delete',[{'user_id':oid,'category':'display_settings','name':'name_format','value':'nickname_full_name'}])
  formats=audit.setdefault('roleNameFormats',{})
  for side in ('customer','provider'):
   uid=config['humans'][side]['id'];prefs=mm.json('GET',f'/api/v4/users/{uid}/preferences')
   if side not in formats:formats[side]={'userId':uid,'before':next((p for p in prefs if p['category']=='display_settings' and p['name']=='name_format'),None)}
   rolepref=formats[side]['before'] if restore else {'user_id':uid,'category':'display_settings','name':'name_format','value':'nickname_full_name'}
   if rolepref:mm.json('PUT',f'/api/v4/users/{uid}/preferences',[rolepref])
   elif restore:mm.call('POST',f'/api/v4/users/{uid}/preferences/delete',[{'user_id':uid,'category':'display_settings','name':'name_format','value':'nickname_full_name'}])
  audit['restored']=restore;_save(path,audit);print({'reviewerDisplayRestored':restore,'roleNameFormats':'nickname_full_name' if not restore else 'restored','displayOnly':True})
 finally:mm.close()
if __name__=='__main__':run('--restore' in sys.argv)
