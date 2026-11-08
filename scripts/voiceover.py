"""Approved Relay narration: safe voice discovery and one continuous generation.

No credential, HTTP header or unfiltered remote error is printed or saved.
Existing audio is reused only when its canonical script matches; no automatic
generation retry is performed after a timeout or provider error.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import time
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.elevenlabs.io"


class VoiceError(RuntimeError):
    def __init__(self, message, safe_fields=None):
        super().__init__(message)
        self.safe_fields = safe_fields or {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(source, out):
    source_text = source.read_text()
    sections, current = [], None
    paragraphs = re.split(r"\n\s*\n", source_text.strip())
    headed = bool(re.fullmatch(r"\d+\.\s+[^\n]+", paragraphs[0].strip()))
    # The reviewed credit-fit option has no spoken headings. Its five exact
    # section anchors preserve the same framework without adding spoken words.
    anchors = [("1. THE PROBLEM", "Messages are failing"), ("2. THE EXISTING SOLUTION", "Today, engineers"),
               ("3. WHY IT FALLS SHORT", "A healthy cloud connection"), ("4. OUR SOLUTION", "Relay connects"),
               ("5. THE PAYOFF", "Run the same test again")]
    for paragraph in paragraphs:
        if not headed:
            match = next((heading for heading, anchor in anchors if paragraph.strip().startswith(anchor)), None)
            if match:
                current = {"heading": match, "paragraphs": []}
                sections.append(current)
            if current is None:
                raise VoiceError("Unheaded approved source lacks its known framework anchors")
            current["paragraphs"].append(paragraph.strip())
            continue
        if re.fullmatch(r"\d+\.\s+[^\n]+", paragraph.strip()):
            current = {"heading": paragraph.strip(), "paragraphs": []}
            sections.append(current)
        else:
            if current is None:
                raise VoiceError("Approved source must begin with a section heading")
            current["paragraphs"].append(paragraph.strip())
    if len(sections) != 5 or any(not section["paragraphs"] for section in sections):
        raise VoiceError("Expected the approved five complete sections")
    spoken = "\n\n".join(p for section in sections for p in section["paragraphs"]) + "\n"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "narration-script.txt"
    if (out / "narration-original.mp3").exists() and target.read_text() != spoken:
        raise VoiceError("Existing generation belongs to a different script; preserved without overwrite")
    target.write_text(spoken)
    plan = {"status": "USER_APPROVED_SCRIPT", "source": str(source.relative_to(ROOT)),
            "source_sha256": sha(source_text.encode()), "script_sha256": sha(spoken.encode()),
            "spoken_headings": False, "words": len(spoken.split()), "characters": len(spoken.strip()),
            "sections": sections, "one_continuous_generation": True, "tempo_factor": 1.0}
    (out / "approved-script.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    return plan


def credentials(path):
    if path.stat().st_mode & 0o077:
        raise VoiceError("Private credential file permissions must be 0600")
    value = path.read_text().strip()
    if not value:
        raise VoiceError("Private credential file is empty")
    return value


def call(key, method, path, body=None, timeout=45):
    if not path.startswith(("/v2/voices", "/v1/voices", "/v1/text-to-speech/", "/v1/models")):
        raise VoiceError("Endpoint outside the speech workflow")
    req = request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                          headers={"xi-api-key": key, "content-type": "application/json"}, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.load(response), {"request_id": response.headers.get("request-id") or response.headers.get("x-request-id")}
    except error.HTTPError as exc:
        fields = {"http_status": exc.code}
        try:
            remote = json.load(exc)
            detail = remote.get("detail") or {}
            if isinstance(detail, dict):
                code = detail.get("status") or detail.get("code") or remote.get("code")
                message = detail.get("message") or remote.get("message")
                def sanitize(value):
                    value = str(value or "").replace(key, "[redacted]")
                    return re.sub(r"(?:sk_[A-Za-z0-9_-]+|Bearer\s+\S+)", "[redacted]", value)[:400]
                fields.update(code=sanitize(code), message=sanitize(message))
        except (ValueError, AttributeError):
            pass
        raise VoiceError(f"ElevenLabs returned HTTP {exc.code}; no automatic retry", fields) from None
    except (OSError, ValueError, TimeoutError):
        raise VoiceError("Speech request failed or timed out; no automatic retry. Check existing history before another generation") from None


def list_voices(key, out):
    params = parse.urlencode({"page_size": 100, "voice_type": "default", "include_total_count": "false"})
    result, _ = call(key, "GET", "/v2/voices?" + params)
    voices = [{k: voice.get(k) for k in ("voice_id", "name", "category", "labels", "description", "high_quality_base_model_ids")}
              for voice in result.get("voices", [])]
    if not voices:
        raise VoiceError("No available default voices returned; no generation attempted")
    (out / "available-default-voices.json").write_text(json.dumps(voices, indent=2, ensure_ascii=False) + "\n")
    return voices


def generate(key, out, voice_id, model_id="eleven_multilingual_v2"):
    plan = json.loads((out / "approved-script.json").read_text())
    spoken = (out / "narration-script.txt").read_text()
    if plan["status"] not in ("USER_APPROVED_V3", "USER_APPROVED_SCRIPT") or sha(spoken.encode()) != plan["script_sha256"]:
        raise VoiceError("Canonical text differs from the approved preparation")
    meta_path = out / "generation-metadata.json"
    if (out / "narration-original.mp3").exists():
        meta = json.loads(meta_path.read_text())
        if meta["script_sha256"] == plan["script_sha256"] and meta["voice_id"] == voice_id:
            return {"reused": True, "voice_name": meta["voice_name"], "voice_id": voice_id}
        raise VoiceError("Existing audio preserved; no replacement generation permitted")
    voices = json.loads((out / "available-default-voices.json").read_text())
    voice = next((voice for voice in voices if voice["voice_id"] == voice_id), None)
    if voice is None:
        raise VoiceError("Selected voice was not in the available default voice list")
    settings = {"stability": .43, "similarity_boost": .75, "style": .10, "use_speaker_boost": True, "speed": 1.0}
    intent = {"started_at_unix": time.time(), "voice_id": voice_id, "voice_name": voice["name"],
              "model_id": model_id, "script_sha256": plan["script_sha256"], "characters": len(spoken.strip()),
              "request_count": 1, "automatic_retry": False, "voice_settings": settings}
    intent_path = out / "generation-intent.json"
    if intent_path.exists():
        raise VoiceError("A generation was already attempted; inspect its result/history before any paid retry")
    intent_path.write_text(json.dumps(intent, indent=2) + "\n")
    payload = {"text": spoken.strip(), "model_id": model_id, "voice_settings": settings,
               "apply_text_normalization": "auto", "seed": 40819}
    try:
        result, safe_headers = call(key, "POST", "/v1/text-to-speech/" + parse.quote(voice_id, safe="") +
                                   "/with-timestamps?output_format=mp3_44100_128", payload, timeout=240)
    except VoiceError as exc:
        (out / "generation-failure.json").write_text(json.dumps({"at_unix": time.time(),
                "script_sha256": plan["script_sha256"], **exc.safe_fields}, indent=2) + "\n")
        raise
    if not isinstance(result.get("audio_base64"), str):
        raise VoiceError("Provider did not return audio; no retry attempted")
    audio = base64.b64decode(result["audio_base64"], validate=True)
    if len(audio) < 1000:
        raise VoiceError("Provider audio is unexpectedly short; preserved request identity, no retry")
    (out / "narration-original.mp3").write_bytes(audio)
    alignments = {k: result.get(k) for k in ("alignment", "normalized_alignment")}
    (out / "provider-alignment.json").write_text(json.dumps(alignments, ensure_ascii=False) + "\n")
    meta = {**intent, **safe_headers, "completed_at_unix": time.time(), "provider": "ElevenLabs",
            "endpoint": "/v1/text-to-speech/{voice_id}/with-timestamps", "original_audio_sha256": sha(audio),
            "bytes": len(audio), "one_continuous_generation": True, "native_tempo_factor": 1.0,
            "voice_labels": voice.get("labels"), "ai_generated_narration": True}
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    return {k: meta[k] for k in ("voice_name", "voice_id", "bytes", "script_sha256", "one_continuous_generation")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "voices", "generate"))
    parser.add_argument("--source", type=Path, default=ROOT / "demo/mattermost-script-v3.txt")
    parser.add_argument("--output", type=Path, default=ROOT / "demo/final")
    parser.add_argument("--key-file", type=Path, default=ROOT / ".runtime/elevenlabs.key")
    parser.add_argument("--voice-id")
    parser.add_argument("--model-id", default="eleven_multilingual_v2")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            plan = prepare(args.source, args.output)
            print(json.dumps({k: plan[k] for k in ("status", "words", "characters", "script_sha256")}))
        elif args.command == "voices":
            voices = list_voices(credentials(args.key_file), args.output)
            male = [voice for voice in voices if str((voice.get("labels") or {}).get("gender", "")).lower() == "male"]
            print(json.dumps(male, indent=2, ensure_ascii=False))
        else:
            if not args.voice_id:
                raise VoiceError("Explicit selected voice ID is required")
            print(json.dumps(generate(credentials(args.key_file), args.output, args.voice_id, args.model_id)))
    except (VoiceError, OSError, ValueError, KeyError) as exc:
        print(str(exc) if isinstance(exc, VoiceError) else "Local speech preparation validation failed (" + type(exc).__name__ + ")", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
