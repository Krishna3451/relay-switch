"""Local-only mastering, real provider-timed captions and paragraph edit beats."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import textwrap
import wave

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = "ffmpeg"


def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Local media processing failed: " + result.stderr[-1200:])
    return result


def signature(text):
    return "".join(c.casefold() for c in text if c.isalnum())


def stamp(seconds):
    value = round(seconds * 1000)
    hours, value = divmod(value, 3600000)
    minutes, value = divmod(value, 60000)
    seconds, value = divmod(value, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{value:03d}"


def prepare(out):
    plan = json.loads((out / "approved-script.json").read_text())
    script = (out / "narration-script.txt").read_text()
    if hashlib.sha256(script.encode()).hexdigest() != plan["script_sha256"]:
        raise ValueError("Approved narration changed")
    provider = json.loads((out / "provider-alignment.json").read_text())
    alignment = provider.get("normalized_alignment") or provider.get("alignment")
    if not alignment:
        raise ValueError("Actual provider alignment is required; estimated subtitles are refused")
    chars, starts, ends = [alignment[k] for k in ("characters", "character_start_times_seconds", "character_end_times_seconds")]
    if not chars or len({len(chars), len(starts), len(ends)}) != 1:
        raise ValueError("Incomplete character timing")
    if any(not math.isfinite(v) or v < 0 for v in starts + ends) or any(a > b for a, b in zip(starts, starts[1:])):
        raise ValueError("Invalid provider times")
    conversion = "Absolute provider character end times retained"
    if any(e < s for s, e in zip(starts, ends)):
        discrepancy = max(abs((starts[i + 1] - starts[i]) - ends[i]) for i in range(len(starts) - 1))
        if discrepancy > .002:
            raise ValueError("Unrecognized provider duration format")
        ends = [s + e for s, e in zip(starts, ends)]
        conversion = "Derived end=start+duration after independent adjacent-start verification"
    full = "".join(chars)
    mapped, indices = [], []
    for index, character in enumerate(chars):
        if character.isalnum():
            mapped.extend(character.casefold())
            indices.extend([index] * len(character.casefold()))
    mapped = "".join(mapped)
    paragraphs = [(section_index + 1, section["heading"], paragraph)
                  for section_index, section in enumerate(plan["sections"]) for paragraph in section["paragraphs"]]
    positions = []
    anchors = []
    for _, _, paragraph in paragraphs:
        anchor_words = []
        for word in paragraph.split()[:6]:
            if any(character.isdigit() for character in word):
                break
            anchor_words.append(word)
        anchor = " ".join(anchor_words)
        if len(anchor_words) < 3:
            raise ValueError("Choose a longer nonnumeric paragraph anchor")
        target = signature(anchor)
        first = mapped.find(target)
        if first < 0 or mapped.find(target, first + 1) >= 0:
            raise ValueError("Missing or ambiguous spoken paragraph anchor: " + anchor)
        positions.append(indices[first])
        anchors.append(anchor)
    if positions != sorted(positions):
        raise ValueError("Actual speech does not follow approved paragraph order")
    raw = out / "narration-raw.wav"
    run([FFMPEG, "-v", "error", "-y", "-i", str(out / "narration-original.mp3"), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(raw)])
    with wave.open(str(raw)) as audio:
        samples, rate = audio.getnframes(), audio.getframerate()
    duration = samples / rate
    if ends[-1] > duration + .25:
        raise ValueError("Provider timing exceeds actual audio")
    measured = run([FFMPEG, "-hide_banner", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    match = re.search(r'\{\s*"input_i"[\s\S]*?\}', measured.stderr)
    if not match:
        raise ValueError("Audio loudness measurement missing")
    loud = json.loads(match.group())
    filt = ("loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=" + loud["input_i"] + ":measured_TP=" + loud["input_tp"] +
            ":measured_LRA=" + loud["input_lra"] + ":measured_thresh=" + loud["input_thresh"] + ":offset=" + loud["target_offset"] +
            ":linear=true,aresample=48000,apad,atrim=end_sample=" + str(samples))
    run([FFMPEG, "-v", "error", "-y", "-i", str(raw), "-af", filt, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(out / "narration.wav")])
    with wave.open(str(out / "narration.wav")) as audio:
        if audio.getnframes() != samples:
            raise ValueError("Mastering changed narration length")
    run([FFMPEG, "-v", "error", "-y", "-i", str(out / "narration.wav"), "-c:a", "aac", "-b:a", "192k", str(out / "narration.m4a")])
    run([FFMPEG, "-v", "error", "-y", "-i", str(out / "narration.wav"), "-c:a", "libmp3lame", "-b:a", "192k", str(out / "narration.mp3")])
    boundaries = [0.0]
    for position in positions[1:]:
        preceding = position - 1
        while preceding >= 0 and chars[preceding].isspace():
            preceding -= 1
        before, onset = ends[preceding], starts[position]
        boundaries.append((before + onset) / 2 if before <= onset else onset)
    boundaries.append(duration)
    beats = [{"id": f"beat-{i+1:02d}", "section": section, "heading": heading, "text": text,
              "anchor": anchors[i], "start": boundaries[i], "end": boundaries[i+1],
              "duration": boundaries[i+1] - boundaries[i], "spokenStart": starts[positions[i]]}
             for i, (section, heading, text) in enumerate(paragraphs)]
    # Compact phrase captions, using the actual word start/end indices.
    words = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", full)]
    captions, group = [], []
    for word in words:
        proposed = " ".join([x[0] for x in group] + [word[0]])
        if group and (len(proposed) > 82 or starts[word[1]] - starts[group[0][1]] > 6.0):
            captions.append(group)
            group = []
        group.append(word)
        if re.search(r"[.!?][”’\"']?$", word[0]) and len(group) >= 3:
            captions.append(group)
            group = []
    if group:
        captions.append(group)
    lines, cue_data = [], []
    for i, group in enumerate(captions, 1):
        start, end = max(0, starts[group[0][1]]), min(duration, ends[group[-1][2] - 1])
        text = " ".join(x[0] for x in group)
        if end <= start:
            raise ValueError("Empty caption timing")
        cue_data.append({"start": start, "end": end, "text": text})
        lines.extend([str(i), stamp(start) + " --> " + stamp(end),
                      "\n".join(textwrap.wrap(text, 43, break_long_words=False, break_on_hyphens=False)), ""])
    (out / "narration.srt").write_text("\n".join(lines), encoding="utf-8")
    (out / "beat-timing.json").write_text(json.dumps({"duration": duration, "beats": beats, "captions": cue_data}, indent=2, ensure_ascii=False) + "\n")
    metadata = json.loads((out / "generation-metadata.json").read_text())
    manifest = {**metadata, "audio_seconds": duration, "sample_count": samples, "sample_rate": rate,
                "continuous_audio": True, "tempo_factor": 1.0, "sample_count_preserved": True,
                "mastering": {"lufs": -16, "true_peak_dbtp": -1.5, "whole_track_only": True},
                "alignment_conversion": conversion, "caption_count": len(cue_data), "beat_count": len(beats),
                "aac_sha256": hashlib.sha256((out / "narration.m4a").read_bytes()).hexdigest()}
    (out / "narration-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"duration": duration, "beats": len(beats), "captions": len(cue_data), "voice": metadata["voice_name"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "demo/final")
    args = parser.parse_args()
    prepare(args.output)
