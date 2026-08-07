#!/usr/bin/env python3
"""Dispatch generation readiness (M6) + weapon inventory primaries."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _weapon_inventory_block() -> dict[str, Any]:
    """Soft attach of cross-modality primaries (never raises to callers)."""
    try:
        from weapon_inventory import inventory_report, primary_for

        rep = inventory_report(validate=True)
        still = primary_for("text-to-image")
        edit = primary_for("local-image-edit")
        motion = primary_for("image-to-video")
        tts = primary_for("tts_zh_ship")
        bgm = primary_for("bgm")
        return {
            "ok": bool(rep.get("ok")),
            "line": rep.get("line"),
            "primaries": rep.get("primaries"),
            "still_primary": (still or {}).get("id"),
            "edit_primary": (edit or {}).get("id"),
            "motion_primary": (motion or {}).get("id"),
            "tts_primary": (tts or {}).get("id"),
            "bgm_primary": (bgm or {}).get("id"),
            "profile_default": rep.get("profile_default"),
            "validation_ok": bool((rep.get("validation") or {}).get("ok")),
            "cli": "aifilm weapon inventory --tier primary",
        }
    except Exception as exc:  # noqa: BLE001 — soft
        return {"ok": False, "error": str(exc)[:160]}


def generation_ready_report(root: Path | str) -> dict[str, Any]:
    base = _root(root)
    spec = read_json(base / "film-spec.json") or {}
    bible = read_json(base / "style-bible.json") or {}
    reg = read_json(base / "assets-registry.json") or {}
    style_locked = False
    if isinstance(bible, dict):
        style_locked = bool(
            bible.get("locked")
            or str(bible.get("state") or "").lower() in {"approved", "locked"}
            or bible.get("style_fingerprint")
        )
    try:
        from still_source import audit_film_still_sources

        ssa = audit_film_still_sources(base)
    except Exception as exc:
        ssa = {"ok": True, "hard": [], "peak_missing": [], "error": str(exc)[:120]}
    # P0 2026-08-07: keyframe subject-fill audit (postage-stamp / cast fullbody)
    try:
        from composition_fill_gate import audit_film_composition_fill

        cfa = audit_film_composition_fill(base, auto_remedy=False, max_shots=80)
    except Exception as exc:
        cfa = {"ok": True, "hard": [], "checked": 0, "error": str(exc)[:120]}
    shots: list[dict[str, Any]] = []
    if isinstance(spec, dict):
        for scene in spec.get("scenes") or []:
            if isinstance(scene, dict):
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict) and sh.get("id"):
                        shots.append(sh)
        if not shots and isinstance(spec.get("shots"), list):
            shots = [s for s in spec["shots"] if isinstance(s, dict) and s.get("id")]
    flf_eligible = flf_missing_last = 0
    try:
        from h3_media_pack import resolve_first_frame_path, resolve_last_frame_path
        from h3_workflow import _approved_still

        for sh in shots[:40]:
            sid = str(sh["id"])
            first, _ = resolve_first_frame_path(
                base, sid, shot=sh, approved_still=_approved_still(base, sid)
            )
            last, _ = resolve_last_frame_path(base, sid, shot=sh)
            if first and last:
                flf_eligible += 1
            elif first and not last:
                flf_missing_last += 1
    except Exception:
        pass
    peak_missing = list(ssa.get("peak_missing") or [])
    hard = list(ssa.get("hard") or [])
    fill_hard = list(cfa.get("hard") or [])
    blockers: list[str] = []
    if hard:
        blockers.extend(str(x) for x in hard[:5])
    if fill_hard:
        blockers.append(f"COMPOSITION_FILL:{len(fill_hard)}")
        blockers.extend(str(x) for x in fill_hard[:3])
    if not style_locked and shots:
        blockers.append("STYLE_NOT_LOCKED")

    inv = _weapon_inventory_block()
    line_parts = [
        f"style={'lock' if style_locked else 'open'}",
        f"still_src={'ok' if ssa.get('ok') else 'hard'}",
        f"fill={'ok' if cfa.get('ok') else f'hard{len(fill_hard)}'}",
        f"flf={flf_eligible}/{len(shots) or 0}",
        f"reg={'yes' if isinstance(reg, dict) and reg else 'no'}",
    ]
    if peak_missing:
        line_parts.append(f"peak_miss={len(peak_missing)}")
    if inv.get("still_primary"):
        line_parts.append(f"still_wp={inv['still_primary']}")
    if inv.get("motion_primary"):
        line_parts.append(f"motion_wp={inv['motion_primary']}")

    hints: list[str] = []
    if not style_locked and shots:
        hints.append("lock style-bible before bulk")
    if peak_missing:
        hints.append("peak wardrobe still missing — use state photo / Qwen edit primary")
    if fill_hard:
        hints.append(
            "keyframe subject fill too small — ensure_fill_frame / CU reseed "
            "(never raw fullbody cast master as I2V first frame)"
        )
    if flf_missing_last and flf_eligible == 0 and shots:
        hints.append("no last frames yet — I2V default; produce _end.png for FLF")
    elif flf_missing_last:
        hints.append(
            f"{flf_missing_last} shots missing last → FLF upgrade via still-challenge --as end"
        )
    if inv.get("motion_primary"):
        hints.append(
            f"motion primary={inv['motion_primary']} · still primary={inv.get('still_primary')}"
        )

    return {
        "schema_version": 1,
        "kind": "generation-ready",
        "ok": bool(style_locked or not shots) and not peak_missing and bool(cfa.get("ok", True)),
        "style_locked": style_locked,
        "still_source_ok": bool(ssa.get("ok")),
        "composition_fill_ok": bool(cfa.get("ok", True)),
        "composition_fill_hard": fill_hard[:12],
        "composition_fill_checked": int(cfa.get("checked") or 0),
        "peak_missing": peak_missing[:12],
        "hard": hard[:8],
        "registry_present": bool(isinstance(reg, dict) and reg),
        "shot_count": len(shots),
        "flf_eligible": flf_eligible,
        "flf_missing_last": flf_missing_last,
        "blockers": blockers[:8],
        "line": " · ".join(line_parts),
        "weapon_inventory": inv,
        "inventory_line": inv.get("line"),
        "hints": hints[:6],
    }
