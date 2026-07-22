#!/usr/bin/env python3
"""Check that subtitles cover spoken lipsync dialogue without ignoring safe-area intent."""

import re
from pathlib import Path
from typing import Any

from performance_evidence import find_shot, performance_contract
from util import read_json, write_json

_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})")


def _sec(part: tuple[str, str, str, str]) -> float:
    h, m, s, ms = (int(v) for v in part)
    return h * 3600 + m * 60 + s + ms / 1000


def _cues(path: Path) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "-->" in line:
            found = _TIME.findall(line)
            if len(found) == 2:
                out.append((_sec(found[0]), _sec(found[1])))
    return out


def build_subtitle_dialogue_alignment(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    srt = next((p for p in (root / "out" / "final.srt", root / "final.srt") if p.is_file()), None)
    timeline = read_json(root / "timeline.json") or {}
    cursor, required = 0.0, 0
    errors: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    cues = _cues(srt) if srt else []
    for item in timeline.get("shots") or []:
        if not isinstance(item, dict):
            continue
        sid, duration = str(item.get("id") or ""), float(item.get("duration_sec") or 0)
        shot, strict = find_shot(root, sid)
        contract = performance_contract(shot, required=strict)
        voice = contract.get("channels", {}).get("voice", {})
        if voice.get("kind") == "dialogue" and voice.get("lipsync") is True:
            required += 1
            review = read_json(root / "receipts" / "reviews" / f"{sid}.json") or {}
            evidence = (review.get("performance_contract") or {}).get("evidence") or {}
            delivery = evidence.get("dialogue_delivery") if isinstance(evidence, dict) else None
            end = cursor + float((delivery or {}).get("timestamp_sec") or 0)
            overlapping = [cue for cue in cues if cue[0] <= end and cue[1] >= cursor]
            area = (
                (shot.get("safe_area") or (shot.get("dsl") or {}).get("safe_area") or {})
                if isinstance(shot, dict)
                else {}
            )
            rows.append(
                {"shot_id": sid, "speech_end_sec": round(end, 3), "cue_count": len(overlapping)}
            )
            if not srt or not overlapping:
                errors.append(
                    {
                        "code": "DIALOGUE_SUBTITLE_MISSING",
                        "shot_id": sid,
                        "message": "no subtitle cue covers lipsync dialogue",
                    }
                )
            elif max(cue[1] for cue in overlapping) + 0.05 < end:
                errors.append(
                    {
                        "code": "SUBTITLE_ENDS_BEFORE_DIALOGUE",
                        "shot_id": sid,
                        "message": "subtitle disappears before delivered dialogue ends",
                    }
                )
            if (
                not isinstance(area, dict)
                or area.get("subtitle_clear") is not True
                or area.get("subject_clear") is not True
            ):
                errors.append(
                    {
                        "code": "SUBTITLE_SAFE_AREA_UNCLEAR",
                        "shot_id": sid,
                        "message": "dialogue shot must declare subtitle_clear and subject_clear",
                    }
                )
        cursor += duration
    report = {
        "schema_version": 1,
        "kind": "subtitle-dialogue-alignment",
        "required": bool(required),
        "ok": not errors,
        "srt": str(srt) if srt else None,
        "shots": rows,
        "errors": errors,
        "limitation": "Cue timing and authored safe-area declarations are checked; actual visual occlusion still requires human review.",
    }
    if write:
        path = root / "receipts" / "subtitle-dialogue-alignment.json"
        write_json(path, report)
        report["path"] = str(path)
    return report
