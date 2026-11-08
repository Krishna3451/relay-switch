"""Join the preferred light opening to the verified native Mattermost demo."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'demo/final-v2'
DELIVERY = OUT / 'delivery'
FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'
FPS = 24
RATE = 48000
OPENING_FRAMES = 860
DEMO_CUT_FRAME = 1272  # 53.000s, after old introductory dissolve; Maya starts53.184s.
DEMO_END_FRAME = 3732
OPENING_DURATION = OPENING_FRAMES / FPS
DEMO_CUT = DEMO_CUT_FRAME / FPS
FINAL_FRAMES = OPENING_FRAMES + DEMO_END_FRAME - DEMO_CUT_FRAME
FINAL_DURATION = FINAL_FRAMES / FPS
OFFSET = OPENING_DURATION - DEMO_CUT


def run(args):
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-1800:])
    return result.stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path):
    return json.loads(run([FFPROBE, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def read_wave(path):
    with wave.open(str(path), 'rb') as source:
        assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (RATE, 1, 2)
        return source.readframes(source.getnframes())


def seconds(value):
    h, m, s = value.replace(',', '.').split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def srt_stamp(value):
    ms = round(value * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def srt_rows(path):
    rows = []
    for block in re.split(r'\n\s*\n', path.read_text().strip()):
        lines = block.splitlines()
        start, end = lines[1].split(' --> ')
        rows.append({'start': seconds(start), 'end': seconds(end), 'text': '\n'.join(lines[2:])})
    return rows


def main():
    DELIVERY.mkdir(parents=True, exist_ok=True)
    opening = ROOT / 'demo/opening-v2/delivery/Relay-opening.mp4'
    original = ROOT / 'demo/final/Relay-demo.mp4'
    sources = [opening, original, ROOT / 'demo/opening-v2/narration.wav', ROOT / 'demo/final/narration.wav']
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    for path in [opening, original]:
        pic = next(s for s in probe(path)['streams'] if s['codec_type'] == 'video')
        assert (pic['width'], pic['height'], pic['r_frame_rate']) == (1920, 1080, '24/1')

    # Preserve exact mastered PCM samples. Only28.146ms of alignment silence is
    # added at the join, and19.167ms after the unchanged original ending.
    first_pcm = read_wave(sources[2])
    original_pcm = read_wave(sources[3])
    first_samples = len(first_pcm) // 2
    join_sample = OPENING_FRAMES * RATE // FPS
    cut_sample = DEMO_CUT_FRAME * RATE // FPS
    final_samples = FINAL_FRAMES * RATE // FPS
    first_pad = join_sample - first_samples
    assert first_pad >= 0
    retained_pcm = original_pcm[cut_sample * 2:]
    combined = first_pcm + bytes(first_pad * 2) + retained_pcm
    end_pad = final_samples - len(combined) // 2
    assert end_pad >= 0
    combined += bytes(end_pad * 2)
    master = OUT / 'narration-combined.wav'
    with wave.open(str(master), 'wb') as target:
        target.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        target.writeframes(combined)
    assert combined[:len(first_pcm)] == first_pcm
    assert combined[join_sample * 2:join_sample * 2 + len(retained_pcm)] == retained_pcm

    captions = srt_rows(ROOT / 'demo/opening-v2/delivery/Relay-opening.srt')
    source_captions = srt_rows(ROOT / 'demo/final/Relay-demo.srt')
    for row in source_captions:
        if row['end'] <= DEMO_CUT:
            continue
        assert row['start'] >= DEMO_CUT, 'A source caption crosses the proposed cut'
        captions.append({**row, 'start': row['start'] + OFFSET, 'end': row['end'] + OFFSET})
    assert all(row['end'] > row['start'] >= 0 and row['end'] <= FINAL_DURATION for row in captions)
    assert all(a['end'] <= b['start'] for a, b in zip(captions, captions[1:]))
    caption_path = DELIVERY / 'Relay-final.srt'
    caption_path.write_text('\n\n'.join(f"{i}\n{srt_stamp(r['start'])} --> {srt_stamp(r['end'])}\n{r['text']}" for i, r in enumerate(captions, 1)) + '\n')

    timing = json.loads((ROOT / 'demo/final/beat-timing.json').read_text())
    demo_beats = [b for b in timing['beats'] if b['spokenStart'] >= DEMO_CUT]
    narration = (ROOT / 'demo/opening-v2/narration-script.txt').read_text().strip() + '\n\n' + '\n\n'.join(b['text'] for b in demo_beats) + '\n'
    (DELIVERY / 'narration-script.txt').write_text(narration)
    video = DELIVERY / 'Relay-final.mp4'
    filters = (f'[0:v]trim=start_frame=0:end_frame={OPENING_FRAMES},setpts=PTS-STARTPTS,setsar=1[v0];'
               f'[1:v]trim=start_frame={DEMO_CUT_FRAME}:end_frame={DEMO_END_FRAME},setpts=PTS-STARTPTS,setsar=1[v1];'
               '[v0][v1]concat=n=2:v=1:a=0[v]')
    encode = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-filter_complex_threads', '1',
              '-i', str(opening), '-i', str(original), '-i', str(master), '-i', str(caption_path),
              '-filter_complex', filters, '-map', '[v]', '-map', '2:a:0', '-map', '3:s:0',
              '-frames:v', str(FINAL_FRAMES), '-t', f'{FINAL_DURATION:.9f}', '-r', str(FPS),
              '-c:v', 'libx264', '-preset', 'fast', '-crf', '16', '-threads', '4', '-pix_fmt', 'yuv420p',
              '-c:a', 'aac', '-b:a', '192k', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng',
              '-disposition:s:0', '0', '-movflags', '+faststart', str(video)]
    run(encode)
    final_probe = probe(video)
    decode = [FFMPEG, '-v', 'error', '-i', str(video), '-f', 'null', '-']
    run(decode)
    checks = {'correct_preferred_light_opening': 'opening-v2' in str(opening),
              'cut_after_old_intro_and_before_maya_speech': DEMO_CUT == 53.0 and DEMO_CUT < 53.184,
              'source_files_unchanged': all(sha(ROOT / p) == h for p, h in source_hashes.items()),
              'opening_pcm_exact': combined[:len(first_pcm)] == first_pcm,
              'retained_demo_pcm_exact': combined[join_sample * 2:join_sample * 2 + len(retained_pcm)] == retained_pcm,
              'sample_aligned_join': join_sample == 1720000 and len(combined) // 2 == final_samples,
              'caption_timeline_valid': len(captions) == 38,
              'duration_valid': abs(float(final_probe['format']['duration']) - FINAL_DURATION) < .05,
              'full_decode_passed': True}
    report = {'passed': all(checks.values()), 'checks': checks, 'video': str(video.relative_to(ROOT)),
              'video_sha256': sha(video), 'duration_seconds': FINAL_DURATION, 'fps': FPS, 'dimensions': [1920, 1080],
              'source_hashes': source_hashes, 'splice': {'opening_seconds': OPENING_DURATION, 'original_demo_start_seconds': DEMO_CUT,
                  'original_demo_end_seconds': DEMO_END_FRAME / FPS, 'demo_timeline_offset_seconds': OFFSET,
                  'join_kind': 'Clean picture cut; alignment silence only; no extra dissolve or voice overlap'},
              'audio': {'master': str(master.relative_to(ROOT)), 'master_sha256': sha(master), 'rate': RATE,
                  'samples': final_samples, 'opening_padding_samples': first_pad, 'ending_padding_samples': end_pad,
                  'tempo_factor': 1.0, 'new_speech_requests': 0, 'mastering_changed': False},
              'caption_count': len(captions), 'script_words': len(narration.split()), 'ffprobe': final_probe,
              'full_decode': {'command': decode, 'exit_code': 0},
              'provenance': 'Preferred light editorial opening followed by original verified native take03 demo, with its chronology unchanged.'}
    (OUT / 'assembly-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    (DELIVERY / 'README.txt').write_text(
        'RELAY — FINAL STITCHED DEMO\n\n'
        '2 minutes 18 seconds, 1920×1080 landscape, 24 fps.\n'
        'The preferred light 35.8-second opening is followed directly by Maya’s report in the original Mattermost demo.\n'
        'The repeated original introduction is removed. Narration words and pace are unchanged; no new speech was generated.\n'
        'English captions are embedded and provided as a sidecar SRT.\n'
        'Fictional companies and scripted presenter approvals; actual scoped agents, Switch events and local recovery checks in the original native recording.\n'
        'The opening uses labelled editorial illustrations. The demo preserves its actual recorded results and earlier reading holds/idle-wait edits.\n')
    if not report['passed']:
        raise ValueError('Final assembly check failed')
    print(json.dumps({'passed': True, 'video': str(video), 'duration': FINAL_DURATION, 'caption_count': len(captions)}, indent=2))


if __name__ == '__main__':
    main()
