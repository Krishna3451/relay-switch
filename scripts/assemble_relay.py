"""Assemble editorial opening cards and reviewed native Mattermost windows.

Actual screenshot cadence is retained. Static waits may be omitted only by
reviewing explicit windows; short spoken beats must never speed up arrivals.
One continuous mastered narration stream is copied, with no speech retiming.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
FPS, FADE, HANDLE = 24, 10, 5


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Local assembly failed: " + result.stderr[-1800:])
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path):
    return json.loads(run([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]).stdout)


def jpeg_dimensions(path):
    """Inspect original screenshot dimensions without launching a decoder."""
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError("Native capture source is not a JPEG")
    offset = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 3 < len(data):
        if data[offset] != 0xFF:
            raise ValueError("Malformed native JPEG header")
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in sof:
            return [int.from_bytes(data[offset + 5:offset + 7], "big"), int.from_bytes(data[offset + 3:offset + 5], "big")]
        offset += length
    raise ValueError("Native screenshot dimensions are unavailable")


def audio_hash(path):
    result = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-vn", "-c:a", "copy", "-f", "adts", "-"], capture_output=True)
    if result.returncode:
        raise ValueError("Could not inspect continuous audio stream")
    return hashlib.sha256(result.stdout).hexdigest()


def plan_template(out):
    approved = json.loads((out / "approved-script.json").read_text())
    entries = []
    index = 0
    for section_index, section in enumerate(approved["sections"], 1):
        for paragraph_index, paragraph in enumerate(section["paragraphs"]):
            index += 1
            entry = {"beat": f"beat-{index:02d}", "narration": paragraph, "section": section_index}
            if section_index <= 3:
                card = ("problem" if paragraph_index == 0 else "two-companies") if section_index == 1 else "existing" if section_index == 2 else "why"
                entry.update(kind="editorial_card", file="cards/" + card + ".png", reviewed=True,
                             note="Clearly labelled editorial illustration, not an interface capture")
            else:
                lower = paragraph.lower()
                stage, stream = "close", "shared"
                if section_index == 4:
                    if lower.startswith("relay connects"):
                        stage = "prepare"
                    elif lower.startswith("maya reports"):
                        stage = "incident"
                    elif lower.startswith(("teamchat’s agent acknowledges", "teamchat's agent acknowledges", "teamchat’s agent starts", "teamchat's agent starts")):
                        stage, stream = "incident", "teamchat"
                    elif lower.startswith("maya reviews"):
                        stage, stream = "share_question", "teamchat"
                    elif lower.startswith(("that question", "the question")):
                        stage = "share_question"
                    elif lower.startswith("it finds"):
                        stage, stream = "approve_cloud", "harborcloud"
                    elif lower.startswith("the agent applies"):
                        stage = "share_cloud_result"
                    elif lower.startswith("some parts of teamchat"):
                        stage, stream = "share_cloud_result", "teamchat"
                    elif lower.startswith("teamchat’s agent uses") or lower.startswith("teamchat's agent uses"):
                        stage, stream = "approve_app", "teamchat"
                    elif lower.startswith("the agent performs"):
                        stage = "share_app_result"
                    elif lower.startswith(("teamchat’s agent proposes", "teamchat's agent proposes")):
                        stage, stream = "approve_app", "teamchat"
                elif lower.startswith("run the same"):
                    stage = "share_app_result"
                elif lower.startswith("maya asks"):
                    stage = "retry"
                entry.update(kind="native_capture", stream=stream, stage=stage, reviewed=False,
                             windows=[{"anchor": "start", "offset_start": 0, "offset_end": 2.3},
                                      {"anchor": "gate_at", "offset_start": -2.0, "offset_end": .3}],
                             note="PROPOSED windows only. Review actual messages, working notices and arrival visibility; adjust before marking reviewed.")
            entries.append(entry)
    value = {"status": "PROPOSED_REQUIRES_CAPTURE_REVIEW", "script_sha256": approved["script_sha256"],
             "capture_root": "recording/native-take", "markers_file": "recording/native-take/markers.json",
             "audio_file": "demo/final/narration.m4a", "native_dimensions": [1600, 900],
             "output_dimensions": [1920, 1080], "fps": FPS, "transition_frames": FADE,
             "outcome_review": {"verified": False, "evidence_file": None,
                 "required": "Actual final24/24 check, cloud-only partial check, and original failed-message retry with unchanged ID and one persisted row"},
             "clips": entries}
    (out / "edit-plan-proposed.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"beats": len(entries), "cards": sum(x["kind"] == "editorial_card" for x in entries),
                      "native_beats": sum(x["kind"] == "native_capture" for x in entries), "status": value["status"]}))


def markers_from(path):
    data = json.loads(path.read_text())
    values = data.get("markers", data.get("stages", [])) if isinstance(data, dict) else data
    return {item["stage"]: item for item in values}


def prepare(plan_path, out, allow_unreviewed=False):
    plan = json.loads(plan_path.read_text())
    timing = json.loads((out / "beat-timing.json").read_text())
    narration = json.loads((out / "narration-manifest.json").read_text())
    if plan["script_sha256"] != narration["script_sha256"]:
        raise ValueError("Edit plan belongs to a different narration")
    if not allow_unreviewed and (not plan.get("outcome_review", {}).get("verified") or any(not c.get("reviewed") for c in plan["clips"])):
        raise ValueError("Capture windows and recorded outcome must be reviewed before final rendering")
    if not allow_unreviewed:
        evidence = plan["outcome_review"].get("evidence_file")
        if not evidence or not (ROOT / evidence).is_file():
            raise ValueError("A real functional outcome artifact is required")
        proof = json.loads((ROOT / evidence).read_text())
        if proof.get("passed") is not True:
            raise ValueError("The recorded native source/scope/outcome audit has not passed")
        final, partial, gateway, retry = [proof.get(key, {}) for key in ("final", "partial", "gatewayCanary", "retry")]
        if final.get("attempted") != 24 or final.get("delivered") != 24:
            raise ValueError("The approved24/24 narration requires actual recorded24/24 delivery")
        if not partial.get("attempted") or partial.get("delivered", partial["attempted"]) >= partial["attempted"]:
            raise ValueError("Recorded cloud-only partial recovery must remain visible and supported")
        gateway_passed = gateway.get("status") == "healthy" or (gateway.get("attempted", 0) > 0 and gateway.get("succeeded") == gateway["attempted"])
        if not gateway_passed:
            raise ValueError("The partial recovery claim requires an actual successful gateway canary")
        if not all(retry.get(key) is True for key in ("originalFailed", "delivered", "sameIdAndBody")) or retry.get("persistedRows") != 1:
            raise ValueError("The original failed-message payoff requires same-ID/body delivery persisted once")
        plan["outcome_review"]["evidence_sha256"] = sha(ROOT / evidence)
    capture_root = (ROOT / plan["capture_root"]).resolve()
    markers_path = ROOT / plan["markers_file"]
    markers = markers_from(markers_path)
    beats = {beat["id"]: beat for beat in timing["beats"]}
    streams, source_hashes, clips = {}, {}, []
    expected = 0
    for entry in plan["clips"]:
        beat = beats[entry["beat"]]
        # Optional reviewed sub-beat boundaries allow a combined condensed
        # paragraph to cut from the shared thread into a private owner review.
        start, end = round(entry.get("start", beat["start"]) * FPS), round(entry.get("end", beat["end"]) * FPS)
        if start != expected or end <= start:
            raise ValueError("Plan must cover the continuous narration exactly once, in order")
        if entry["kind"] == "editorial_card":
            card = (out / entry["file"]).resolve()
            if not card.is_relative_to(out.resolve()) or not card.is_file():
                raise ValueError("Missing local editorial card")
            clips.append({"kind": "editorial_card", "beat": entry["beat"], "path": str(card),
                          "nominal_start_frame": start, "nominal_frames": end - start, "source_sha256": sha(card),
                          "note": "Editorial illustration, not captured product behavior"})
        else:
            stream = entry["stream"]
            if Path(stream).name != stream:
                raise ValueError("Invalid native stream")
            if stream not in streams:
                frames_path = capture_root / stream / "frames.json"
                rows = json.loads(frames_path.read_text())
                if len(rows) < 2 or any(b["at"] <= a["at"] for a, b in zip(rows, rows[1:])):
                    raise ValueError("Native capture timestamps must increase")
                cadence = statistics.median((b["at"] - a["at"]) / 1000 for a, b in zip(rows, rows[1:]))
                streams[stream] = {"rows": rows, "cadence": cadence, "manifest_sha256": sha(frames_path)}
            marker = markers.get(entry["stage"])
            if marker is None:
                raise ValueError("Missing actual capture stage: " + entry["stage"])
            chunks = []
            for window in entry["windows"]:
                window_marker = markers.get(window.get("stage", entry["stage"]))
                if window_marker is None:
                    raise ValueError("Missing the reviewed window's actual capture stage")
                if "first_at_ms" in window:
                    first, last = window["first_at_ms"], window["last_at_ms"]
                else:
                    anchor = window_marker.get(window.get("anchor", "gate_at"))
                    if anchor is None:
                        raise ValueError("Capture marker lacks the chosen anchor")
                    first, last = anchor + window["offset_start"] * 1000, anchor + window["offset_end"] * 1000
                rows = [row for row in streams[stream]["rows"] if first <= row["at"] <= last]
                if not rows:
                    raise ValueError("Reviewed native window contains no captured frames")
                frames = []
                for i, row in enumerate(rows):
                    image = (capture_root / stream / row["file"]).resolve()
                    if not image.is_relative_to(capture_root):
                        raise ValueError("Capture image escaped source root")
                    if jpeg_dimensions(image) != plan["native_dimensions"]:
                        raise ValueError("Source must be the complete verified16:9 viewport")
                    seconds = (rows[i + 1]["at"] - row["at"]) / 1000 if i + 1 < len(rows) else streams[stream]["cadence"]
                    if seconds > 2 and not window.get("reviewed_native_gap"):
                        raise ValueError("Review a native capture gap above2s before retaining it")
                    source = stream + "/" + row["file"]
                    source_hashes[source] = {"at": row["at"], "sha256": sha(image)}
                    frames.append({"path": str(image), "seconds": seconds, "at": row["at"], "source": source})
                chunks.append(frames)
            remaining = end - start
            for i, frames in enumerate(chunks):
                native = sum(frame["seconds"] for frame in frames)
                needed = math.ceil(native * FPS - 1e-9)
                allocated = needed if i + 1 < len(chunks) else remaining
                if allocated < needed:
                    raise ValueError(f"{entry['beat']}: real arrivals need{native:.2f}s; review shorter windows instead of speeding footage")
                clips.append({"kind": "native_capture", "beat": entry["beat"], "stream": stream, "stage": entry["stage"],
                              "nominal_start_frame": start, "nominal_frames": allocated, "native_seconds": native,
                              "reading_hold_seconds": allocated / FPS - native, "frames": frames,
                              "source_first_at_ms": frames[0]["at"], "source_last_at_ms": frames[-1]["at"]})
                start += allocated
                remaining -= allocated
        expected = end
    if expected != round(timing["duration"] * FPS):
        raise ValueError("Narration ending is not fully covered")
    for i, clip in enumerate(clips):
        clip["head_handle_frames"] = HANDLE if i else 0
        clip["tail_handle_frames"] = HANDLE if i + 1 < len(clips) else 0
        clip["render_frames"] = clip["nominal_frames"] + clip["head_handle_frames"] + clip["tail_handle_frames"]
    return plan, timing, narration, streams, source_hashes, clips


def render_clip(clip, index, directory):
    output = directory / f"clip-{index:03d}.mp4"
    handle = clip["head_handle_frames"] / FPS
    if clip["kind"] == "editorial_card":
        source = ["-loop", "1", "-i", clip["path"]]
        transform = "scale=1920:1080:flags=lanczos,setsar=1,fps=24"
    else:
        listing = directory / f"clip-{index:03d}.ffconcat"
        lines = ["ffconcat version1.0"]
        for frame in clip["frames"]:
            path = frame["path"].replace("'", "'\\''")
            lines.extend([f"file '{path}'", "option framerate1000", f"duration {frame['seconds']:.6f}"])
        path = clip["frames"][-1]["path"].replace("'", "'\\''")
        lines.extend([f"file '{path}'", "option framerate1000", "duration1"])
        listing.write_text("\n".join(lines).replace("version1.0", "version 1.0").replace("framerate1000", "framerate 1000").replace("duration1", "duration 1") + "\n")
        source = ["-safe", "0", "-f", "concat", "-i", str(listing)]
        transform = f"scale=1920:1080:flags=lanczos,setsar=1,fps=24,tpad=start_mode=clone:start_duration={handle:.6f}:stop_mode=clone:stop_duration={clip['render_frames']/FPS+1:.6f}"
    run([FFMPEG, "-v", "error", "-y", *source, "-an", "-vf", transform, "-frames:v", str(clip["render_frames"]),
         "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "0", "-pix_fmt", "yuv420p", str(output)])
    return output


def assemble(plan_path, out, dry_run=False):
    plan, timing, narration, streams, sources, clips = prepare(plan_path, out)
    print(json.dumps({"clips": len(clips), "native_source_frames": len(sources), "duration": timing["duration"],
                      "native_seconds": sum(c.get("native_seconds", 0) for c in clips), "mode": "reviewed"}), flush=True)
    if dry_run:
        return
    audio_path = ROOT / plan["audio_file"]
    audio_before = audio_hash(audio_path)
    with tempfile.TemporaryDirectory(prefix="relay-render-") as temporary:
        directory = Path(temporary)
        with ThreadPoolExecutor(max_workers=2) as pool:
            paths = list(pool.map(lambda pair: render_clip(pair[1], pair[0], directory), enumerate(clips)))
        command = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "1"]
        for path in paths:
            command.extend(["-i", str(path)])
        command.extend(["-i", str(audio_path)])
        command.extend(["-i", str(out / "narration.srt")])
        filters = [f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]" for i in range(len(paths))]
        current, total = "v0", clips[0]["render_frames"]
        transitions = []
        for i in range(1, len(paths)):
            offset = (total - FADE) / FPS
            label = f"fade{i}"
            filters.append(f"[{current}][v{i}]xfade=transition=fade:duration={FADE/FPS:.6f}:offset={offset:.6f}[{label}]")
            transitions.append({"start": offset, "end": offset + FADE / FPS, "next_clip": i})
            current, total = label, total + clips[i]["render_frames"] - FADE
        output = out / "Relay-demo.mp4"
        command.extend(["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", f"{len(paths)}:a:0", "-map", f"{len(paths)+1}:s:0",
                        "-t", f"{timing['duration']:.6f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
                        "-disposition:s:0", "0", "-movflags", "+faststart", str(output)])
        run(command)
    if audio_hash(output) != audio_before:
        raise ValueError("Continuous narration audio changed during assembly")
    decode_command = [FFMPEG, "-v", "error", "-i", str(output), "-f", "null", "-"]
    decode_result = run(decode_command)
    for source, record in sources.items():
        if sha(ROOT / plan["capture_root"] / source) != record["sha256"]:
            raise ValueError("An original capture changed during encoding")
    shutil.copyfile(out / "narration.srt", out / "Relay-demo.srt")
    manifest = {"kind": "Reviewed editorial explanation + actual native Mattermost captures", "video": output.name,
                "video_sha256": sha(output), "duration": timing["duration"], "source_dimensions": [1600, 900],
                "output_dimensions": [1920, 1080], "fps": FPS, "uniform_scale": 1.2, "crop_or_padding": False,
                "continuous_audio_copied": True, "aac_adts_sha256": audio_before, "tempo_factor": 1.0,
                "full_decode_check": {"command": decode_command, "exit_code": decode_result.returncode},
                "narration_sha256": narration["script_sha256"], "plan_sha256": sha(plan_path),
                "markers_sha256": sha(ROOT / plan["markers_file"]), "transitions": transitions,
                "streams": {name: {k: v for k, v in value.items() if k != "rows"} for name, value in streams.items()},
                "clips": [{k: v for k, v in clip.items() if k != "frames"} for clip in clips], "sources": sources,
                "outcome_review": plan["outcome_review"], "ffprobe": probe(output),
                "limits": "Fictional companies; actual local HTTP and Switch. Reviewed static waits omitted and real frames held for reading. Editorial opening cards are labelled. Not a continuous wall-clock recording."}
    (out / "assembly-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"video": str(output), "duration": timing["duration"], "audio_unchanged": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "render", "check"))
    parser.add_argument("--output", type=Path, default=ROOT / "demo/final")
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    if args.command == "plan":
        plan_template(args.output)
    else:
        assemble(args.plan or args.output / "edit-plan.json", args.output, dry_run=args.command == "check")


if __name__ == "__main__":
    main()
