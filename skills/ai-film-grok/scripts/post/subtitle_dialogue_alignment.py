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
            start = cursor + float((delivery or {}).get("start_sec") or 0)
            end = cursor + float((delivery or {}).get("timestamp_sec") or 0)
            shot_end = cursor + duration
            overlapping = [cue for cue in cues if cue[0] <= end and cue[1] >= start]
            area = (
                (shot.get("safe_area") or (shot.get("dsl") or {}).get("safe_area") or {})
                if isinstance(shot, dict)
                else {}
            )
            rows.append(
                {
                    "shot_id": sid,
                    "speech_start_sec": round(start, 3),
                    "speech_end_sec": round(end, 3),
                    "cue_count": len(overlapping),
                }
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
            for cue_start, cue_end in overlapping:
                if cue_start < cursor or cue_end > shot_end:
                    errors.append(
                        {
                            "code": "SUBTITLE_OUTSIDE_SHOT_WINDOW",
                            "shot_id": sid,
                            "message": "subtitle cue must be contained by its shot window",
                        }
                    )
                if cue_start < start or cue_end > end:
                    errors.append(
                        {
                            "code": "SUBTITLE_OUTSIDE_DIALOGUE_WINDOW",
                            "shot_id": sid,
                            "message": "dialogue subtitle cue must be contained by its dialogue window",
                        }
                    )
            if (
                not isinstance(area, dict)
                or "subtitle_clear" not in area
                or "subject_clear" not in area
            ):
                errors.append(
                    {
                        "code": "SUBTITLE_SAFE_AREA_UNCLEAR",
                        "shot_id": sid,
                        "message": "dialogue shot must explicitly declare boolean subtitle_clear and subject_clear",
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


def align_sub_sentence_phonemes(
    text: str,
    duration_sec: float,
    *,
    boundary_receipts: list[dict[str, Any]] | None = None,
    start_offset_sec: float = 0.0,
) -> list[dict[str, Any]]:
    """Align words/sub-sentences to timestamps with sub-second precision for lip-sync."""
    text = text.strip()
    if not text or duration_sec <= 0.0:
        return []

    # If boundary receipts exist from TTS, parse exact timestamps
    if boundary_receipts:
        out = []
        for item in boundary_receipts:
            w = str(item.get("word") or item.get("text") or "").strip()
            t0 = start_offset_sec + float(item.get("start_sec") or item.get("start") or 0.0)
            t1 = start_offset_sec + float(item.get("end_sec") or item.get("end") or 0.0)
            if w:
                out.append({"text": w, "start": round(t0, 3), "end": round(t1, 3)})
        if out:
            return out

    # Character-weighted interpolation
    parts = [p.strip() for p in re.split(r"([，。！？\s,!?])", text) if p.strip()]
    chunks = []
    curr = ""
    for p in parts:
        curr += p
        if any(punct in p for punct in "，。！？,!?"):
            chunks.append(curr.strip())
            curr = ""
    if curr.strip():
        chunks.append(curr.strip())

    total_chars = max(1, sum(len(c) for c in chunks))
    cur_t = start_offset_sec
    aligned = []
    for c in chunks:
        ratio = len(c) / total_chars
        seg_dur = duration_sec * ratio
        end_t = cur_t + seg_dur
        aligned.append({"text": c, "start": round(cur_t, 3), "end": round(end_t, 3)})
        cur_t = end_t
    return aligned
