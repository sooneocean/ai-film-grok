"""Read-only scene-sound reconciliation for auditable final-mix gates."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

_ACTION_RULES = (
    (("走", "跑", "进入", "离开", "walk", "run"), "foley", "footsteps"),
    (("门把", "door handle"), "foley", "door_handle"),
    (("开门", "推门", "拉门", "open door"), "foley", "door_open"),
    (("关门", "close door"), "foley", "door_close"),
    (("坐下", "起身", "sit", "stand"), "foley", "seat_contact"),
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


def _source_event(
    candidates: list[dict[str, Any]], root: Path, shot_id: str, kind: str
) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in candidates
            if _matches_required(event, shot_id, kind) and _local_asset_ok(root, event)
        ),
        None,
    )


def _projection_hash(spec: dict[str, Any]) -> str:
    import json

    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def reconcile(root: Path, *, write: bool = True) -> dict[str, Any]:
    """Infer required scene sound without mutating film-spec or buying assets."""
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json")
    if not isinstance(spec, dict):
        spec = {}
    events: list[dict[str, Any]] = []
    for shot in _shots(spec):
        sid = str(shot.get("id") or "")
        raw_cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
        # Only formal audio cues enter the renderer's scene stem. Legacy scene_events
        # are metadata, not proof that a sound reaches the final mix.
        cues = [{**item, "shot_id": sid} for item in raw_cues if isinstance(item, dict)]
        text = " ".join(
            str(shot.get(key) or "") for key in ("action", "visible_change", "sound_cues")
        )
        for words, track, kind in _ACTION_RULES:
            if not any(word.lower() in text.lower() for word in words):
                continue
            source_event = _source_event(cues, root, sid, kind)
            status = "ok" if source_event else "blocked"
            origin = "audio_cues" if source_event in cues else "inferred"
            events.append(
                {
                    "shot_id": sid,
                    "track": track,
                    "kind": kind,
                    "priority": "required",
                    "source": origin,
                    "status": status,
                    "needs_review": not bool(source_event),
                    "reason": "missing verified local scene-sound asset"
                    if status == "blocked"
                    else None,
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
