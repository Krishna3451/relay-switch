"""Extract actual final-video frames at narration cues for independent review."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "demo/final")
    args = parser.parse_args()
    out = args.output
    video = out / "Relay-demo.mp4"
    beats = json.loads((out / "beat-timing.json").read_text())
    cues = json.loads((out / "cue-timing.json").read_text())["cues"]
    qa = out / "qa"
    qa.mkdir(exist_ok=True)
    shots = [{"label": "opening", "time": 1.0}, {"label": "two-companies", "time": 8.0},
             {"label": "existing-solution", "time": 18.0}, {"label": "why", "time": 35.0}]
    shots += [{"label": cue["phrase"], "time": min(cue["start"] + .8, beats["duration"] - .25)} for cue in cues]
    shots += [{"label": label, "time": timestamp} for label, timestamp in [
        ("Maya actual disclosure reply",80.6),
        ("Leo actual operation approval",99.0),
        ("Cloud6/6 but fresh chat15/24",108.5),
        ("Maya actual operation approval",121.7),
        ("Pre-retry24/24 verification",135.5),
        ("Original same-message retry confirmation",144.8),
        ("Later latest24/24 check",151.5)]]
    for index, shot in enumerate(shots, 1):
        path = qa / f"frame-{index:02d}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(shot["time"]), "-i", str(video),
                        "-frames:v", "1", "-q:v", "2", str(path)], check=True)
        shot["file"] = str(path.relative_to(ROOT))
        shot["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    value = {"video": str(video.relative_to(ROOT)), "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
             "shots": shots, "review_status": "Awaiting independent visual review; extraction does not itself prove screen content"}
    (qa / "frame-index.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    subprocess.run(["swift", "-module-cache-path", "/private/tmp/relay-swift-cache", str(ROOT / "scripts/prepare-contact-sheet.swift"), str(qa)], cwd=ROOT, check=True)
    print(json.dumps({"extracted_frames": len(shots), "index": str(qa / "frame-index.json")}))


if __name__ == "__main__":
    main()
