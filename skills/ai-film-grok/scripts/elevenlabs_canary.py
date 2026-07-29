#!/usr/bin/env python3
"""Bounded, auditable ElevenLabs bilingual TTS canary.

This module is deliberately separate from the general ``external`` backend:
the canary can make at most one paid request per approved language and records
only safe evidence.  It never reads a key from CLI arguments or writes one to
disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from security_policy import atomic_write_bytes, atomic_write_text
from util import utc_now

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
VOICES_URL = "https://api.elevenlabs.io/v1/voices"
DEFAULT_MODEL = "eleven_multilingual_v2"
RECEIPT_REL = Path("receipts/elevenlabs-canary")
ARMORY_REL = Path("receipts/voice-armory/elevenlabs.json")
SAMPLES = {
    "zh": "你好，这是中文角色声线测试。",
    "ja": "こんにちは、これは日本語の役声テストです。",
}
_VOICE_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


class ElevenLabsCanaryError(RuntimeError):
    pass


def _key() -> str:
    # Deliberately do not import config_loader: the user-directed environment
    # variable is the only credential source for this paid diagnostic.
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def _validate_voice_id(value: str) -> str:
    voice_id = value.strip()
    if not _VOICE_ID.fullmatch(voice_id) or voice_id.startswith("zh-CN-"):
        raise ElevenLabsCanaryError(
            "voice must be a real ElevenLabs voice ID, not an Edge Neural name"
        )
    return voice_id


def _request(url: str, *, key: str, body: bytes | None = None) -> bytes:
    req = urllib.request.Request(
        url,
        data=body,
        method="POST" if body is not None else "GET",
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg" if body is not None else "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        # Server detail may include account or request information; receipt
        # stores only the safe status code.
        raise ElevenLabsCanaryError(f"ELEVENLABS_HTTP_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ElevenLabsCanaryError("ELEVENLABS_NETWORK_ERROR") from exc


def list_voices() -> dict[str, Any]:
    """Return account voice metadata without persisting credentials."""
    key = _key()
    if not key:
        raise ElevenLabsCanaryError("ELEVENLABS_API_KEY_UNSET")
    try:
        payload = json.loads(_request(VOICES_URL, key=key).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ElevenLabsCanaryError("ELEVENLABS_VOICE_LIST_INVALID") from exc
    voices = payload.get("voices") if isinstance(payload, dict) else None
    if not isinstance(voices, list):
        raise ElevenLabsCanaryError("ELEVENLABS_VOICE_LIST_INVALID")
    return {
        "ok": True,
        "voices": [
            {
                "voice_id": str(v.get("voice_id") or ""),
                "name": str(v.get("name") or ""),
                "category": str(v.get("category") or ""),
                "labels": v.get("labels") if isinstance(v.get("labels"), dict) else {},
            }
            for v in voices
            if isinstance(v, dict) and _VOICE_ID.fullmatch(str(v.get("voice_id") or ""))
        ],
    }


def _audio_metrics(path: Path, *, chars: int) -> dict[str, Any]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ElevenLabsCanaryError("AUDIO_DECODE_FAILED") from exc
    if probe.returncode or duration <= 0:
        raise ElevenLabsCanaryError("AUDIO_DURATION_INVALID")

    volume = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    mean_match = re.search(r"mean_volume:\s*(-?[\d.]+) dB", volume.stderr)
    silence = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            str(path),
            "-af",
            "silencedetect=n=-45dB:d=0.1",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    silence_seconds = sum(
        float(item) for item in re.findall(r"silence_duration:\s*([\d.]+)", silence.stderr)
    )
    return {
        "decode_ok": True,
        "duration_sec": round(duration, 3),
        "mean_volume_db": float(mean_match.group(1)) if mean_match else None,
        "silence_ratio": round(min(1.0, silence_seconds / duration), 4),
        "speaking_rate_chars_per_sec": round(chars / duration, 3),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _load_armory(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "provider": "elevenlabs", "entries": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ElevenLabsCanaryError("ARMORY_CATALOG_INVALID") from exc
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        raise ElevenLabsCanaryError("ARMORY_CATALOG_INVALID")
    return value


def _upsert_candidate(root: Path, result: dict[str, Any]) -> Path:
    catalog_path = root / ARMORY_REL
    catalog = _load_armory(catalog_path)
    entries = [
        e
        for e in catalog["entries"]
        if not (
            isinstance(e, dict)
            and e.get("voice_id") == result["voice_id"]
            and e.get("language") == result["language"]
        )
    ]
    entries.append(
        {
            "profile_id": f"elevenlabs_{result['language']}_{result['voice_id']}",
            "provider": "elevenlabs",
            "backend": "external",
            "voice_id": result["voice_id"],
            "language": result["language"],
            "model": result["model"],
            "status": "candidate",
            "human_review": "required",
            "allowed_use": "character_dialogue_only",
            "forbidden_use": "zh_narration",
            "sample_sha256": result["sha256"],
            "verified_at": result["verified_at"],
        }
    )
    catalog["entries"] = entries
    catalog["updated_at"] = utc_now()
    _write_json(catalog_path, catalog)
    return catalog_path


def review_candidate(root: Path, *, language: str, decision: str) -> dict[str, Any]:
    if language not in SAMPLES or decision not in {"approve", "reject"}:
        raise ElevenLabsCanaryError("review requires zh|ja and approve|reject")
    path = Path(root).expanduser().resolve() / ARMORY_REL
    catalog = _load_armory(path)
    matches = [
        e for e in catalog["entries"] if isinstance(e, dict) and e.get("language") == language
    ]
    if len(matches) != 1:
        raise ElevenLabsCanaryError("ARMORY_CANDIDATE_NOT_UNIQUE")
    entry = matches[0]
    entry["status"] = "ready" if decision == "approve" else "rejected"
    entry["human_review"] = decision
    entry["reviewed_at"] = utc_now()
    _write_json(path, catalog)
    return {"ok": True, "catalog": str(path), "language": language, "status": entry["status"]}


def run_canary(
    root: Path, *, zh_voice: str, ja_voice: str, model: str, confirm_cost: bool, max_paid_calls: int
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    if not confirm_cost:
        raise ElevenLabsCanaryError("COST_CONFIRMATION_REQUIRED")
    if max_paid_calls != 2:
        raise ElevenLabsCanaryError("CANARY_REQUIRES_MAX_PAID_CALLS_2")
    voice_by_language = {"zh": _validate_voice_id(zh_voice), "ja": _validate_voice_id(ja_voice)}
    key = _key()
    receipt_path = root / RECEIPT_REL / "receipt.json"
    report: dict[str, Any] = {
        "schema_version": 1,
        "provider": "elevenlabs",
        "model": model,
        "max_paid_calls": 2,
        "no_retry": True,
        "created_at": utc_now(),
        "results": [],
    }
    if not key:
        report.update(
            {
                "ok": False,
                "status": "blocked",
                "reason": "ELEVENLABS_API_KEY_UNSET",
                "paid_calls_attempted": 0,
            }
        )
        _write_json(receipt_path, report)
        return report | {"receipt_path": str(receipt_path)}

    for language in ("zh", "ja"):
        text = SAMPLES[language]
        voice_id = voice_by_language[language]
        out = root / RECEIPT_REL / f"{language}.mp3"
        try:
            payload = json.dumps({"text": text, "model_id": model}).encode("utf-8")
            audio = _request(API_URL.format(voice_id=voice_id), key=key, body=payload)
            if len(audio) < 200:
                raise ElevenLabsCanaryError("AUDIO_TINY")
            atomic_write_bytes(out, audio)
            metrics = _audio_metrics(out, chars=len(text))
            result = {
                "language": language,
                "voice_id": voice_id,
                "model": model,
                "status": "ready-candidate",
                "human_review": "required",
                "path": str(out),
                "sha256": hashlib.sha256(audio).hexdigest(),
                "bytes": len(audio),
                "verified_at": utc_now(),
                "metrics": metrics,
            }
            result["armory_catalog"] = str(_upsert_candidate(root, result))
            report["results"].append(result)
        except ElevenLabsCanaryError as exc:
            report["results"].append(
                {
                    "language": language,
                    "voice_id": voice_id,
                    "status": "blocked",
                    "reason": str(exc),
                }
            )
            break  # no retry and no further paid call after a failure
    report["paid_calls_attempted"] = len(report["results"])
    report["ok"] = len(report["results"]) == 2 and all(
        r["status"] == "ready-candidate" for r in report["results"]
    )
    report["status"] = "ready-candidate" if report["ok"] else "blocked"
    _write_json(receipt_path, report)
    return report | {"receipt_path": str(receipt_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded ElevenLabs bilingual TTS canary")
    parser.add_argument("--root", required=True)
    parser.add_argument("--zh-voice")
    parser.add_argument("--ja-voice")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--confirm-cost", action="store_true")
    parser.add_argument("--max-paid-calls", type=int, default=0)
    parser.add_argument("--review-language", choices=("zh", "ja"))
    parser.add_argument("--decision", choices=("approve", "reject"))
    parser.add_argument("--list-voices", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.list_voices:
            payload = list_voices()
        elif args.review_language or args.decision:
            if not args.review_language or not args.decision:
                raise ElevenLabsCanaryError("review requires --review-language and --decision")
            payload = review_candidate(
                Path(args.root), language=args.review_language, decision=args.decision
            )
        else:
            if not args.zh_voice or not args.ja_voice:
                raise ElevenLabsCanaryError("run requires --zh-voice and --ja-voice")
            payload = run_canary(
                Path(args.root),
                zh_voice=args.zh_voice,
                ja_voice=args.ja_voice,
                model=args.model,
                confirm_cost=args.confirm_cost,
                max_paid_calls=args.max_paid_calls,
            )
    except ElevenLabsCanaryError as exc:
        payload = {"ok": False, "status": "blocked", "reason": str(exc)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
