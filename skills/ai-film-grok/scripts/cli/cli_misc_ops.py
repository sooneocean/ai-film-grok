"""Init/misc CLI + leftover parsers — extracted from aifilm_grok (public cmd strings unchanged).

Uses scripts/core for film IO/emit/gates (no hub cycle for basic IO).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from util.errors import FilmError


def _run_optimization_cli(args: argparse.Namespace, action: str) -> int:
    import aifilm_grok as hub

    return hub._run_optimization_cli(args, action)


def _run_quality_reporting_cli(args: argparse.Namespace, command: str) -> int:
    import aifilm_grok as hub

    return hub._run_quality_reporting_cli(args, command)



def add_misc_ops_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    init_p = sub.add_parser("init", help="Create film root")
    init_p.add_argument("--theme", required=True)
    init_p.add_argument("--title", required=True)
    init_p.add_argument("--root", required=True)
    init_p.add_argument("--aspect", default="9:16")
    init_p.add_argument("--force", action="store_true")

    truth = sub.add_parser(
        "truth", help="Read-only audit of production authority records and projection drift"
    )
    truth_sub = truth.add_subparsers(dest="truth_action", required=True)
    truth_audit = truth_sub.add_parser("audit")
    truth_audit.add_argument("--root", required=True)
    truth_audit.set_defaults(no_write=True)

    manifest_cmd = sub.add_parser(
        "manifest", help="Preflight or explicitly migrate production manifest truth"
    )
    manifest_sub = manifest_cmd.add_subparsers(dest="manifest_action", required=True)
    manifest_preflight = manifest_sub.add_parser("preflight")
    manifest_preflight.add_argument("--root", required=True)
    manifest_migrate = manifest_sub.add_parser("migrate")
    manifest_migrate.add_argument("--root", required=True)
    manifest_migrate.add_argument(
        "--write", action="store_true", help="Persist only when migration preflight passes"
    )

    vibevoice_asr = sub.add_parser(
        "vibevoice-asr",
        help="Local VibeVoice-ASR candidate-only subtitle and speaker review",
    )
    vibevoice_asr_sub = vibevoice_asr.add_subparsers(dest="vibevoice_asr_action", required=True)
    vibevoice_asr_sub.add_parser(
        "probe",
        help="Check local adapter configuration only; never starts inference or downloads a model",
    )
    vibevoice_run = vibevoice_asr_sub.add_parser(
        "run", help="Run the declared local adapter and write a candidate-only ASR review"
    )
    vibevoice_run.add_argument("--root", required=True, help="Film workspace root")
    vibevoice_run.add_argument("--audio", required=True, help="Verified local audio in root")
    vibevoice_run.add_argument("--subtitles", default=None, help="Optional in-root SRT sidecar")

    semantic_index = sub.add_parser(
        "semantic-index",
        help="Opt-in private semantic retrieval; returns source-bound review candidates only",
    )
    semantic_index_sub = semantic_index.add_subparsers(dest="semantic_index_action", required=True)
    for action, help_text in (
        ("build", "Embed allowlisted local authoring records into a derived index"),
        ("query", "Return ranked source-bound candidates from a fresh local index"),
    ):
        action_parser = semantic_index_sub.add_parser(action, help=help_text)
        action_parser.add_argument("--root", required=True, help="Film root")
        action_parser.add_argument(
            "--base-url",
            default=os.environ.get("AIFILM_LOCAL_EMBEDDING_BASE_URL", ""),
            help="Private OpenAI-compatible /v1 URL (or AIFILM_LOCAL_EMBEDDING_BASE_URL)",
        )
        action_parser.add_argument(
            "--model",
            default="text-embedding-nomic-embed-text-v1.5",
            help="Approved local embedding model; default text-embedding-nomic-embed-text-v1.5",
        )
        action_parser.add_argument(
            "--timeout", type=int, default=45, help="1-120 seconds; default 45"
        )
        if action == "query":
            action_parser.add_argument(
                "--query", required=True, help="Question to retrieve local candidates"
            )
            action_parser.add_argument(
                "--limit", type=int, default=5, help="1-20 results; default 5"
            )

    prompt_budget = sub.add_parser(
        "prompt-budget", help="Audit prompt-token estimates and repeated provider-bound lines"
    )
    prompt_budget.add_argument("--root", required=True)
    prompt_budget.add_argument(
        "--write", action="store_true", help="Write receipts/prompt-budget.json"
    )
    prompt_budget.add_argument(
        "--max-estimated-tokens",
        type=int,
        default=None,
        help="Set a review threshold; never rewrites prompts or approves compression",
    )

    compression_pilot = sub.add_parser(
        "prompt-compression-pilot",
        help="Write a hash-bound, evidence-required prompt-compression Pilot ledger",
    )
    compression_pilot.add_argument("--root", required=True)
    compression_pilot.add_argument(
        "--candidate-json",
        required=True,
        help="Root-contained JSON: source_line plus candidate prompt text for each Pilot shot",
    )

    compression_attest = sub.add_parser(
        "prompt-compression-attest",
        help="Bind candidate media/QA and existing human Pilot approval to a compression ledger",
    )
    compression_attest.add_argument("--root", required=True)
    compression_attest.add_argument("--evidence-json", required=True)
    compression_attest.add_argument("--user-phrase", required=True)

    answer = sub.add_parser(
        "planning-answer", help="Apply structured answers to open graph authoring fields only"
    )
    answer.add_argument("--root", required=True)
    answer.add_argument(
        "--answers-json",
        required=True,
        help='JSON list: [{"node_ref":"…","field":"…","value":"…"}]',
    )
    answer.add_argument("--dry-run", action="store_true")
    answer.add_argument(
        "--expected-transaction-id",
        default=None,
        help="Require the exact transaction_id returned by a prior dry-run",
    )

    history = sub.add_parser(
        "planning-history", help="Show planning readiness progression and current blockers"
    )
    history.add_argument("--root", required=True)

    autopilot = sub.add_parser(
        "planning-autopilot", help="Show safe automatic planning steps and human lock points"
    )
    autopilot.add_argument("--root", required=True)

    refaudit = sub.add_parser(
        "analyze-reference",
        help="Analyze a reference video: probe, contact sheet, keyframes, shot grammar",
    )
    refaudit.add_argument("video", help="Reference video path")
    refaudit.add_argument(
        "--root", default=None, help="Film root (writes to <root>/reference-analysis)"
    )
    refaudit.add_argument("--out", default=None, help="Output dir (overrides --root)")
    refaudit.add_argument(
        "--frames",
        default="0,3,6,9,13,18,24,30,36",
        help="Comma-separated timestamps (seconds) for keyframe extraction",
    )

    # v1.23: product brief expansion (product intro video track)

    brief_p = sub.add_parser(
        "brief",
        help="Product brief: expand a product intro into a structured video brief",
    )
    brief_sub = brief_p.add_subparsers(dest="brief_action", required=True)
    brief_expand = brief_sub.add_parser(
        "expand", help="Expand raw product text → product-brief.json"
    )
    brief_expand.add_argument("--root", required=True, help="Film root")
    brief_expand.add_argument("--text", default=None, help="Raw product description text")
    brief_expand.add_argument("--file", default=None, help="Path to product description file")
    brief_expand.add_argument("--title", default=None, help="Product name override")
    brief_expand.add_argument(
        "--target-duration", type=float, default=40.0, help="Target duration seconds"
    )
    brief_expand.add_argument(
        "--voice-style", default="warm", help="Voice style hint (warm/tech/neutral)"
    )
    brief_expand.add_argument("--language", default="zh", choices=["zh", "en"], help="VO language")

    local_llm = sub.add_parser(
        "local-llm",
        help="Opt-in private LLM drafts; cannot modify story truth or approve production",
    )
    local_llm_sub = local_llm.add_subparsers(dest="local_llm_action", required=True)
    for action, help_text in (
        ("probe", "Read the private model list without starting inference"),
        ("draft", "Generate one human-review-only creative candidate"),
        ("shot-draft", "Generate exactly two schema-validated candidate shots"),
    ):
        action_parser = local_llm_sub.add_parser(action, help=help_text)
        action_parser.add_argument(
            "--base-url",
            default=os.environ.get("AIFILM_LOCAL_LLM_BASE_URL", ""),
            help="Private OpenAI-compatible /v1 URL (or AIFILM_LOCAL_LLM_BASE_URL)",
        )
        action_parser.add_argument(
            "--model",
            default="openai/gpt-oss-20b",
            help="Approved local model id; default openai/gpt-oss-20b",
        )
        if action in {"draft", "shot-draft"}:
            action_parser.add_argument(
                "--prompt", required=True, help="Draft request; never writes film files"
            )
            action_parser.add_argument(
                "--timeout", type=int, default=45, help="1-120 seconds; default 45"
            )

    ne = sub.add_parser(
        "narrative-evidence",
        help="Create or validate executed/human evidence for episode hooks and plot points",
    )
    ne_sub = ne.add_subparsers(dest="narrative_evidence_action", required=True)
    ne_init = ne_sub.add_parser("init", help="Create the plan-side evidence ledger")
    ne_init.add_argument("--root", required=True)
    ne_record = ne_sub.add_parser("record", help="Register one executed evidence item")
    ne_record.add_argument("--root", required=True)
    ne_record.add_argument("--evidence-id", required=True)
    ne_record.add_argument("--status", required=True, choices=("verified", "missing", "uncertain"))
    ne_record.add_argument("--shot-id")
    ne_record.add_argument("--start-sec", type=float)
    ne_record.add_argument("--end-sec", type=float)
    ne_record.add_argument("--media-path")
    ne_record.add_argument("--reviewer")
    ne_record.add_argument("--user-phrase")
    ne_record.add_argument("--note", default="")
    ne_validate = ne_sub.add_parser("validate", help="Validate current media-backed evidence")
    ne_validate.add_argument("--root", required=True)

    sub.add_parser(
        "beat-evidence", help="Validate planned shot actions against human review evidence"
    ).add_argument("--root", required=True)

    sub.add_parser(
        "editor-cut", help="Check deterministic rough-cut readiness and active take integrity"
    ).add_argument("--root", required=True)

    subtitle_boundaries = sub.add_parser(
        "subtitle-cut-boundaries", help="Check subtitle cues against hard and Continue cuts"
    )
    subtitle_boundaries.add_argument("--root", required=True)

    # v1.23: delivery-level FFmpeg quality gates (objective, pre-scorecard)

    subtitle_alignment = sub.add_parser(
        "subtitle-dialogue-alignment",
        help="Check subtitle coverage and safe area for lipsync dialogue",
    )
    subtitle_alignment.add_argument("--root", required=True)

    skill_p = sub.add_parser("skill", help="Skill Registry: list|show|validate|run")
    skill_sub = skill_p.add_subparsers(dest="skill_action", required=True)
    sk_list = skill_sub.add_parser("list", help="List registered skills")
    sk_list.add_argument("--tag", default=None, help="Filter by tag")
    sk_list.add_argument("--phase", default=None, help="Filter by phase id (e.g. 1, 2)")
    sk_show = skill_sub.add_parser("show", help="Show one skill + contracts")
    sk_show.add_argument("--id", dest="id", required=True, help="skill_id e.g. image.animate")
    sk_validate = skill_sub.add_parser("validate", help="Validate runtime input/output envelope")
    sk_validate.add_argument("--skill-id", required=True)
    sk_validate.add_argument("--payload-file", required=True)
    sk_validate.add_argument("--direction", choices=("input", "output"), default="input")
    sk_run = skill_sub.add_parser("run", help="Run one fixed registry skill transaction")
    sk_run.add_argument("--skill-id", required=True)
    sk_run.add_argument("--payload-file", required=True)
    sk_run.add_argument("--dry-run", action="store_true")

    performance_timeline = sub.add_parser(
        "performance-timeline",
        help="Compile checksum-bound per-shot performance evidence into a director timeline",
    )
    performance_timeline.add_argument("--root", required=True)

    sub.add_parser(
        "audio-visual", help="Check audio, dialogue, subtitle and timeline alignment"
    ).add_argument("--root", required=True)

def cmd_init(args: argparse.Namespace) -> int:
    """Build a new root off-path, then publish the complete Professional project."""
    import aifilm_grok as hub  # hub-only helpers
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    destination = Path(args.root).expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        return hub._cmd_init_in_place(args)
    if destination.is_symlink():
        raise FilmError(f"Refusing to initialize a symlink root: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.aifilm-init-", dir=destination.parent)
    )
    staged_args = argparse.Namespace(**vars(args))
    staged_args.root = str(staging)
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            result = hub._cmd_init_in_place(staged_args)
        if result != 0:
            raise FilmError(f"staged init failed with status {result}")
        (staging / "README.md").write_text(
            f"# {args.title.strip()}\n\nTheme: {args.theme.strip()}\n\n"
            f"Provider: Grok Imagine\nRoot: `{destination}`\n",
            encoding="utf-8",
        )
        if destination.exists():
            destination.rmdir()
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    payload = json.loads(captured.getvalue())
    payload["root"] = str(destination)
    emit(payload)
    return result


def cmd_truth(args: argparse.Namespace) -> int:
    """Audit production authority records without modifying the film root."""
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from production_truth import audit_production_truth

    report = audit_production_truth(Path(args.root))
    emit(report)
    return 0 if report["ok"] else 2


def cmd_manifest(args: argparse.Namespace) -> int:
    """Preflight or explicitly migrate a manifest before production use."""
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from manifest_truth import migrate_manifest, preflight_manifest

    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    if args.manifest_action == "preflight":
        report = preflight_manifest(root, manifest)
        emit(report)
        return 0 if report["ok"] else 2
    report = migrate_manifest(root, write=bool(args.write))
    emit(report)
    return 0 if report["ok"] else 2


def cmd_vibevoice_asr(args: argparse.Namespace) -> int:
    from config_loader import get_config
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from vibevoice_asr_review import VibeVoiceASRError, capability_probe, create_report

    get_config()
    try:
        if args.vibevoice_asr_action == "probe":
            report = capability_probe()
        else:
            report = create_report(args.root, audio=args.audio, subtitles=args.subtitles)
    except VibeVoiceASRError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0


def cmd_skill(args: argparse.Namespace) -> int:
    """Skill Registry route delegated to the registry CLI module."""
    from cli_skill import run
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    report, code = run(args)
    emit(report)
    return code


def cmd_assets(args: argparse.Namespace) -> int:
    """Phase 4: structured Character/Location/Prop + CharacterState ↔ state-index."""
    from asset_registry import assets_check, assets_status, sync_assets
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    action = str(getattr(args, "assets_action", "") or "")
    root_s = getattr(args, "root", None)
    if not root_s:
        raise FilmError("assets requires --root")
    root = Path(root_s).expanduser().resolve()

    if action == "sync":
        report = sync_assets(
            root,
            write=not bool(getattr(args, "no_write", False)),
            force=bool(getattr(args, "force", False)),
            update_graph=not bool(getattr(args, "no_graph", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "status":
        report = assets_status(root, auto_sync=bool(getattr(args, "sync", False)))
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "check":
        report = assets_check(
            root,
            sync_first=not bool(getattr(args, "no_sync", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    raise FilmError(f"unknown assets action {action!r}")


def cmd_graph(args: argparse.Namespace) -> int:
    """Graph command adapter split between read-only and mutation domains."""
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    root = Path(args.root).expanduser().resolve()
    action = str(getattr(args, "graph_action", "") or "")
    if action in {"validate", "status"}:
        from cli_graph import status as status_graph_cli
        from cli_graph import validate as validate_graph_cli

        runner = validate_graph_cli if action == "validate" else status_graph_cli
        report, code = runner(args, root)
        emit(report)
        return code

    from cli_graph_mutation import GraphMutationError, run

    try:
        report, code = run(args, root)
    except GraphMutationError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_plan(args: argparse.Namespace) -> int:
    """Phase 3: story.normalize → beat/shot plan → drama-graph (+ film-spec seed)."""
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    action = str(getattr(args, "plan_action", "") or "")
    if action == "receive":
        from narrative_control import control_status
        from story_reception import ReceptionError, load_story_reception
        from util import write_json

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan receive requires --root")
        root = Path(root_s).expanduser().resolve()
        status = control_status(root)
        if "story" in set(status.get("locked_scopes") or []):
            raise FilmError("story is locked; unlock story before receiving a revised treatment")
        try:
            reception_path = Path(str(getattr(args, "file", ""))).expanduser().resolve()
            reception = load_story_reception(reception_path)
        except ReceptionError as exc:
            raise FilmError(str(exc)) from exc
        output = root / "receipts" / "story-reception.json"
        if output.exists() and not bool(getattr(args, "force", False)):
            raise FilmError(
                "story reception already exists; pass --force before story lock to replace it"
            )
        write_json(output, reception)
        emit(
            {
                "ok": True,
                "action": "receive",
                "path": str(output),
                "source_sha256": reception["source"]["sha256"],
                "summary": {
                    "title": reception["treatment"].get("title"),
                    "logline": reception["treatment"].get("logline"),
                    "unknowns": reception["fidelity"].get("unknowns") or [],
                    "mature_intimacy": reception["treatment"].get("mature_intimacy") or {},
                },
            }
        )
        return 0
    if action in {"edit", "lock", "unlock", "replan"}:
        from cli_plan_mutation import PlanMutationError, run

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError(f"plan {action} requires --root")
        try:
            report, code = run(args, Path(root_s).expanduser().resolve())
        except PlanMutationError as exc:
            raise FilmError(f"{exc.code}: {exc}") from exc
        emit(report)
        return code
    if action == "run":
        from cli_plan_run import PlanRunError, run

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan run requires --root")
        try:
            report, code = run(args, Path(root_s).expanduser().resolve())
        except PlanRunError as exc:
            raise FilmError(str(exc)) from exc
        emit(report)
        return code
    if action == "project":
        from cli_plan_project import run

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan project requires --root")
        report, code = run(args, Path(root_s).expanduser().resolve())
        emit(report)
        return code
    if action in {"validate", "status"}:
        from cli_plan import status as status_plan_cli
        from cli_plan import validate as validate_plan_cli

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError(f"plan {action} requires --root")
        runner = validate_plan_cli if action == "validate" else status_plan_cli
        report, code = (
            runner(args, Path(root_s).expanduser().resolve())
            if action == "validate"
            else runner(Path(root_s).expanduser().resolve())
        )
        emit(report)
        return code
    if action == "validate-structure":
        from story_structure import validate_story_structure_at_root

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan validate-structure requires --root")
        report = validate_story_structure_at_root(
            Path(root_s).expanduser().resolve(),
            strict=bool(getattr(args, "strict", False)),
            write_receipt=True,
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "shot-cards":
        from shot_card import export_shot_cards

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan shot-cards requires --root")
        report = export_shot_cards(
            Path(root_s).expanduser().resolve(),
            write_files=not bool(getattr(args, "no_write", False)),
            strict_purpose=bool(getattr(args, "strict_purpose", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "coverage-check":
        from coverage_check import coverage_check_at_root

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan coverage-check requires --root")
        report = coverage_check_at_root(
            Path(root_s).expanduser().resolve(),
            strict=bool(getattr(args, "strict", False)),
            write_receipt=not bool(getattr(args, "no_write", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "storyboard":
        from storyboard_status import (
            check_storyboard_gate,
            load_storyboard_receipt,
            set_storyboard_status,
        )

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan storyboard requires --root")
        root_p = Path(root_s).expanduser().resolve()
        sb_action = str(getattr(args, "action", "status") or "status")
        if sb_action == "set":
            st = getattr(args, "status", None)
            if not st:
                raise FilmError("plan storyboard set requires --status")
            report = set_storyboard_status(
                root_p,
                status=str(st),
                user_phrase=str(getattr(args, "user_phrase", None) or ""),
                notes=str(getattr(args, "notes", None) or ""),
            )
        elif sb_action == "gate":
            report = check_storyboard_gate(
                root_p,
                strict=bool(getattr(args, "strict", False)),
            )
        else:
            rec = load_storyboard_receipt(root_p)
            report = {
                "ok": bool(rec),
                "kind": "storyboard-status",
                "status": (rec or {}).get("status"),
                "receipt": rec or None,
                "root": str(root_p),
            }
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "continuity-audit":
        from continuity_audit import continuity_audit_at_root

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan continuity-audit requires --root")
        report = continuity_audit_at_root(
            Path(root_s).expanduser().resolve(),
            strict=bool(getattr(args, "strict", False)),
            write_receipt=not bool(getattr(args, "no_write", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "scene-drama":
        from scene_drama import scene_drama_at_root

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan scene-drama requires --root")
        strict_flag = bool(getattr(args, "strict", False))
        report = scene_drama_at_root(
            Path(root_s).expanduser().resolve(),
            strict=True if strict_flag else None,
            write_receipt=not bool(getattr(args, "no_write", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "debrief":
        from cli_plan import run_debrief

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan debrief requires --root")
        report, code = run_debrief(args, Path(root_s).expanduser().resolve())
        emit(report)
        return code
    if action == "normalize":
        from cli_plan_normalize import PlanNormalizeError, run

        root_s = getattr(args, "root", None)
        try:
            report, code = run(
                args,
                Path(root_s).expanduser().resolve() if root_s else None,
            )
        except PlanNormalizeError as exc:
            raise FilmError(str(exc)) from exc
        emit(report)
        return code

    raise FilmError(f"unknown plan action {action!r}")


def cmd_workshop(args: argparse.Namespace) -> int:
    """Creative workshop contracts stay local and never invoke a provider."""
    from cli_workshop import WorkshopError, run_workshop
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    try:
        report, code = run_workshop(args)
    except WorkshopError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_review_ui(args: argparse.Namespace) -> int:
    """Run the loopback-only review console without duplicating approval state."""
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from review_ui import ReviewUIError, run_review_ui

    try:
        report, code = run_review_ui(args)
    except (OSError, ValueError, ReviewUIError) as exc:
        raise FilmError(str(exc)) from exc
    if args.review_ui_action != "serve":
        emit(report)
    return code


def cmd_interactive(args: argparse.Namespace) -> int:
    from cli_interactive import run_interactive
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    report, code = run_interactive(args)
    emit(report)
    return code


def cmd_comfy(args: argparse.Namespace) -> int:
    from cli_comfy import run_comfy
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return run_comfy(args)


def cmd_h3(args: argparse.Namespace) -> int:
    """MiniMax H3 local motion lane (plan / run / list)."""
    from cli_h3 import run_h3
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    report = run_h3(args)
    emit(report)
    return 0 if report.get("ok") is not False else 1


def cmd_still_challenge(args: argparse.Namespace) -> int:
    """FRW i2i still-material challenge (≥30s/unit) for better I2V/R2V sources."""
    from cli_still_challenge import run_still_challenge_cli
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    report = run_still_challenge_cli(args)
    emit(report)
    return 0 if report.get("ok") is not False else 1


def cmd_upscale(args: argparse.Namespace) -> int:
    """Real-ESRGAN formal upscale (selects-after; no auto-promote)."""
    from cli_upscale import run_upscale_cli
    from core.emit import emit

    report = run_upscale_cli(args)
    emit(report)
    return 0 if report.get("ok") is not False else 1


def cmd_workflow(args: argparse.Namespace) -> int:
    """Wave A–C throughput: closeout / pilot-pack / bulk-preflight / lease / tunnel."""
    from cli_workflow import run_workflow_cmd
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return run_workflow_cmd(args)


def cmd_node(args: argparse.Namespace) -> int:
    from cli_node import run_node
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return run_node(args, emit=emit)


def cmd_weapon(args: argparse.Namespace) -> int:
    from cli_weapon import run_weapon
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return run_weapon(args, emit=emit)


def cmd_route(args: argparse.Namespace) -> int:
    from cli_route import run
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from production_router import RouteExplainError

    try:
        report, code = run(args)
    except RouteExplainError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_team(args: argparse.Namespace) -> int:
    from cli_team import run
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
    from production_team import ProductionTeamError

    try:
        report, code = run(args)
    except ProductionTeamError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_metrics(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return _run_optimization_cli(args, "metrics")


def cmd_experiment(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return _run_optimization_cli(args, "experiment")


def cmd_gold(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return _run_optimization_cli(args, "gold")


def cmd_dashboard(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return _run_optimization_cli(args, "dashboard")


def cmd_optimization_program(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return _run_optimization_cli(args, "optimization-program")


def cmd_quality_ledger(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return _run_quality_reporting_cli(args, "quality-ledger")


def cmd_production_report(args: argparse.Namespace) -> int:
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    return _run_quality_reporting_cli(args, "production-report")

