"""Cross-check the final audio, dialogue, subtitle and shot timeline evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subtitle_dialogue_alignment import build_subtitle_dialogue_alignment
from util import read_json, write_json


def build_audio_visual_alignment(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    subtitle = build_subtitle_dialogue_alignment(root, write=False)
    receipts = root / "receipts"
    mix = read_json(receipts / "mix_report.json") or {}
    tts = read_json(receipts / "tts-rehearsal.json") or {}
    errors: list[dict[str, str]] = list(subtitle.get("errors") or [])
    timeline = read_json(root / "timeline.json") or {}
    has_shots = bool(timeline.get("shots"))
    if has_shots and not mix:
        errors.append(
            {
                "code": "AUDIO_MIX_REPORT_MISSING",
                "message": "timeline exists but receipts/mix_report.json is missing",
            }
        )
    if tts and tts.get("ok") is False:
        errors.append(
            {"code": "TTS_REHEARSAL_FAILED", "message": "tts rehearsal receipt is not valid"}
        )
    report = {
        "schema_version": 1,
        "kind": "audio-visual-alignment",
        "ok": not errors,
        "subtitle_alignment": subtitle,
        "audio": {
            "mix_report_present": bool(mix),
            "mix_report_path": str(receipts / "mix_report.json") if mix else None,
            "tts_rehearsal_present": bool(tts),
        },
        "errors": errors,
        "limitation": "Timing and receipts are machine-checked; audible mix quality still requires human review.",
    }
    if write:
        path = receipts / "audio-visual-alignment.json"
        write_json(path, report)
        report["path"] = str(path)
    return report
