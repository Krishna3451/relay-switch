"""Assemble the approved standalone opening without changing its voice tempo."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'demo/opening-v2'
FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'


def run(args):
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-1500:])
    return result.stdout


def probe(path):
    return json.loads(run([FFPROBE, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(text):
    return ''.join(c.casefold() for c in text if c.isalnum())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--visual', type=Path, required=True)
    args = parser.parse_args()
    source = args.visual.resolve()
    script = (OUT / 'narration-script.txt').read_text()
    approved = json.loads((OUT / 'approved-script.json').read_text())
    meta = json.loads((OUT / 'narration-manifest.json').read_text())
    provider = json.loads((OUT / 'provider-alignment.json').read_text())
    alignment = provider.get('normalized_alignment') or provider['alignment']
    text_matches = signature(''.join(alignment['characters'])) == signature(script)
    if digest(OUT / 'narration-script.txt') != approved['script_sha256'] or not text_matches:
        raise ValueError('Narration does not match the approved opening')
    duration = meta['audio_seconds']
    if not 35 <= duration <= 40 or meta['voice_settings']['speed'] != 1.0:
        raise ValueError('Opening must retain approved 35–40-second native narration')
    info = probe(source)
    picture = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if (picture['width'], picture['height'], picture['r_frame_rate']) != (1920, 1080, '24/1'):
        raise ValueError('Opening visuals must be 1920×1080 at 24 fps')
    if abs(float(info['format']['duration']) - duration) > .05:
        raise ValueError('Visual duration differs from the actual voice timing')
    delivery = OUT / 'delivery'
    delivery.mkdir(exist_ok=True)
    final = delivery / 'Relay-opening.mp4'
    run([FFMPEG, '-v', 'error', '-y', '-i', str(source), '-i', str(OUT / 'narration.m4a'),
         '-i', str(OUT / 'narration.srt'), '-map', '0:v:0', '-map', '1:a:0', '-map', '2:s:0',
         '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng',
         '-disposition:s:0', '0', '-movflags', '+faststart', str(final)])
    final_info = probe(final)
    decode_command = [FFMPEG, '-v', 'error', '-i', str(final), '-f', 'null', '-']
    run(decode_command)
    aac_hashes = [hashlib.sha256(run([FFMPEG, '-v', 'error', '-i', str(path), '-map', '0:a:0',
                                    '-c:a', 'copy', '-f', 'adts', '-'])).hexdigest()
                  for path in [OUT / 'narration.m4a', final]]
    key = (ROOT / '.runtime/elevenlabs.key').read_text().strip().encode()
    for source_name, target_name in [('narration.srt', 'Relay-opening.srt'),
                                     ('narration-script.txt', 'narration-script.txt')]:
        shutil.copyfile(OUT / source_name, delivery / target_name)
    (delivery / 'README.txt').write_text(
        'RELAY — STANDALONE OPENING\n\n'
        '35.8 seconds, 1920×1080 landscape at 24 fps.\n'
        'The approved 83-word narration is unchanged, spoken by ElevenLabs Will at normal speed.\n'
        'These are animated editorial illustrations of the fictional scenario, not recorded customer app screens or new execution evidence.\n'
        'TeamChat is the messaging app for people and teams; HarborCloud is its cloud platform.\n'
        'Only the opening has been produced here. The original full Mattermost demo remains separate.\n'
        'Optional English captions are embedded and provided as a sidecar SRT.\n')
    checks = {'approved_script_hash': digest(OUT / 'narration-script.txt') == approved['script_sha256'],
              'provider_text_matches_approved_words': text_matches,
              'one_continuous_generation': meta['one_continuous_generation'],
              'normal_narration_speed': meta['voice_settings']['speed'] == 1.0 and meta['tempo_factor'] == 1.0,
              'aac_stream_unchanged': aac_hashes[0] == aac_hashes[1],
              'requested_duration': 35 <= float(final_info['format']['duration']) <= 40,
              '1080p24': (picture['width'], picture['height'], picture['r_frame_rate']) == (1920, 1080, '24/1'),
              'full_decode_passed': True,
              'private_key_absent': all(key not in p.read_bytes() for p in delivery.iterdir() if p.is_file())}
    report = {'passed': all(checks.values()), 'checks': checks, 'duration_seconds': float(final_info['format']['duration']),
              'voice_seconds': duration, 'words': approved['words'], 'voice': meta['voice_name'],
              'script_sha256': approved['script_sha256'], 'video_sha256': digest(final),
              'visual_source': str(source.relative_to(ROOT)), 'visual_source_sha256': digest(source),
              'full_decode': {'command': decode_command, 'exit_code': 0},
              'audio_adts_sha256': aac_hashes[0], 'ffprobe': final_info,
              'disclosure': 'Animated editorial opening. Not a new native-service execution or reconstructed Mattermost UI.'}
    (OUT / 'assembly-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['passed']:
        raise ValueError('Opening assembly checks did not all pass')
    print(json.dumps({'passed': True, 'video': str(final), 'duration': report['duration_seconds']}))


if __name__ == '__main__':
    main()
