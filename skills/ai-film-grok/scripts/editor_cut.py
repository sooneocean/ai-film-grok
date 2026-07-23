"""Deterministic rough-cut readiness report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from continuity_chain import load_frame_chain_receipt
from media_qa import analyze_media
from util import read_json, sha256_file, write_json


def build_editor_cut_report(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    manifest = read_json(root / "manifest.json") or {}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    previous_id: str | None = None
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            sid = str(shot.get("id") or "")
            if not sid:
                continue
            clip = clips.get(sid) if isinstance(clips.get(sid), dict) else {}
            path = Path(str(clip.get("path") or ""))
            exists = path.is_file()
            row = {
                "shot_id": sid,
                "clip_path": str(path) if exists else None,
                "clip_sha256": sha256_file(path) if exists else None,
                "state": clip.get("state"),
                "status": clip.get("status"),
                "duration_sec": clip.get("duration_sec"),
                "take_id": clip.get("take_id"),
                "previous_shot_id": previous_id,
                "transition": shot.get("transition") or (shot.get("dsl") or {}).get("transition"),
            }
            if exists and not row["duration_sec"]:
                probe = analyze_media(path, require_audio=False, require_motion=False)
                row["duration_sec"] = probe.get("duration_sec")
                row["technical_qa"] = probe
            rows.append(row)
            if not exists:
                errors.append(
                    {
                        "code": "EDITOR_CLIP_MISSING",
                        "shot_id": sid,
                        "message": "registered clip file is missing",
                    }
                )
            if clip.get("status") != "approved" or clip.get("state") not in {None, "active"}:
                errors.append(
                    {
                        "code": "EDITOR_CLIP_NOT_ACTIVE",
                        "shot_id": sid,
                        "message": "clip is not an approved active take",
                    }
                )
            duration = float(row.get("duration_sec") or 0)
            if duration <= 0:
                errors.append(
                    {
                        "code": "EDITOR_DURATION_MISSING",
                        "shot_id": sid,
                        "message": "clip duration is missing",
                    }
                )
            previous_id = sid
    joins = load_frame_chain_receipt(root).get("joins") or []
    for join in joins:
        if isinstance(join, dict) and join.get("to") and join.get("byte_identical") is not True:
            errors.append(
                {
                    "code": "EDITOR_CONTINUITY_JOIN_FAILED",
                    "shot_id": str(join.get("to")),
                    "message": "continue join is not byte-identical",
                }
            )
    report = {
        "schema_version": 1,
        "kind": "editor-cut",
        "ok": not errors and bool(rows),
        "shot_count": len(rows),
        "shots": rows,
        "errors": errors,
        "policy": {"approved_active_take_only": True, "continue_join": "byte-identical"},
    }
    if write:
        path = root / "receipts" / "editor-cut.json"
        write_json(path, report)
        report["path"] = str(path)
    return report
