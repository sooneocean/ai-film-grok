"""Read-only scene-sound reconciliation for auditable final-mix gates."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

_ACTION_RULES = (
    (("走", "跑", "进入", "离开", "walk", "run"), "foley", "footsteps"),
    (("门把", "door handle"), "foley", "door_handle"),
    (
        (
            "开门",
            "推门",
            "拉门",
            "open door",
            "opens door",
            "opens the door",
            "opened door",
            "opened the door",
            "door opens",
        ),
        "foley",
        "door_open",
    ),
    (("关门", "close door"), "foley", "door_close"),
    (("坐下", "起身", "sit", "stand"), "foley", "seat_contact"),
    (
        ("杯", "手机", "钥匙", "抽屉", "拿起", "放下", "cup", "phone", "key", "drawer"),
        "foley",
        "prop_contact",
    ),
)


def _shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    top_level = spec.get("shots")
    if isinstance(top_level, list):
        return [shot for shot in top_level if isinstance(shot, dict)]
    return [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]


def _local_asset_ok(root: Path, event: dict[str, Any]) -> bool:
    source = str(event.get("source") or event.get("asset") or "")
    expected_sha256 = str(event.get("source_sha256") or "")
    if not source.startswith("local:") or not expected_sha256:
        return False
    try:
        path = (root / source.removeprefix("local:")).resolve()
        path.relative_to(root)
    except ValueError:
        return False
    if not path.is_file():
        return False
    actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return actual_sha256 == expected_sha256


def _matches_required(event: dict[str, Any], shot_id: str, kind: str) -> bool:
    if str(event.get("shot_id") or "") != shot_id:
        return False
    if str(event.get("kind") or "") == kind:
        return True
    if str(event.get("kind") or "") not in {"foley", "sfx"}:
        return False
    hint = " ".join(
        str(event.get(field) or "") for field in ("asset_hint", "asset", "source")
    ).lower()
    return kind in hint


def _timeline_number(value: object, *, low: float = 0.0) -> float | None:
    """Mirror the formal timeline's numeric floor without compiling unrelated cues."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= low else None


def _reaches_scene_stem(event: dict[str, Any]) -> bool:
    """Require the fields that make a verified cue executable in the final stem."""
    if str(event.get("kind") or "").lower() not in {"foley", "sfx", "ambience"}:
        return False
    # This deliberately matches audio_timeline's bool() conversion: a malformed
    # string such as "false" is currently muted by the compiler and must not pass here.
    if bool(event.get("muted", False)):
        return False
    if not str(event.get("license") or "").strip():
        return False
    if "start_offset_sec" not in event:
        return False
    duration = _timeline_number(event.get("duration_sec"), low=0.001)
    start = _timeline_number(event.get("start_offset_sec"))
    if duration is None or start is None:
        return False
    gain = _timeline_number(event.get("gain", 1.0))
    pan = _timeline_number(event.get("pan", 0.0), low=-1.0)
    if gain is None or pan is None or abs(pan) > 1:
        return False
    for field in ("fade_in_sec", "fade_out_sec"):
        fade = _timeline_number(event.get(field, 0))
        if fade is None or fade > duration:
            return False
    return True


def _source_event(
    candidates: list[dict[str, Any]],
    root: Path,
    shot_id: str,
    kind: str,
    *,
    expected_material: str | None = None,
) -> dict[str, Any] | None:
    verified = [
        event
        for event in candidates
        if _matches_required(event, shot_id, kind)
        and _local_asset_ok(root, event)
        and _reaches_scene_stem(event)
    ]
    if expected_material is not None:
        matching = next(
            (event for event in verified if _event_material(event) == expected_material), None
        )
        if matching is not None:
            return matching
    return verified[0] if verified else None


def _material_value(shot: dict[str, Any], *fields: str) -> str | None:
    """Read a declared production material without guessing from prose."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    for source in (shot, dsl):
        for field in fields:
            value = source.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
    return None


def _expected_material(shot: dict[str, Any], kind: str) -> str | None:
    if kind == "footsteps":
        return _material_value(shot, "floor_material", "floor", "ground_material", "ground")
    if kind in {"door_handle", "door_open", "door_close"}:
        return _material_value(shot, "door_material")
    if kind == "prop_contact":
        return _material_value(shot, "prop_material")
    return None


def _event_material(event: dict[str, Any]) -> str | None:
    for field in ("material", "surface_material"):
        value = event.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _event_status(
    source_event: dict[str, Any] | None,
    *,
    expected_material: str | None,
) -> tuple[str, bool, str | None]:
    if source_event is None:
        return "blocked", True, "missing verified executable local scene-sound asset"
    if expected_material is None:
        return "needs_review", True, "material is unknown; verify neutral or selected asset"
    actual_material = _event_material(source_event)
    if actual_material is None:
        return "blocked", True, f"asset material missing; expected {expected_material}"
    if actual_material != expected_material:
        return (
            "blocked",
            True,
            f"asset material {actual_material} does not match {expected_material}",
        )
    return "ok", False, None


def _projection_hash(spec: dict[str, Any]) -> str:
    import json

    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _explicit_true(shot: dict[str, Any], *fields: str) -> bool:
    """Only an actual boolean true opts a scene out of required ambience."""
    return any(shot.get(field) is True for field in fields)


def reconcile(root: Path, *, write: bool = True) -> dict[str, Any]:
    """Infer required scene sound without mutating film-spec or buying assets."""
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json")
    if not isinstance(spec, dict):
        spec = {}
    events: list[dict[str, Any]] = []
    for shot in _shots(spec):
        sid = str(shot.get("id") or "")
        if not sid:
            continue
        raw_cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
        # Only formal audio cues enter the renderer's scene stem. Legacy scene_events
        # are metadata, not proof that a sound reaches the final mix.
        cues = [{**item, "shot_id": sid} for item in raw_cues if isinstance(item, dict)]
        text = " ".join(
            str(shot.get(key) or "") for key in ("action", "visible_change", "sound_cues")
        )
        # A scene without a deliberate narrative silence still needs a continuous
        # acoustic space. This is separate from short foley hits and cannot be
        # satisfied by a generic SFX accent.
        if not _explicit_true(shot, "scene_silent", "narrative_silence"):
            ambience = _source_event(cues, root, sid, "ambience")
            events.append(
                {
                    "shot_id": sid,
                    "track": "ambience",
                    "kind": "ambience",
                    "priority": "required",
                    "source": "audio_cues" if ambience else "inferred",
                    "status": "ok" if ambience else "blocked",
                    "needs_review": not bool(ambience),
                    "reason": (
                        None if ambience else "missing verified executable local ambience asset"
                    ),
                }
            )
        for words, track, kind in _ACTION_RULES:
            if not any(word.lower() in text.lower() for word in words):
                continue
            material = _expected_material(shot, kind)
            source_event = _source_event(cues, root, sid, kind, expected_material=material)
            status, needs_review, reason = _event_status(source_event, expected_material=material)
            origin = "audio_cues" if source_event in cues else "inferred"
            events.append(
                {
                    "shot_id": sid,
                    "track": track,
                    "kind": kind,
                    "priority": "required",
                    "source": origin,
                    "status": status,
                    "expected_material": material,
                    "actual_material": _event_material(source_event) if source_event else None,
                    "needs_review": needs_review,
                    "reason": reason,
                }
            )
    blocked = sorted({item["shot_id"] for item in events if item["status"] == "blocked"})
    review = sum(1 for item in events if item["needs_review"])
    report = {
        "schema_version": 1,
        "checked_at": utc_now(),
        "source_projection_sha256": _projection_hash(spec),
        "summary": {
            "required": len(events),
            "ok": sum(1 for item in events if item["status"] == "ok"),
            "needs_review": review,
            "blocked": sum(1 for item in events if item["status"] == "blocked"),
        },
        "events": events,
        "blocking_shot_ids": blocked,
        "degradations": [],
        "status": "blocked" if blocked else ("needs_review" if review else "ok"),
    }
    if write:
        (root / "receipts").mkdir(parents=True, exist_ok=True)
        write_json(root / "receipts" / "scene-sound-status.json", report)
    return report
