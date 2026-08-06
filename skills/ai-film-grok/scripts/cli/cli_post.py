#!/usr/bin/env python3
"""Post / final / compose / closeout / desktop-export CLI handlers.

Extracted from aifilm_grok. Public command strings unchanged.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.constants import EXPORT_METADATA_FILES, MANIFEST_NAME
from core.emit import emit
from core.film_io import (
    film_dirs,
    load_director_notes,
    load_manifest,
    save_director_notes,
    save_manifest,
)
from core.gates import recompute_gates
from core.paths import record_file_matches, which_npx_safe
from director_review import (
    SCORECARD_DIMENSIONS,
    DirectorReviewError,
    build_grades_from_cli,
    build_notes_from_scorecard_failures,
    build_scorecard_from_cli,
    open_reshoot_items,
    parse_fail_reasons,
    parse_shot_id_list,
    scorecard_all_pass,
    scorecard_payload,
    validate_scorecard_for_approve,
)
from logger import log
from media_qa import MediaQAError, analyze_media
from runtime_policy import sha256
from security_policy import (
    SecurityPolicyError,
    reject_symlinks,
    safe_existing_file,
    safe_subdirectory,
    safe_workspace_directory,
)
from util import read_json as _util_read_json
from util import require_json as read_json
from util import sha256_file, utc_now, write_json
from util.errors import FilmError
from util.subprocess import run
from util.validators import film_output_path


def cmd_post_quality(args: argparse.Namespace) -> int:
    from post_quality import audio_delivery_gate, premium_master_qc, register_vfx_shot, vfx_gate

    root = Path(args.root).expanduser().resolve()
    action = str(args.post_action)
    if action == "vfx-register":
        report = register_vfx_shot(
            root,
            shot_id=args.shot_id,
            plate=args.plate,
            status=args.status,
            reviewer=args.reviewer,
            notes=args.notes,
        )
    elif action == "vfx-check":
        report = vfx_gate(root)
    elif action == "audio-check":
        report = audio_delivery_gate(root)
    elif action == "master-qc":
        report = premium_master_qc(root, final=args.final)
    else:
        raise FilmError(f"Unknown post quality action: {action}")
    emit(report)
    return 0 if report.get("ok") else 2


def _commit_selected_bgm_usage(
    root: Path,
    *,
    output: str | None = None,
    output_sha256: str | None = None,
) -> dict[str, Any] | None:
    """Commit approved-library use only after a successful final command."""
    selection_path = root / "receipts" / "bgm-selection.json"
    selection = _util_read_json(selection_path)
    if not isinstance(selection, dict) or not selection.get("selections"):
        return None
    mix_path = root / "audio" / "mix_report.json"
    mix = _util_read_json(mix_path)
    music_template = (
        mix.get("music_template")
        if isinstance(mix, dict) and isinstance(mix.get("music_template"), dict)
        else {}
    )
    if (
        music_template.get("source") != "approved_library"
        or music_template.get("mode") != "approved_library"
    ):
        # A stale selection receipt must not affect a procedural or legacy rerun.
        return None
    if not all(
        isinstance(item, dict) and item.get("asset_id") and item.get("sha256")
        for item in selection.get("selections") or []
    ):
        raise FilmError("approved-library selection receipt is not checksum-bound")
    selected_bindings = [
        (str(item.get("shot_id") or ""), str(item["asset_id"]), str(item["sha256"]))
        for item in selection["selections"]
    ]
    mixed_bindings = [
        (
            str(item.get("shot_id") or ""),
            str(item.get("asset_id") or ""),
            str(item.get("sha256") or ""),
        )
        for item in music_template.get("selections") or []
        if isinstance(item, dict)
    ]
    if (
        selected_bindings != mixed_bindings
        or selection.get("catalog_revision") != music_template.get("catalog_revision")
        or selection.get("catalog_sha256") != music_template.get("catalog_sha256")
    ):
        raise FilmError("approved-library selection does not match this final mix")
    checksum = str(output_sha256 or "")
    if len(checksum) != 64 and output:
        output_path = Path(output).expanduser()
        if output_path.is_file():
            checksum = sha256_file(output_path)
    if len(checksum) != 64:
        delivery = _util_read_json(root / "out" / "final-delivery.json") or {}
        checksum = str(delivery.get("output_sha256") or "")
    if len(checksum) != 64:
        raise FilmError("cannot commit BGM usage without the successful final checksum")
    from bgm_library import commit_usage, default_library_root

    committed = commit_usage(default_library_root(), selection, final_sha256=checksum)
    selection["usage_committed"] = True
    selection["usage_commit"] = committed
    write_json(selection_path, selection)
    if isinstance(mix, dict):
        music_template["usage_commit"] = committed
        mix["music_template"] = music_template
        write_json(mix_path, mix)
    return committed


def cmd_final(args: argparse.Namespace) -> int:
    """FFmpeg final, optionally followed by HyperFrames/Remotion designed-post compose-render."""
    skill_dir = Path(__file__).resolve().parents[2]
    script = skill_dir / "scripts" / "render_final.py"
    if not script.is_file():
        raise FilmError(f"Missing {script}")
    root = Path(args.root).expanduser().resolve()
    import os as _os

    from production_truth import ProductionTruthError, require_current_canonical_truth

    # H3 native / incomplete drama-graph ship: --skip-canonical-truth or AIFILM_SKIP_CANONICAL_TRUTH=1
    try:
        from production_truth import (
            resolve_skip_canonical_truth,
            write_skip_canonical_truth_receipt,
        )
    except ImportError:  # pragma: no cover
        from plan.production_truth import (  # type: ignore
            resolve_skip_canonical_truth,
            write_skip_canonical_truth_receipt,
        )

    skip_contract = resolve_skip_canonical_truth(
        flag=bool(getattr(args, "skip_canonical_truth", False)),
        env=dict(_os.environ),
    )
    skip_truth = bool(skip_contract.get("skip"))
    if not skip_truth:
        try:
            require_current_canonical_truth(root)
        except ProductionTruthError as exc:
            raise FilmError(
                f"{exc}. Fix drama-graph/manifest truth, or pass --skip-canonical-truth "
                f"(H3 native bulk ship; not for canonical series lock)."
            ) from exc
    else:
        log(
            "final: skipping require_current_canonical_truth "
            "(--skip-canonical-truth or AIFILM_SKIP_CANONICAL_TRUTH)"
        )
        try:
            write_skip_canonical_truth_receipt(root, skip_contract)
        except Exception:  # noqa: BLE001
            pass
    post_engine = str(getattr(args, "post_engine", "hyperframes") or "hyperframes").strip().lower()
    if post_engine not in {"ffmpeg", "hyperframes", "remotion"}:
        raise FilmError("--post-engine must be ffmpeg|hyperframes|remotion")
    post_plan: dict[str, Any] | None = None
    if (root / "post-plan.json").is_file():
        sys.path.insert(0, str(skill_dir / "scripts"))
        try:
            from post_plan import PostPlanError, load_post_plan, record_render_evidence

            post_plan = load_post_plan(root, required=True)
            if post_engine != post_plan["post_owner"]:
                raise PostPlanError(
                    f"post-plan post_owner={post_plan['post_owner']}; --post-engine {post_engine} is not allowed"
                )
        except ImportError as exc:
            raise FilmError(f"Cannot import post_plan: {exc}") from exc
        except PostPlanError as exc:
            raise FilmError(str(exc)) from exc

    # Lesson preflight (default on): hard blocks; soft logs; --skip-preflight escapes
    preflight_report: dict[str, Any] | None = None
    if not bool(getattr(args, "skip_preflight", False)):
        sys.path.insert(0, str(skill_dir / "scripts"))
        try:
            from preflight import PreflightError, run_preflight
        except ImportError as exc:
            raise FilmError(f"Cannot import preflight: {exc}") from exc
        try:
            preflight_report = run_preflight(root)
        except PreflightError as exc:
            raise FilmError(str(exc)) from exc
        hard = preflight_report.get("hard") or []
        soft = preflight_report.get("soft") or []
        if hard:
            codes = ", ".join(str(i.get("code")) for i in hard if isinstance(i, dict))
            msgs = "; ".join(str(i.get("message")) for i in hard if isinstance(i, dict))
            raise FilmError(
                f"final blocked by preflight hard gates [{codes}]: {msgs}. "
                f'Run aifilm preflight --root "{root}" then fix, or --skip-preflight (not recommended).'
            )
        if soft:
            for item in soft:
                if not isinstance(item, dict):
                    continue
                log(
                    f"preflight soft [{item.get('code')}]: {item.get('message')} "
                    f"| fix: {item.get('fix') or '—'}"
                )
        if bool(getattr(args, "preflight_strict", False)) and soft:
            codes = ", ".join(str(i.get("code")) for i in soft if isinstance(i, dict))
            raise FilmError(
                f"final blocked by preflight --preflight-strict soft gates [{codes}]. "
                f'Run aifilm preflight --root "{root}" or drop --preflight-strict.'
            )
        log(f"preflight ok (hard=0 soft={len(soft)}) → post_engine={post_engine}")

    from cinematic_audit import write_audit

    cinematic = write_audit(root, require_authored_contract=True, require_clip_evidence=True)
    skip_cinematic = bool(getattr(args, "skip_cinematic", False)) or (
        str(_os.environ.get("AIFILM_SKIP_CINEMATIC") or "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if not cinematic.get("ok"):
        if skip_cinematic:
            log(
                "final: skipping cinematic audit block ["
                + ", ".join(cinematic.get("blocking_codes") or [])
                + "] (--skip-cinematic / AIFILM_SKIP_CINEMATIC) → OFFICIAL_FINAL_PLATE honesty"
            )
            try:
                from util import utc_now, write_json

                write_json(
                    root / "receipts" / "skip-cinematic.json",
                    {
                        "schema_version": 1,
                        "kind": "skip_cinematic",
                        "at": utc_now(),
                        "blocking_codes": list(cinematic.get("blocking_codes") or []),
                        "note": "plate path only; not master_lock",
                    },
                )
            except Exception:  # noqa: BLE001
                pass
        else:
            raise FilmError(
                "Cannot render final: cinematic audit failed ["
                + ", ".join(cinematic.get("blocking_codes") or [])
                + "]. Escape: --skip-cinematic or AIFILM_SKIP_CINEMATIC=1 "
                "(writes plate honesty; not master)."
            )

    # Fail early before TTS if loop-risk VO would force boring stream_loop.
    # When receipts/tts-rehearsal.json present, measured_duration_sec preferred over estimate.
    from production_gates import (
        ProductionGateError,
        assert_heat_allows_final,
        assert_no_loop_risk,
    )

    try:
        assert_no_loop_risk(
            root,
            force=bool(getattr(args, "allow_loop_risk", False)),
            strict_tts_rehearsal=bool(getattr(args, "strict_tts_rehearsal", False)),
        )
    except ProductionGateError as exc:
        raise FilmError(str(exc)) from exc

    # Wave 6: adult-max final requires heat final_ok (S-grade), not only A
    try:
        assert_heat_allows_final(
            root,
            force=bool(getattr(args, "skip_heat_gate", False)),
        )
    except ProductionGateError as exc:
        raise FilmError(str(exc)) from exc

    # Shot inventory must be complete before final (no indexing past missing clips)
    try:
        man_inv = load_manifest(root)
        sum_inv = recompute_gates(root, man_inv)
        from shot_inventory import InventoryError, assert_inventory_for_final

        shot_ids = list(sum_inv.get("shot_ids") or [])
        approved_clips = list(sum_inv.get("approved_clips") or [])
        # H3 native stage-2 / plate path: film-spec may fail cinematic framing
        # validate (empty shot_ids) while timeline + candidate clips exist.
        allow_cand = bool(getattr(args, "allow_candidate_clips", False)) or (
            str(_os.environ.get("AIFILM_FINAL_ALLOW_CANDIDATE_CLIPS") or "").strip().lower()
            in {"1", "true", "yes", "on"}
        ) or skip_cinematic or skip_truth
        if (not shot_ids or allow_cand) and (root / "timeline.json").is_file():
            try:
                from util import read_json as _rj

                tl = _rj(root / "timeline.json") or {}
                tl_ids = [
                    str(s.get("id"))
                    for s in (tl.get("shots") or [])
                    if isinstance(s, dict) and s.get("id")
                ]
                if tl_ids:
                    shot_ids = tl_ids
            except Exception:  # noqa: BLE001
                pass
        if allow_cand:
            clips = man_inv.get("clips") if isinstance(man_inv.get("clips"), dict) else {}
            usable = []
            for sid, rec in clips.items():
                if not isinstance(rec, dict):
                    continue
                st = str(rec.get("status") or "").lower()
                if st in {"approved", "candidate"} and rec.get("path"):
                    usable.append(str(sid))
            if usable:
                approved_clips = usable
        assert_inventory_for_final(shot_ids, approved_clips)
    except InventoryError as exc:
        raise FilmError(str(exc)) from exc

    # True-video-only: no Ken Burns / panel still-motion on hero timeline
    try:
        from true_video_policy import TrueVideoPolicyError, assert_manifest_true_video

        assert_manifest_true_video(root)
    except TrueVideoPolicyError as exc:
        raise FilmError(str(exc)) from exc

    if args.out_name:
        film_output_path(root, args.out_name)

    # ── Staged final (P0 · 2026-07-23 / 2026-08-05 caption_path): no assumed captions ──
    # stage_plate  → FFmpeg VO/BGM/clips; caption_path decides burn vs off
    # master_hf    → plate subs=off; HF/Remotion owns designed captions
    # ship_hardburn→ plate burn; designed post may grade only (no second caption layer)
    # Never: hand-mux silent plate and claim "HF will have burned subs".
    stages_receipt: dict[str, Any] = {}
    try:
        from post_route import (
            PostRouteError,
            apply_route_to_plate,
            resolve_caption_path,
            write_post_route,
        )

        route = resolve_caption_path(
            root,
            post_engine=post_engine,
            explicit=getattr(args, "caption_path", None),
            prefer_ship=bool(getattr(args, "ship_hardburn", False)),
        )
        plate = apply_route_to_plate(
            route,
            subs_mode=str(getattr(args, "subs", None) or "").strip().lower() or None,
            plate_cards=str(getattr(args, "plate_cards", None) or "auto"),
        )
        route_receipt = write_post_route(
            root,
            {
                **route,
                "plate_subs": plate["subs"],
                "plate_cards": plate["plate_cards"],
            },
        )
        stages_receipt["post_route"] = {
            "caption_path": plate["caption_path"],
            "source": route.get("source"),
            "path": route_receipt.get("path"),
        }
        subs_mode = plate["subs"]
        plate_cards = plate["plate_cards"]
        allow_burned_underlay_route = bool(plate.get("allow_burned_underlay"))
        designed_caption_owner = bool(plate.get("designed_caption_owner"))
        log(
            f"post_route: caption_path={plate['caption_path']} "
            f"source={route.get('source')} plate_subs={subs_mode} "
            f"plate_cards={plate_cards}"
        )
        for note in route.get("notes") or []:
            log(f"post_route note: {note}")
    except PostRouteError as exc:
        raise FilmError(str(exc)) from exc
    except ImportError as exc:
        raise FilmError(f"Cannot import post_route: {exc}") from exc

    cmd = [sys.executable, str(script), "--root", str(root)]
    if args.out_name:
        cmd += ["--out-name", args.out_name]
    if args.voice:
        cmd += ["--voice", args.voice]
    if getattr(args, "tts_backend", None):
        cmd += ["--tts-backend", args.tts_backend]
    # Use --flag=value so values starting with '-' (e.g. -5%) are not eaten as flags
    if getattr(args, "vo_rate", None):
        cmd += [f"--vo-rate={args.vo_rate}"]
    if getattr(args, "vo_pitch", None):
        cmd += [f"--vo-pitch={args.vo_pitch}"]
    if getattr(args, "vo_gain", None) is not None:
        cmd += [f"--vo-gain={args.vo_gain}"]
    if getattr(args, "vocal_color_gain", None) is not None:
        cmd += ["--vocal-color-gain", str(args.vocal_color_gain)]
    if args.title:
        cmd += ["--title", args.title]
    if args.end_title:
        cmd += ["--end-title", args.end_title]
    if args.music:
        cmd += ["--music", args.music]
    if args.music_license:
        cmd += ["--music-license", args.music_license]
    if getattr(args, "music_template", None):
        cmd += ["--music-template", str(args.music_template)]
    if args.music_volume is not None:
        cmd += ["--music-volume", str(args.music_volume)]
    if getattr(args, "transition_sec", None) is not None:
        cmd += ["--transition-sec", str(args.transition_sec)]
    if getattr(args, "native_audio_volume", None) is not None:
        cmd += ["--native-audio-volume", str(args.native_audio_volume)]
    if args.music_mood:
        cmd += ["--music-mood", args.music_mood]
    if getattr(args, "music_seed", None) is not None:
        cmd += ["--music-seed", str(int(args.music_seed))]
    if getattr(args, "sidechain_threshold", None) is not None:
        cmd += ["--sidechain-threshold", str(args.sidechain_threshold)]
    if getattr(args, "sidechain_ratio", None) is not None:
        cmd += ["--sidechain-ratio", str(args.sidechain_ratio)]
    if getattr(args, "sidechain_attack", None) is not None:
        cmd += ["--sidechain-attack", str(args.sidechain_attack)]
    if getattr(args, "sidechain_release", None) is not None:
        cmd += ["--sidechain-release", str(args.sidechain_release)]
    if getattr(args, "loudnorm", None):
        cmd += ["--loudnorm", str(args.loudnorm)]
    if getattr(args, "target_lufs", None) is not None:
        cmd += ["--target-lufs", str(args.target_lufs)]
    if getattr(args, "lipsync", None):
        cmd += ["--lipsync", args.lipsync]
    if getattr(args, "sub_lead", None) is not None:
        cmd += ["--sub-lead", str(args.sub_lead)]
    if getattr(args, "sub_max_unit", None) is not None:
        cmd += ["--sub-max-unit", str(args.sub_max_unit)]
    if getattr(args, "sub_max_chars", None) is not None:
        cmd += ["--sub-max-chars", str(args.sub_max_chars)]
    if getattr(args, "title_dur", None) is not None:
        cmd += ["--title-dur", str(args.title_dur)]
    if getattr(args, "end_dur", None) is not None:
        cmd += ["--end-dur", str(args.end_dur)]
    if getattr(args, "allow_loop_risk", False):
        cmd += ["--allow-loop-risk"]
    if bool(getattr(args, "skip_preflight", False)):
        cmd += ["--skip-preflight"]
    if bool(getattr(args, "skip_heat_gate", False)):
        cmd += ["--skip-heat-gate"]
    if getattr(args, "vo_fit", None):
        cmd += ["--vo-fit", str(args.vo_fit)]
    if bool(getattr(args, "resume", False)):
        cmd += ["--resume"]
    if bool(getattr(args, "force", False)):
        cmd += ["--force"]
    cmd += ["--subs", subs_mode]
    cmd += ["--plate-cards", plate_cards]
    log(
        f"stage_plate: render_final.py (post_engine={post_engine}, "
        f"subs={subs_mode}, plate_cards={plate_cards}) — captions NOT assumed here"
    )
    # Short films retain the 1200s floor; longform scales by picture clock,
    # shot count and lipsync work instead of being killed by a fixed timeout.
    requested_timeout = int(getattr(args, "plate_timeout", 0) or 0)
    if requested_timeout > 0:
        plate_timeout = requested_timeout
    else:
        from longform import estimate_plate_timeout

        plate_timeout = estimate_plate_timeout(
            root,
            lipsync=str(getattr(args, "lipsync", "off") or "off"),
        )
    from pipeline_events import append_event

    append_event(
        root,
        stage="final-plate",
        phase="started",
        note=f"timeout_sec={plate_timeout}",
    )
    try:
        proc = run(cmd, check=False, timeout=plate_timeout)
    except subprocess.TimeoutExpired as exc:
        append_event(
            root,
            stage="final-plate",
            phase="failed",
            note=f"timeout_sec={plate_timeout}",
        )
        # Wave D: do not leave agents guessing — point at direct render_final + floor
        skill_scripts = Path(__file__).resolve().parents[2]  # scripts/
        raise FilmError(
            f"final plate timed out after {plate_timeout}s. "
            f"Retry with --plate-timeout {max(plate_timeout * 2, 1800)} "
            f"or direct: {skill_scripts / 'runtime-python'} "
            f"{skill_scripts / 'render_final.py'} --root {root} "
            f"(set AIFILM_FFMPEG_TIMEOUT≥1800 for long mixes)"
        ) from exc
    append_event(
        root,
        stage="final-plate",
        phase="completed" if proc.returncode == 0 else "failed",
        note=f"returncode={proc.returncode}; timeout_sec={plate_timeout}",
    )
    sys.stderr.write(proc.stderr or "")
    ffmpeg_result: dict[str, Any] | None = None
    if proc.stdout:
        try:
            ffmpeg_result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            # keep raw for ffmpeg-only path
            if post_engine == "ffmpeg":
                print(proc.stdout)
    stages_receipt["plate"] = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "subs": subs_mode,
        "plate_cards": plate_cards,
        "timeout_sec": plate_timeout,
        "ffmpeg": {
            "output": (ffmpeg_result or {}).get("output"),
            "srt": (ffmpeg_result or {}).get("srt") or str(root / "out" / "final.srt"),
            "subtitles": (ffmpeg_result or {}).get("subtitles"),
        },
    }
    if proc.returncode != 0:
        if post_engine == "ffmpeg" and not proc.stdout:
            pass
        elif post_engine != "ffmpeg":
            emit(
                {
                    "ok": False,
                    "post_engine": post_engine,
                    "stage": "plate",
                    "stages": stages_receipt,
                    "error": (proc.stderr or proc.stdout or "render_final failed")[:2000],
                    "ffmpeg": ffmpeg_result,
                }
            )
        return proc.returncode

    if post_engine == "ffmpeg":
        if ffmpeg_result is not None:
            # Ship/plate path: durable pixel ink receipt (P0-B)
            try:
                from caption_pixel_check import run_caption_pixel_check

                final_guess = Path(
                    str(ffmpeg_result.get("output") or root / "out" / "film_final.mp4")
                )
                stages_receipt["caption_pixel"] = run_caption_pixel_check(
                    root, final_mp4=final_guess if final_guess.is_file() else None, write=True
                )
            except Exception as exc:  # noqa: BLE001
                stages_receipt["caption_pixel"] = {"ok": False, "error": str(exc)[:200]}
            out_obj = {
                **ffmpeg_result,
                "post_engine": "ffmpeg",
                "caption_path": (stages_receipt.get("post_route") or {}).get("caption_path"),
                "stages": stages_receipt,
                "caption_owner": "ffmpeg_plate",
            }
            bgm_usage = _commit_selected_bgm_usage(
                root,
                output=out_obj.get("output"),
                output_sha256=out_obj.get("output_sha256"),
            )
            if bgm_usage is not None:
                out_obj["bgm_usage"] = bgm_usage
            if preflight_report is not None:
                out_obj["preflight"] = {
                    "hard_ok": preflight_report.get("hard_ok"),
                    "soft_count": len(preflight_report.get("soft") or []),
                    "soft_codes": [
                        i.get("code")
                        for i in (preflight_report.get("soft") or [])
                        if isinstance(i, dict)
                    ],
                }
            emit(out_obj)
        elif proc.stdout:
            print(proc.stdout)
        return 0

    # stage_hf / stage_remotion: designed-post AFTER plate (subs off)
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_render import (
            ComposeRenderError,
            compose_render,
            probe_designed_post_tooling,
            probe_remotion_readiness,
        )
        from final_stages import (
            ensure_captions_after_hf,
            patch_delivery_burned_in,
            write_stages_receipt,
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_render/final_stages: {exc}") from exc

    if post_engine == "hyperframes":
        tooling = probe_designed_post_tooling()
        if not tooling.get("npx") or not tooling.get("hyperframes_ok"):
            raise FilmError(
                "post-engine=hyperframes 需要 Node/npx + hyperframes；"
                f"tooling={tooling}。可改用 --post-engine ffmpeg，"
                "或安装 Node 22+ 后重试。"
            )
        allow_burned = (
            bool(getattr(args, "allow_burned_underlay", False)) or allow_burned_underlay_route
        )
        if designed_caption_owner:
            log(
                "stage_hf: HyperFrames export+render owns designed captions "
                "(caption_path=master_hf; plate was subs=off; no double-burn assume)"
            )
        else:
            log(
                "stage_hf: HyperFrames grade/title only "
                "(caption_path=ship_hardburn; plate already burned; allow_burned_underlay)"
            )
            allow_burned = True
        try:
            result = compose_render(
                root,
                engine="hyperframes",
                export_first=True,
                force_export=True,
                layout="underlay",
                compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
                quality=str(getattr(args, "compose_quality", "standard") or "standard"),
                out_name=str(args.out_name or "film_final.mp4"),
                register=True,
                skip_check=bool(getattr(args, "skip_compose_check", False)),
                keep_raw=bool(getattr(args, "keep_compose_raw", False)),
                require_preview=bool(getattr(args, "require_preview", False)),
                title_dur=float(getattr(args, "title_dur", 1.5) or 1.5),
                end_dur=1.5,
                allow_burned_underlay=allow_burned,
                title_sequence=getattr(args, "title_sequence", None),
                end_roll=getattr(args, "end_roll", None),
            )
        except ComposeRenderError as exc:
            raise FilmError(str(exc)) from exc
        if post_plan is not None and result.get("rendered"):
            try:
                record_render_evidence(
                    root,
                    engine=post_engine,
                    output=result.get("output"),
                    composition_checked=bool(result.get("steps", {}).get("check", {}).get("ok")),
                    ffprobe_readback=bool(
                        result.get("register", {}).get("technical_qa", {}).get("ok")
                    ),
                    technical_qa_report=result.get("register", {}).get("report"),
                )
            except PostPlanError as exc:
                raise FilmError(str(exc)) from exc
        stages_receipt["hf"] = {
            "ok": True,
            "output": result.get("output"),
            "output_sha256": result.get("output_sha256"),
        }

        final_path = Path(str(result.get("output") or root / "out" / "film_final.mp4"))
        # stage_caption: master_hf → HF ownership gate; ship_hardburn → pixel ink only
        if designed_caption_owner:
            log("stage_caption: verify HF caption ownership (no assume) ...")
            caption_gate = ensure_captions_after_hf(
                root,
                final_mp4=final_path,
            )
            stages_receipt["caption"] = caption_gate
            if not caption_gate.get("ok"):
                stages_path = write_stages_receipt(root, stages_receipt)
                emit(
                    {
                        "ok": False,
                        "post_engine": "hyperframes",
                        "stage": "caption",
                        "stages": stages_receipt,
                        "stages_receipt": str(stages_path),
                        "error": caption_gate.get("error")
                        or "HF caption gate failed; a HyperFrames re-render is required",
                        "next": [
                            "inspect compose/hyperframes caption layout and SRT binding",
                            "re-run: aifilm final --post-engine hyperframes --caption-path master_hf",
                            "or ship path: aifilm final --caption-path ship_hardburn --post-engine ffmpeg",
                        ],
                    }
                )
                return 2
            owner = str(caption_gate.get("caption_owner") or "hyperframes")
            burned = owner in {
                "hyperframes",
                "hyperframes_export_only",
            }
        else:
            log("stage_caption: ship_hardburn — pixel ink check on plate-burned delivery ...")
            from caption_pixel_check import run_caption_pixel_check

            pixel = run_caption_pixel_check(root, final_mp4=final_path, write=True)
            stages_receipt["caption"] = {
                "ok": bool(pixel.get("ok")),
                "caption_owner": "ffmpeg_plate",
                "caption_path": "ship_hardburn",
                "pixel": pixel,
            }
            if not pixel.get("ok"):
                stages_path = write_stages_receipt(root, stages_receipt)
                emit(
                    {
                        "ok": False,
                        "post_engine": "hyperframes",
                        "stage": "caption",
                        "stages": stages_receipt,
                        "stages_receipt": str(stages_path),
                        "error": pixel.get("error")
                        or "caption pixel ink missing after ship hardburn",
                        "next": [
                            pixel.get("next_cmd")
                            or f'aifilm final --root "{root}" --caption-path ship_hardburn --post-engine ffmpeg',
                        ],
                    }
                )
                return 2
            owner = "ffmpeg_plate"
            burned = True
        # Always refresh durable pixel receipt when delivery succeeds
        try:
            from caption_pixel_check import run_caption_pixel_check

            stages_receipt["caption_pixel"] = run_caption_pixel_check(
                root, final_mp4=final_path, write=True
            )
        except Exception as exc:  # noqa: BLE001
            stages_receipt["caption_pixel"] = {"ok": False, "error": str(exc)[:200]}
        stages_receipt["deliver"] = patch_delivery_burned_in(root, burned_in=burned, owner=owner)
        stages_path = write_stages_receipt(root, stages_receipt)
        log(f"stage_deliver: caption_owner={owner} burned_in={burned} receipt={stages_path}")
        out_obj: dict[str, Any] = {
            "ok": True,
            "post_engine": "hyperframes",
            "caption_path": stages_receipt.get("post_route", {}).get("caption_path"),
            "ffmpeg": ffmpeg_result,
            "compose": result,
            "output": str(final_path),
            "output_sha256": result.get("output_sha256"),
            "caption_owner": owner,
            "stages": stages_receipt,
            "stages_receipt": str(stages_path),
            "final_complete": False,
            "next": result.get("next"),
        }
    else:
        # remotion
        if not which_npx_safe():
            raise FilmError(
                "post-engine=remotion 需要 Node/npx。"
                "安装 Node 22+ 后重试，或 --post-engine hyperframes|ffmpeg。"
            )
        npm_install = bool(getattr(args, "npm_install", False))
        readiness = probe_remotion_readiness(root)
        log(
            f"post-engine=remotion → compose-render "
            f"(npm_install={npm_install}, prior_ready={readiness.get('ready')}) ..."
        )
        try:
            result = compose_render(
                root,
                engine="remotion",
                export_first=True,
                force_export=True,
                layout="underlay",
                compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
                out_name=str(args.out_name or "film_final.mp4"),
                register=True,
                keep_raw=bool(getattr(args, "keep_compose_raw", False)),
                require_preview=bool(getattr(args, "require_preview", False)),
                npm_install=npm_install,
                npm_install_timeout=int(getattr(args, "npm_install_timeout", 900) or 900),
                title_dur=float(getattr(args, "title_dur", 1.5) or 1.5),
                end_dur=1.5,
                allow_burned_underlay=bool(getattr(args, "allow_burned_underlay", False)),
                title_sequence=getattr(args, "title_sequence", None),
                end_roll=getattr(args, "end_roll", None),
            )
        except ComposeRenderError as exc:
            raise FilmError(str(exc)) from exc
        if post_plan is not None and result.get("rendered"):
            try:
                record_render_evidence(
                    root,
                    engine=post_engine,
                    output=result.get("output"),
                    ffprobe_readback=bool(
                        result.get("register", {}).get("technical_qa", {}).get("ok")
                    ),
                    technical_qa_report=result.get("register", {}).get("report"),
                )
            except PostPlanError as exc:
                raise FilmError(str(exc)) from exc
        # compose_render may return ok=False when not ready (no raise)
        out_obj = {
            "ok": bool(result.get("ok")),
            "post_engine": "remotion" if result.get("rendered") else None,
            "rendered": result.get("rendered"),
            "ffmpeg": ffmpeg_result,
            "compose": result,
            "output": result.get("output"),
            "output_sha256": result.get("output_sha256"),
            "final_complete": False,
            "next": result.get("next") or result.get("next_steps"),
            "error": result.get("error"),
            "message": result.get("message"),
        }
        if out_obj.get("ok"):
            bgm_usage = _commit_selected_bgm_usage(
                root,
                output=out_obj.get("output"),
                output_sha256=out_obj.get("output_sha256"),
            )
            if bgm_usage is not None:
                out_obj["bgm_usage"] = bgm_usage
        if preflight_report is not None:
            out_obj["preflight"] = {
                "hard_ok": preflight_report.get("hard_ok"),
                "soft_count": len(preflight_report.get("soft") or []),
                "soft_codes": [
                    i.get("code")
                    for i in (preflight_report.get("soft") or [])
                    if isinstance(i, dict)
                ],
            }
        emit(out_obj)
        return 0 if out_obj.get("ok") else 2

    if preflight_report is not None:
        out_obj["preflight"] = {
            "hard_ok": preflight_report.get("hard_ok"),
            "soft_count": len(preflight_report.get("soft") or []),
            "soft_codes": [
                i.get("code") for i in (preflight_report.get("soft") or []) if isinstance(i, dict)
            ],
        }
    bgm_usage = _commit_selected_bgm_usage(
        root,
        output=out_obj.get("output"),
        output_sha256=out_obj.get("output_sha256"),
    )
    if bgm_usage is not None:
        out_obj["bgm_usage"] = bgm_usage
    emit(out_obj)
    return 0


def cmd_review_final(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    from production_truth import ProductionTruthError, require_current_canonical_truth

    try:
        require_current_canonical_truth(root)
    except ProductionTruthError as exc:
        raise FilmError(str(exc)) from exc
    from cinematic_audit import write_audit

    cinematic = write_audit(root, require_authored_contract=True, require_media_evidence=True)
    if not cinematic.get("ok"):
        raise FilmError(
            "Cannot approve final: cinematic audit failed ["
            + ", ".join(cinematic.get("blocking_codes") or [])
            + "]"
        )
    manifest = load_manifest(root)
    review_input = None
    if getattr(args, "review_file", None):
        try:
            from final_review_input import FinalReviewInputError, apply_review_input

            review_input = apply_review_input(args, root=root, path=args.review_file)
        except FinalReviewInputError as exc:
            raise FilmError(str(exc)) from exc
    summary = recompute_gates(root, manifest)
    if not summary["gates"]["clips_complete"]:
        raise FilmError(
            "Cannot approve final: not every planned clip has endpoint, identity, motion, and decode QA"
        )
    final_record = (manifest.get("outputs") or {}).get("final_film")
    if (root / "post-plan.json").is_file():
        try:
            from post_plan import PostPlanError, load_post_plan

            plan = load_post_plan(root, required=True)
            if (
                not isinstance(final_record, dict)
                or final_record.get("post_engine") != plan["post_owner"]
            ):
                raise PostPlanError(
                    f"post-plan post_owner={plan['post_owner']} does not match final_film post_engine="
                    f"{(final_record or {}).get('post_engine')}"
                )
        except PostPlanError as exc:
            raise FilmError(f"Cannot approve final: {exc}") from exc
    out_dir = film_dirs(root)["out"]
    if not record_file_matches(out_dir, final_record, field="final film path"):
        raise FilmError(
            "Cannot approve final: final film is missing or its SHA-256 no longer matches"
        )
    final_path = safe_existing_file(out_dir, final_record["path"], field="final film path")
    try:
        technical_qa = analyze_media(final_path, require_audio=True, require_motion=True)
    except (MediaQAError, SecurityPolicyError) as exc:
        raise FilmError(str(exc)) from exc
    if not technical_qa.get("ok"):
        raise FilmError(f"Cannot approve final: technical QA failed: {technical_qa.get('errors')}")
    from final_editorial_review import audit as editorial_audit

    editorial_review = editorial_audit(root, write=True)
    if not editorial_review.get("ok"):
        codes = ", ".join(
            str(item.get("code") or "FAILED") for item in editorial_review.get("issues") or []
        )
        raise FilmError("Cannot approve final: editorial review requires recut [" + codes + "]")
    editorial_receipt = Path(str(editorial_review["path"]))
    editorial_review["receipt_sha256"] = sha256(editorial_receipt)
    # v1.23: objective delivery-quality gate before the director's subjective scorecard.
    # Fails here = not worth a human reviewer's time (decode errors, missing audio,
    # black frames, freezes, or overall score below the floor).
    from quality_check_video import QualityCheckError, load_quality_report, run_quality_check

    quality_report = load_quality_report(root)
    if not quality_report or quality_report.get("video") != str(final_path):
        try:
            quality_report = run_quality_check(
                final_path,
                out_dir=str(out_dir),
                expect_audio=True,
                expect_subtitles=True,
                srt=str(out_dir / "final.srt") if (out_dir / "final.srt").is_file() else None,
                min_score=0,
            )
        except QualityCheckError as exc:
            raise FilmError(f"Cannot approve final: delivery quality check failed: {exc}") from exc
    if quality_report.get("hard_fail"):
        failed_gates = [
            name
            for name, gate in (quality_report.get("gates") or {}).items()
            if isinstance(gate, dict) and gate.get("status") == "fail"
        ]
        raise FilmError(
            f"Cannot approve final: delivery quality hard-fail on {', '.join(failed_gates)} "
            f"(score={quality_report.get('score')}/100). "
            "Fix the technical issue then re-run review-final."
        )
    # Adult max cannot inherit a plan-only score.  The receipt binds each
    # reviewed act/climax clip and the current audio/timeline evidence.
    try:
        from adult_max_director import build_evidence

        adult_sensory = build_evidence(root, write=True)
    except (OSError, ValueError) as exc:
        raise FilmError(f"Cannot approve final: adult max sensory evidence failed: {exc}") from exc
    if adult_sensory.get("active") and not adult_sensory.get("ok"):
        raise FilmError(
            "Cannot approve final: adult max sensory evidence is incomplete ["
            + ", ".join(adult_sensory.get("codes") or [])
            + "]"
        )
    # P0 · Wave 6: heat final_ok (S-grade + arc) before final_complete
    try:
        from production_gates import ProductionGateError, assert_heat_allows_final

        heat_gate = assert_heat_allows_final(root, write_receipt=True)
    except ProductionGateError as exc:
        raise FilmError(f"Cannot approve final: {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise FilmError(f"Cannot approve final: heat final gate failed: {exc}") from exc
    if heat_gate.get("active") is False and heat_gate.get("skipped"):
        pass
    # Keep full heat receipt for audit (scorecard body)
    try:
        from heat_check import heat_check as _heat_check

        heat_rep_final = _heat_check(root)
    except Exception as exc:  # pragma: no cover
        heat_rep_final = {"ok": False, "error": str(exc)}
    with contextlib.suppress(OSError):
        write_json(
            root / "receipts" / "heat-final-gate.json",
            {
                "ok": True,
                "at": utc_now(),
                "gate": heat_gate,
                "impact_score": heat_gate.get("score"),
                "target_s": heat_gate.get("target_s"),
                "heat_line": (heat_rep_final or {}).get("line"),
            },
        )
    reviewer = str(args.reviewer or "").strip()
    notes = str(args.notes or "").strip()
    if not args.approve:
        raise FilmError(
            "Full-film review requires explicit --approve after watching the entire film"
        )
    if not reviewer or not notes:
        raise FilmError("Full-film review requires non-empty --reviewer and --notes")
    try:
        card = build_scorecard_from_cli(args)
        manifest_contract = int(manifest.get("review_contract_version") or 1)
        grades = build_grades_from_cli(args, required=manifest_contract >= 3)
        fail_reasons = parse_fail_reasons(
            list(getattr(args, "fail_reason", None) or []),
            failures=[dim for dim, passed in card.items() if not passed],
            required=manifest_contract >= 3,
        )
    except DirectorReviewError as exc:
        raise FilmError(str(exc)) from exc
    if manifest_contract >= 3 and not getattr(args, "watched_full", False):
        raise FilmError("review contract v3 requires --watched-full")
    screening_evidence: dict[str, Any] = {}
    if manifest_contract >= 2:
        try:
            from director_review import parse_timestamp_evidence

            screening_evidence = parse_timestamp_evidence(
                list(getattr(args, "screening_evidence", None) or []),
                required=SCORECARD_DIMENSIONS,
                duration_sec=float(technical_qa.get("duration_sec") or 0.0),
            )
        except DirectorReviewError as exc:
            raise FilmError(str(exc)) from exc
    from performance_timeline import build_performance_timeline

    performance_timeline = build_performance_timeline(root)
    if performance_timeline["required"] and not performance_timeline["ok"]:
        codes = ", ".join(sorted({item["code"] for item in performance_timeline["errors"]}))
        raise FilmError(f"Cannot approve final: performance timeline is incomplete: {codes}")
    from speech_performance_timing import build_speech_performance_timing

    speech_performance_timing = build_speech_performance_timing(root)
    if speech_performance_timing["required"] and not speech_performance_timing["ok"]:
        codes = ", ".join(sorted({item["code"] for item in speech_performance_timing["errors"]}))
        raise FilmError(f"Cannot approve final: speech/performance timing is incomplete: {codes}")
    from audio_provenance import build_audio_provenance

    audio_provenance = build_audio_provenance(root)
    if audio_provenance["required"] and not audio_provenance["ok"]:
        codes = ", ".join(sorted({item["code"] for item in audio_provenance["errors"]}))
        raise FilmError(f"Cannot approve final: audio provenance is incomplete: {codes}")
    from subtitle_dialogue_alignment import build_subtitle_dialogue_alignment

    subtitle_dialogue_alignment = build_subtitle_dialogue_alignment(root)
    if subtitle_dialogue_alignment["required"] and not subtitle_dialogue_alignment["ok"]:
        codes = ", ".join(sorted({item["code"] for item in subtitle_dialogue_alignment["errors"]}))
        raise FilmError(f"Cannot approve final: subtitle/dialogue alignment is incomplete: {codes}")
    from subtitle_cut_boundaries import build_subtitle_cut_boundaries

    subtitle_cut_boundaries = build_subtitle_cut_boundaries(root)
    if subtitle_cut_boundaries["required"] and not subtitle_cut_boundaries["ok"]:
        raise FilmError("Cannot approve final: subtitle crosses a hard or continue cut boundary")
    from director_ledger import build_director_ledger

    director_ledger = build_director_ledger(root)
    if director_ledger["required"] and not director_ledger["ok"]:
        raise FilmError(
            "Cannot approve final: director exception ledger has pending re-approval items"
        )

    from narrative_evidence import validate_narrative_evidence

    narrative_evidence = validate_narrative_evidence(root, require_verified=True)
    if narrative_evidence.get("required") and not narrative_evidence.get("ok"):
        codes = ", ".join(
            sorted({str(item.get("code")) for item in narrative_evidence.get("issues") or []})
        )
        raise FilmError(
            f"Cannot approve final: narrative hook/plot-point evidence is incomplete [{codes}]. "
            "Write narrative-evidence.json with executed and human_review evidence first."
        )

    # Scorecard fail → write director_notes reshoot list, do not approve
    if not scorecard_all_pass(card):
        shot_ids = parse_shot_id_list(getattr(args, "reshoot_shots", None))
        existing = load_director_notes(root)
        package = build_notes_from_scorecard_failures(
            card,
            notes_text=notes,
            output_sha256=str(final_record.get("sha256") or ""),
            shot_ids=shot_ids,
            existing=existing,
        )
        notes_path = save_director_notes(root, package)
        open_items = open_reshoot_items(package)
        # Persist failed attempt for audit (not approved)
        failed_review = {
            "approved": False,
            "reviewed_at": utc_now(),
            "reviewer": reviewer,
            "notes": notes,
            "output_sha256": final_record["sha256"],
            "technical_qa": technical_qa,
            "scorecard": scorecard_payload(card),
            "grades": grades,
            "fail_reasons": fail_reasons,
            "watched_full": bool(getattr(args, "watched_full", False)),
            "screening_evidence": screening_evidence,
            "performance_timeline": performance_timeline,
            "speech_performance_timing": speech_performance_timing,
            "audio_provenance": audio_provenance,
            "director_notes_path": str(notes_path),
            "open_reshoot_ids": [it.get("id") for it in open_items],
        }
        write_json(out_dir / "final-review-failed.json", failed_review)
        recompute_gates(root, manifest)
        save_manifest(root, manifest)
        fails = ",".join(scorecard_payload(card)["failures"])
        raise FilmError(
            f"scorecard fail [{fails}] — wrote {len(open_items)} open reshoot item(s) to "
            f"{notes_path}; resolve with director-notes then re-run review-final with all pass"
        )

    try:
        scorecard = validate_scorecard_for_approve(card)
    except DirectorReviewError as exc:
        raise FilmError(str(exc)) from exc
    review = {
        "approved": True,
        "reviewed_at": utc_now(),
        "reviewer": reviewer,
        "notes": notes,
        "output_sha256": final_record["sha256"],
        "technical_qa": technical_qa,
        "editorial_review": editorial_review,
        "scorecard": scorecard,
        "grades": grades,
        "fail_reasons": fail_reasons,
        "watched_full": bool(getattr(args, "watched_full", False)),
        "screening": {
            "path": str(final_path),
            "sha256": final_record["sha256"],
            "duration_sec": technical_qa.get("duration_sec"),
        },
        "screening_evidence": screening_evidence,
        "performance_timeline": performance_timeline,
        "speech_performance_timing": speech_performance_timing,
        "audio_provenance": audio_provenance,
        "subtitle_dialogue_alignment": subtitle_dialogue_alignment,
        "subtitle_cut_boundaries": subtitle_cut_boundaries,
        "director_ledger": director_ledger,
        "narrative_evidence": narrative_evidence,
        "adult_max_sensory": adult_sensory,
    }
    review_path = out_dir / "final-review.json"
    write_json(review_path, review)
    review["path"] = str(review_path)
    manifest.setdefault("outputs", {})["final_review"] = review
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    try:
        from pipeline_events import append_event

        append_event(root, stage="review-final", phase="completed")
        if review_input is not None:
            append_event(
                root,
                stage="review-final",
                phase="human_time",
                human_minutes=float(review_input["human_minutes"]),
                actor=str(review_input["reviewer"]),
                note="review-file",
            )
    except OSError:
        pass
    try:
        from quality_ledger import emit_quality_ledger

        quality_ledger = emit_quality_ledger(root)
    except (OSError, ValueError) as exc:
        raise FilmError(
            f"final review succeeded but quality ledger could not be written: {exc}"
        ) from exc
    try:
        from production_report import emit_production_report

        production_report = emit_production_report(root)
    except (OSError, ValueError) as exc:
        raise FilmError(
            f"final review succeeded but production report could not be written: {exc}"
        ) from exc
    try:
        from optimization_metrics import emit_metrics

        optimization_metrics = emit_metrics(root)
    except (OSError, ValueError) as exc:
        optimization_metrics = {"ok": False, "error": str(exc)}
    emit(
        {
            "ok": True,
            "final_complete": manifest["gates"]["final_complete"],
            "review": review,
            "quality_ledger": str(root / "receipts" / "quality-ledger.json"),
            "retrospective_complete": quality_ledger["retrospective_complete"],
            "production_report": production_report["paths"],
            "optimization_metrics": optimization_metrics,
        }
    )
    return 0


def cmd_final_editorial_review(args: argparse.Namespace) -> int:
    """Write the no-spend final editorial report without granting approval."""
    from final_editorial_review import audit

    report = audit(Path(args.root).expanduser().resolve(), write=True)
    emit(report)
    return 0 if report["ok"] else 2


def cmd_compose_preview(args: argparse.Namespace) -> int:
    """Open HyperFrames or Remotion Studio and return URL + receipt."""
    skill_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_preview import (
            ComposePreviewError,
            compose_preview,
            load_preview_receipt,
            preview_status,
            preview_stop,
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_preview: {exc}") from exc

    root = Path(args.root).expanduser().resolve()
    engine = str(getattr(args, "engine", "hyperframes") or "hyperframes").strip().lower()
    default_port = 3003 if engine == "remotion" else 3002
    port = getattr(args, "port", None)
    port_i = int(port) if port is not None else default_port
    hf_dir = root / "compose" / "hyperframes"
    try:
        if getattr(args, "stop", False):
            if engine == "remotion":
                emit(
                    {
                        "ok": False,
                        "engine": "remotion",
                        "error": "Remotion Studio stop is manual (kill studio process)",
                    }
                )
                return 2
            if not hf_dir.is_dir():
                raise FilmError("compose/hyperframes missing")
            emit(preview_stop(hf_dir))
            return 0
        if getattr(args, "status_only", False):
            if engine == "remotion":
                rem = root / "compose" / "remotion"
                emit(
                    {
                        "ok": True,
                        "engine": "remotion",
                        "dir": str(rem),
                        "package": (rem / "package.json").is_file(),
                        "node_modules": (rem / "node_modules" / "remotion").is_dir(),
                        "receipt": load_preview_receipt(root),
                    }
                )
                return 0
            if not hf_dir.is_dir():
                raise FilmError("compose/hyperframes missing")
            emit({"ok": True, **preview_status(hf_dir)})
            return 0
        result = compose_preview(
            root,
            engine=engine,
            port=port_i,
            open_browser=not bool(getattr(args, "no_open", False)),
            export_if_missing=not bool(getattr(args, "no_export", False)),
            background=not bool(getattr(args, "foreground", False)),
            force_new=bool(getattr(args, "force_new", False)),
        )
    except ComposePreviewError as exc:
        raise FilmError(str(exc)) from exc
    emit(result)
    return 0 if result.get("ok") is not False else 2


def cmd_export_compose(args: argparse.Namespace) -> int:
    """Export approved clips + film-spec timeline into HyperFrames/Remotion packages.

    Designed-post bridge only — does not replace Grok I2V or default FFmpeg final.
    """
    skill_dir = Path(__file__).resolve().parents[2]
    script = skill_dir / "scripts" / "export_composition.py"
    if not script.is_file():
        raise FilmError(f"Missing {script}")
    # Import sibling module for in-process export (tests + consistent errors)
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from export_composition import ComposeExportError, export_composition
    except ImportError as exc:
        raise FilmError(f"Cannot import export_composition: {exc}") from exc

    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    summary = recompute_gates(root, manifest)
    if not summary["gates"].get("clips_complete"):
        raise FilmError(
            "export-compose requires clips_complete (every planned shot has approved register-clip)"
        )
    requested_engine = str(getattr(args, "engine", "both") or "both")
    requested_owner = str(getattr(args, "post_owner", "") or "").strip().lower()
    if requested_owner not in {"", "ffmpeg", "hyperframes", "remotion"}:
        raise FilmError("--post-owner must be ffmpeg|hyperframes|remotion")
    owner = requested_owner or ("remotion" if requested_engine == "remotion" else "hyperframes")
    try:
        from post_plan import PostPlanError, ensure_post_plan

        post_plan, post_plan_created = ensure_post_plan(root, owner=owner)
    except ImportError as exc:
        raise FilmError(f"Cannot import post_plan: {exc}") from exc
    except PostPlanError as exc:
        raise FilmError(str(exc)) from exc
    locked_owner = str(post_plan["post_owner"])
    if not post_plan_created:
        if requested_owner and requested_owner != locked_owner:
            raise FilmError(
                f"post-plan post_owner={locked_owner}; --post-owner {requested_owner} would overwrite it"
            )
        if requested_engine not in {locked_owner, "both"}:
            raise FilmError(
                f"post-plan post_owner={locked_owner}; export-compose --engine {requested_engine} is not allowed "
                "(use the owner engine or --engine both for comparison)"
            )
    try:
        result = export_composition(
            root,
            engine=requested_engine,
            title_dur=float(getattr(args, "title_dur", 1.5) or 1.5),
            end_dur=float(getattr(args, "end_dur", 1.5) or 1.5),
            force=bool(getattr(args, "force", False)),
            layout=str(getattr(args, "layout", "auto") or "auto"),
            compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
            title_sequence=getattr(args, "title_sequence", None),
            end_roll=getattr(args, "end_roll", None),
        )
    except ComposeExportError as exc:
        raise FilmError(str(exc)) from exc
    result["post_plan"] = {
        "path": str(root / "post-plan.json"),
        "post_owner": post_plan["post_owner"],
        "created": post_plan_created,
    }
    emit(result)
    return 0


def cmd_compose_render(args: argparse.Namespace) -> int:
    """HyperFrames check+render+audio mux+register final (designed post)."""
    skill_dir = Path(__file__).resolve().parents[2]
    if not (skill_dir / "scripts" / "compose_render.py").is_file():
        raise FilmError("Missing compose_render.py")
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_render import ComposeRenderError, compose_render, register_final_film
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_render: {exc}") from exc

    root = Path(args.root).expanduser().resolve()
    try:
        from post_plan import PostPlanError, record_render_evidence, validate_render_owner

        selected_engine = (
            str(getattr(args, "post_engine", "external") or "external")
            if getattr(args, "register_only", None)
            else str(getattr(args, "engine", "hyperframes") or "hyperframes")
        )
        plan = validate_render_owner(root, selected_engine)
    except ImportError as exc:
        raise FilmError(f"Cannot import post_plan: {exc}") from exc
    except PostPlanError as exc:
        raise FilmError(str(exc)) from exc
    if getattr(args, "register_only", None):
        try:
            result = register_final_film(
                root,
                Path(args.register_only),
                out_name=str(getattr(args, "out_name", None) or "film_final.mp4"),
                post_engine=str(getattr(args, "post_engine", None) or "external"),
                force=True,
            )
        except ComposeRenderError as exc:
            raise FilmError(str(exc)) from exc
        if plan is not None:
            try:
                validate_render_owner(
                    root, str(getattr(args, "post_engine", "external") or "external")
                )
                record_render_evidence(
                    root,
                    engine=str(plan["post_owner"]),
                    output=str(args.register_only),
                    ffprobe_readback=bool(result.get("technical_qa", {}).get("ok")),
                    technical_qa_report=result.get("report"),
                )
            except PostPlanError as exc:
                raise FilmError(str(exc)) from exc
        emit(result)
        return 0

    manifest = load_manifest(root)
    summary = recompute_gates(root, manifest)
    if not summary["gates"].get("clips_complete"):
        raise FilmError("compose-render requires clips_complete")
    try:
        result = compose_render(
            root,
            engine=str(getattr(args, "engine", "hyperframes") or "hyperframes"),
            export_first=not bool(getattr(args, "no_export", False)),
            force_export=not bool(getattr(args, "no_force_export", False)),
            layout=str(getattr(args, "layout", "auto") or "auto"),
            compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
            quality=str(getattr(args, "quality", "standard") or "standard"),
            out_name=str(getattr(args, "out_name", None) or "film_final.mp4"),
            register=not bool(getattr(args, "no_register", False)),
            skip_check=bool(getattr(args, "skip_check", False)),
            keep_raw=bool(getattr(args, "keep_raw", False)),
            require_preview=bool(getattr(args, "require_preview", False)),
            npm_install=bool(getattr(args, "npm_install", False)),
            npm_install_timeout=int(getattr(args, "npm_install_timeout", 900) or 900),
            title_dur=float(getattr(args, "title_dur", 1.5) or 1.5),
            end_dur=float(getattr(args, "end_dur", 1.5) or 1.5),
            allow_burned_underlay=bool(getattr(args, "allow_burned_underlay", False)),
            title_sequence=getattr(args, "title_sequence", None),
            end_roll=getattr(args, "end_roll", None),
        )
    except ComposeRenderError as exc:
        raise FilmError(str(exc)) from exc
    if plan is not None and result.get("rendered"):
        try:
            record_render_evidence(
                root,
                engine=str(plan["post_owner"]),
                output=result.get("output"),
                composition_checked=bool(result.get("steps", {}).get("check", {}).get("ok")),
                ffprobe_readback=bool(result.get("register", {}).get("technical_qa", {}).get("ok")),
                technical_qa_report=result.get("register", {}).get("report"),
            )
        except PostPlanError as exc:
            raise FilmError(str(exc)) from exc
    emit(result)
    return 0


def cmd_register_final(args: argparse.Namespace) -> int:
    """Register an external/composed MP4 as formal final_film candidate."""
    skill_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_render import ComposeRenderError, register_final_film
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_render: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    try:
        from post_plan import PostPlanError, record_render_evidence, validate_render_owner

        plan = validate_render_owner(
            root, str(getattr(args, "post_engine", "external") or "external")
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import post_plan: {exc}") from exc
    except PostPlanError as exc:
        raise FilmError(str(exc)) from exc
    manifest = load_manifest(root) if (root / MANIFEST_NAME).is_file() else {}
    if int(manifest.get("quality_evidence_contract_version") or 0) >= 1:
        from quality_closure import _shot_quality_closure

        closure = _shot_quality_closure(root)
        if not closure.get("ok") or not int(closure.get("approved_shot_count") or 0):
            raise FilmError(
                "register-final requires complete current per-shot quality evidence; "
                f"missing={closure.get('missing')}, duplicates={closure.get('duplicates')}"
            )
    try:
        result = register_final_film(
            root,
            Path(args.source),
            out_name=str(getattr(args, "out_name", None) or "film_final.mp4"),
            post_engine=str(getattr(args, "post_engine", None) or "external"),
            require_motion=not bool(getattr(args, "allow_static", False)),
            force=True,
        )
    except ComposeRenderError as exc:
        raise FilmError(str(exc)) from exc
    if plan is not None:
        try:
            record_render_evidence(
                root,
                engine=str(plan["post_owner"]),
                output=str(getattr(args, "source", "")),
                ffprobe_readback=bool(result.get("technical_qa", {}).get("ok")),
                technical_qa_report=result.get("report"),
            )
        except PostPlanError as exc:
            raise FilmError(str(exc)) from exc
    emit(result)
    return 0


def cmd_post_plan(args: argparse.Namespace) -> int:
    """Create and validate the single editorial-to-post handoff contract."""
    skill_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from post_plan import (
            PostPlanError,
            delivery_status,
            load_post_plan,
            new_post_plan,
            post_plan_path,
            validate_post_plan,
            write_post_plan,
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import post_plan: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    try:
        if args.post_plan_action == "init":
            plan = new_post_plan(
                root,
                owner=str(getattr(args, "owner", "hyperframes") or "hyperframes"),
                edl_path=getattr(args, "edl", None),
                master_subtitles=getattr(args, "master_subtitles", "out/final.srt"),
                audio_plan=getattr(args, "audio_plan", "sound-plan.json"),
            )
            path = write_post_plan(root, plan, force=bool(getattr(args, "force", False)))
            emit({"ok": True, "path": str(path), "post_plan": plan})
            return 0
        plan = load_post_plan(root, required=True)
        result = validate_post_plan(
            root, plan, check_artifacts=bool(getattr(args, "check_artifacts", False))
        )
        result["path"] = str(post_plan_path(root))
        result["delivery"] = delivery_status(root, plan)
        if args.post_plan_action == "show":
            result["post_plan"] = plan
        emit(result)
        return 0 if result["ok"] else 2
    except PostPlanError as exc:
        raise FilmError(str(exc)) from exc


def cmd_closeout(args: argparse.Namespace) -> int:
    """Wave A1: heat → review gate → post-audit → optional export next_cmd."""
    from closeout import closeout_run, closeout_status

    root = Path(args.root).expanduser().resolve()
    action = str(getattr(args, "closeout_action", "run") or "run")
    if action == "status":
        report = closeout_status(root)
        emit(report)
        return 0 if report.get("ok") else 2
    report = closeout_run(
        root,
        execute=not bool(getattr(args, "status_only", False)),
        export=bool(getattr(args, "export", False)),
        export_name=getattr(args, "name", None),
    )
    emit(report)
    # 0 = delivery_ready or stopped only at optional export; 2 = hard stop mid ladder
    if report.get("delivery_ready") or report.get("ok"):
        return 0
    if report.get("stopped_at") == "export_desktop":
        return 0
    return 2


def cmd_export_desktop(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        raise FilmError(f"Desktop not found: {desktop}")
    name = args.name.strip() or (load_manifest(root).get("title") or "GrokFilm")
    try:
        dest = safe_subdirectory(desktop, name, field="Desktop export name")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    if dest.exists() and not args.force:
        raise FilmError(f"Desktop export already exists: {dest} (pass --force to update it)")
    manifest = load_manifest(root)
    recompute_gates(root, manifest)
    if not manifest["gates"]["final_complete"]:
        raise FilmError(
            "Desktop export requires completed technical QA and explicit full-film final review"
        )
    # Wave 6: re-check adult-max heat before shipping desktop (no silent cool export)
    try:
        from production_gates import ProductionGateError, assert_heat_allows_final

        assert_heat_allows_final(root, write_receipt=False)
    except ProductionGateError as exc:
        raise FilmError(str(exc)) from exc
    post_receipt = read_json(root / "receipts" / "post-audit.json") or {}
    from post_audit import audit_freshness

    freshness = audit_freshness(root, post_receipt)
    if not post_receipt:
        raise FilmError(
            "Desktop export requires a current post-audit receipt; run aifilm post-audit --root first"
        )
    if freshness.get("stale"):
        raise FilmError(
            "Desktop export requires a fresh post-audit; evidence changed: "
            + ", ".join(freshness.get("mismatches") or [])
        )
    if not post_receipt.get("delivery_ready"):
        raise FilmError("Desktop export blocked by post-audit hard failures")
    # Delivery Truth · high-motion product gate (hard-defaults: only ok → desktop film_final)
    try:
        from i2v_motion_gate import I2VMotionGateError, assert_i2v_final_gate_for_export

        assert_i2v_final_gate_for_export(root)
    except I2VMotionGateError as exc:
        raise FilmError(str(exc)) from exc
    # Wave ε · composite cinema gate (true-video / variety / five-track / inventory)
    try:
        from cinematic_gate import CinematicGateError, assert_cinematic_gate_for_export

        assert_cinematic_gate_for_export(root)
    except CinematicGateError as exc:
        raise FilmError(str(exc)) from exc
    dirs = film_dirs(root)
    try:
        reject_symlinks(dest, field="Desktop export destination")
        for key in ("out", "audio", "keyframes", "clips", "canonical"):
            reject_symlinks(dirs[key], field=f"film {key} export source")
        for meta in EXPORT_METADATA_FILES:
            if (root / meta).is_symlink():
                raise SecurityPolicyError(
                    f"Invalid export source: symbolic links are not allowed: {root / meta}"
                )
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    for sub in ("成片", "关键帧", "镜头片段", "定妆与场景", "简报", "项目状态"):
        try:
            safe_workspace_directory(dest, sub, field=f"Desktop {sub} directory").mkdir(
                parents=True, exist_ok=True
            )
        except SecurityPolicyError as exc:
            raise FilmError(str(exc)) from exc

    out_dir = dirs["out"]
    from delivery_artifact import DeliveryArtifactError, export_final_artifacts

    try:
        export_final_artifacts(root, manifest, dest / "成片")
    except DeliveryArtifactError as exc:
        raise FilmError(f"Desktop export final artifact is invalid: {exc}") from exc
    for side in ("final.srt", "final-delivery.json", "production-report.html"):
        src = out_dir / side
        if src.is_file():
            shutil.copy2(src, dest / "成片" / side)
    production_receipt = root / "receipts" / "production-report.json"
    if production_receipt.is_file():
        shutil.copy2(production_receipt, dest / "项目状态" / production_receipt.name)
    # clean stale intermediate copies from previous exports
    for stale in (dest / "成片").glob("*.mp4"):
        if stale.name not in ("film_final.mp4", "film_silent.mp4") and (
            "pre_" in stale.name or stale.name.endswith("_dual.mp4") or "里番" in stale.name
        ):
            with contextlib.suppress(OSError):
                stale.unlink()
    # audio stems
    try:
        audio_export = safe_workspace_directory(dest, "音频", field="Desktop audio directory")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    audio_export.mkdir(exist_ok=True)
    for audio in dirs["audio"].glob("*"):
        if audio.is_file():
            shutil.copy2(audio, audio_export / audio.name)
    for img in sorted(dirs["keyframes"].glob("*")):
        if img.is_file():
            shutil.copy2(img, dest / "关键帧" / img.name)
    for clip in sorted(dirs["clips"].glob("*")):
        if clip.is_file():
            shutil.copy2(clip, dest / "镜头片段" / clip.name)
    for can in sorted(dirs["canonical"].glob("*")):
        if can.is_file():
            shutil.copy2(can, dest / "定妆与场景" / can.name)
    for meta in EXPORT_METADATA_FILES:
        src = root / meta
        if src.is_file():
            shutil.copy2(src, dest / "简报" / meta)
    # pilot + compose pointers
    for pilot_name in ("pilot-approval.json", "pilot-scorecard.json"):
        src = root / "receipts" / pilot_name
        if src.is_file():
            shutil.copy2(src, dest / "项目状态" / pilot_name)
    for side in ("director_notes.json",):
        src = root / side
        if src.is_file():
            shutil.copy2(src, dest / "项目状态" / side)
    compose_preview = root / "compose" / "preview.json"
    if compose_preview.is_file():
        shutil.copy2(compose_preview, dest / "项目状态" / "compose-preview.json")
    shutil.copy2(root / MANIFEST_NAME, dest / "项目状态" / MANIFEST_NAME)
    delivery_manifest = {
        "kind": "desktop-delivery-manifest",
        "created_at": utc_now(),
        "source_root": str(root),
        "files": {},
    }
    readback_path = dest / "成片" / "delivery-readback.json"
    readback = _util_read_json(readback_path)
    if not isinstance(readback, dict) or readback.get("ok") is not True:
        raise FilmError("Desktop export requires successful hash and decode read-back")
    delivery_manifest["readback"] = readback
    for exported in sorted((dest / "成片").iterdir()):
        if exported.is_file():
            delivery_manifest["files"][f"成片/{exported.name}"] = {
                "sha256": sha256(exported),
                "size": exported.stat().st_size,
            }
    delivery_manifest_path = dest / "项目状态" / "delivery-manifest.json"
    write_json(delivery_manifest_path, delivery_manifest)

    readme = dest / "README.txt"
    silent = (manifest.get("outputs") or {}).get("silent_film") or {}
    final = (manifest.get("outputs") or {}).get("final_film") or {}
    readme.write_text(
        "\n".join(
            [
                f"{manifest.get('title', name)} · Grok Imagine 输出",
                "=" * 40,
                "",
                "【成片】先看这里（正式版优先）",
                f"  主文件目录: {dest / '成片'}",
                f"  final:  {final.get('path', '(尚未 final — 跑 aifilm_grok.py final)')}",
                f"  silent: {silent.get('path', '(尚未 assemble)')}",
                "",
                "【关键帧】keyframes",
                "【镜头片段】image_to_video clips",
                "【定妆与场景】canonical masters",
                "【音频】edge-tts 口白 + 配乐",
                "【简报】style-bible / film-spec / timeline / final-delivery.json",
                "",
                f"项目根: {root}",
                f"导出时间: {utc_now()}",
                "说明: motion 为 frame-1 I2V，非 first/last-frame；正式版含口白/字幕/BGM。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    outputs = manifest.setdefault("outputs", {})
    outputs["desktop_dir"] = str(dest)
    outputs["desktop_delivery"] = {
        "directory": str(dest),
        "path": str(delivery_manifest_path),
        "sha256": sha256(delivery_manifest_path),
        "readback_path": str(readback_path),
        "readback_sha256": sha256(readback_path),
        "final_output_sha256": str(final.get("sha256") or ""),
    }
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "desktop_dir": str(dest),
            "main_film_dir": str(dest / "成片"),
            "readback": readback,
        }
    )
    return 0

def add_post_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pa = sub.add_parser("post-audit", help="Unified post-production audit")
    pa.add_argument("--root", required=True)

    caption_audit = sub.add_parser(
        "caption-frame-audit",
        help="Extract final-MP4 frames during subtitle cues for human readability review",
    )
    caption_audit.add_argument("--root", required=True)
    caption_audit.add_argument("--max-frames", type=int, default=5)

    caption_pixel = sub.add_parser(
        "caption-pixel-check",
        help="Machine ink check: final MP4 bottom-band looks like burned captions at cue mids",
    )
    caption_pixel.add_argument("--root", required=True)
    caption_pixel.add_argument("--max-samples", type=int, default=5)
    caption_pixel.add_argument(
        "--final",
        default=None,
        help="Optional path to final MP4 (default out/film_final.mp4)",
    )

    post_doc = sub.add_parser(
        "post-doctor",
        help="One-page post health: caption_path, double-burn, SRT, five-track, timeline clock",
    )
    post_doc.add_argument("--root", required=True)

    tl_clock = sub.add_parser(
        "timeline-clock",
        help="Audit/rewrite single on-picture timeline clock (film_timeline authority)",
    )
    tl_clock_sub = tl_clock.add_subparsers(dest="timeline_clock_action", required=True)
    tl_aud = tl_clock_sub.add_parser("audit", help="Compare film_timeline vs timeline.json")
    tl_aud.add_argument("--root", required=True)
    tl_rw = tl_clock_sub.add_parser(
        "rewrite",
        help="Rewrite timeline.json shot_starts from film_timeline (on-picture slots)",
    )
    tl_rw.add_argument("--root", required=True)

    transition_audit = sub.add_parser(
        "transition-frame-audit",
        help="Extract final-MP4 frames around every planned shot transition for human review",
    )
    transition_audit.add_argument("--root", required=True)

    transition_template = sub.add_parser(
        "transition-frame-review-template",
        help="Create a per-seam human decision template for the current transition audit",
    )
    transition_template.add_argument("--root", required=True)

    transition_attest = sub.add_parser(
        "transition-frame-attest",
        help="Record human approval for current per-transition review frames",
    )
    transition_attest.add_argument("--root", required=True)
    transition_attest.add_argument("--user-phrase", required=True)
    transition_attest.add_argument(
        "--decisions",
        help="Path to completed transition-review-decisions JSON; required when the film has joins",
    )

    caption_attest = sub.add_parser(
        "caption-frame-attest",
        help="Record human readability approval for current caption review frames",
    )
    caption_attest.add_argument("--root", required=True)
    caption_attest.add_argument("--user-phrase", required=True)

    fin = sub.add_parser(
        "final", help="Render formal final: edge-tts VO + BGM + burned Chinese subs"
    )
    fin.add_argument("--root", required=True)
    fin.add_argument("--out-name", default="film_final.mp4")
    fin.add_argument(
        "--caption-path",
        default=None,
        choices=["master_hf", "ship_hardburn"],
        help=(
            "One caption decision: master_hf=plate subs off + HF/Remotion owns captions; "
            "ship_hardburn=plate PIL/ffmpeg burn (no double layer). Default from post-engine."
        ),
    )
    fin.add_argument(
        "--ship-hardburn",
        action="store_true",
        help="Alias for --caption-path ship_hardburn (fast ship / gate-red path)",
    )
    fin.add_argument(
        "--resume",
        action="store_true",
        help="Resume valid per-shot stretch/lipsync checkpoints from receipts/checkpoints/",
    )
    fin.add_argument(
        "--force",
        action="store_true",
        help="Clear per-shot final-render checkpoints before rendering",
    )
    fin.add_argument("--transition-sec", type=float, default=None, help="Inter-shot xfade seconds")
    fin.add_argument(
        "--allow-loop-risk",
        action="store_true",
        help="Allow final when VO would stream_loop short plates (discouraged); does NOT skip measured over-plate",
    )
    fin.add_argument(
        "--strict-tts-rehearsal",
        action="store_true",
        help="Require receipts/tts-rehearsal.json before final; measured VO preferred for pacing",
    )
    fin.add_argument(
        "--vo-fit",
        default=None,
        choices=["atempo", "legacy"],
        help="slot mode: atempo=VO speed to plate (default three-axis); legacy=old pad/stretch",
    )
    fin.add_argument(
        "--voice",
        default=None,
        help="edge voice or provider voice id; default comes from film-spec",
    )
    fin.add_argument(
        "--tts-backend",
        default=None,
        choices=["audio_node", "auto", "minimax", "fish", "edge", "external"],
        help="audio_node: private Qwen3-TTS on the 5090; auto: external > MiniMax > pinned Fish > edge",
    )
    fin.add_argument("--vo-rate", default=None)
    fin.add_argument("--vo-pitch", default=None)
    fin.add_argument("--vo-gain", type=float, default=None)
    fin.add_argument(
        "--vocal-color-gain",
        type=float,
        default=None,
        help="Independent 娇喘/语助词 track gain (0..1.5; film-spec voice_tracks.vocal_color_gain)",
    )
    fin.add_argument("--title")
    fin.add_argument("--end-title")
    fin.add_argument("--music", help="External BGM file (overrides audio/bgm.wav templates)")
    fin.add_argument(
        "--music-license",
        help="License note; or place audio/*.license.txt beside the file",
    )
    fin.add_argument(
        "--music-template",
        default=None,
        choices=["off", "auto", "on", "timeline", "approved_library"],
        help=(
            "BGM: auto/on/off retain legacy behavior; timeline uses film-local cue templates; "
            "approved_library requires shared human-approved cue matches"
        ),
    )
    fin.add_argument(
        "--music-volume",
        type=float,
        default=0.52,
        help="BGM mix gain once; ~0.45-0.58 dual-track (VO clear + BGM audible)",
    )
    fin.add_argument(
        "--native-audio-volume",
        type=float,
        default=None,
        help="Mix gain for generated clip audio preserved as native stems (default from film-spec or 0.72; primary video sound)",
    )
    fin.add_argument(
        "--music-mood",
        default="rnb",
        help="playful|dark|warm|rnb|sensual|soul — 色气默认 rnb (seductive R&B/Soul；勿对里番用 dark)",
    )
    fin.add_argument(
        "--music-seed",
        type=int,
        default=None,
        help="Procedural BGM seed (change for a new anti-fatigue take; default = hash of title)",
    )
    fin.add_argument(
        "--sidechain-threshold",
        type=float,
        default=None,
        help="VO→BGM sidechain threshold (rnb default 0.07)",
    )
    fin.add_argument(
        "--sidechain-ratio",
        type=float,
        default=None,
        help="VO→BGM sidechain ratio (rnb default 3.2)",
    )
    fin.add_argument(
        "--sidechain-attack",
        type=float,
        default=None,
        help="Sidechain attack ms (rnb default 15)",
    )
    fin.add_argument(
        "--sidechain-release",
        type=float,
        default=None,
        help="Sidechain release ms — higher = BGM returns slower in VO pauses (rnb default 720)",
    )
    fin.add_argument(
        "--loudnorm",
        default=None,
        choices=["off", "auto", "on"],
        help="Mix loudness: auto (default, only if too loud/quiet) | on | off",
    )
    fin.add_argument(
        "--target-lufs",
        type=float,
        default=None,
        help="loudnorm target LUFS (default -16 shortform)",
    )
    fin.add_argument(
        "--lipsync",
        default="off",
        choices=["auto", "off", "require", "latentsync", "external", "wav2lip"],
        help="Lip-sync OFF by default. RTX node uses LatentSync 1.6 for approved close-up repair.",
    )
    fin.add_argument("--sub-lead", type=float, default=0.08, help="Show subtitles early (seconds)")
    fin.add_argument(
        "--sub-max-unit", type=float, default=1.75, help="Max seconds per subtitle line"
    )
    fin.add_argument("--sub-max-chars", type=int, default=14, help="Max Chinese chars per line")
    fin.add_argument(
        "--title-dur",
        type=float,
        default=1.5,
        help="Title pad seconds (designed-post keeps pad; glyphs only if --plate-cards text)",
    )
    fin.add_argument(
        "--end-dur",
        type=float,
        default=None,
        help="End card pad seconds (default: render_final 1.6; designed-post still draws 完)",
    )
    fin.add_argument(
        "--plate-cards",
        choices=["text", "blank", "auto"],
        default="blank",
        help="blank=pad only with no glyphs (default); text is an explicit FFmpeg-only compatibility override",
    )
    fin.add_argument(
        "--post-engine",
        default="hyperframes",
        choices=["ffmpeg", "hyperframes", "remotion"],
        help=(
            "Staged final: ffmpeg=plate burns captions; "
            "hyperframes=stage_plate (subs off) → stage_hf captions → "
            "stage_caption verify (HF failure blocks and must re-render) → deliver. "
            "Never assumes HF burned without gate."
        ),
    )
    fin.add_argument(
        "--subs",
        default="off",
        choices=["burn", "off"],
        help=(
            "Plate only: off is the default so HyperFrames is the sole text/caption layer; "
            "burn is an explicit FFmpeg-only compatibility override."
        ),
    )
    fin.add_argument(
        "--plate-timeout",
        type=int,
        default=0,
        help="Seconds for stage_plate; 0 auto-scales from duration, shots and lipsync (floor 1200)",
    )
    fin.add_argument(
        "--no-caption-recovery",
        action="store_true",
        help=("Deprecated compatibility flag; HyperFrames delivery never uses caption recovery"),
    )
    fin.add_argument(
        "--compose-quality",
        default=None,
        choices=["draft", "standard", "high"],
        help="HyperFrames render quality when --post-engine hyperframes",
    )
    fin.add_argument(
        "--compose-preset",
        default="auto",
        choices=["auto", "ecchi-rnb", "minimal"],
        help="Designed-post title/caption look: auto (from mood/tone) | ecchi-rnb | minimal",
    )
    fin.add_argument(
        "--title-sequence",
        default=None,
        choices=["auto", "none"],
        help="Override film-spec title_sequence mode (auto=spec/default, none=suppress)",
    )
    fin.add_argument(
        "--end-roll",
        default=None,
        choices=["auto", "none", "cast_only", "full"],
        help="Override film-spec end_roll mode (auto=spec/default, none=suppress)",
    )
    fin.add_argument(
        "--require-preview",
        action="store_true",
        help="With designed-post: require receipts/compose-preview.json first",
    )
    fin.add_argument(
        "--npm-install",
        action="store_true",
        help="With --post-engine remotion: run npm install once before render (network)",
    )
    fin.add_argument(
        "--npm-install-timeout",
        type=int,
        default=900,
        help="Seconds for remotion --npm-install (default 900)",
    )
    fin.add_argument(
        "--allow-burned-underlay",
        action="store_true",
        help="Allow underlay when plate already has burned-in captions (double-burn risk)",
    )
    fin.add_argument(
        "--skip-compose-check",
        action="store_true",
        help="Skip hyperframes check before render (not recommended)",
    )
    fin.add_argument(
        "--keep-compose-raw",
        action="store_true",
        help="Keep out/film_*_raw.mp4 when using designed-post engines",
    )
    fin.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip lesson preflight hard gates before final (not recommended)",
    )
    fin.add_argument(
        "--skip-canonical-truth",
        action="store_true",
        help=(
            "Skip production-truth canonical graph/manifest gate before final. "
            "For H3 keep_native bulk ship when drama-graph is incomplete; "
            "also AIFILM_SKIP_CANONICAL_TRUTH=1. Not for locked canonical series."
        ),
    )
    fin.add_argument(
        "--skip-heat-gate",
        action="store_true",
        help="Skip adult-max heat final_ok (S-grade) gate before final (not recommended)",
    )
    fin.add_argument(
        "--skip-cinematic",
        action="store_true",
        help=(
            "Skip cinematic audit hard block before final (H3 native stage-2 plate path). "
            "Also AIFILM_SKIP_CINEMATIC=1. Marks plate honesty; not master_lock."
        ),
    )
    fin.add_argument(
        "--allow-candidate-clips",
        action="store_true",
        help=(
            "Count candidate clips as inventory-complete for final plate path "
            "(H3 native season). Also AIFILM_FINAL_ALLOW_CANDIDATE_CLIPS=1."
        ),
    )
    fin.add_argument(
        "--preflight-strict",
        action="store_true",
        help="Also block final on preflight soft warnings",
    )

    review = sub.add_parser(
        "review-final",
        help="Record explicit end-to-end final-film approval with director scorecard",
    )
    review.add_argument("--root", required=True)
    review.add_argument(
        "--review-file",
        help="Hash-bound JSON emitted by review-ui; replaces reviewer/notes/score/grade/evidence flags",
    )
    review.add_argument("--approve", action="store_true")
    review.add_argument("--reviewer")
    review.add_argument("--notes")
    review.add_argument(
        "--watched-full", action="store_true", help="Required by review contract v3"
    )
    for dim in SCORECARD_DIMENSIONS:
        flag = f"--score-{dim.replace('_', '-')}"
        review.add_argument(
            flag,
            choices=["pass", "fail"],
            default=None,
            dest=f"score_{dim}",
            help=f"Director scorecard dimension '{dim}' (required with --approve)",
        )
        review.add_argument(
            f"--grade-{dim.replace('_', '-')}",
            type=int,
            choices=range(1, 6),
            default=None,
            dest=f"grade_{dim}",
            help="v3 numeric grade 1-5",
        )
    review.add_argument(
        "--reshoot-shots",
        default="",
        help="Comma-separated shot ids to attach to identity/style/motion/escalation fails (writes director_notes)",
    )
    review.add_argument(
        "--screening-evidence",
        action="append",
        default=[],
        help="v1.6: repeat dimension@seconds:note for each final scorecard dimension",
    )
    review.add_argument(
        "--fail-reason",
        action="append",
        default=[],
        help="v3 repeat dimension:CANONICAL_CODE[:shot]",
    )

    editorial_review = sub.add_parser(
        "final-editorial-review",
        help="Write a hash-bound no-spend editorial review before final approval",
    )
    editorial_review.add_argument("--root", required=True)

    postq = sub.add_parser("post-quality", help="VFX, audio and premium Master QC contracts")
    postq_sub = postq.add_subparsers(dest="post_action", required=True)
    vr = postq_sub.add_parser("vfx-register")
    vr.add_argument("--root", required=True)
    vr.add_argument("--shot-id", required=True)
    vr.add_argument("--plate", required=True)
    vr.add_argument(
        "--status", choices=("pending", "wip", "review", "approved", "rejected"), required=True
    )
    vr.add_argument("--reviewer", required=True)
    vr.add_argument("--notes", default="")
    for name in ("vfx-check", "audio-check"):
        post_check = postq_sub.add_parser(name)
        post_check.add_argument("--root", required=True)
    mq = postq_sub.add_parser("master-qc")
    mq.add_argument("--root", required=True)
    mq.add_argument("--final", default=None)

    closeout = sub.add_parser(
        "closeout",
        help="Delivery ladder: heat → review-final gate → post-audit → optional export",
    )
    closeout_sub = closeout.add_subparsers(dest="closeout_action", required=True)
    cos = closeout_sub.add_parser("status", help="Read-only closeout ladder status")
    cos.add_argument("--root", required=True)
    cor = closeout_sub.add_parser(
        "run",
        help="Run automatable steps; stop at human review-final (never auto-approve)",
    )
    cor.add_argument("--root", required=True)
    cor.add_argument(
        "--export",
        action="store_true",
        help="After post-audit ok, emit export-desktop next_cmd (requires --name)",
    )
    cor.add_argument("--name", default=None, help="Desktop export folder name (with --export)")
    cor.add_argument(
        "--status-only",
        action="store_true",
        help="Do not run post-audit; status snapshot only",
    )

    cpv = sub.add_parser(
        "compose-preview",
        help="Start HyperFrames or Remotion Studio; write receipts/compose-preview.json",
    )
    cpv.add_argument("--root", required=True)
    cpv.add_argument(
        "--engine",
        default="hyperframes",
        choices=["hyperframes", "remotion"],
        help="hyperframes (default) | remotion (needs npm install in compose/remotion)",
    )
    cpv.add_argument(
        "--port",
        type=int,
        default=None,
        help="Studio port (default 3002 HF / 3003 Remotion)",
    )
    cpv.add_argument("--no-open", action="store_true", help="Print URL only; do not open browser")
    cpv.add_argument(
        "--no-export", action="store_true", help="Do not auto export-compose if missing"
    )
    cpv.add_argument("--foreground", action="store_true", help="Block instead of background server")
    cpv.add_argument("--force-new", action="store_true")
    cpv.add_argument("--stop", action="store_true", help="Stop background Studio (HF only)")
    cpv.add_argument(
        "--status",
        action="store_true",
        dest="status_only",
        help="Show running Studio URL without starting",
    )

    ec = sub.add_parser(
        "export-compose",
        help="Export approved clips to HyperFrames/Remotion designed-post packages",
    )
    ec.add_argument("--root", required=True)
    ec.add_argument(
        "--engine",
        default="both",
        choices=["hyperframes", "remotion", "both"],
        help="hyperframes (HTML Studio, default primary) | remotion | both",
    )
    ec.add_argument(
        "--post-owner",
        choices=["ffmpeg", "hyperframes", "remotion"],
        default=None,
        help="Create a missing post-plan with this owner (default follows --engine)",
    )
    ec.add_argument(
        "--layout",
        default="auto",
        choices=["auto", "multiclip", "underlay"],
        help="auto: underlay when film_final exists",
    )
    ec.add_argument(
        "--compose-preset",
        default="auto",
        choices=["auto", "ecchi-rnb", "minimal"],
        help="Title/caption preset: auto|ecchi-rnb|minimal",
    )
    ec.add_argument("--title-dur", type=float, default=1.5)
    ec.add_argument("--end-dur", type=float, default=1.5)
    ec.add_argument(
        "--title-sequence",
        default=None,
        choices=["auto", "none"],
        help="Override film-spec title_sequence mode (auto=spec/default, none=suppress)",
    )
    ec.add_argument(
        "--end-roll",
        default=None,
        choices=["auto", "none", "cast_only", "full"],
        help="Override film-spec end_roll mode (auto=spec/default, none=suppress)",
    )
    ec.add_argument("--force", action="store_true", help="Overwrite existing compose/")

    cr = sub.add_parser(
        "compose-render",
        help="HyperFrames check+render+audio+register final (designed post)",
    )
    cr.add_argument("--root", required=True)
    cr.add_argument(
        "--engine",
        default="hyperframes",
        choices=["hyperframes", "remotion", "both"],
    )
    cr.add_argument("--layout", default="auto", choices=["auto", "multiclip", "underlay"])
    cr.add_argument(
        "--compose-preset",
        default="auto",
        choices=["auto", "ecchi-rnb", "minimal"],
        help="Title/caption preset: auto|ecchi-rnb|minimal",
    )
    cr.add_argument(
        "--require-preview",
        action="store_true",
        help="Require receipts/compose-preview.json before HyperFrames render",
    )
    cr.add_argument(
        "--npm-install",
        action="store_true",
        help="Remotion: run npm install in compose/remotion before auto-render (network)",
    )
    cr.add_argument(
        "--npm-install-timeout",
        type=int,
        default=900,
        help="Timeout seconds for --npm-install (default 900)",
    )
    cr.add_argument("--quality", default="standard", choices=["draft", "standard", "high"])
    cr.add_argument("--out-name", default="film_final.mp4")
    cr.add_argument("--no-export", action="store_true")
    cr.add_argument("--no-force-export", action="store_true")
    cr.add_argument("--no-register", action="store_true")
    cr.add_argument("--skip-check", action="store_true")
    cr.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep out/film_hyperframes_raw.mp4 after audio mux",
    )
    cr.add_argument("--title-dur", type=float, default=1.5)
    cr.add_argument("--end-dur", type=float, default=1.5)
    cr.add_argument(
        "--title-sequence",
        default=None,
        choices=["auto", "none"],
        help="Override film-spec title_sequence mode (auto=spec/default, none=suppress)",
    )
    cr.add_argument(
        "--end-roll",
        default=None,
        choices=["auto", "none", "cast_only", "full"],
        help="Override film-spec end_roll mode (auto=spec/default, none=suppress)",
    )
    cr.add_argument(
        "--allow-burned-underlay",
        action="store_true",
        help="Allow underlay when plate already has burned-in captions (double-burn risk)",
    )
    cr.add_argument(
        "--register-only",
        default=None,
        help="Only register existing MP4 as final_film",
    )
    cr.add_argument("--post-engine", default="external")

    pp = sub.add_parser(
        "post-plan",
        help="Create or validate the editorial-to-HyperFrames/Remotion handoff",
    )
    pp.add_argument("--root", required=True)
    pp_sub = pp.add_subparsers(dest="post_plan_action", required=True)
    pp_init = pp_sub.add_parser("init", help="Write post-plan.json with one post owner")
    pp_init.add_argument(
        "--owner", choices=["ffmpeg", "hyperframes", "remotion"], default="hyperframes"
    )
    pp_init.add_argument("--edl", default=None, help="Workspace-relative video-use EDL path")
    pp_init.add_argument("--master-subtitles", default="out/final.srt")
    pp_init.add_argument("--audio-plan", default="sound-plan.json")
    pp_init.add_argument("--force", action="store_true")
    pp_validate = pp_sub.add_parser("validate", help="Validate post-plan.json")
    pp_validate.add_argument("--check-artifacts", action="store_true")
    pp_sub.add_parser("show", help="Print post-plan.json and its validation result")

    rf = sub.add_parser(
        "register-final",
        help="Register external/composed MP4 as formal final_film candidate",
    )
    rf.add_argument("--root", required=True)
    rf.add_argument("--source", required=True)
    rf.add_argument("--out-name", default="film_final.mp4")
    rf.add_argument(
        "--post-engine",
        default="external",
        help="Label: external|hyperframes|remotion|ffmpeg",
    )
    rf.add_argument(
        "--allow-static",
        action="store_true",
        help="Allow motion QA soft path (title-only tests; production leave off)",
    )

    ex = sub.add_parser("export-desktop", help="Copy deliverables to ~/Desktop/<name>")
    ex.add_argument("--root", required=True)
    ex.add_argument("--name", required=True)
    ex.add_argument("--force", action="store_true")
