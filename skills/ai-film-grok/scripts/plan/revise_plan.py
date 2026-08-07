"""Defect class → minimal regeneration unit (Film Production OS W6).

Default: fix the smallest production unit; never regenerate whole scene for local defects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

# defect → recommended action + unit scope
DEFECT_ROUTES: dict[str, dict[str, str]] = {
    "face": {
        "action": "face_repair",
        "unit": "shot_region",
        "description": "face identity / drift — repair or re-still + I2V same shot",
    },
    "hand": {
        "action": "regional_regeneration",
        "unit": "shot_region",
        "description": "hands/anatomy region — regional regen or inpaint",
    },
    "performance": {
        "action": "new_take",
        "unit": "take",
        "description": "acting/energy wrong — new take, keep shot card",
    },
    "camera": {
        "action": "regenerate_shot",
        "unit": "shot",
        "description": "framing/motion wrong — re-I2V this shot only",
    },
    "continuity": {
        "action": "regenerate_transition_shots",
        "unit": "shot_pair",
        "description": "continuity break — regen affected join shots, not whole scene",
    },
    "dialogue": {
        "action": "adr_or_native_retake",
        "unit": "audio",
        "description": "dialogue problem — ADR / native retake; avoid full visual regen",
    },
    "background": {
        "action": "inpaint_or_composite",
        "unit": "shot_region",
        "description": "bg artifact — inpaint/composite",
    },
    "timing": {
        "action": "edit_retime",
        "unit": "edit",
        "description": "timing — cut/retime in editor; no regen",
    },
    "wardrobe": {
        "action": "restill_no_redress",
        "unit": "shot",
        "description": "wardrobe continuity — re-still from undress-anchor; no redress",
    },
    "motion": {
        "action": "regenerate_motion",
        "unit": "shot",
        "description": "mean/motion low — re-I2V / alt mode; keep keyframe if ok",
    },
}


def plan_revision(
    *,
    defect: str,
    shot_id: str = "",
    scene_id: str = "",
    notes: str = "",
) -> dict[str, Any]:
    key = str(defect or "").strip().lower().replace("-", "_")
    # aliases
    aliases = {
        "faces": "face",
        "hands": "hand",
        "acting": "performance",
        "audio": "dialogue",
        "bg": "background",
        "pace": "timing",
        "duration": "timing",
        "clothing": "wardrobe",
        "dress": "wardrobe",
    }
    key = aliases.get(key, key)
    if key not in DEFECT_ROUTES:
        return {
            "ok": False,
            "error": f"unknown defect {defect!r}; known={sorted(DEFECT_ROUTES)}",
            "known_defects": sorted(DEFECT_ROUTES),
        }
    route = DEFECT_ROUTES[key]
    # Guard: never expand to whole scene for local units
    forbidden_whole_scene = route["unit"] in {
        "shot_region",
        "take",
        "audio",
        "edit",
        "shot",
        "shot_pair",
    }
    return {
        "ok": True,
        "kind": "revise-plan",
        "defect": key,
        "shot_id": shot_id or None,
        "scene_id": scene_id or None,
        "action": route["action"],
        "unit": route["unit"],
        "description": route["description"],
        "notes": notes or None,
        "regenerate_whole_scene": False,
        "forbids_whole_scene_default": forbidden_whole_scene,
        "at": utc_now(),
    }


def revise_plan_at_root(
    root: Path | str,
    *,
    defect: str,
    shot_id: str = "",
    scene_id: str = "",
    notes: str = "",
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    report = plan_revision(
        defect=defect, shot_id=shot_id, scene_id=scene_id, notes=notes
    )
    report["root"] = str(root_p)
    if write_receipt and report.get("ok"):
        path = root_p / "receipts" / "revise-plan.json"
        # append history
        hist = read_json(path) or {"kind": "revise-plan-log", "entries": []}
        if not isinstance(hist, dict):
            hist = {"kind": "revise-plan-log", "entries": []}
        entries = hist.setdefault("entries", [])
        if isinstance(entries, list):
            entries.append(report)
        write_json(path, hist)
        report["receipt"] = str(path)
    return report
