#!/usr/bin/env python3
"""Export an allowlisted public Relay tree; never copy local enrollment state."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
CODE_SUFFIXES = {'.py', '.sh', '.mjs', '.js', '.swift', '.html', '.css', '.svg', '.md'}
SKIP_PARTS = {'.runtime', '.git', '.venv', '__pycache__', 'node_modules'}
METRIC_KEYS = {'status', 'testedAt', 'attempted', 'delivered', 'successRate',
               'p95LatencyMs', 'durationMs', 'concurrency', 'sloMs'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def clean(value):
    if isinstance(value, str):
        return value.replace(str(ROOT) + '/', '').replace(str(ROOT), '.')
    if isinstance(value, dict):
        return {clean(k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def metrics(value):
    if isinstance(value.get('health'), dict):
        value = value['health']
    return {k: v for k, v in value.items() if k in METRIC_KEYS}


def summary(path):
    original = path.read_bytes()
    source = json.loads(original)
    if source.get('publication', {}).get('kind') == 'sanitized-public-summary':
        return clean(source)
    if path.name == 'native-verification.json':
        keep = ['passed', 'checks', 'participation', 'modelCalls', 'distinctThreads',
                'summedInferenceSeconds', 'actualReleases', 'nativeSourceReplies', 'sourceHashes']
        public = {k: source[k] for k in keep if k in source}
        for key in ['before', 'partial', 'appRecovery', 'final']:
            public[key] = metrics(source.get(key, {}))
        public['gatewayCanary'] = {k: v for k, v in source.get('gatewayCanary', {}).items()
                                   if k in {'status', 'testedAt', 'concurrency', 'attempted', 'succeeded', 'scope'}}
        public['retry'] = {k: v for k, v in source.get('retry', {}).items()
                           if k in {'originalFailed', 'delivered', 'persistedRows', 'sameIdAndBody'}}
        responses = source.get('retry', {}).get('responses', [])
        public['retry']['repeatedRequestRecognizedAsDuplicate'] = bool(responses and responses[-1].get('duplicate'))
        omitted = ['native and coordination transcripts', 'account/room/source-post/message IDs',
                   'private room URLs', 'individual HTTP response rows', 'token usage metadata']
    elif path.name == 'causal-proof.json':
        public = {k: source[k] for k in ['createdAt', 'mechanism', 'fixedWorkload', 'allPassed'] if k in source}
        public['arms'] = [{'arm': arm['arm'], 'measurement': metrics(arm.get('measurement', {})),
                           'assertion': arm['assertion']} for arm in source.get('arms', [])]
        omitted = ['individual message/allocation IDs and rows', 'raw diagnostic snapshots', 'operation receipts']
    elif path.name == 'live-audit.json':
        keep = ['passed', 'modelCalls', 'perRole', 'distinctCliThreads', 'summedInferenceSeconds',
                'actualSwitchReleases', 'ownerOperations', 'disclosures', 'approvalMode', 'sourceHashes', 'secretScan']
        public = {k: source[k] for k in keep if k in source}
        for key in ['beforeHealth', 'afterHealth']:
            public[key] = metrics(source.get(key, {}))
        omitted = ['individual CLI thread records', 'private archive paths', 'account/team identifiers',
                   'setup/previous-run transcripts', 'token usage metadata']
    elif path.name == 'live-verification.json':
        public = {k: source[k] for k in ['at', 'mode', 'model', 'transport', 'approval', 'checks', 'passed'] if k in source}
        for key in ['before', 'after']:
            public[key] = metrics(source.get(key, {}))
        omitted = ['coordination transcripts, source identities and message rows']
    else:
        return clean(source)
    public['publication'] = {'kind': 'sanitized-public-summary',
                             'original_artifact_sha256': sha(original),
                             'omitted': omitted,
                             'note': 'Recorded aggregate outcomes are unchanged. The original private artifact is retained locally; this summary is not an independent attestation.'}
    return clean(public)


def verification_markdown(demo_dir):
    movies = sorted((ROOT / demo_dir / 'delivery').glob('*.mp4'))
    if len(movies) != 1:
        raise ValueError('Selected demo delivery must contain exactly one final MP4')
    movie = movies[0].relative_to(ROOT)
    return f'''# Recorded local verification

These are bounded synthetic local checks, not a production deployment or a
support-speed comparison. The selected final video is
[final Relay video](../{movie}) (1080p24).

The recorded native run used 12 live model calls in separate company histories,
six reviewed Switch releases and nine original enrolled-account source posts.
All eleven native audit checks passed. Its fixed app workload was 24 actual HTTP
requests at concurrency 12 with a 1,100 ms p95 target.

| Recorded stage | Cloud check | App delivery | App p95 |
|---|---:|---:|---:|
| Incident | Unrepaired | 13/24 | 781.03 ms |
| Cloud recovery | 6/6 | 15/24 | 823.19 ms |
| App recovery, before retry | Already verified | 24/24 | 355.58 ms |
| Closing check, after retry | Already verified | 24/24 | 341.11 ms |

The originally failed message was retried with its unchanged ID/body/author.
The repeated identical request was recognized as a duplicate and exactly one
message row was persisted. The video retains cloud recovery → app recovery →
original-message retry → closing-check order.

The separate four-arm causal check delivered 14/24 with neither repair, app-only
repair or cloud-only repair, and 24/24 after both repairs. It tests actual local
HTTP contention/readiness and logical serving allocations, not EC2 or packet loss.

The reviewer accounts belong to a fictional scenario controlled by one presenter.
Their replies are scripted presenter inputs; the underlying scoped agents,
Switch events, approval checks and workload execution were real. Separate model
contexts/API credentials do not provide OS isolation from trusted host admins.
A central agent granted equivalent access remains a valid alternative.

- [Native aggregate evidence](native-verification.json)
- [Four-arm causal evidence](causal-proof.json)
- [Earlier web-bridge aggregate audit](live-audit.json)
- [Final assembly checks](../{demo_dir}/assembly-manifest.json)
- [Final join/content review](../{demo_dir}/qa/review-report.json)
- [Publication omissions and prerequisites](../SUBMISSION-NOTES.md)

Public JSON files explicitly state sanitization and preserve original artifact
hashes. Private transport transcripts, actor/room/source IDs, session data and
multi-gigabyte raw frames are omitted. The selected film and its QA checkpoints
remain available. The recorded source hashes describe the historical run; later
submission cleanup must not be described as a new live verification.
'''


def known_secrets():
    values = set()
    names = {'api_key', 'password', 'token', 'readToken', 'applyToken', 'internal_token',
             'access_token', 'refresh_token', 'client_secret'}
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in names and isinstance(item, str) and len(item) > 12:
                    values.add(item.encode())
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    for pattern in ['**/.runtime/**/config.json', '**/.runtime/**/provisioning.json',
                    '**/.runtime/**/browser-session.json', '**/.runtime/**/engine.json',
                    '**/.runtime/**/*oauth*.json', '**/.runtime/**/*token*.json',
                    '**/.runtime/**/*credentials*.json']:
        for path in ROOT.glob(pattern):
            try:
                visit(json.loads(path.read_text()))
            except (OSError, ValueError):
                pass
    for path in ROOT.glob('**/.runtime/**/*.key'):
        value = path.read_bytes().strip()
        if len(value) > 12:
            values.add(value)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--demo-dir', type=Path, default=Path('demo/final-v3'),
                        help='Selected final video edition; only its curated delivery/QA is exported')
    parser.add_argument('--refresh', action='store_true', help='Refresh only a previously generated export')
    args = parser.parse_args()
    target = args.output.resolve()
    demo_dir = (ROOT / args.demo_dir).resolve().relative_to(ROOT)
    if target == ROOT or ROOT in target.parents:
        raise ValueError('Use a staging directory outside the source tree')
    marker = target / 'PUBLIC-EXPORT.json'
    if target.exists() and any(target.iterdir()) and not (args.refresh and marker.is_file()):
        raise ValueError('Nonempty destination is not an explicitly refreshed public export')
    previous = json.loads(marker.read_text()).get('files', {}) if marker.exists() else {}
    paths = set()
    for name in ['README.md', 'SUBMISSION-NOTES.md', 'requirements.txt', 'requirements-lock.txt', 'package.json', '.gitignore',
                 'LICENSE', 'LICENSE.md', 'NOTICE', 'pyproject.toml']:
        if (ROOT / name).is_file():
            paths.add(Path(name))
    for folder in ['engine', 'agents', 'tests', 'tests_agents', 'scripts', 'web', 'docs', '.github']:
        if not (ROOT / folder).exists():
            continue
        for source in (ROOT / folder).rglob('*'):
            relative = source.relative_to(ROOT)
            if source.is_file() and not (set(relative.parts) & SKIP_PARTS):
                is_doc_asset = folder == 'docs' and (
                    source.suffix in {'.png', '.mp4', '.vtt', '.woff2', '.ico'}
                    or source.name == '.nojekyll'
                )
                is_workflow = folder == '.github' and source.suffix in {'.yml', '.yaml'}
                if source.suffix in CODE_SUFFIXES or source.name.startswith('run-') or is_doc_asset or is_workflow:
                    paths.add(relative)
    for source in (ROOT / demo_dir / 'delivery').glob('*'):
        if source.suffix in {'.mp4', '.srt', '.txt', '.json'}:
            paths.add(source.relative_to(ROOT))
    for source in (ROOT / demo_dir / 'qa').glob('*'):
        if source.suffix in {'.png', '.json'}:
            paths.add(source.relative_to(ROOT))
    paths.add(demo_dir / 'assembly-manifest.json')
    for name in ['mattermost-script-v3.txt', 'mattermost-live-flow-v3.txt']:
        paths.add(Path('demo') / name)
    for variant in ['opening-v2', 'opening-v3', 'opening-v4']:
        for name in ['voice-cues.json', 'narration-script.txt']:
            if (ROOT / 'demo' / variant / name).exists():
                paths.add(Path('demo') / variant / name)
    evidence = ['causal-proof.json', 'native-verification.json', 'live-verification.json',
                'live-audit.json', 'native-profile-restoration.json', 'submission-audit.json',
                'submission-causal-proof.json']
    paths.update(Path('evidence') / name for name in evidence)
    generated = {'evidence/VERIFICATION.md': verification_markdown(demo_dir).encode()}
    for relative in paths:
        source = ROOT / relative
        source.resolve().relative_to(ROOT)
        if source.is_symlink():
            raise ValueError('Public export refuses source symlinks: ' + str(relative))
        if source.suffix == '.json':
            original = json.loads(source.read_text())
            value = summary(source) if relative.parent == Path('evidence') else clean(original)
            if value == original:
                generated[str(relative)] = source.read_bytes()
            else:
                if 'publication' not in value:
                    value['publication'] = {'kind': 'public-copy', 'original_artifact_sha256': sha(source.read_bytes()),
                                            'transformations': ['Absolute operator workspace paths replaced with repository-relative paths.'],
                                            'note': 'Historical source-file hashes refer to the original artifacts; no measurement or media content changed.'}
                generated[str(relative)] = (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()
        else:
            generated[str(relative)] = source.read_bytes()
    secrets = known_secrets()
    patterns = [re.compile(rb'sk_[a-f0-9]{32,}'), re.compile(rb'sk-proj-[A-Za-z0-9_-]{20,}'),
                re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'), re.compile(rb'github_pat_[A-Za-z0-9_]{30,}'),
                re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
    failures = []
    for name, data in generated.items():
        if any(secret in data for secret in secrets) or any(pattern.search(data) for pattern in patterns):
            failures.append(name)
        if re.search(rb'/Users/[^/\s]+/(?:Documents|Desktop|Downloads)/', data):
            failures.append(name + ' (absolute user path)')
    if failures:
        raise ValueError('Public export scan refused files: ' + ', '.join(sorted(set(failures))))
    target.mkdir(parents=True, exist_ok=True)
    for name in previous.keys() - generated.keys():
        old = target / name
        old.resolve().relative_to(target)
        if old.is_file() and sha(old.read_bytes()) == previous[name]['sha256']:
            old.unlink()
        elif old.exists():
            raise ValueError('Refusing to remove a changed stale export file: ' + name)
    for name, data in generated.items():
        destination = target / name
        destination.resolve().relative_to(target)
        if destination.is_symlink():
            raise ValueError('Public export refuses destination symlinks: ' + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        source = ROOT / name
        if source.exists() and source.stat().st_mode & 0o111:
            destination.chmod(0o755)
    report = {'kind': 'allowlisted-public-source-export', 'files': {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in sorted(generated.items())},
              'file_count': len(generated), 'known_secret_values_checked': len(secrets),
              'known_secret_occurrences': 0, 'credential_pattern_occurrences': 0,
              'raw_runtime_and_frames_excluded': True,
              'sanitized_evidence': [str(Path('evidence') / name) for name in evidence if name in {'causal-proof.json', 'native-verification.json', 'live-verification.json', 'live-audit.json'}]}
    marker.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(target), 'files': len(generated), 'bytes': sum(map(len, generated.values())),
                      'known_secret_occurrences': 0, 'credential_pattern_occurrences': 0}))


if __name__ == '__main__':
    main()
