#!/usr/bin/env python3
"""Reject subtitle cues that carry old-shot text across hard editorial boundaries."""

from pathlib import Path
from typing import Any

from subtitle_dialogue_alignment import _cues
from util import read_json, write_json


def build_subtitle_cut_boundaries(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    timeline = read_json(root / "timeline.json") or {}
    srt = next((p for p in (root / "out" / "final.srt", root / "final.srt") if p.is_file()), None)
    shots = [item for item in timeline.get("shots") or [] if isinstance(item, dict)]
    # Prefer composition / package film_timeline (title pad + xfade clock = SRT clock)
    film_tl: dict[str, Any] = {}
    for rel in (
        "compose/hyperframes/composition-data.json",
        "compose/composition-package.json",
        "out/_final_work/film_timeline.json",
        "receipts/film_timeline.json",
    ):
        pkg = read_json(root / rel) or {}
        cand = pkg.get("film_timeline") if isinstance(pkg.get("film_timeline"), dict) else pkg
        if isinstance(cand, dict) and cand.get("shot_starts"):
            film_tl = cand
            break
    shot_starts = (
        [float(x) for x in film_tl.get("shot_starts") or []]
        if isinstance(film_tl.get("shot_starts"), list)
        else []
    )
    title_dur = float(
        film_tl.get("title_duration")
        or spec.get("title_duration")
        or spec.get("title_dur")
        or 0.0
    )
    spec_shots = {
        str(shot.get("id")): shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict) and str(shot.get("id") or "")
    }
    intents = (
        spec.get("transition_intents") if isinstance(spec.get("transition_intents"), list) else []
    )
    carryovers = (
        spec.get("subtitle_carryovers") if isinstance(spec.get("subtitle_carryovers"), list) else []
    )
    boundaries: list[dict[str, Any]] = []
    # Absolute cut times on the final/SRT clock (with title pad when known)
    if len(shot_starts) >= 2:
        for index in range(len(shot_starts) - 1):
            next_id = (
                str(shots[index + 1].get("id") or "")
                if index + 1 < len(shots)
                else f"shot{index+2:02d}"
            )
            from_id = (
                str(shots[index].get("id") or "")
                if index < len(shots)
                else f"shot{index+1:02d}"
            )
            next_shot = spec_shots.get(next_id, {})
            next_dsl = next_shot.get("dsl") if isinstance(next_shot.get("dsl"), dict) else {}
            chain = str(next_dsl.get("chain_mode") or "").lower()
            if (index < len(intents) and intents[index] == "hard") or chain in {
                "continue",
                "match",
                "byte",
            }:
                boundaries.append(
                    {
                        "sec": round(float(shot_starts[index + 1]), 3),
                        "from_shot_id": from_id,
                        "to_shot_id": next_id,
                        "clock": "film_timeline.shot_starts",
                    }
                )
    else:
        cursor = max(0.0, title_dur)
        for index, shot in enumerate(shots[:-1]):
            cursor += float(shot.get("duration_sec") or 0)
            next_shot = spec_shots.get(str(shots[index + 1].get("id") or ""), {})
            next_dsl = next_shot.get("dsl") if isinstance(next_shot.get("dsl"), dict) else {}
            chain = str(next_dsl.get("chain_mode") or "").lower()
            if (index < len(intents) and intents[index] == "hard") or chain in {
                "continue",
                "match",
                "byte",
            }:
                boundaries.append(
                    {
                        "sec": round(cursor, 3),
                        "from_shot_id": str(shot.get("id") or ""),
                        "to_shot_id": str(shots[index + 1].get("id") or ""),
                        "clock": "timeline.json+title_dur",
                    }
                )
    errors = []
    authorized = []
    for start, end in _cues(srt) if srt else []:
        for boundary in boundaries:
            if start < boundary["sec"] < end:
                permit = next(
                    (
                        item
                        for item in carryovers
                        if isinstance(item, dict)
                        and item.get("from_shot_id") == boundary["from_shot_id"]
                        and item.get("to_shot_id") == boundary["to_shot_id"]
                        and item.get("human_approved") is True
                        and str(item.get("reason") or "").strip()
                        and float(item.get("cue_start_sec") or -1) <= start
                        and float(item.get("cue_end_sec") or -1) >= end
                    ),
                    None,
                )
                if permit:
                    authorized.append(
                        {
                            "boundary_sec": boundary["sec"],
                            "reason": permit["reason"],
                            "cue": {"start_sec": start, "end_sec": end},
                        }
                    )
                    continue
                errors.append(
                    {
                        "code": "SUBTITLE_CROSSES_HARD_CUT",
                        "boundary_sec": boundary["sec"],
                        "message": "subtitle cue spans a hard/continue cut boundary",
                    }
                )
    report = {
        "schema_version": 1,
        "kind": "subtitle-cut-boundaries",
        "required": bool(boundaries),
        "ok": not errors,
        "srt": str(srt) if srt else None,
        "hard_boundaries": boundaries,
        "authorized_carryovers": authorized,
        "errors": errors,
        "limitation": "Checks authored timeline boundaries; human review still judges whether a deliberate carried subtitle is artistically justified.",
    }
    if write:
        path = root / "receipts" / "subtitle-cut-boundaries.json"
        write_json(path, report)
        report["path"] = str(path)
    return report
