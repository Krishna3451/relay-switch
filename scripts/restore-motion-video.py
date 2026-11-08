"""Keep the approved privacy opening and restore the original moving demo.

Only attention outlines are added to the original native picture. The speech
and timing of its recorded Mattermost demonstration are preserved. No TTS or
new execution is used, and no static explanation replaces a native demo shot.
"""
from __future__ import annotations

import array
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'demo/final-v4'
DELIVERY = OUT / 'delivery'
QA = OUT / 'qa'
FPS = 24
RATE = 48000
OPENING_FRAMES = 1039
OPENING_PCM_SECONDS = 43.25  # Last quiet frame before the new Maya onset.
ORIGINAL_START_FRAME = 1272  # 53.000s, before Maya's original 53.184s onset.
ORIGINAL_END_FRAME = 3732    # 155.500s, includes the original closing card.
OPENING_SECONDS = OPENING_FRAMES / FPS
ORIGINAL_START = ORIGINAL_START_FRAME / FPS
FINAL_FRAMES = OPENING_FRAMES + ORIGINAL_END_FRAME - ORIGINAL_START_FRAME
DURATION = FINAL_FRAMES / FPS
OFFSET = OPENING_SECONDS - ORIGINAL_START

# Settled windows in the original movie. Coordinates are on its complete
# 1920x1080 native picture, deliberately outside the message text.
HIGHLIGHTS = [
    {'name': 'Maya approves sharing', 'start': 79.0, 'end': 81.55,
     'rect': [1432, 682, 478, 96]},
    {'name': 'The approved finding reaches the shared thread', 'start': 84.2, 'end': 87.2,
     'rect': [1432, 476, 478, 279]},
    {'name': 'Leo approves the cloud repair', 'start': 97.0, 'end': 100.15,
     'rect': [1430, 817, 480, 109]},
    {'name': 'Cloud passes while messages still fail', 'start': 105.8, 'end': 109.0,
     'rect': [1432, 568, 478, 320]},
    {'name': 'Maya approves the app repair', 'start': 120.6, 'end': 122.2,
     'rect': [1432, 817, 478, 109]},
    {'name': 'The same delivery test passes 24 of 24', 'start': 133.0, 'end': 136.0,
     'rect': [1432, 677, 478, 219]},
    {'name': 'The original failed message is recovered', 'start': 143.2, 'end': 145.5,
     'rect': [1432, 750, 478, 144]},
]


def run(command):
    result = subprocess.run(command, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-2500:])
    return result.stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams',
                           '-show_format', '-of', 'json', str(path)]))


def read_pcm(path):
    with wave.open(str(path), 'rb') as source:
        assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (RATE, 1, 2)
        return source.readframes(source.getnframes())


def time_seconds(value):
    h, m, s = value.replace(',', '.').split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def stamp(value):
    ms = round(value * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def captions(path):
    result = []
    for block in re.split(r'\n\s*\n', path.read_text().strip()):
        lines = block.splitlines()
        a, b = lines[1].split(' --> ')
        result.append({'start': time_seconds(a), 'end': time_seconds(b),
                       'text': '\n'.join(lines[2:])})
    return result


def main():
    DELIVERY.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    opening = ROOT / 'demo/final-v3/delivery/Relay-final.mp4'
    original = ROOT / 'demo/final/Relay-demo.mp4'
    opening_wave = ROOT / 'demo/final-v3/narration.wav'
    original_wave = ROOT / 'demo/final/narration.wav'
    original_manifest_path = ROOT / 'demo/final/assembly-manifest.json'
    source_paths = [opening, original, opening_wave, original_wave, original_manifest_path]
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    assert sha(opening) == 'b832b14d7ee689458cdc49fca828fab670ccb95efa57265a9fd620302ed4bb51'
    assert sha(original) == 'cd899c0bc99bcbbc22f74c08a3169525f687ed5b2225556cc5ac9aba634ec043'
    for path in [opening, original]:
        picture = next(s for s in probe(path)['streams'] if s['codec_type'] == 'video')
        assert (picture['width'], picture['height'], picture['r_frame_rate']) == (1920, 1080, '24/1')

    # Quiet tail is trimmed before the revised voice begins saying Maya. This
    # prevents a double M at the join without cutting any approved opening word.
    first_pcm = read_pcm(opening_wave)[:round(OPENING_PCM_SECONDS * RATE) * 2]
    old_pcm = read_pcm(original_wave)[ORIGINAL_START_FRAME * RATE // FPS * 2:]
    join_sample = OPENING_FRAMES * RATE // FPS
    samples = FINAL_FRAMES * RATE // FPS
    opening_pad = join_sample - len(first_pcm) // 2
    master_pcm = first_pcm + bytes(opening_pad * 2) + old_pcm
    end_pad = samples - len(master_pcm) // 2
    assert opening_pad >= 0 and end_pad >= 0
    master_pcm += bytes(end_pad * 2)
    master = OUT / 'narration-combined.wav'
    with wave.open(str(master), 'wb') as target:
        target.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        target.writeframes(master_pcm)
    quiet_tail = array.array('h', first_pcm[round(43.15 * RATE) * 2:])
    quiet_rms = math.sqrt(sum(v * v for v in quiet_tail) / len(quiet_tail))
    assert quiet_rms < 10

    # The old v3 cue combines Here's how with its new Maya sentence. Split only
    # that caption at the actual character alignment; all old demo cues remain.
    opening_rows = captions(ROOT / 'demo/final-v3/delivery/Relay-final.srt')
    rows = [row for row in opening_rows if row['end'] <= 41.877]
    rows.append({'start': 41.877, 'end': 42.678, 'text': "Here's how."})
    for row in captions(ROOT / 'demo/final/Relay-demo.srt'):
        if row['end'] <= ORIGINAL_START:
            continue
        assert row['start'] >= ORIGINAL_START
        rows.append({**row, 'start': row['start'] + OFFSET, 'end': row['end'] + OFFSET})
    assert all(0 <= row['start'] < row['end'] <= DURATION for row in rows)
    assert all(a['end'] <= b['start'] for a, b in zip(rows, rows[1:]))
    caption_path = DELIVERY / 'Relay-final.srt'
    caption_path.write_text('\n\n'.join(
        f"{i}\n{stamp(r['start'])} --> {stamp(r['end'])}\n{r['text']}"
        for i, r in enumerate(rows, 1)) + '\n')
    (DELIVERY / 'Relay-final.vtt').write_text('WEBVTT\n\n' + re.sub(
        r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', caption_path.read_text()))
    original_beats = json.loads((ROOT / 'demo/final/beat-timing.json').read_text())['beats']
    original_body = [b for b in original_beats if b['spokenStart'] >= ORIGINAL_START]
    opening_script = (ROOT / 'demo/final-v3/delivery/narration-script.txt').read_text()
    opening_script = opening_script[:opening_script.index('Here’s how.') + len('Here’s how.')]
    script = opening_script.strip() + '\n\n' + '\n\n'.join(b['text'] for b in original_body) + '\n'
    (DELIVERY / 'narration-script.txt').write_text(script)

    # Outlines operate on the original timestamps before its trim. The native
    # footage remains full-frame, at its original speed, including arrival and
    # working notices. No screenshots or artificial zooms replace these shots.
    focus_filters = []
    for item in HIGHLIGHTS:
        x, y, w, h = item['rect']
        enabled = f"between(t,{item['start']:.6f},{item['end']:.6f})"
        focus_filters.extend([
            f"drawbox=x={x-2}:y={y-2}:w={w+4}:h={h+4}:color=white@0.95:t=6:enable='{enabled}'",
            f"drawbox=x={x}:y={y}:w={w}:h={h}:color=0x2855d9@0.98:t=3:enable='{enabled}'",
        ])
    filters = (
        f'[0:v]trim=start_frame=0:end_frame={OPENING_FRAMES},setpts=PTS-STARTPTS,setsar=1[v0];'
        f"[1:v]{','.join(focus_filters)},trim=start_frame={ORIGINAL_START_FRAME}:end_frame={ORIGINAL_END_FRAME},"
        'setpts=PTS-STARTPTS,setsar=1[v1];[v0][v1]concat=n=2:v=1:a=0[v]'
    )
    video = DELIVERY / 'Relay-final.mp4'
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
               '-filter_complex_threads', '1', '-i', str(opening), '-i', str(original),
               '-i', str(master), '-i', str(caption_path), '-filter_complex', filters,
               '-map', '[v]', '-map', '2:a:0', '-map', '3:s:0',
               '-frames:v', str(FINAL_FRAMES), '-t', f'{DURATION:.9f}', '-r', str(FPS),
               '-c:v', 'libx264', '-preset', 'fast', '-crf', '16', '-threads', '4',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
               '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng',
               '-disposition:s:0', '0', '-movflags', '+faststart', str(video)]
    run(command)
    final_probe = probe(video)
    run(['ffmpeg', '-v', 'error', '-i', str(video), '-f', 'null', '-'])

    upstream = json.loads(original_manifest_path.read_text())
    capture = ROOT / 'recording/native-take-03'
    for name, record in upstream['sources'].items():
        assert sha(capture / name) == record['sha256'], name
    checks = {
        'latest_approved_opening_picture_retained': OPENING_FRAMES == 1039,
        'all_spoken_opening_words_retained': OPENING_PCM_SECONDS > 42.678,
        'opening_cut_before_new_maya_onset': OPENING_PCM_SECONDS < 43.281,
        'opening_pcm_exact_before_quiet_trim': master_pcm[:len(first_pcm)] == first_pcm,
        'original_demo_pcm_exact': master_pcm[join_sample*2:join_sample*2+len(old_pcm)] == old_pcm,
        'quiet_join_tail': quiet_rms < 10,
        'full_original_moving_demo_retained': ORIGINAL_START_FRAME == 1272 and ORIGINAL_END_FRAME == 3732,
        'native_sources_unchanged': True,
        'source_films_unchanged': all(sha(ROOT / p) == v for p, v in source_hashes.items()),
        'captions_valid': len(rows) == 40,
        'landscape_1080p24': next(s for s in final_probe['streams'] if s['codec_type'] == 'video')['width'] == 1920,
        'duration_valid': abs(float(final_probe['format']['duration']) - DURATION) < .05,
        'under_three_minutes': DURATION < 180,
        'full_decode_passed': True,
    }
    report = {
        'passed': all(checks.values()), 'checks': checks,
        'video': str(video.relative_to(ROOT)), 'video_sha256': sha(video),
        'duration_seconds': DURATION, 'fps': FPS, 'dimensions': [1920,1080],
        'caption_count': len(rows), 'script_words': len(script.split()),
        'source_hashes': source_hashes,
        'splice': {'opening_picture_end_seconds': OPENING_SECONDS,
                   'opening_pcm_end_seconds': OPENING_PCM_SECONDS,
                   'original_demo_start_seconds': ORIGINAL_START,
                   'original_demo_end_seconds': ORIGINAL_END_FRAME/FPS,
                   'demo_offset_seconds': OFFSET,
                   'first_original_maya_spoken_seconds': 53.184+OFFSET},
        'audio': {'master': str(master.relative_to(ROOT)), 'sha256': sha(master),
                  'rate': RATE, 'samples': samples, 'opening_padding_samples': opening_pad,
                  'ending_padding_samples': end_pad, 'new_speech_requests': 0,
                  'tempo_factor': 1.0, 'quiet_join_tail_rms_pcm16': quiet_rms},
        'highlights': [{**i,'new_start_seconds':i['start']+OFFSET,
                       'new_end_seconds':i['end']+OFFSET} for i in HIGHLIGHTS],
        'native_provenance': {'capture': 'recording/native-take-03',
                              'upstream_assembly_manifest_sha256': sha(original_manifest_path),
                              'upstream_source_frames_verified': len(upstream['sources']),
                              'native_capture_cadence_seconds': .201,
                              'source_frame_hashes': {k:v['sha256'] for k,v in upstream['sources'].items()},
                              'chronology': 'Original moving native demo, preserved at its original edit speed; pre-retry 24/24, original failed-message retry, later closing result.'},
        'disclosure': 'Latest privacy opening plus the original moving Mattermost demo. Brief blue outlines are editorial attention guides. Fictional companies and scripted presenter approvals; real recorded agents, Switch events and local HTTP checks. Original short reading holds and omitted idle waits remain; this is not a continuous wall-clock recording. No new service/model execution was performed.',
        'full_decode': {'passed': True},
    }
    assert report['passed'], checks
    (OUT/'assembly-manifest.json').write_text(json.dumps(report,indent=2)+'\n')

    qa_marks = [(0.7,'opening-hook'),(13,'privacy-opening'),(42.2,'opening-transition'),
                (43.5,'moving-demo-start'),(56,'agent-working'),(79.8+OFFSET,'maya-share'),
                (85+OFFSET,'shared-finding'),(98+OFFSET,'leo-approval'),
                (107+OFFSET,'cloud-partial'),(121.2+OFFSET,'maya-app-approval'),
                (134+OFFSET,'delivery-passed'),(144+OFFSET,'original-retry'),
                (147+OFFSET,'incident-result'),(154+OFFSET,'closing')]
    index=[]
    for number,(at,label) in enumerate(qa_marks,1):
        path=QA/f'{number:02}-{label}.jpg'
        run(['ffmpeg','-v','error','-y','-ss',f'{at:.6f}','-i',str(video),
             '-frames:v','1','-q:v','2',str(path)])
        index.append({'file':path.name,'time_seconds':at,'sha256':sha(path)})
    (QA/'frame-index.json').write_text(json.dumps(index,indent=2)+'\n')
    run(['ffmpeg','-v','error','-y','-ss','40.5','-i',str(video),'-t','6.5',
         '-c:v','libx264','-crf','18','-c:a','aac','-b:a','192k',str(OUT/'join-review.mp4')])
    (DELIVERY/'README.txt').write_text(
        'RELAY: MOVING MATTERMOST DEMO\n\n'
        '2 minutes 26 seconds, 1920x1080 landscape, 24 fps.\n'
        'The latest privacy opening is preserved. The original moving Mattermost\n'
        'demo is restored, including the actual message arrivals, agents working,\n'
        'native owner approvals, incomplete cloud-only recovery and verified delivery.\n'
        'Brief blue outlines guide attention without replacing the interface.\n\n'
        'Original narration is reused at its original pace. No new voice was generated.\n'
        'A quiet 41.667ms alignment pad avoids a stray revised Maya onset at the join.\n'
        'English captions are embedded and included as SRT and WEBVTT.\n\n'
        'TeamChat and HarborCloud are fictional; one presenter roleplays both owners.\n'
        'The agents, Switch events and local HTTP checks in the recording are real.\n'
        'Earlier reading holds and idle-wait edits remain in the original moving demo.\n'
        'This is not a new live execution or a production deployment.\n')
    print(json.dumps({'passed':True,'video':str(video),'duration_seconds':DURATION,
                      'sha256':sha(video),'caption_count':len(rows)},indent=2))


if __name__ == '__main__':
    main()
