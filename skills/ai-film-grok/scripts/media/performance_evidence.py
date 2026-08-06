#!/usr/bin/env python3
"""Human-observation evidence contract for authored performance channels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from content_channels import resolve_content_channels
from util import read_json


class PerformanceEvidenceError(ValueError):
    pass


EVIDENCE_KINDS = frozenset(
    {
        "action_visible",
        "dialogue_delivery",
        "end_state_visible",
        "mouth_still",
        "must_show_visible",
        "reaction_visible",
        "start_state_visible",
        "trigger_visible",
        "visible_change_visible",
    }
)


def _present(value: object) -> bool:
    return str(value or "").strip().lower() not in {
        "",
        "none",
        "n/a",
        "needs_authoring",
        "待补写",
        "无",
    }


def find_shot(root: Path, shot_id: str) -> tuple[dict[str, Any] | None, bool]:
    """Return the canonical shot and whether its project requires the contract."""
    spec = read_json(Path(root).expanduser().resolve() / "film-spec.json")
    if not isinstance(spec, dict):
        return None, False
    strict = spec.get("content_channels_strict") is True
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and str(shot.get("id") or "") == shot_id:
                return shot, strict or isinstance(shot.get("content_channels"), dict)
    return None, strict


def performance_contract(shot: dict[str, Any] | None, *, required: bool) -> dict[str, Any]:
    """Derive reviewable facts without claiming a machine can judge acting."""
    if not required or not isinstance(shot, dict):
        return {"required": False, "requirements": [], "channels": {}}
    channels = resolve_content_channels(shot)
    voice = channels["voice"]
    performance = channels["performance"]
    motion = channels["motion"]
    requirements: list[dict[str, str]] = []
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    # These are the director's observable promises.  They cannot be inferred
    # from a prompt or a thumbnail: the reviewer must point at the generated
    # clip where each promise is actually visible.
    for field, kind in (
        ("start_state", "start_state_visible"),
        ("must_show", "must_show_visible"),
        ("visible_change", "visible_change_visible"),
        ("end_state", "end_state_visible"),
    ):
        value = shot.get(field) or dsl.get(field)
        if _present(value):
            requirements.append({"kind": kind, "reason": field, "value": str(value).strip()})
    if _present(motion["scene_trigger"]) and motion["scene_trigger"] != "none":
        requirements.append(
            {
                "kind": "trigger_visible",
                "reason": "scene_trigger",
                "value": motion["scene_trigger"],
            }
        )
    if _present(performance["playable_action"]):
        requirements.append(
            {
                "kind": "action_visible",
                "reason": "playable_action",
                "value": performance["playable_action"],
            }
        )
    if _present(performance["reaction_trigger"]):
        requirements.extend(
            [
                {
                    "kind": "trigger_visible",
                    "reason": "reaction_trigger",
                    "value": performance["reaction_trigger"],
                },
                {
                    "kind": "reaction_visible",
                    "reason": "reaction_after_trigger",
                    "value": performance["reaction_trigger"],
                },
            ]
        )
    if voice["kind"] == "dialogue" and voice["lipsync"]:
        requirements.append(
            {"kind": "dialogue_delivery", "reason": "lipsync_dialogue", "value": voice["text"]}
        )
    if voice["kind"] == "narration" and not voice["lipsync"] and voice["on_camera"]:
        requirements.append(
            {"kind": "mouth_still", "reason": "off_lipsync_narration", "value": voice["text"]}
        )
    return {"required": True, "requirements": requirements, "channels": channels}


def parse_performance_evidence(
    values: list[str] | None, *, duration_sec: float
) -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    for raw in values or []:
        try:
            kind_part, rest = str(raw).split("@", 1)
            time_part, note = rest.split(":", 1)
            kind = kind_part.strip().lower()
            timestamp = float(time_part.strip())
        except (TypeError, ValueError):
            raise PerformanceEvidenceError(
                "performance evidence must use kind@seconds:note"
            ) from None
        if kind not in EVIDENCE_KINDS:
            raise PerformanceEvidenceError(f"unknown performance evidence kind: {kind}")
        if timestamp < 0 or timestamp > duration_sec:
            raise PerformanceEvidenceError(
                f"performance evidence timestamp for {kind} is outside clip duration"
            )
        if not note.strip():
            raise PerformanceEvidenceError(f"performance evidence note for {kind} is empty")
        if kind in parsed:
            raise PerformanceEvidenceError(f"duplicate performance evidence for {kind}")
        parsed[kind] = {"timestamp_sec": round(timestamp, 3), "note": note.strip()}
    return parsed


def validate_performance_evidence(
    contract: dict[str, Any], evidence: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    requirements = contract.get("requirements") or []
    required_kinds = {
        item["kind"] for item in requirements if isinstance(item, dict) and item.get("kind")
    }
    codes: list[str] = []
    missing = sorted(required_kinds - set(evidence))
    if missing:
        codes.append("PERFORMANCE_EVIDENCE_MISSING")
    trigger = evidence.get("trigger_visible")
    reaction = evidence.get("reaction_visible")
    action = evidence.get("action_visible")
    if trigger and reaction and reaction["timestamp_sec"] < trigger["timestamp_sec"]:
        codes.append("REACTION_BEFORE_TRIGGER")
    if trigger and action and action["timestamp_sec"] < trigger["timestamp_sec"]:
        codes.append("ACTION_BEFORE_TRIGGER")
    start = evidence.get("start_state_visible")
    end = evidence.get("end_state_visible")
    change = evidence.get("visible_change_visible")
    if start and change and change["timestamp_sec"] < start["timestamp_sec"]:
        codes.append("VISIBLE_CHANGE_BEFORE_START_STATE")
    if change and end and end["timestamp_sec"] < change["timestamp_sec"]:
        codes.append("END_STATE_BEFORE_VISIBLE_CHANGE")
    if start and end and end["timestamp_sec"] <= start["timestamp_sec"]:
        codes.append("END_STATE_NOT_AFTER_START_STATE")
    return {
        "ok": not codes,
        "codes": codes,
        "missing": missing,
        "requirements": requirements,
        "evidence": evidence,
        "judgment_source": "human_observation",
        "limitation": "Timestamped human observation; this receipt does not claim automatic face, mouth, or acting recognition.",
    }
