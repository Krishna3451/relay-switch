"""Bind the revised privacy narrative to genuine take03 source windows."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'demo/final-v3'
CAPTURE = ROOT / 'recording/native-take-03'
FPS = 24


def signature(text):
    return ''.join(c.casefold() for c in text if c.isalnum())


def main():
    provider = json.loads((OUT / 'provider-alignment.json').read_text())
    alignment = provider.get('normalized_alignment') or provider['alignment']
    chars, starts = alignment['characters'], alignment['character_start_times_seconds']
    mapped, indices = [], []
    for index, char in enumerate(chars):
        for letter in char.casefold():
            if letter.isalnum():
                mapped.append(letter)
                indices.append(index)
    normalized = ''.join(mapped)
    anchors = {
        'hook': 'You send an important message',
        'companies': 'TeamChat is a messaging app',
        'privacy': 'But their logs can contain',
        'manual': 'Engineers must pick out what is safe to share',
        'relay': 'Relay connects their agents through Switch',
        'own': 'Each investigates its own systems',
        'shareControl': 'Only owner-approved findings reach',
        'changeControl': 'Each company approves changes',
        'outcome': 'Then both teams test what customers care about',
        'transition': 'Here’s how',
        'report': 'Maya reports the problem in the shared Mattermost',
        'leoPresence': 'Leo, HarborCloud’s engineer, confirms',
        'diagnose': 'TeamChat’s agent checks its own service',
        'privateContext': 'Its detailed diagnostic observations stay',
        'approveShare': 'Maya reviews that finding',
        'sharedQuestion': 'The exact approved text arrives',
        'cloudPlan': 'It finds the overload',
        'cloudApprove': 'Leo reviews the change',
        'partial': 'HarborCloud’s connection is healthy',
        'appPlan': 'It proposes recovering the failed parts',
        'appApprove': 'Maya reviews and approves the change',
        'appResult': 'The agent performs the recovery',
        'appShared': 'Its reviewed result returns',
        'test': 'Run the same delivery test again',
        'retry': 'Maya asks the agent to retry',
        'retryResult': 'The same message arrives',
        'ending': 'Both teams controlled what was shared',
        'endingResult': 'The incident thread records their findings',
        'closing': 'Relay. Two teams. One recovery',
    }
    cues = {}
    for name, anchor in anchors.items():
        needle = signature(anchor)
        first = normalized.find(needle)
        if first < 0 or normalized.find(needle, first + 1) >= 0:
            raise ValueError('Missing or ambiguous voice anchor: ' + name)
        cues[name] = starts[indices[first]]
    duration = json.loads((OUT / 'narration-manifest.json').read_text())['audio_seconds']
    cues['end'] = duration
    if list(cues.values()) != sorted(cues.values()):
        raise ValueError('Narration cue order changed')
    frame_count = round(duration * FPS)
    streams = {name: json.loads((CAPTURE / name / 'frames.json').read_text())
               for name in ('shared', 'teamchat', 'harborcloud')}
    source_hashes = {}
    clips = []

    def native(key, until, stream, window, mode, label):
        first, last = window
        rows = [r for r in streams[stream] if first <= r['at'] <= last]
        if not rows:
            raise ValueError('Missing reviewed native source window')
        begin = round(cues[key] * FPS) if key != 'report' else round(cues['report'] * FPS)
        end = round(cues[until] * FPS)
        # Hold after the retained source window; never accelerate recorded arrivals.
        needed = (rows[-1]['at'] - rows[0]['at']) / 1000
        if end - begin < needed * FPS - 1:
            raise ValueError('New narration is too short for actual source cadence: ' + key)
        frames = []
        for row in rows:
            path = CAPTURE / stream / row['file']
            relative = str(path.relative_to(ROOT))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != row['sha256']:
                raise ValueError('Original native capture changed')
            source_hashes[relative] = digest
            frames.append({'path': relative, 'offset': (row['at'] - rows[0]['at']) / 1000})
        clips.append({'start': begin / FPS, 'end': end / FPS, 'mode': mode,
                      'stream': stream, 'label': label, 'frames': frames,
                      'sourceWindow': [first, last]})

    native('report', 'leoPresence', 'shared', (1794102852200, 1794102855200), 'wide', 'Shared incident · Maya reports the failure')
    native('leoPresence', 'diagnose', 'shared', (1794102870750, 1794102873500), 'wide', 'Shared incident · both teams are present')
    native('diagnose', 'privateContext', 'teamchat', (1794102879500, 1794102881200), 'diagnosis', 'TeamChat · private workroom')
    native('privateContext', 'approveShare', 'teamchat', (1794102879500, 1794102881200), 'private-context', 'TeamChat · private diagnostic context')
    native('approveShare', 'sharedQuestion', 'teamchat', (1794102880600, 1794102883700), 'approve-share', 'Maya approves the reviewed finding')
    native('sharedQuestion', 'cloudPlan', 'shared', (1794102881600, 1794102885300), 'trace-share', 'Shared incident · the same approved finding')
    native('cloudPlan', 'cloudApprove', 'harborcloud', (1794102901100, 1794102903800), 'cloud-plan', 'HarborCloud · private owner review')
    native('cloudApprove', 'partial', 'harborcloud', (1794102902850, 1794102905400), 'cloud-approve', 'Leo approves his company’s change')
    native('partial', 'appPlan', 'shared', (1794102924000, 1794102927300), 'partial', 'Cloud repaired · customer messages still fail')
    native('appPlan', 'appApprove', 'teamchat', (1794102942600, 1794102944900), 'app-plan', 'TeamChat · separate app recovery')
    native('appApprove', 'appResult', 'teamchat', (1794102944100, 1794102946100), 'app-approve', 'Maya approves the app change')
    native('appResult', 'appShared', 'teamchat', (1794102946100, 1794102948250), 'app-result', 'The approved app recovery runs')
    native('appShared', 'test', 'shared', (1794102964600, 1794102967700), 'app-shared', 'The reviewed app result returns through Switch')
    native('test', 'retry', 'shared', (1794102967800, 1794102970900), 'test', 'Same 24-message test · before retry')
    native('retry', 'retryResult', 'shared', (1794102982100, 1794102983700), 'retry', 'Retrying the earlier failed message')
    native('retryResult', 'ending', 'shared', (1794102983700, 1794102985900), 'retry-result', 'Original identity and text · delivered once')
    # The later closing check appears only after the retry, preserving chronology.
    native('ending', 'endingResult', 'shared', (1794102985000, 1794102987550), 'ending-control', 'Owners controlled what was shared and changed')
    native('endingResult', 'closing', 'shared', (1794103003200, 1794103005600), 'ending-result', 'Shared record · findings, approvals and verified results')
    proof = json.loads((ROOT / 'evidence/native-verification.json').read_text())
    proposal = next(p for p in proof['coordination']['proposals']
                    if p['role'] == 'teamchat' and p['body']['kind'] == 'question')
    content = proposal['body']['content']
    question = content['summary'].split('HarborCloud:', 1)[1].strip()
    actual_question = 'HarborCloud: ' + question
    comparison_private = 'recording/native-take-03/teamchat/frame-000619.jpg'
    comparison_shared = 'recording/native-take-03/shared/frame-000626.jpg'
    for name in (comparison_private, comparison_shared):
        source_hashes[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    value = {'kind': 'Revised light editorial opening + genuine native take03 with explanatory focus/highlights',
             'duration': duration, 'fps': FPS, 'frameCount': frame_count, 'cues': cues, 'clips': clips,
             'approvedFinding': content, 'exactQuestion': actual_question,
             'comparisonPrivate': comparison_private, 'comparisonShared': comparison_shared,
             'sourceHashes': source_hashes, 'nativeProofSha256': hashlib.sha256((ROOT / 'evidence/native-verification.json').read_bytes()).hexdigest(),
             'disclosure': 'Potential sensitive-record examples in opening are illustrative. The fixture uses synthetic diagnostics. The full approved finding, including the highlighted question, crosses Switch; underlying role diagnostics are not copied.'}
    (OUT / 'privacy-edit-plan.json').write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'seconds': duration, 'nativeClips': len(clips), 'nativeSourceFrames': len(source_hashes),
                      'introSeconds': cues['report'], 'exactQuestion': actual_question}))


if __name__ == '__main__':
    main()
