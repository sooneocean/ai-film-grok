#!/usr/bin/env python3
"""Status command cluster — extracted from aifilm_grok.py.

Contains ``cmd_status`` and its four private helpers. Each helper is
called only by ``cmd_status`` and depends solely on the generic utility
layer (emit / load_manifest / read_json) plus lazy sibling imports.

Symbols are re-exported by aifilm_grok for backward compatibility, so
existing imports like ``from aifilm_grok import _status_audio_summary``
keep working.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def cmd_status(args: argparse.Namespace) -> int:
    # Lazy import from aifilm_grok to avoid a circular import at module load.
    from aifilm_grok import (
        GATE_ORDER,
        MANIFEST_NAME,
        _pipeline_bundle,
        emit,
        load_manifest,
        read_json,
        recompute_gates,
        save_manifest,
    )

    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    summary = recompute_gates(root, manifest)
    save_manifest(root, manifest)
    next_gate = None
    for name in GATE_ORDER:
        if not summary["gates"].get(name):
            next_gate = name
            break
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    final_rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else {}
    compose_pkg = root / "compose" / "package.json"
    compose_hf = root / "compose" / "hyperframes" / "index.html"
    compose_preview_meta = root / "compose" / "preview.json"
    pilot_path = root / "receipts" / "pilot-approval.json"
    pilot_score_path = root / "receipts" / "pilot-scorecard.json"
    pilot_data = read_json(pilot_path) if pilot_path.is_file() else {}
    try:
        from production_gates import pilot_is_user_approved as _pilot_ok

        pilot_ok = _pilot_ok(pilot_data) if pilot_data else False
    except Exception:
        pilot_ok = False
    gates = summary.get("gates") or {}
    open_n = int(summary.get("open_reshoot_count") or 0)
    try:
        next_actions, pipeline_stage, next_cmd, _next_id = _pipeline_bundle(
            root, gates=gates, open_n=open_n, persist=True
        )
    except Exception:
        next_actions = []
        pipeline_stage = {"stage": "unknown", "label_zh": "未知", "error": "detect_failed"}
        next_cmd = None
    emit(
        {
            "ok": True,
            "root": str(root),
            "title": manifest.get("title"),
            "provider_default": manifest.get("provider_default"),
            "pipeline_stage": pipeline_stage,
            "stage": pipeline_stage.get("stage") if isinstance(pipeline_stage, dict) else None,
            "stage_label": pipeline_stage.get("label_zh")
            if isinstance(pipeline_stage, dict)
            else None,
            "next_gate": next_gate,
            "next_actions": next_actions,
            "next_cmd": next_cmd or (next_actions[0]["cmd"] if next_actions else None),
            "post_engine": final_rec.get("post_engine") or "none",
            "final_film": {
                "path": final_rec.get("path"),
                "sha256": (final_rec.get("sha256") or "")[:16] or None,
                "duration_sec": final_rec.get("duration_sec"),
                "post_engine": final_rec.get("post_engine"),
            }
            if final_rec
            else None,
            "pilot": {
                "user_approved": pilot_ok,
                "approval_present": pilot_path.is_file(),
                "scorecard_present": pilot_score_path.is_file(),
            },
            "audio": _status_audio_summary(root),
            "inventory": _status_inventory(root, summary),
            "evidence": _status_evidence(root),
            "compose": {
                "export_present": compose_pkg.is_file(),
                "hyperframes_index": compose_hf.is_file(),
                "remotion_package": (root / "compose" / "remotion" / "package.json").is_file(),
                "remotion": _status_remotion_probe(root),
                "preview_meta": str(compose_preview_meta)
                if compose_preview_meta.is_file()
                else None,
                "preview_receipt": str(root / "receipts" / "compose-preview.json")
                if (root / "receipts" / "compose-preview.json").is_file()
                else None,
                "export_meta": outputs.get("compose_export"),
            },
            **summary,
            "manifest": str(root / MANIFEST_NAME),
        }
    )
    return 0


def _status_inventory(root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    """Shot inventory consistency for status (fail-closed signal, not silent partial)."""
    try:
        from shot_inventory import check_shot_inventory, discover_vo_stem_ids

        shot_ids = summary.get("shot_ids") or []
        approved = summary.get("approved_clips") or []
        vo_ids = discover_vo_stem_ids(root)
        report = check_shot_inventory(
            shot_ids,
            approved,
            vo_stem_ids=vo_ids if vo_ids else None,
            require_vo=bool(vo_ids),
        )
        return report
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _status_evidence(root: Path) -> dict[str, Any]:
    """intent vs executed vs human_review — plan cannot impersonate delivery."""
    try:
        from evidence_status import classify_evidence

        return classify_evidence(root)
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _status_audio_summary(root: Path) -> dict[str, Any]:
    """Phase F: surface TTS / sound_plan / mix_report for agent routing."""
    from aifilm_grok import read_json

    out: dict[str, Any] = {
        "tts_backend": None,
        "vo_voice": None,
        "sound_plan_mood": None,
        "auto_sfx": None,
        "sidechain": None,
        "mix_report": None,
        "loudness": None,
    }
    spec_path = root / "film-spec.json"
    if spec_path.is_file():
        try:
            spec = read_json(spec_path)
            out["tts_backend"] = spec.get("tts_backend")
            out["vo_voice"] = spec.get("vo_voice")
            sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
            out["sound_plan_mood"] = sp.get("mood")
            out["auto_sfx"] = sp.get("auto_sfx")
            out["sidechain"] = sp.get("sidechain")
            if spec.get("_tts_notes"):
                out["tts_notes"] = spec.get("_tts_notes")
        except Exception as exc:
            out["spec_error"] = str(exc)[:160]
    mix_path = root / "audio" / "mix_report.json"
    if mix_path.is_file():
        try:
            mix = read_json(mix_path)
            out["mix_report"] = str(mix_path)
            out["sfx_overlay_count"] = mix.get("sfx_overlay_count")
            out["sidechain_applied"] = mix.get("sidechain_applied")
            if isinstance(mix.get("sidechain"), dict):
                out["sidechain"] = mix.get("sidechain")
            out["loudness"] = mix.get("loudness")
            out["loudness_before"] = mix.get("loudness_before")
            out["loudnorm_applied"] = mix.get("loudnorm_applied")
            out["loudnorm_decision"] = mix.get("loudnorm_decision")
            out["loudnorm_policy"] = mix.get("loudnorm_policy")
            out["bed_source"] = mix.get("bed_source")
            out["music_template"] = mix.get("music_template")
        except Exception as exc:
            out["mix_error"] = str(exc)[:160]
    # Also surface whether a local template file exists (pre-final)
    try:
        from sound_plan import resolve_music_template

        mt = resolve_music_template(
            root,
            mood=out.get("sound_plan_mood") or "rnb",
            plan=None,
            music_arg=None,
            mode="auto",
        )
        out["local_music_available"] = bool(mt)
        if mt:
            out["local_music_path"] = mt.get("relative") or mt.get("path")
    except Exception:
        out["local_music_available"] = False
    return out


def _status_remotion_probe(root: Path) -> dict[str, Any]:
    """Best-effort remotion readiness for status JSON (never raises)."""
    try:
        from compose_render import probe_remotion_readiness

        info = probe_remotion_readiness(root)
        return {
            "ready": bool(info.get("ready")),
            "missing": info.get("missing") or [],
            "package_json": bool(info.get("package_json")),
            "node_modules": bool(info.get("node_modules")),
        }
    except Exception as exc:
        return {"ready": False, "error": str(exc)[:200]}
