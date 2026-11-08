"""Mux and verify the revised disclosure/ownership narrative against take03."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'demo/final-v3'


def run(args):
    r=subprocess.run(args,capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors='replace')[-1500:])
    return r.stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sig(text):
    return ''.join(c.casefold() for c in text if c.isalnum())


def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))


def audio_hash(path):
    return hashlib.sha256(run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c:a','copy','-f','adts','-'])).hexdigest()


def main():
    plan=json.loads((OUT/'privacy-edit-plan.json').read_text())
    approved=json.loads((OUT/'approved-script.json').read_text())
    provider=json.loads((OUT/'provider-alignment.json').read_text())
    aligned=provider.get('normalized_alignment') or provider['alignment']
    script=(OUT/'narration-script.txt').read_text()
    proof_path=ROOT/'evidence/native-verification.json'
    proof=json.loads(proof_path.read_text())
    if not proof['passed'] or sha(proof_path)!=plan['nativeProofSha256']:
        raise ValueError('Original measured native proof changed or did not pass')
    proposal=next(p for p in proof['coordination']['proposals'] if p['role']=='teamchat' and p['body']['kind']=='question')
    shared=next(m for m in proof['coordination']['messages'] if m['role']=='teamchat' and m['kind']=='question')
    same_finding=proposal['body']['content']==shared['content']==plan['approvedFinding']
    if not same_finding:
        raise ValueError('Private approved finding differs from actual shared content')
    for name,digest in plan['sourceHashes'].items():
        if sha(ROOT/name)!=digest:
            raise ValueError('Original native source frame changed')
    picture=OUT/'visuals/film-silent.mp4'
    source=probe(picture)
    video=next(s for s in source['streams'] if s['codec_type']=='video')
    if (video['width'],video['height'],video['r_frame_rate'])!=(1920,1080,'24/1'):
        raise ValueError('Expected complete1080p24 editorial/capture composition')
    if abs(float(source['format']['duration'])-plan['duration'])>.05:
        raise ValueError('Picture duration does not match the approved voice')
    delivery=OUT/'delivery';delivery.mkdir(exist_ok=True)
    target=delivery/'Relay-final.mp4'
    run(['ffmpeg','-v','error','-y','-i',str(picture),'-i',str(OUT/'narration.m4a'),'-i',str(OUT/'narration.srt'),
         '-map','0:v:0','-map','1:a:0','-map','2:s:0','-c:v','copy','-c:a','copy','-c:s','mov_text',
         '-metadata:s:s:0','language=eng','-disposition:s:0','0','-movflags','+faststart',str(target)])
    decode=['ffmpeg','-v','error','-i',str(target),'-f','null','-'];run(decode)
    audio_before=audio_hash(OUT/'narration.m4a');audio_after=audio_hash(target)
    checks={'approved_words_retained':sig(script)==sig(''.join(aligned['characters'])) and sha(OUT/'narration-script.txt')==approved['script_sha256'],
            'private_and_shared_approved_finding_exact':same_finding,
            'original_native_outcome_audit_passed':proof['passed'],
            'native_source_hashes_match':all(sha(ROOT/k)==v for k,v in plan['sourceHashes'].items()),
            'cloud_healthy_while_app_degraded':proof['gatewayCanary']['succeeded']==6 and proof['gatewayCanary']['attempted']==6 and proof['partial']['delivered']==15,
            'pre_retry_24of24':proof['appRecovery']['delivered']==24 and proof['appRecovery']['attempted']==24,
            'earlier_failed_message_recovered_once':proof['retry']['originalFailed'] and proof['retry']['delivered'] and proof['retry']['sameIdAndBody'] and proof['retry']['persistedRows']==1,
            'aac_audio_unchanged':audio_before==audio_after,'full_decode_passed':True,
            'key_patterns_absent':not re.search(rb'sk_[a-f0-9]{32,}',target.read_bytes())}
    for source_name,target_name in [('narration.srt','Relay-final.srt'),('narration-script.txt','narration-script.txt')]:
        shutil.copyfile(OUT/source_name,delivery/target_name)
    description=(
        'RELAY — REVISED FINAL DEMO\n\n'
        'Light editorial opening explains why raw logs need review, then actual native Mattermost recordings show owner-approved collaboration.\n'
        'The full approved 330-word narration is one continuous ElevenLabs Will generation at normal speed.\n'
        'The full 367-character finding, including its highlighted question and cited incident references, is what crosses Switch. The underlying detailed agent observation is not copied.\n'
        'Possible customer/private-record examples in the opening are illustrative. The recorded local fixture uses synthetic diagnostics and contains no real customer records.\n'
        'Source crops, matching-question boxes and measured result labels are editorial annotations of actual captured posts. The private/shared comparison shows successive recorded moments, not a live side-by-side app.\n'
        'The original verified native take03 is reused. No new native posts, service run or agent execution was generated for this edit.\n'
        'Fictional companies; scripted presenter inputs through enrolled human accounts; actual scoped models, Switch transport and local HTTP services in the original run. The trusted localhost host/presenter can access both sides; this is not cryptographic or OS isolation and does not demonstrate automatic PII redaction.\n'
        'The recorded sequence remains: cloud 6/6 with app 15/24, separately approved app recovery 24/24 before retry, original-ID/body retry delivered once, then a later closing check.\n')
    (delivery/'README.txt').write_text(description)
    report={'passed':all(checks.values()),'checks':checks,'video':str(target.relative_to(ROOT)),
            'video_sha256':sha(target),'duration_seconds':float(probe(target)['format']['duration']),
            'voice_seconds':plan['duration'],'fps':24,'dimensions':[1920,1080],
            'native_source_frames':len(plan['sourceHashes']),'native_source_hashes':plan['sourceHashes'],
            'script_sha256':approved['script_sha256'],'exact_approved_finding':plan['approvedFinding'],
            'exact_highlighted_question':plan['exactQuestion'],'continuous_aac_sha256':audio_before,
            'full_decode':{'command':decode,'exit_code':0},'scope_disclosure':plan['disclosure']}
    (OUT/'assembly-checks.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    (OUT/'assembly-manifest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    if not report['passed']:
        raise ValueError('Not all revised film checks passed')
    print(json.dumps({'passed':True,'video':str(target),'seconds':report['duration_seconds'],'checks':checks}))


if __name__=='__main__':main()
