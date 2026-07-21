#!/usr/bin/env python3
"""Single-shot lipsync canary (craft Media/Verified safety).

Does not change default final --lipsync off. Writes receipts/lipsync-canary.json.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LipsyncCanaryError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def run_lipsync_canary(
    root: Path,
    *,
    shot_id: str,
    backend: str = "auto",
    video: Path | None = None,
    audio: Path | None = None,
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    shot_id = str(shot_id).strip()
    if not shot_id:
        raise LipsyncCanaryError("shot_id required")

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    from lipsync_backend import lipsync_one, probe, resolve_backend

    info = probe()
    ready = info.get("ready") or []
    report: dict[str, Any] = {
        "ok": False,
        "kind": "ai-film-lipsync-canary",
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": str(root),
        "shot_id": shot_id,
        "probe": {
            "ready": ready,
            "wav2lip_root": info.get("wav2lip_root"),
            "musetalk_root": info.get("musetalk_root"),
            "backend_trust": info.get("backend_trust"),
        },
        "next_unlock": None,
    }

    if not ready:
        w2 = info.get("wav2lip_root")
        report["error"] = "no locked lipsync backend ready"
        report["next_unlock"] = (
            f'backend-lock inspect --backend wav2lip --root "{w2}" && '
            f'backend-lock lock --backend wav2lip --root "{w2}" --acknowledge-trusted-weights'
            if w2
            else "Install Wav2Lip weights + backend-lock (see references/lipsync.md / audio-fallback.md)"
        )
        outp = root / "receipts" / "lipsync-canary.json"
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["receipt_path"] = str(outp)
        return report

    man = _read_json(root / "manifest.json")
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    rec = clips.get(shot_id) if isinstance(clips.get(shot_id), dict) else {}

    face = Path(video).expanduser() if video else None
    if face is None and rec.get("path"):
        face = Path(str(rec["path"]))
    if face is None and (root / "clips").is_dir():
        for c in sorted((root / "clips").glob(f"{shot_id}*")):
            if c.suffix.lower() in {".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".webp"}:
                face = c
                break
    if face is None or not face.is_file():
        raise LipsyncCanaryError(
            f"no video/face for shot {shot_id!r}; pass --video or register-clip first"
        )

    aud = Path(audio).expanduser() if audio else None
    if aud is None:
        for p in (
            root / "audio" / "narration" / f"{shot_id}.wav",
            root / "audio" / "narration" / f"{shot_id}.mp3",
            root / "receipts" / "tts-rehearsal-audio" / f"{shot_id}.mp3",
            root / "receipts" / "tts-rehearsal-audio" / f"{shot_id}.wav",
            root / "audio" / "narration.wav",
        ):
            if p.is_file():
                aud = p
                break
    if aud is None or not aud.is_file():
        raise LipsyncCanaryError(
            f"no audio for shot {shot_id!r}; run tts-rehearse or pass --audio"
        )

    be = resolve_backend(backend)
    if be == "off":
        raise LipsyncCanaryError("backend resolved to off — lock a backend first")

    out_dir = root / "receipts" / "lipsync-canary"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / f"{shot_id}-{be}.mp4"

    try:
        result = lipsync_one(video=face, audio=aud, out=out_mp4, backend=be)
        report["result"] = result
        report["ok"] = bool(result.get("ok")) and out_mp4.is_file()
        report["backend_used"] = result.get("backend") or be
        report["output"] = str(out_mp4) if out_mp4.is_file() else result.get("out")
        if report["ok"] and out_mp4.is_file():
            report["bytes"] = out_mp4.stat().st_size
            report["note"] = "Watch face for warp/jitter before final --lipsync auto"
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["error"] = str(exc)[:500]
        report["output"] = str(out_mp4) if out_mp4.is_file() else None

    outp = root / "receipts" / "lipsync-canary.json"
    outp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["receipt_path"] = str(outp)
    return report
