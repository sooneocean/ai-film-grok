#!/usr/bin/env python3
"""Local control plane for the ai-film-grok pipeline (no Studio required)."""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure skill package root is importable before `scripts.*` (shell wrapper does not set PYTHONPATH)
_SKILL_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (_SKILL_DIR, _SCRIPTS_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# Shared runtime (W1): single implementation in scripts/core/* — re-export for hard-compat.
from core import (  # noqa: E402, F401
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    DIRECTOR_NOTES_NAME,
    EXPORT_METADATA_FILES,
    GATE_ORDER,
    MANIFEST_NAME,
    NATIVE_AUDIO_AUDIBLE_MIN_DB,
    SCHEMA_VERSION,
    _auto_promote_last_to_next,
    _register_media,
    director_notes_path,
    emit,
    empty_manifest,
    ensure_tree,
    film_dirs,
    film_output_path,
    load_director_notes,
    load_manifest,
    media_duration,
    normalize_clip,
    recompute_gates,
    record_file_matches,
    save_director_notes,
    save_manifest,
    valid_shot_id,
    which_npx_safe,
)

# probe_native_audio_mean_volume stays on hub for test patchability of ``run``.
from runtime_policy import sha256  # noqa: F401 — re-exported; tests use aifilm_grok.sha256
from util import require_json as read_json
from util import sha256_file, utc_now, write_json
from util.errors import FilmError  # noqa: E402 — re-exported for backward compat
from util.subprocess import run
from util.validators import aspect_dims


def probe_native_audio_mean_volume(path: Path) -> float | None:
    """Hard-compat: delegates to core.media_ops with hub ``run`` for test patches."""
    from core.media_ops import probe_native_audio_mean_volume as _probe

    return _probe(path, run_fn=run)



def grok_permission_mode(config_path: Path) -> str | None:
    if not config_path.is_file():
        return None
    try:
        import tomllib

        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return "unreadable"
    for section in (config, config.get("ui") or {}, config.get("cli") or {}):
        if isinstance(section, dict) and isinstance(section.get("permission_mode"), str):
            return section["permission_mode"]
    return None



def _infer_medium_from_theme(theme: str, title: str) -> tuple[str, str, str]:
    """Return (medium, rendering, signature_hint) from theme/title keywords."""
    blob = f"{theme} {title}".lower()
    anime_keys = (
        "anime",
        "doujin",
        "manga",
        "漫剧",
        "同人",
        "里番",
        "二次元",
        "anime",
        "cel",
    )
    if any(k in blob for k in anime_keys):
        medium = "high-quality anime illustration"
        rendering = "clean anime linework, soft cel shading, stable character sheets"
        sig = (
            f"Vertical consistent high-quality anime short for '{title}', "
            "clean linework, coherent palette, stable cast identity and wardrobe across shots."
        )
        return medium, rendering, sig
    medium = "photoreal cinematic short"
    rendering = "photoreal, detailed skin/fabric; switch to anime only if theme requires"
    sig = (
        f"Consistent film style for '{title}': photoreal cinematic short, "
        "natural skin texture, coherent palette, stable wardrobe and identity across shots."
    )
    return medium, rendering, sig


def _cmd_init_in_place(args: argparse.Namespace) -> int:
    title = args.title.strip()
    theme = args.theme.strip()
    aspect = args.aspect
    root = Path(args.root).expanduser().resolve()
    root_has_content = root.exists() and any(root.iterdir())
    if root_has_content and not args.force:
        raise FilmError(f"Root not empty: {root} (pass --force to reuse)")
    if root_has_content and args.force and not (root / "production-book.json").is_file():
        raise FilmError(
            "legacy root has no production-book.json; run "
            f'aifilm director migrate-audit --root "{root}" before any explicit migration'
        )
    ensure_tree(root)
    (root / "canonical" / "cast").mkdir(parents=True, exist_ok=True)
    (root / "canonical" / "lookbook").mkdir(parents=True, exist_ok=True)
    w, h = aspect_dims(aspect)
    brief = {
        "title": title,
        "theme": theme,
        "aspect_ratio": aspect,
        "width": w,
        "height": h,
        "created_at": utc_now(),
        "provider": "grok-imagine",
    }
    medium, rendering, sig = _infer_medium_from_theme(theme, title)
    style = {
        "schema_version": 1,
        "locked": False,
        "title": title,
        "medium": medium,
        "palette": "to be filled from theme",
        "lighting": "motivated practicals, natural contrast",
        "lens": "contemporary digital cinema, modest depth of field",
        "rendering": rendering,
        "signature_block": sig,
        "identity_lock": "to be filled: face hair eyes wardrobe for each recurring adult cast member",
        "negative_hints": (
            "do not change face identity, do not switch medium mid-film, "
            "no underage characters, no random outfit recolor"
        ),
        "canonical_style_path": None,
        "cast_masters": {},
        "updated_at": utc_now(),
    }
    film_spec = {
        "title": title,
        "description": theme,
        "aspect_ratio": aspect,
        "scenes": [],
    }
    try:
        from bgm_library import BGMLibraryError, default_library_root, library_status

        if library_status(default_library_root()).get("ready_for_default"):
            film_spec["audio_policy"] = {
                "mode": "auto",
                "bed_source": "approved_library",
            }
    except (BGMLibraryError, OSError, ValueError):
        # A missing or corrupt optional shared library cannot make init unusable.
        pass
    timeline = {
        "schema_version": 1,
        "fps": DEFAULT_FPS,
        "width": w,
        "height": h,
        "shots": [],
    }
    write_json(root / "brief.json", brief)
    write_json(root / "style-bible.json", style)
    write_json(root / "film-spec.json", film_spec)
    write_json(root / "timeline.json", timeline)
    manifest = empty_manifest(title=title, theme=theme, aspect=aspect)
    # Existing projects and clients remain on v2 until they explicitly opt in
    # to v3; v3 changes the review input contract and must not be silent.
    manifest["review_contract_version"] = 2
    manifest["truth_contract"]["contract_sha256"] = sha256_file(root / "film-spec.json")
    save_manifest(root, manifest)
    from production_book import init_production_book

    init_production_book(
        root,
        title=title,
        rigor="professional",
        format_pack="vertical-short",
        genre_pack="drama",
        quality_target="standard",
    )
    try:
        from pipeline_events import append_event

        append_event(root, stage="init", phase="completed")
    except OSError:
        pass
    (root / "README.md").write_text(
        f"# {title}\n\nTheme: {theme}\n\nProvider: Grok Imagine\nRoot: `{root}`\n",
        encoding="utf-8",
    )
    emit(
        {
            "ok": True,
            "root": str(root),
            "title": title,
            "aspect_ratio": aspect,
            "width": w,
            "height": h,
            "workflow": {
                "entry": "/ai-film-grok",
                "mode": "professional",
                "internal_stage_model": "professional-director-11",
            },
        }
    )
    return 0




def _pipeline_bundle(
    root: Path,
    *,
    gates: dict[str, Any],
    open_n: int = 0,
    persist: bool = True,
) -> tuple[list[dict[str, str]], dict[str, Any], str | None, str | None]:
    """Build next_actions + pipeline_stage; optionally persist sidecar for HUD."""
    from next_actions import (
        build_next_actions,
        detect_pipeline_stage,
        persist_pipeline_stage,
    )

    pipeline = detect_pipeline_stage(root, gates=gates, open_reshoot_count=open_n)
    book = read_json(root / "production-book.json") or {}
    if book.get("rigor") == "professional":
        from dispatch import build_dispatch

        packet = build_dispatch(
            root,
            gates=gates,
            open_reshoot_count=open_n,
            include_capability=False,
            write_receipt=persist,
            use_state_cache=False,
        )
        actions = list(packet.get("next_actions") or [])
        next_cmd = packet.get("next_cmd")
        next_id = packet.get("next_id")
        pipeline["workflow"] = packet.get("workflow")
        pipeline["workflow_stage"] = (packet.get("workflow") or {}).get("current_stage")
        pipeline["bound_next_action"] = packet.get("next_action")
        pipeline["state_hash"] = packet.get("state_hash")
    else:
        actions = build_next_actions(root, gates=gates, open_reshoot_count=open_n)
        next_cmd = actions[0]["cmd"] if actions else None
        next_id = actions[0].get("id") if actions else None
    if persist:
        with contextlib.suppress(OSError):
            persist_pipeline_stage(
                root,
                pipeline,
                next_cmd=next_cmd,
                next_id=next_id,
            )
    return actions, pipeline, next_cmd, next_id






















from cli_bootstrap import (  # noqa: E402 — lock-runtime/resume-manifest (W5d)
    cmd_lock_runtime,
    cmd_resume_manifest,
)
from cli_director_ops import (  # noqa: E402
    cmd_department,
    cmd_director,
    cmd_director_notes,
    cmd_serial,
)
from cli_evidence import (  # noqa: E402 — evidence cluster extracted (W5d)
    cmd_production_evidence,
    cmd_promotion_report,
    cmd_speech_preview,
    cmd_state_index,
)
from cli_longform import cmd_longform  # noqa: E402
from cli_media import (  # noqa: E402, F401
    cmd_assemble,
    cmd_auto_cut,
    cmd_continuity_chain,
    cmd_extract_frame,
    cmd_face_identity,
    cmd_ingest_footage,
    cmd_lint_continuity,
    cmd_lock_style,
    cmd_reencode_clips,
    cmd_register_clip,
    cmd_register_still,
    cmd_shortform,
    cmd_style_lock,
)
from cli_misc_ops import (  # noqa: E402
    cmd_assets,
    cmd_comfy,
    cmd_dashboard,
    cmd_experiment,
    cmd_gold,
    cmd_h3,
    cmd_init,
    cmd_interactive,
    cmd_manifest,
    cmd_metrics,
    cmd_node,
    cmd_optimization_program,
    cmd_plan,
    cmd_production_report,
    cmd_quality_ledger,
    cmd_review_ui,
    cmd_route,
    cmd_still_challenge,
    cmd_upscale,
    cmd_team,
    cmd_truth,
    cmd_vibevoice_asr,
    cmd_weapon,
    cmd_workflow,
    cmd_workshop,
)
from cli_motion_ops import (  # noqa: E402
    cmd_env_plate,
    cmd_frw,
    cmd_frw_lipsync,
    cmd_i2v_motion_gate,
    cmd_motion_plan,
)
from cli_oauth import (  # noqa: E402 — oauth/usage extracted (W5d)
    cmd_generation_usage,
    cmd_grok_oauth,
)
from cli_orchestrate import (  # noqa: E402 — orchestration cluster extracted (W5d)
    cmd_advance,
    cmd_autopilot,
    cmd_craft,
    cmd_dispatch,
    cmd_next,
    cmd_selects,
    cmd_stage,
)
from cli_pilot import cmd_pilot  # noqa: E402 — pilot cluster extracted (W5)
from cli_post import (  # noqa: E402, F401
    _commit_selected_bgm_usage,
    cmd_closeout,
    cmd_compose_preview,
    cmd_compose_render,
    cmd_export_compose,
    cmd_export_desktop,
    cmd_final,
    cmd_final_editorial_review,
    cmd_post_plan,
    cmd_post_quality,
    cmd_register_final,
    cmd_review_final,
)
from cli_quality_ops import (  # noqa: E402
    cmd_benchmark,
    cmd_cinematic_audit,
    cmd_creative_pipeline,
    cmd_dailies,
    cmd_delivery_package,
    cmd_dialogue_benchmark,
    cmd_dialogue_benchmark_approve,
    cmd_dialogue_benchmark_queue,
    cmd_dialogue_benchmark_review,
    cmd_dialogue_production_plan,
    cmd_heat,
    cmd_preflight,
    cmd_provider_canary,
    cmd_quality,
    cmd_quality_closure,
    cmd_quality_status,
)
from cli_review_ops import (  # noqa: E402
    cmd_external_review,
    cmd_review_contract,
    cmd_review_shot,
    cmd_visual_text_audit,
    cmd_visual_text_repair,
)
from cli_status import (  # noqa: E402, F401
    _classify_doctor_readiness,
    _status_audio_summary,
    _status_evidence,
    _status_inventory,
    _status_remotion_probe,
    cmd_doctor,
    cmd_status,
)
from cli_write_spec import (  # noqa: E402, F401
    _compatibility_vo_mode,
    cmd_write_spec,
)


def _run_optimization_cli(args: argparse.Namespace, action: str) -> int:
    from cli_optimization import OptimizationCliError, dashboard, experiment, gold, metrics, program

    runners = {
        "metrics": metrics,
        "experiment": experiment,
        "gold": gold,
        "dashboard": dashboard,
        "optimization-program": program,
    }
    try:
        report, code = runners[action](args)
    except OptimizationCliError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code







def _run_quality_reporting_cli(args: argparse.Namespace, command: str) -> int:
    from cli_quality_reporting import QualityReportingCliError, production_report, quality_ledger

    runners = {"quality-ledger": quality_ledger, "production-report": production_report}
    try:
        report = runners[command](args)
    except QualityReportingCliError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0







def _cmd_graph_legacy(args: argparse.Namespace) -> int:
    """Vertical Drama Graph: legacy derive/import + canonical project/validate/status."""
    root = Path(args.root).expanduser().resolve()
    if str(getattr(args, "graph_action", "") or "") in {"validate", "status"}:
        from cli_graph import status as status_graph_cli
        from cli_graph import validate as validate_graph_cli

        runner = validate_graph_cli if args.graph_action == "validate" else status_graph_cli
        report, code = runner(args, root)
        emit(report)
        return code
    from drama_graph import derive_graph, graph_path, validate_graph
    from narrative_control import (
        GRAPH_SCHEMA_VERSION,
        draft_director_board,
        graph_content_sha256,
        graph_locked_for_projection,
    )

    action = str(getattr(args, "graph_action", "") or "")
    if action == "derive":
        existing = (
            json.loads(graph_path(root).read_text(encoding="utf-8"))
            if graph_path(root).is_file()
            else {}
        )
        if int(existing.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION:
            raise FilmError(
                "canonical drama-graph exists; use aifilm graph project or plan edit, not graph derive"
            )
        graph = derive_graph(root, write=not bool(getattr(args, "no_write", False)))
        v = validate_graph(graph)
        emit(
            {
                "ok": bool(v.get("ok")),
                "action": "derive",
                "path": str(graph_path(root)),
                "shot_count": v.get("shot_count"),
                "warnings": (graph.get("warnings") or []) + (v.get("warnings") or []),
                "errors": v.get("errors") or [],
                "project": graph.get("project"),
                "episode_count": len(graph.get("episodes") or []),
            }
        )
        return 0 if v.get("ok") else 1
    if action == "import":
        existing = (
            json.loads(graph_path(root).read_text(encoding="utf-8"))
            if graph_path(root).is_file()
            else {}
        )
        if int(existing.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION:
            raise FilmError(
                "canonical drama-graph already exists; refusing legacy import overwrite"
            )
        graph = derive_graph(root, write=False)
        spec = (
            json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            if (root / "film-spec.json").is_file()
            else {}
        )
        di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
        graph["schema_version"] = GRAPH_SCHEMA_VERSION
        graph["derived_from"] = {
            **(graph.get("derived_from") or {}),
            "mode": "legacy-import",
            "imported_at": utc_now(),
        }
        graph["story"] = {
            "genre": str(spec.get("genre") or "adult"),
            "premise": str(spec.get("description") or di.get("logline") or ""),
            "logline": str(di.get("logline") or spec.get("description") or ""),
            "theme": str(di.get("theme") or ""),
            "protagonist_ids": list(di.get("cast") or spec.get("cast_ids") or []),
            "protagonist_goal": str(di.get("protagonist_goal") or ""),
            "protagonist_want": str(di.get("protagonist_want") or ""),
            "protagonist_need": str(di.get("protagonist_need") or ""),
            "protagonist_arc": str(di.get("protagonist_arc") or ""),
            "opposition": str(di.get("opposition") or ""),
            "stakes": str(di.get("stakes") or ""),
            "climax_choice": str(di.get("climax_choice") or ""),
            "ending_hook": str(di.get("ending_hook") or ""),
            "emotional_arc": list(di.get("emotional_arc") or []),
            "act_structure": di.get("act_structure")
            if isinstance(di.get("act_structure"), dict)
            else {},
            "pace_chart": list(di.get("pace_chart") or []),
            "constraints": list(di.get("taboos") or []),
            "status": "needs_authoring",
        }
        for ep in graph.get("episodes") or []:
            for scene in ep.get("scenes") or []:
                for beat in scene.get("beats") or []:
                    if not isinstance(beat, dict):
                        continue
                    beat.setdefault("objective", "needs_authoring")
                    beat.setdefault("obstacle", "needs_authoring")
                    beat.setdefault("tactic", "needs_authoring")
                    beat.setdefault("turn", "needs_authoring")
                    beat.setdefault("outcome", "needs_authoring")
                    beat.setdefault("state_delta", "needs_authoring")
                    beat.setdefault("director_board", draft_director_board())
        from narrative_control import ensure_graph_controls

        ensure_graph_controls(graph)
        write_json(graph_path(root), graph)
        migration = {
            "schema_version": 1,
            "kind": "drama-graph-migration",
            "at": utc_now(),
            "source": "film-spec.json",
            "target": "drama-graph.json",
            "target_schema_version": GRAPH_SCHEMA_VERSION,
            "content_sha256": graph_content_sha256(graph),
            "note": "legacy import is draft-only; complete director_board and lock scopes before projection",
        }
        write_json(root / "receipts" / "graph-migration.json", migration)
        emit(
            {
                "ok": True,
                "action": "import",
                "path": str(graph_path(root)),
                "receipt": str(root / "receipts" / "graph-migration.json"),
                "state": graph.get("state"),
                "content_sha256": graph_content_sha256(graph),
            }
        )
        return 0
    if action == "project":
        graph = (
            json.loads(graph_path(root).read_text(encoding="utf-8"))
            if graph_path(root).is_file()
            else {}
        )
        if int(graph.get("schema_version") or 0) < GRAPH_SCHEMA_VERSION:
            raise FilmError(
                "graph project requires canonical graph v2; run aifilm graph import first"
            )
        ready = graph_locked_for_projection(graph)
        if not ready.get("ok"):
            raise FilmError(
                "graph is not ready for projection: "
                + ", ".join(
                    ready.get("missing_scopes")
                    or [
                        i.get("code", "NARRATIVE")
                        for i in (ready.get("semantic") or {}).get("errors", [])
                    ]
                )
            )
        from story_plan import project_graph_to_film_spec

        existing = (
            json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            if (root / "film-spec.json").is_file()
            else {}
        )
        has_shots = any(
            isinstance(sc, dict) and sc.get("shots") for sc in (existing.get("scenes") or [])
        )
        if has_shots and not bool(getattr(args, "force", False)):
            raise FilmError("film-spec already has shots; pass --force to overwrite projection")
        norm_path = root / "receipts" / "story-normalize.json"
        norm = json.loads(norm_path.read_text(encoding="utf-8")) if norm_path.is_file() else None
        spec = project_graph_to_film_spec(graph, base_spec=existing, normalized=norm)
        write_json(root / "film-spec.json", spec)
        emit(
            {
                "ok": True,
                "action": "project",
                "path": str(root / "film-spec.json"),
                "source_revision": graph.get("revision"),
                "source_sha256": graph_content_sha256(graph),
            }
        )
        return 0
    raise FilmError(f"unknown graph action {action!r}")

















from cli_audio import (  # noqa: E402 — audio cluster extracted (W5c)
    cmd_adult_female_voice_pack,
    cmd_ambience_candidate,
    cmd_audio_event,
    cmd_audio_plan,
    cmd_audio_produce,
    cmd_audio_tts_render,
    cmd_audio_verify,
    cmd_bgm_candidate,
    cmd_bgm_library,
    cmd_capability,
    cmd_elevenlabs_canary,
    cmd_lipsync_canary,
    cmd_lipsync_challenge,
    cmd_lipsync_node,
    cmd_lipsync_pilot,
    cmd_performance_candidate,
    cmd_sfx_canary,
    cmd_sfx_candidate,
    cmd_sfx_library,
    cmd_tts_ab,
    cmd_tts_rehearse,
    cmd_verify,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aifilm_grok", description="ai-film-grok local control plane")
    sub = p.add_subparsers(dest="cmd", required=True)

    from cli_bootstrap import add_bootstrap_parsers
    from cli_evidence import add_evidence_parsers
    from cli_oauth import add_oauth_parsers
    from cli_orchestrate import add_orchestrate_parsers

    add_bootstrap_parsers(sub)
    add_oauth_parsers(sub)
    add_orchestrate_parsers(sub)
    add_evidence_parsers(sub)

    from cli_director_ops import add_director_ops_parsers
    from cli_media import add_media_parsers
    from cli_misc_ops import add_misc_ops_parsers
    from cli_motion_ops import add_motion_ops_parsers
    from cli_post import add_post_parsers
    from cli_quality_ops import add_quality_ops_parsers
    from cli_review_ops import add_review_ops_parsers
    from cli_status import add_status_parsers

    add_status_parsers(sub)
    add_media_parsers(sub)
    add_post_parsers(sub)
    add_quality_ops_parsers(sub)
    add_director_ops_parsers(sub)
    add_motion_ops_parsers(sub)
    add_review_ops_parsers(sub)
    add_misc_ops_parsers(sub)


    from cli_audio import add_audio_parsers

    add_audio_parsers(sub)

    from cli_write_spec import add_write_spec_parsers

    add_write_spec_parsers(sub)

    speech_performance_timing = sub.add_parser(
        "speech-performance-timing",
        help="Check measured dialogue duration against delivery evidence and reaction space",
    )
    speech_performance_timing.add_argument("--root", required=True)

    audio_provenance = sub.add_parser(
        "audio-provenance",
        help="Bind dialogue rehearsal audio hashes to voice carrier and registered final MP4",
    )
    audio_provenance.add_argument("--root", required=True)
    from cli_optimization import add_optimization_parsers

    add_optimization_parsers(sub)

    from cli_quality_reporting import add_quality_reporting_parsers

    add_quality_reporting_parsers(sub)

    ledger = sub.add_parser(
        "director-ledger", help="Build checksum-bound ledger of human-approved exceptions"
    )
    ledger.add_argument("--root", required=True)
    from cli_pilot import add_pilot_parsers

    add_pilot_parsers(sub)

    from cli_graph import add_graph_parsers

    add_graph_parsers(sub)

    from cli_team import add_team_parsers

    add_team_parsers(sub)

    # Phase 2: Skill Registry shell
    from cli_plan import add_plan_parsers

    add_plan_parsers(sub)
    from cli_longform import add_longform_parsers

    add_longform_parsers(sub)

    from cli_assets import add_assets_parsers

    add_assets_parsers(sub)

    from cli_workshop import add_workshop_parsers

    add_workshop_parsers(sub)

    from review_ui import add_review_ui_parsers

    add_review_ui_parsers(sub)
    from cli_interactive import add_interactive_parsers

    add_interactive_parsers(sub)

    from cli_comfy import add_comfy_parsers
    from cli_h3 import add_h3_parsers
    from cli_still_challenge import add_still_challenge_parsers
    from cli_upscale import add_upscale_parsers

    add_comfy_parsers(sub)
    add_h3_parsers(sub)
    add_still_challenge_parsers(sub)
    add_upscale_parsers(sub)
    from cli_node import add_node_parsers

    add_node_parsers(sub)
    from cli_weapon import add_weapon_parsers

    add_weapon_parsers(sub)
    from cli_bgm_library import add_bgm_library_parsers

    add_bgm_library_parsers(sub)
    from cli_route import add_route_parsers

    add_route_parsers(sub)

    from cli_workflow import add_workflow_parsers

    add_workflow_parsers(sub)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        # Every film-root plugin command refreshes the lightweight scene-sound
        # receipt before its own work. It never generates, downloads, or mutates
        # film-spec; write-spec repeats it after writing the new projection.
        if getattr(args, "root", None) and args.cmd != "external-review":
            root = Path(args.root).expanduser().resolve()
            if (root / "film-spec.json").is_file():
                from scene_sound import reconcile as reconcile_scene_sound

                reconcile_scene_sound(root, write=not bool(getattr(args, "no_write", False)))
        # Fast dispatch: simple one-command → one-handler (61 commands).
        # Inline branches below handle lazy imports / sub-actions.
        _SIMPLE_DISPATCH: dict[str, argparse.Namespace] = {
            "doctor": cmd_doctor,
            "lock-runtime": cmd_lock_runtime,
            "review-shot": cmd_review_shot,
            "review-contract": cmd_review_contract,
            "frw-lipsync": cmd_frw_lipsync,
            "env-plate": cmd_env_plate,
            "motion-plan": cmd_motion_plan,
            "i2v-motion-gate": cmd_i2v_motion_gate,
            "grok-oauth": cmd_grok_oauth,
            "dispatch": cmd_dispatch,
            "advance": cmd_advance,
            "autopilot": cmd_autopilot,
            "craft": cmd_craft,
            "selects": cmd_selects,
            "audio-plan": cmd_audio_plan,
            "audio-verify": cmd_audio_verify,
            "verify": cmd_verify,
            "audio-tts-render": cmd_audio_tts_render,
            "audio-produce": cmd_audio_produce,
            "audio-event": cmd_audio_event,
            "bgm-candidate": cmd_bgm_candidate,
            "bgm-library": cmd_bgm_library,
            "performance-candidate": cmd_performance_candidate,
            "adult-female-voice-pack": cmd_adult_female_voice_pack,
            "ambience-candidate": cmd_ambience_candidate,
            "sfx-canary": cmd_sfx_canary,
            "sfx-candidate": cmd_sfx_candidate,
            "sfx-library": cmd_sfx_library,
            "lipsync-node": cmd_lipsync_node,
            "lipsync-canary": cmd_lipsync_canary,
            "lipsync-pilot": cmd_lipsync_pilot,
            "lipsync-challenge": cmd_lipsync_challenge,
            "capability": cmd_capability,
            "tts-ab": cmd_tts_ab,
            "elevenlabs-canary": cmd_elevenlabs_canary,
            "init": cmd_init,
            "resume-manifest": cmd_resume_manifest,
            "status": cmd_status,
            "truth": cmd_truth,
            "quality-status": cmd_quality_status,
            "production-evidence": cmd_production_evidence,
            "stage": cmd_stage,
            "write-spec": cmd_write_spec,
            "lint-continuity": cmd_lint_continuity,
            "extract-frame": cmd_extract_frame,
            "continuity-chain": cmd_continuity_chain,
            "lock-style": cmd_lock_style,
            "style-lock": cmd_style_lock,
            "face-identity": cmd_face_identity,
            "register-still": cmd_register_still,
            "tts-rehearse": cmd_tts_rehearse,
            "register-clip": cmd_register_clip,
            "assemble": cmd_assemble,
            "ingest-footage": cmd_ingest_footage,
            "auto-cut": cmd_auto_cut,
            "shortform": cmd_shortform,
            "reencode-clips": cmd_reencode_clips,
            "final": cmd_final,
            "review-final": cmd_review_final,
            "final-editorial-review": cmd_final_editorial_review,
            "benchmark": cmd_benchmark,
            "dialogue-benchmark": cmd_dialogue_benchmark,
            "dialogue-benchmark-review": cmd_dialogue_benchmark_review,
            "dialogue-benchmark-approve": cmd_dialogue_benchmark_approve,
            "dialogue-production-plan": cmd_dialogue_production_plan,
            "visual-text-audit": cmd_visual_text_audit,
            "visual-text-repair": cmd_visual_text_repair,
            "dialogue-benchmark-queue": cmd_dialogue_benchmark_queue,
            "creative-pipeline": cmd_creative_pipeline,
            "dailies": cmd_dailies,
            "post-quality": cmd_post_quality,
            "provider-canary": cmd_provider_canary,
            "delivery-package": cmd_delivery_package,
            "quality-closure": cmd_quality_closure,
            "promotion-report": cmd_promotion_report,
            "director-notes": cmd_director_notes,
            "next": cmd_next,
            "preflight": cmd_preflight,
            "cinematic-audit": cmd_cinematic_audit,
            "quality": cmd_quality,
            "heat": cmd_heat,
            "state-index": cmd_state_index,
            "pilot": cmd_pilot,
            "closeout": cmd_closeout,
            "compose-preview": cmd_compose_preview,
            "export-compose": cmd_export_compose,
            "compose-render": cmd_compose_render,
            "post-plan": cmd_post_plan,
            "register-final": cmd_register_final,
            "export-desktop": cmd_export_desktop,
            "frw": cmd_frw,
            "manifest": cmd_manifest,
            "director": cmd_director,
            "serial": cmd_serial,
            "department": cmd_department,
            "plan": cmd_plan,
            "longform": cmd_longform,
            "assets": cmd_assets,
            "workshop": cmd_workshop,
            "review-ui": cmd_review_ui,
            "interactive": cmd_interactive,
            "usage": cmd_generation_usage,
            "metrics": cmd_metrics,
            "experiment": cmd_experiment,
            "gold": cmd_gold,
            "dashboard": cmd_dashboard,
            "optimization-program": cmd_optimization_program,
            "quality-ledger": cmd_quality_ledger,
            "production-report": cmd_production_report,
            "external-review": cmd_external_review,
            "vibevoice-asr": cmd_vibevoice_asr,
            "speech-preview": cmd_speech_preview,
            "comfy": cmd_comfy,
            "h3": cmd_h3,
            "still-challenge": cmd_still_challenge,
            "upscale": cmd_upscale,
            "node": cmd_node,
            "weapon": cmd_weapon,
            "route": cmd_route,
            "team": cmd_team,
            # closeout → cmd_closeout (closeout.py). pilot pack → cmd_pilot.
            "pilot-pack": cmd_workflow,
            "bulk-preflight": cmd_workflow,
            "variety-precheck": cmd_workflow,
            "select-shortlist": cmd_workflow,
            "anti-hijack": cmd_workflow,
            "ship-prep": cmd_workflow,
            "gpu-lease": cmd_workflow,
            "tunnel-probe": cmd_workflow,
            "tunnel-ensure": cmd_workflow,
            "queue-progress": cmd_workflow,
            "agent-review-final": cmd_workflow,
            "fidelity": cmd_workflow,
            "design-go": cmd_workflow,
            # 2026-08-06 打通: parsers exist in cli_workflow but were missing from dispatch
            "gate-auto": cmd_workflow,
            "cinematic-gate": cmd_workflow,
            "five-track": cmd_workflow,
        }
        handler = _SIMPLE_DISPATCH.get(args.cmd)
        if handler is not None:
            return handler(args)

        # R3: residual cmds formerly inlined as if-ladder (see cli/cli_hub_residual.py)
        from cli.cli_hub_residual import RESIDUAL_CMDS
        from cli.cli_hub_residual import run as run_hub_residual

        if args.cmd in RESIDUAL_CMDS:
            return run_hub_residual(args)
        raise FilmError(f"Unknown command {args.cmd}")
    except FilmError as exc:
        emit({"ok": False, "error": str(exc)})
        return 2
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        emit({"ok": False, "error": f"Command failed: {err[:2000]}"})
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
