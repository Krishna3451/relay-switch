"""Curate only user-facing deliverables; exclude catalogs/account/API metadata."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "demo/final")
    args = parser.parse_args()
    out = args.output
    assembly = json.loads((out / "assembly-manifest.json").read_text())
    audio = json.loads((out / "audio-checks.json").read_text())
    review = json.loads((out / "qa/review-report.json").read_text())
    if review.get("passed") is not True:
        raise ValueError("Independent visual review must pass before delivery")
    if not audio["passed"] or not assembly["continuous_audio_copied"]:
        raise ValueError("Verified audio and assembly are required before packaging")
    evidence = ROOT / assembly["outcome_review"]["evidence_file"]
    if hashlib.sha256(evidence.read_bytes()).hexdigest() != assembly["outcome_review"]["evidence_sha256"] or json.loads(evidence.read_text()).get("passed") is not True:
        raise ValueError("Recorded native evidence changed after assembly")
    delivery = out / "delivery"
    delivery.mkdir(exist_ok=True)
    curated = {"Relay-demo.mp4", "Relay-demo.srt", "Relay-voiceover.mp3", "narration-script.txt",
               "video-description.txt", "START-HERE.txt", "delivery-checks.json"}
    if any(file.name not in curated for file in delivery.iterdir()):
        raise ValueError("Delivery folder contains an unreviewed file; preserving it instead of packaging")
    for source, target in [("Relay-demo.mp4", "Relay-demo.mp4"), ("Relay-demo.srt", "Relay-demo.srt"),
                           ("narration.mp3", "Relay-voiceover.mp3"), ("narration-script.txt", "narration-script.txt")]:
        shutil.copyfile(out / source, delivery / target)
    description = ("Relay connects two fictional companies, TeamChat and HarborCloud, during a shared incident. "
        "A presenter plays Maya and Leo through their enrolled Mattermost accounts; their approvals are scripted presenter inputs. "
        "The agents investigate actual local HTTP services, exchange owner-reviewed findings through real Switch events, and carry out separately approved recovery actions. "
        "The recorded checks distinguish a repaired cloud connection from reliable chat delivery, then verify 24 of 24 messages and a same-ID retry persisted once. "
        "Editorial opening cards are labelled. The video shortens reviewed static waits and holds real frames for reading; selected message arrivals retain their captured cadence. "
        "Narration is AI-generated with ElevenLabs Will at normal speed. This is a bounded local causal adaptation, not an AWS or Slack emulator, and it does not establish superiority over one agent with equivalent access.\n")
    (delivery / "video-description.txt").write_text(description)
    (delivery / "START-HERE.txt").write_text(
        "RELAY — NATIVE MATTERMOST DEMO\n\nPlay Relay-demo.mp4.\n"
        f"Full 1920×1080 landscape, 24 fps. Duration {assembly['duration']:.3f} seconds.\n"
        "One continuous 356-word Will narration at normal pace; optional English captions are embedded and also supplied alongside.\n"
        "Relay-voiceover.mp3 is the standalone mastered narration.\n"
        "See video-description.txt for fictional-roleplay and editing disclosures.\n"
        "Provider catalogs, account information and credentials are excluded from this delivery folder.\n")
    check = {"duration_seconds": assembly["duration"], "dimensions": assembly["output_dimensions"], "fps": assembly["fps"],
             "continuous_audio_copied": assembly["continuous_audio_copied"], "native_tempo_factor": 1.0,
             "full_decode_check": assembly["full_decode_check"],
             "independent_visual_review_passed": review["passed"],
             "approved_script_sha256": assembly["narration_sha256"], "actual_native_outcome_verified": True,
             "files": {file.name: {"sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "bytes": file.stat().st_size}
                       for file in delivery.iterdir() if file.is_file() and file.name != "delivery-checks.json"}}
    (delivery / "delivery-checks.json").write_text(json.dumps(check, indent=2) + "\n")
    with zipfile.ZipFile(out / "Relay-demo-pack.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(delivery.iterdir()):
            if file.is_file():
                archive.write(file, file.name)
    print(json.dumps({"video": str(delivery / "Relay-demo.mp4"), "package": str(out / "Relay-demo-pack.zip")}))


if __name__ == "__main__":
    main()
