"""Hub residual command handlers (R3) — table entry, zero argv rename.

Moved from aifilm_grok.main if-ladder. Prefer domain cli_* for new work.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cli_misc_ops import cmd_graph, cmd_skill
from core import emit
from security_policy import SecurityPolicyError, safe_existing_file
from util import require_json as read_json
from util.errors import FilmError


def run(args: Any) -> int:
    """Handle residual hub cmds. Returns process exit code."""
    if args.cmd == "local-llm":
        from local_llm import LocalLLMError
        from local_llm import draft as local_llm_draft
        from local_llm import probe as local_llm_probe
        from local_llm import shot_draft as local_llm_shot_draft

        try:
            token = os.environ.get("AIFILM_LOCAL_LLM_TOKEN") or None
            if args.local_llm_action == "probe":
                report = local_llm_probe(args.base_url, model=args.model, token=token)
            elif args.local_llm_action == "draft":
                report = local_llm_draft(
                    args.base_url,
                    model=args.model,
                    prompt=args.prompt,
                    token=token,
                    timeout=args.timeout,
                )
            else:
                report = local_llm_shot_draft(
                    args.base_url,
                    model=args.model,
                    prompt=args.prompt,
                    token=token,
                    timeout=args.timeout,
                )
        except LocalLLMError as exc:
            raise FilmError(f"{exc.code}: {exc}") from exc
        emit(report)
        return 0 if report.get("ok", True) else 2

    if args.cmd == "local-omni-review":
        from local_omni_review import LocalOmniReviewError
        from local_omni_review import probe as local_omni_probe
        from local_omni_review import review_frames as local_omni_review_frames

        try:
            token = os.environ.get("AIFILM_LOCAL_OMNI_TOKEN") or None
            if args.local_omni_review_action == "probe":
                report = local_omni_probe(args.base_url, model=args.model, token=token)
            else:
                report = local_omni_review_frames(
                    args.root,
                    args.base_url,
                    frame_index=args.frame_index,
                    model=args.model,
                    token=token,
                    sanitized=bool(args.sanitized),
                    timeout=args.timeout,
                )
        except LocalOmniReviewError as exc:
            raise FilmError(f"LOCAL_OMNI_REVIEW_ERROR: {exc}") from exc
        emit(report)
        return 0 if report.get("ok", True) else 2

    if args.cmd == "semantic-index":
        from semantic_index import SemanticIndexError, build_index, query_index

        try:
            token = os.environ.get("AIFILM_LOCAL_EMBEDDING_TOKEN") or None
            if args.semantic_index_action == "build":
                report = build_index(
                    args.root,
                    args.base_url,
                    model=args.model,
                    token=token,
                    timeout=args.timeout,
                )
            else:
                report = query_index(
                    args.root,
                    args.base_url,
                    model=args.model,
                    query=args.query,
                    limit=args.limit,
                    token=token,
                    timeout=args.timeout,
                )
        except SemanticIndexError as exc:
            raise FilmError(f"SEMANTIC_INDEX_ERROR: {exc}") from exc
        emit(report)
        return 0

    if args.cmd == "narrative-evidence":
        from narrative_evidence import (
            NarrativeEvidenceError,
            init_narrative_evidence,
            record_narrative_evidence,
            validate_narrative_evidence,
        )

        root = Path(args.root).expanduser().resolve()
        try:
            if args.narrative_evidence_action == "init":
                report = init_narrative_evidence(root)
            elif args.narrative_evidence_action == "record":
                report = record_narrative_evidence(
                    root,
                    evidence_id=args.evidence_id,
                    status=args.status,
                    shot_id=args.shot_id,
                    start_sec=args.start_sec,
                    end_sec=args.end_sec,
                    media_path=args.media_path,
                    reviewer=args.reviewer,
                    user_phrase=args.user_phrase,
                    note=args.note,
                )
            else:
                report = validate_narrative_evidence(root, require_verified=True)
        except NarrativeEvidenceError as exc:
            report = {"ok": False, "issues": [{"code": exc.code, "message": str(exc)}]}
        emit(report)
        return 0 if report.get("ok", True) else 1
    if args.cmd == "post-audit":
        from post_audit import audit

        report = audit(Path(args.root).expanduser().resolve())
        emit(report)
        return 0 if report.get("delivery_ready") else 1
    if args.cmd == "caption-frame-audit":
        from caption_frame_audit import build_caption_frame_audit

        emit(build_caption_frame_audit(Path(args.root), max_frames=args.max_frames))
        return 0
    if args.cmd == "caption-pixel-check":
        from caption_pixel_check import run_caption_pixel_check

        final = (
            Path(args.final).expanduser().resolve()
            if getattr(args, "final", None)
            else None
        )
        report = run_caption_pixel_check(
            Path(args.root),
            max_samples=int(getattr(args, "max_samples", 5) or 5),
            write=True,
            final_mp4=final,
        )
        emit(report)
        return 0 if report.get("ok") else 2
    if args.cmd == "post-doctor":
        from post_doctor import run_post_doctor

        report = run_post_doctor(Path(args.root), write=True)
        emit(report)
        return 0 if report.get("ok") else 2
    if args.cmd == "timeline-clock":
        from timeline_clock import (
            TimelineClockError,
            audit_timeline_clock,
            rewrite_timeline_from_film,
        )

        action = str(getattr(args, "timeline_clock_action", None) or "audit")
        root = Path(args.root).expanduser().resolve()
        try:
            if action == "rewrite":
                report = rewrite_timeline_from_film(root)
            else:
                report = audit_timeline_clock(root, write=True)
        except TimelineClockError as exc:
            emit({"ok": False, "error": str(exc)})
            return 2
        emit(report)
        return 0 if report.get("ok") else 2
    if args.cmd == "transition-frame-audit":
        from transition_frame_audit import build_transition_frame_audit

        emit(build_transition_frame_audit(Path(args.root)))
        return 0
    if args.cmd == "transition-frame-review-template":
        from transition_frame_audit import build_transition_review_template

        emit(build_transition_review_template(Path(args.root)))
        return 0
    if args.cmd == "transition-frame-attest":
        from transition_frame_audit import attest_transition_review

        emit(
            attest_transition_review(
                Path(args.root),
                user_phrase=args.user_phrase,
                decisions_path=Path(args.decisions) if args.decisions else None,
            )
        )
        return 0
    if args.cmd == "caption-frame-attest":
        from caption_frame_audit import attest_caption_readability

        emit(attest_caption_readability(Path(args.root), user_phrase=args.user_phrase))
        return 0
    if args.cmd == "bible":
        root = Path(args.root).expanduser().resolve()
        if args.bible_cmd == "init":
            from visual_bible import load_bible, save_bible

            bible = load_bible(root)
            save_bible(root, bible)
            emit({"ok": True, "msg": "Visual Bible initialized/migrated to v2"})
        elif args.bible_cmd == "lock":
            from visual_bible import update_bible_state

            update_bible_state(root, "Approved")
            emit({"ok": True, "msg": "Visual Bible locked (Approved)"})
        elif args.bible_cmd == "state":
            from visual_bible import update_bible_state

            update_bible_state(root, args.set)
            emit({"ok": True, "msg": f"Visual Bible state updated to {args.set}"})
        return 0
    if args.cmd == "performance-timeline":
        from performance_timeline import build_performance_timeline

        report = build_performance_timeline(Path(args.root))
        emit(report)
        return 0 if report["ok"] else 2
    if args.cmd == "speech-performance-timing":
        from speech_performance_timing import build_speech_performance_timing

        report = build_speech_performance_timing(Path(args.root))
        emit(report)
        return 0 if report["ok"] else 2
    if args.cmd == "audio-provenance":
        from audio_provenance import build_audio_provenance

        report = build_audio_provenance(Path(args.root))
        emit(report)
        return 0 if report["ok"] else 2
    if args.cmd == "subtitle-dialogue-alignment":
        from subtitle_dialogue_alignment import build_subtitle_dialogue_alignment

        report = build_subtitle_dialogue_alignment(Path(args.root))
        emit(report)
        return 0 if report["ok"] else 2
    if args.cmd == "subtitle-cut-boundaries":
        from subtitle_cut_boundaries import build_subtitle_cut_boundaries

        report = build_subtitle_cut_boundaries(Path(args.root))
        emit(report)
        return 0 if report["ok"] else 2
    if args.cmd == "quality-check":
        from quality_check_video import QualityCheckError, run_quality_check

        out_dir = args.out
        if not out_dir and args.root:
            out_dir = str(Path(args.root).expanduser().resolve() / "out")
        try:
            report = run_quality_check(
                args.video,
                out_dir=out_dir,
                expect_audio=args.expect_audio,
                expect_subtitles=args.expect_subtitles,
                srt=args.srt,
                min_score=args.min_score,
                allow_black=args.allow_black,
                allow_freeze=args.allow_freeze,
            )
        except QualityCheckError as exc:
            raise FilmError(str(exc)) from exc
        emit(report)
        return 0 if report["passed"] else 1
    if args.cmd == "review-pack":
        from review_pack import (
            ReviewPackError,
            build_review_pack,
            comfy_download_target,
            ensure_review_pack_available,
        )

        supplied = [bool(args.source), bool(args.comfy_filename)]
        if sum(supplied) != 1:
            raise FilmError("review-pack requires exactly one of --source or --comfy-filename")
        root = Path(args.root).expanduser().resolve()
        source = Path(args.source).expanduser() if args.source else None
        download = None
        if args.comfy_filename:
            from comfy_armory import ComfyArmoryError, default_base_url
            from comfy_video import ComfyVideoError, download_result

            try:
                ensure_review_pack_available(root, pack_id=args.id)
                base_url = args.comfy_base_url or default_base_url()
                source = comfy_download_target(
                    root, pack_id=args.id, filename=args.comfy_filename
                )
                download = download_result(
                    base_url,
                    {
                        "filename": args.comfy_filename,
                        "subfolder": args.comfy_subfolder,
                        "type": args.comfy_type,
                    },
                    source,
                )
            except (
                ComfyArmoryError,
                ComfyVideoError,
                ReviewPackError,
                SecurityPolicyError,
            ) as exc:
                raise FilmError(str(exc)) from exc
        try:
            report = build_review_pack(
                root,
                pack_id=args.id,
                source=source,
                expect_audio=args.expect_audio,
                download=download,
            )
        except (ReviewPackError, ValueError) as exc:
            raise FilmError(str(exc)) from exc
        emit(report)
        return 0 if report["ok"] else 1
    if args.cmd == "analyze-reference":
        from reference_audit import ReferenceAuditError, run_reference_audit

        out_dir = args.out
        if not out_dir and args.root:
            out_dir = str(Path(args.root).expanduser().resolve() / "reference-analysis")
        try:
            report = run_reference_audit(args.video, out_dir=out_dir, frames=args.frames)
        except ReferenceAuditError as exc:
            raise FilmError(str(exc)) from exc
        emit(report)
        return 0
    if args.cmd == "brief":
        from product_brief import ProductBriefError, expand_product_brief, save_product_brief

        text = args.text
        if not text and args.file:
            text = Path(args.file).expanduser().resolve().read_text(encoding="utf-8")
        if not text:
            raise FilmError("brief expand requires --text or --file")
        try:
            packet = expand_product_brief(
                text,
                title=args.title,
                target_duration=args.target_duration,
                voice_style=args.voice_style,
                language=args.language,
            )
        except ProductBriefError as exc:
            raise FilmError(str(exc)) from exc
        path = save_product_brief(args.root, packet)
        packet["receipt_path"] = str(path)
        emit(packet)
        return 0
    if args.cmd == "director-ledger":
        from director_ledger import build_director_ledger

        emit(build_director_ledger(Path(args.root)))
        return 0
    if args.cmd == "planning-autopilot":
        from planning_autopilot import build_planning_autopilot

        emit(build_planning_autopilot(Path(args.root)))
        return 0
    if args.cmd == "planning-answer":
        from planning_autopilot import apply_authoring_answers

        try:
            answers = json.loads(args.answers_json)
        except json.JSONDecodeError as exc:
            raise FilmError(f"--answers-json must be valid JSON: {exc}") from exc
        if not isinstance(answers, list):
            raise FilmError("--answers-json must be a JSON list")
        emit(
            apply_authoring_answers(
                Path(args.root),
                answers,
                dry_run=bool(args.dry_run),
                expected_transaction_id=args.expected_transaction_id,
            )
        )
        return 0
    if args.cmd == "planning-history":
        from planning_autopilot import planning_history_summary

        emit(planning_history_summary(Path(args.root)))
        return 0
    if args.cmd == "prompt-budget":
        from prompt_budget import prompt_budget_report

        emit(
            prompt_budget_report(
                Path(args.root),
                write=bool(args.write),
                max_estimated_tokens=args.max_estimated_tokens,
            )
        )
        return 0
    if args.cmd == "prompt-compression-pilot":
        from prompt_compression_pilot import build_prompt_compression_pilot

        candidate_path = safe_existing_file(
            Path(args.root), args.candidate_json, field="prompt-compression candidate JSON"
        )
        candidate = read_json(candidate_path)
        if not isinstance(candidate, dict):
            raise FilmError("--candidate-json must be a JSON object")
        emit(build_prompt_compression_pilot(Path(args.root), candidate))
        return 0
    if args.cmd == "prompt-compression-attest":
        from prompt_compression_pilot import attest_prompt_compression_pilot

        evidence_path = safe_existing_file(
            Path(args.root), args.evidence_json, field="prompt-compression evidence JSON"
        )
        evidence = read_json(evidence_path)
        if not isinstance(evidence, dict):
            raise FilmError("--evidence-json must be a JSON object")
        emit(
            attest_prompt_compression_pilot(
                Path(args.root), evidence, user_phrase=args.user_phrase
            )
        )
        return 0
    if args.cmd == "beat-evidence":
        from beat_action_evidence import build_beat_action_evidence

        report = build_beat_action_evidence(Path(args.root))
        emit(report)
        return 0 if report["ok"] else 2
    if args.cmd == "editor-cut":
        from editor_cut import build_editor_cut_report

        report = build_editor_cut_report(Path(args.root))
        emit(report)
        return 0 if report["ok"] else 2
    if args.cmd == "audio-visual":
        from audio_visual_alignment import build_audio_visual_alignment

        report = build_audio_visual_alignment(Path(args.root))
        emit(report)
        return 0 if report["ok"] else 2
    if args.cmd == "graph":
        # allow --no-derive to flip auto_derive off for status
        if getattr(args, "graph_action", None) == "status" and bool(
            getattr(args, "no_derive", False)
        ):
            args.derive_if_missing = False
        return cmd_graph(args)
    if args.cmd == "skill":
        if args.skill_action == "run":
            from skill_runner import run_skill

            report = run_skill(args.skill_id, args.payload_file, dry_run=bool(args.dry_run))
            emit(report)
            return 0 if report.get("ok") else 2
        return cmd_skill(args)
    raise FilmError(f"Unknown residual command {getattr(args, 'cmd', None)}")


RESIDUAL_CMDS = frozenset({
    "analyze-reference",
    "audio-provenance",
    "audio-visual",
    "beat-evidence",
    "bible",
    "brief",
    "caption-frame-attest",
    "caption-frame-audit",
    "caption-pixel-check",
    "director-ledger",
    "editor-cut",
    "graph",
    "local-llm",
    "local-omni-review",
    "narrative-evidence",
    "performance-timeline",
    "planning-answer",
    "planning-autopilot",
    "planning-history",
    "post-audit",
    "post-doctor",
    "prompt-budget",
    "prompt-compression-attest",
    "prompt-compression-pilot",
    "quality-check",
    "review-pack",
    "semantic-index",
    "skill",
    "speech-performance-timing",
    "subtitle-cut-boundaries",
    "subtitle-dialogue-alignment",
    "timeline-clock",
    "transition-frame-attest",
    "transition-frame-audit",
    "transition-frame-review-template",
})
