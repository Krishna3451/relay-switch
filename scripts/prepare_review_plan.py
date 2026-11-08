"""Reproduce the visually reviewed take03 edit; source footage is immutable."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'demo/final'
plan=json.loads((OUT/'edit-plan-proposed.json').read_text())
beats={x['id']:x for x in json.loads((OUT/'beat-timing.json').read_text())['beats']}
clips=[]
def card(n,file,start=None,end=None):
 b=beats[f'beat-{n:02d}']; clips.append(dict(beat=b['id'],section=b['section'],narration=b['text'],kind='editorial_card',file=f'cards/{file}.png',reviewed=True,**({'start':start} if start is not None else {}),**({'end':end} if end is not None else {})))
def shot(n,stream,stage,first,last,start=None,end=None,note=''):
 b=beats[f'beat-{n:02d}']; clips.append(dict(beat=b['id'],section=b['section'],narration=b['text'],kind='native_capture',stream=stream,stage=stage,reviewed=True,windows=[dict(first_at_ms=first,last_at_ms=last)],review_note=note,**({'start':start} if start is not None else {}),**({'end':end} if end is not None else {})))
card(1,'problem');card(2,'two-companies');card(3,'existing');card(4,'existing');card(5,'why')
# Establish the actual shared incident and the two real, scoped owner rooms.
shot(6,'shared','incident',1794102848500,1794102851000,end=45.8,note='Pre-incident shared-room baseline; no report shown before narration.')
shot(6,'teamchat','incident',1794102848500,1794102851000,start=45.8,end=49.0,note='Actual private TeamChat room, before the incident report.')
shot(6,'harborcloud','incident',1794102848500,1794102851000,start=49.0,note='Actual private HarborCloud room, before the incident report.')
# Report and presence are real source-bound owner posts, from their separate stages.
shot(7,'shared','incident',1794102852200,1794102855200,end=59.302,note='Maya report arrives at2852720; actual failed test card follows at2853099.')
shot(7,'shared','presence',1794102870750,1794102873500,start=59.302,note='Leo actual reply arrives at2871995; retained native cadence.')
# The acknowledgement predates Leo; this is a reading hold, not a claim that Leo starts the app investigation.
shot(8,'shared','presence',1794102872300,1794102874900,end=67.871,note='Existing TeamChat acknowledgement is readable in the shared root thread.')
shot(8,'teamchat','incident',1794102853000,1794102861350,start=67.871,note='Actual private working notice and later diagnostic question arrive in the same continuous source window.')
shot(9,'teamchat','share_question',1794102880600,1794102883700,note='Reviewed native question thread, actual Maya Share with HarborCloud reply and verified release.')
shot(10,'shared','share_question',1794102881600,1794102885300,note='Actual approved question and HarborCloud working acknowledgement arrive within171ms; no manufactured typing.')
shot(11,'harborcloud','approve_cloud',1794102901100,1794102903800,end=94.806,note='Focused private proposal before Leo replies; six-concurrent target is visible.')
shot(11,'harborcloud','approve_cloud',1794102902850,1794102905400,start=94.806,note='Actual Leo approval arrives at2904140; window ends before operation result.')
shot(12,'harborcloud','approve_cloud',1794102905600,1794102907800,end=102.956,note='Actual operation acknowledgement and6/6 vs15/24 report, no approval-only green.')
shot(12,'shared','share_cloud_result',1794102924000,1794102927300,start=102.956,note='The reviewed cloud result actually arrives at2924657; full text states cloud6/6 but fresh chat15/24.')
shot(13,'teamchat','approve_app',1794102942600,1794102944900,end=119.013,note='Actual focused TeamChat proposal names5failed starts, preserves working servers and bounded replacement.')
shot(13,'teamchat','approve_app',1794102944100,1794102946100,start=119.013,note='Actual Maya approval arrives at2945325; result not yet on screen.')
shot(14,'teamchat','approve_app',1794102946100,1794102948250,end=125.108,note='Actual recovery confirmation reports fresh24/24 before the retry stage.')
shot(14,'shared','share_app_result',1794102964600,1794102967700,start=125.108,note='Actual reviewed app recovery result arrives at2965228, before retry.')
shot(15,'shared','share_app_result',1794102967800,1794102970900,note='Read the actual pre-retry24/24 result; no later close/fresh-check frames moved earlier.')
shot(16,'shared','retry',1794102982100,1794102983700,end=142.558,note='Actual same failed-message thread and Maya Retry this message reply; source stops before retry confirmation.')
shot(16,'shared','retry',1794102983700,1794102985900,start=142.558,note='Actual confirmation at2983919: original identity/body retained, repeated request deduplicated.')
shot(17,'shared','retry',1794102985000,1794102987550,end=149.1,note='Hold the actual same-message retry confirmation; avoid the older provider draft’s generic historical-message caveat.')
shot(17,'shared','close',1794103003200,1794103005600,start=149.1,note='Separate later final check now appears honestly after retry;24/24 and latency target confirmed.')
card(18,'closing')
plan.update(status='REVIEWED_TAKE03_READY',capture_root='recording/native-take-03',markers_file='recording/native-take-03/markers.json',clips=clips,
 outcome_review=dict(verified=True,evidence_file='evidence/native-verification.json',capture_verification_file='recording/native-take-03/capture-verification.json',notes=['Native audit passed all11checks.','Cloud6/6 with fresh chat15/24 is distinct from final24/24.','AppRecovery24/24 exists before retry; the later close check is shown only after retry.','Original failed message is actually retried with unchanged ID/body and exactly one persisted row.']),
 editing_disclosure='Actual native captures only after editorial opening; selected static waits removed, source arrival cadence retained, and real frames held for reading. Fictional companies and scripted presenter inputs; actual live agents, Switch and local services.')
(OUT/'edit-plan.json').write_text(json.dumps(plan,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'reviewed_shots':len(clips),'capture':plan['capture_root'],'proof':plan['outcome_review']['evidence_file']}))
