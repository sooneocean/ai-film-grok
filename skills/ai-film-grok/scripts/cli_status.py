#!/usr/bin/env python3
"""Status command cluster — extracted from aifilm_grok.py.

Contains ``cmd_status`` (and helpers) plus ``cmd_doctor`` / readiness classifier. Each helper is
called only by ``cmd_status`` and depends solely on the generic utility
layer (emit / load_manifest / read_json) plus lazy sibling imports.

Symbols are re-exported by aifilm_grok for backward compatibility, so
existing imports like ``from aifilm_grok import _status_audio_summary``
keep working.
"""

from __future__ import annotations

import argparse
import copy
import os
import shutil
import stat
import sys
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
    )

    root = Path(args.root).expanduser().resolve()
    try:
        from scene_sound import reconcile as reconcile_scene_sound

        scene_sound = reconcile_scene_sound(root, write=False)
    except Exception as exc:
        scene_sound = {"status": "error", "error": str(exc)[:200]}
    manifest = copy.deepcopy(load_manifest(root))
    summary = recompute_gates(root, manifest)
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
            root, gates=gates, open_n=open_n, persist=False
        )
    except Exception:
        next_actions = []
        pipeline_stage = {"stage": "unknown", "label_zh": "未知", "error": "detect_failed"}
        next_cmd = None
        _next_id = None
    try:
        from workflow_spine import build_workflow_status, public_flow_phase

        workflow = pipeline_stage.get("workflow") if isinstance(pipeline_stage, dict) else None
        if not isinstance(workflow, dict):
            workflow = build_workflow_status(root, gates=gates)
        phase = public_flow_phase(workflow) if isinstance(workflow, dict) else None
    except (ImportError, OSError, ValueError):
        phase = None
    from project_state import build_project_state

    project_state = build_project_state(
        root,
        gates=gates,
        open_reshoot_count=open_n,
        next_actions=next_actions,
        next_cmd=next_cmd,
        next_id=_next_id,
    )
    try:
        from promotion_report import build_promotion_report

        promotion = build_promotion_report(root)
        promotion_summary = {
            **promotion["summary"],
            "final_state": promotion["final"]["state"],
            "highest_roi_actions": promotion["highest_roi_actions"],
        }
    except Exception as exc:
        promotion_summary = {"error": str(exc)[:200], "report_only": True}
    emit(
        {
            "ok": True,
            "root": str(root),
            "title": manifest.get("title"),
            "provider_default": manifest.get("provider_default"),
            "phase": phase,
            "pipeline_stage": pipeline_stage,
            "project_state": project_state,
            "canonical_stage": project_state.get("canonical_stage"),
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
            "scene_sound": scene_sound,
            "promotion_report": promotion_summary,
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


def _classify_doctor_readiness(
    *,
    core_checks: dict[str, bool],
    optional_capabilities: dict[str, Any],
    environment_warnings: list[str],
) -> dict[str, Any]:
    """Separate production requirements from optional tools and host advisories."""
    failed_checks = [name for name, ready in core_checks.items() if not ready]
    core_readiness = {
        "ok": not failed_checks,
        "checks": core_checks,
        "failed_checks": failed_checks,
    }
    environment_advisories = {
        "ok": not environment_warnings,
        "warnings": list(environment_warnings),
        "severity": "advisory" if environment_warnings else "none",
        "blocks_core": False,
    }
    strict_blocking = bool(failed_checks)
    strict_status = (
        "blocked" if strict_blocking else "advisory_only" if environment_warnings else "pass"
    )
    return {
        "core_readiness": core_readiness,
        "optional_capabilities": optional_capabilities,
        "environment_advisories": environment_advisories,
        "ok": core_readiness["ok"],
        "strict_ok": bool(core_readiness["ok"] and environment_advisories["ok"]),
        "strict_status": strict_status,
        "strict_blocking": strict_blocking,
    }


def cmd_doctor(args: argparse.Namespace) -> int:
    from aifilm_grok import (
        emit,
        grok_permission_mode,
        read_json,
    )
    from runtime_policy import verify_requirements_lock, verify_runtime_lock

    skill_dir = Path(__file__).resolve().parents[1]
    edge_ok = False
    edge_err = None
    try:
        import edge_tts  # noqa: F401

        edge_ok = True
    except Exception as exc:  # pragma: no cover
        edge_err = str(exc)
    numpy_ok = False
    try:
        import numpy  # noqa: F401

        numpy_ok = True
    except Exception:
        pass
    pil_ok = False
    try:
        from PIL import Image  # noqa: F401

        pil_ok = True
    except Exception:
        pass
    tts_info: dict[str, Any] = {}
    lipsync_info: dict[str, Any] = {}
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from tts_backend import probe as tts_probe  # type: ignore

        tts_info = tts_probe()
    except Exception as exc:
        tts_info = {"ok": False, "error": str(exc)}
    try:
        from lipsync_backend import probe as lipsync_probe  # type: ignore

        lipsync_info = lipsync_probe()
    except Exception as exc:
        lipsync_info = {"ok": False, "error": str(exc)}
    requirements = verify_requirements_lock(skill_dir / "requirements.lock", skill_dir)
    runtime = verify_runtime_lock(skill_dir, skill_dir / "runtime-lock.json")
    schema_ok = False
    schema_error = None
    try:
        import jsonschema

        schema = read_json(skill_dir / "schemas" / "film-spec.schema.json")
        example = read_json(skill_dir / "templates" / "film-spec.example.json")
        jsonschema.validate(example, schema)
        schema_ok = True
    except Exception as exc:
        schema_error = str(exc)
    config_env = skill_dir / "config.env"
    config_env_mode = stat.S_IMODE(config_env.stat().st_mode) if config_env.is_file() else None
    grok_config = Path.home() / ".grok" / "config.toml"
    permission_mode = grok_permission_mode(grok_config)
    grok_log = Path.home() / ".grok" / "logs" / "unified.jsonl"
    log_mode = stat.S_IMODE(grok_log.stat().st_mode) if grok_log.is_file() else None
    environment_warnings: list[str] = []
    if permission_mode == "always-approve":
        environment_warnings.append(
            "Global Grok permission_mode is always-approve; change requires explicit user approval"
        )
    if log_mode is not None and log_mode & 0o077:
        environment_warnings.append(
            f"Grok unified log is readable beyond the owner (mode {oct(log_mode)}); "
            f"fix: chmod 600 {grok_log}"
        )
    if config_env_mode is not None and config_env_mode & 0o077:
        environment_warnings.append(
            f"skill config.env must be owner-only (mode {oct(config_env_mode)})"
        )
    requested_lipsync = str(lipsync_info.get("env_backend") or "auto")
    ready_lipsync_backends = list(lipsync_info.get("ready") or [])
    if requested_lipsync == "require":
        lipsync_required_ok = bool(ready_lipsync_backends)
    else:
        lipsync_required_ok = requested_lipsync in {"off", "auto"} or bool(
            (lipsync_info.get("backends") or {}).get(requested_lipsync)
        )
    report = {
        "ok": True,
        "skill_dir": str(skill_dir),
        "skill_md": (skill_dir / "SKILL.md").is_file(),
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "python": sys.executable,
        "edge_tts": edge_ok,
        "edge_tts_error": edge_err,
        "tts": tts_info,
        "lipsync": lipsync_info,
        "numpy": numpy_ok,
        "pillow": pil_ok,
        "requirements_lock": requirements,
        "runtime_lock": runtime,
        "film_spec_schema": {"ok": schema_ok, "error": schema_error},
        "security_posture": {
            "config_env_mode": oct(config_env_mode) if config_env_mode is not None else None,
            "global_permission_mode": permission_mode,
            "grok_log_mode": oct(log_mode) if log_mode is not None else None,
            "warnings": environment_warnings,
        },
        "render_final": (skill_dir / "scripts" / "render_final.py").is_file(),
        "export_composition": (skill_dir / "scripts" / "export_composition.py").is_file(),
        "compose_render": (skill_dir / "scripts" / "compose_render.py").is_file(),
        "pilot_review": (skill_dir / "scripts" / "pilot_review.py").is_file(),
        "compose_preview": (skill_dir / "scripts" / "compose_preview.py").is_file(),
        "next_actions": (skill_dir / "scripts" / "next_actions.py").is_file(),
        "preflight": (skill_dir / "scripts" / "preflight.py").is_file(),
        "npx": shutil.which("npx"),
        "lipsync_backend": (skill_dir / "scripts" / "lipsync_backend.py").is_file(),
        "tts_backend": (skill_dir / "scripts" / "tts_backend.py").is_file(),
        "provider_default": "grok-imagine",
        "tools": {
            "still_generate": "image_gen (agent tool)",
            "still_edit": "image_edit (agent tool)",
            "motion": "FRW LTX 2.3 → FRW API I2V → Grok Video 1.5",
            "motion_multi_ref": "reference_to_video (agent tool)",
            "vo": "MiMo (default; limited-time free), MiniMax/Fish/edge, or structured AIFILM_TTS_ARGV (cross-provider fallback is opt-in)",
            "lipsync": "locked MuseTalk/Wav2Lip or structured AIFILM_LIPSYNC_ARGV (optional post)",
            "bgm": "numpy procedural R&B (default) or user music file",
            "post": "render_final.py (FFmpeg + PIL subs + optional lipsync)",
            "post_designed": (
                "export-compose + compose-render (HyperFrames E2E; "
                "Remotion auto-render when node_modules ready else next_steps)"
            ),
            "post_engines": ["ffmpeg", "hyperframes", "remotion"],
        },
        "limits": {
            "motion_first_last": False,
            "video_duration_sec": [6, 10],
            "note": "For human-like VO pin a stable provider voice; cross-provider fallback is opt-in.",
        },
    }
    # Designed-post readiness (does not fail default doctor — HF is optional)
    designed: dict[str, Any] = {"ok": False, "required_for": "final --post-engine hyperframes"}
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from compose_render import probe_designed_post_tooling, probe_remotion_readiness

        designed = {
            **probe_designed_post_tooling(),
            "required_for": "final --post-engine hyperframes",
        }
        designed["ok"] = bool(designed.get("npx") and designed.get("hyperframes_ok"))
        # Soft remotion readiness when a package was exported under CWD film roots — probe empty ok
        designed["remotion"] = {
            "note": "Per-film: compose-render --engine remotion after export; needs npm install",
            "probe_fn": "probe_remotion_readiness(film_root)",
        }
        _ = probe_remotion_readiness  # keep import for doctor consumers
    except Exception as exc:  # pragma: no cover — defensive
        designed["error"] = str(exc)[:200]
    # Soft notice only — missing HyperFrames must not fail ffmpeg-only production or --strict
    if not designed.get("ok"):
        designed["soft_warning"] = (
            "designed-post not ready: "
            + str(designed.get("error") or "npx/hyperframes unavailable")
            + " — ffmpeg final still works"
        )
    report["designed_post"] = designed

    # Soft Comfy tunnel probe (C2) — advisory only; missing tunnel must not fail core doctor
    tunnel: dict[str, Any] = {"ok": None, "required_for": "5090 comfy bulk"}
    try:
        from workflow_pack import tunnel_probe

        tunnel = {
            **tunnel_probe(port=int(os.environ.get("AIFILM_COMFY_TUNNEL_PORT") or 18188)),
            "required_for": "5090 comfy bulk",
            "advisory": True,
        }
    except Exception as exc:  # pragma: no cover
        tunnel = {"ok": None, "skipped": True, "error": str(exc)[:160], "advisory": True}
    report["comfy_tunnel"] = tunnel

    # video-use skill readiness (real-footage editing ring, 2026-07-23) — soft probe
    video_use: dict[str, Any] = {"ok": False, "required_for": "ingest-footage / auto-cut"}
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from real_footage import video_use_dir

        vu = video_use_dir()
        video_use = {
            "ok": True,
            "path": str(vu),
            "has_transcribe": (vu / "helpers" / "transcribe.py").is_file(),
            "has_pack": (vu / "helpers" / "pack_transcripts.py").is_file(),
            "has_render": (vu / "helpers" / "render.py").is_file(),
            "has_grade": (vu / "helpers" / "grade.py").is_file(),
            "required_for": "ingest-footage / auto-cut",
        }
    except Exception as exc:  # noqa: BLE001 — soft probe
        video_use["error"] = str(exc)[:200]
        video_use["soft_warning"] = (
            "video-use not installed — install/ symlink the skill for real-footage editing"
        )
    report["video_use"] = video_use

    # I2V provider registry summary (grok + seedance) — soft probe
    i2v_providers: dict[str, Any] = {"ok": False}
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from i2v_provider import preferred, registry_report

        active = preferred()
        reg = registry_report()
        i2v_providers = {
            "ok": True,
            "active": active.name,
            "providers": reg["providers"],
        }
    except Exception as exc:  # noqa: BLE001 — soft probe
        i2v_providers = {"ok": False, "error": str(exc)[:200]}
    report["i2v_providers"] = i2v_providers

    # Grok OAuth (session token from grok login) — soft probe, does not fail doctor by default
    grok_oauth: dict[str, Any] = {"ok": False}
    try:
        from grok_oauth import probe as grok_oauth_probe

        grok_oauth = grok_oauth_probe()
    except Exception as exc:  # pragma: no cover
        grok_oauth = {"ok": False, "error": str(exc)[:200]}
    report["grok_oauth"] = {
        "ok": bool(grok_oauth.get("ok")),
        "source": grok_oauth.get("source"),
        "auth_mode": grok_oauth.get("auth_mode"),
        "ttl_sec": grok_oauth.get("ttl_sec"),
        "has_imagine_image": grok_oauth.get("has_imagine_image"),
        "has_imagine_video": grok_oauth.get("has_imagine_video"),
        "error": grok_oauth.get("error"),
        "hint": grok_oauth.get("hint") or "grok login",
    }
    optional_warnings: list[str] = []
    if not grok_oauth.get("ok"):
        optional_warnings.append(
            "Grok OAuth not ready (optional for API batch; in-session Imagine tools still work if logged in)"
        )

    if not report["ffmpeg"] or not report["ffprobe"]:
        report["ok"] = False
        report["error"] = "ffmpeg/ffprobe not found on PATH"
    elif not edge_ok or not numpy_ok or not pil_ok:
        report["ok"] = False
        report["error"] = (
            "Formal final requires edge-tts + numpy + pillow (pip install --user edge-tts numpy pillow)"
        )
    elif (
        not tts_info.get("ok")
        or not requirements["ok"]
        or not runtime["ok"]
        or not schema_ok
        or not lipsync_required_ok
    ):
        report["ok"] = False
        report["error"] = (
            "Runtime/schema/backend verification failed; inspect nested doctor reports"
        )
    core_checks = {
        "skill_spine": bool(report["skill_md"]),
        "ffmpeg": bool(report["ffmpeg"]),
        "ffprobe": bool(report["ffprobe"]),
        "edge_tts": edge_ok,
        "numpy": numpy_ok,
        "pillow": pil_ok,
        "tts_backend": bool(tts_info.get("ok")),
        "requirements_lock": bool(requirements.get("ok")),
        "runtime_lock": bool(runtime.get("ok")),
        "film_spec_schema": schema_ok,
        "requested_lipsync_backend": lipsync_required_ok,
    }
    optional_capabilities = {
        "lipsync": {
            "enabled": requested_lipsync not in {"off", "auto"},
            "requested_backend": requested_lipsync,
            "ready": bool(ready_lipsync_backends),
            "ready_backends": ready_lipsync_backends,
            "required_request_satisfied": lipsync_required_ok,
        },
        "designed_post": {
            "ready": bool(designed.get("ok")),
            "required_for": designed.get("required_for"),
        },
        "grok_oauth": {
            "ready": bool(grok_oauth.get("ok")),
            "required_for": "API batch generation",
        },
        "warnings": optional_warnings,
    }
    readiness = _classify_doctor_readiness(
        core_checks=core_checks,
        optional_capabilities=optional_capabilities,
        environment_warnings=environment_warnings,
    )
    report.update(readiness)
    if not report["ok"] and "error" not in report:
        report["error"] = "Core readiness failed; inspect core_readiness.failed_checks"

    # P4-3: art check — run director methodology verification
    if getattr(args, "art_check", False):
        art_report: dict[str, Any] = {"ok": True, "checks": {}}
        film_root = Path(getattr(args, "art_root", ".")).expanduser().resolve()
        if (film_root / "film-spec.json").is_file():
            try:
                from director_cli import verify as director_verify

                result = director_verify(film_root)
                art_report["checks"][str(film_root)] = result
                if not result.get("ok"):
                    art_report["ok"] = False
            except Exception as exc:  # noqa: BLE001
                art_report["checks"][str(film_root)] = {"ok": False, "error": str(exc)[:200]}
        report["art_check"] = art_report

    emit(report)
    return 0 if (report["strict_ok"] if getattr(args, "strict", False) else report["ok"]) else 1
