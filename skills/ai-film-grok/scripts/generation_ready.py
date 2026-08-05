#!/usr/bin/env python3
"""Dispatch generation readiness (M6)."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from util import read_json

def _root(path): return Path(path).expanduser().resolve()

def generation_ready_report(root: Path | str) -> dict[str, Any]:
    base = _root(root)
    spec = read_json(base / "film-spec.json") or {}
    bible = read_json(base / "style-bible.json") or {}
    reg = read_json(base / "assets-registry.json") or {}
    style_locked = False
    if isinstance(bible, dict):
        style_locked = bool(bible.get("locked") or str(bible.get("state") or "").lower() in {"approved", "locked"} or bible.get("style_fingerprint"))
    try:
        from still_source import audit_film_still_sources
        ssa = audit_film_still_sources(base)
    except Exception as exc:
        ssa = {"ok": True, "hard": [], "peak_missing": [], "error": str(exc)[:120]}
    shots = []
    if isinstance(spec, dict):
        for scene in spec.get("scenes") or []:
            if isinstance(scene, dict):
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict) and sh.get("id"): shots.append(sh)
        if not shots and isinstance(spec.get("shots"), list):
            shots = [s for s in spec["shots"] if isinstance(s, dict) and s.get("id")]
    flf_eligible = flf_missing_last = 0
    try:
        from h3_media_pack import resolve_first_frame_path, resolve_last_frame_path
        from h3_workflow import _approved_still
        for sh in shots[:40]:
            sid = str(sh["id"])
            first, _ = resolve_first_frame_path(base, sid, shot=sh, approved_still=_approved_still(base, sid))
            last, _ = resolve_last_frame_path(base, sid, shot=sh)
            if first and last: flf_eligible += 1
            elif first and not last: flf_missing_last += 1
    except Exception:
        pass
    peak_missing = list(ssa.get("peak_missing") or [])
    hard = list(ssa.get("hard") or [])
    blockers = []
    if hard: blockers.extend(str(x) for x in hard[:5])
    if not style_locked and shots: blockers.append("STYLE_NOT_LOCKED")
    line_parts = [f"style={'lock' if style_locked else 'open'}", f"still_src={'ok' if ssa.get('ok') else 'hard'}", f"flf={flf_eligible}/{len(shots) or 0}", f"reg={'yes' if isinstance(reg, dict) and reg else 'no'}"]
    if peak_missing: line_parts.append(f"peak_miss={len(peak_missing)}")
    return {"schema_version": 1, "kind": "generation-ready", "ok": bool(style_locked or not shots) and not peak_missing,
            "style_locked": style_locked, "still_source_ok": bool(ssa.get("ok")), "peak_missing": peak_missing[:12],
            "hard": hard[:8], "registry_present": bool(isinstance(reg, dict) and reg), "shot_count": len(shots),
            "flf_eligible": flf_eligible, "flf_missing_last": flf_missing_last, "blockers": blockers[:8],
            "line": " · ".join(line_parts)}
