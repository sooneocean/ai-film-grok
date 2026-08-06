"""CLI shell for Wave A–C throughput commands (closeout / pilot pack / preflight / lease)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from workflow_pack import (
    WorkflowPackError,
    bulk_preflight,
    gpu_lease_acquire,
    gpu_lease_heartbeat,
    gpu_lease_release,
    gpu_lease_status,
    queue_progress_honest,
    select_shortlist,
    ship_prep,
    tunnel_probe,
    variety_precheck,
)


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def add_workflow_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # closeout status|run lives on aifilm_grok (closeout.py) — do not re-register.
    # Preferred pilot GO: `aifilm pilot pack`. Keep hyphen alias for agents.
    pack = sub.add_parser(
        "pilot-pack",
        help="Alias of `pilot pack` — GO pack → receipts/pilot-go.json",
    )
    pack.add_argument("--root", required=True)
    pack.add_argument("--shots", default="", help="Comma shot ids (default auto-pick)")

    # bulk-preflight
    bp = sub.add_parser(
        "bulk-preflight",
        help="Single-door bulk readiness (pilot/heat/state/still/anatomy/tunnel/lease)",
    )
    bp.add_argument("--root", required=True)
    bp.add_argument("--no-tunnel", action="store_true")
    bp.add_argument("--tunnel-port", type=int, default=18188)
    bp.add_argument("--no-lease", action="store_true")

    # variety
    vp = sub.add_parser(
        "variety-precheck",
        help="Design-time anti-boring matrix (poses / face CU / adjacent motion)",
    )
    vp.add_argument("--root", required=True)

    # five-track (Wave δ)
    ft = sub.add_parser(
        "five-track",
        help="5-Track cinema mix plan/status (DX/FX/BG/MX/SUB · -16 LUFS)",
    )
    ft.add_argument("--root", required=True)
    ft.add_argument(
        "five_track_action",
        nargs="?",
        default="plan",
        choices=["plan", "status", "audit"],
        help="plan|status (default plan) or audit (fail-closed)",
    )
    ft.add_argument("--no-write", action="store_true")

    # select shortlist
    ss = sub.add_parser(
        "select-shortlist",
        help=(
            "Multi-take preferred shortlist by mean + composition anti-hijack "
            "(optional --promote into manifest)"
        ),
    )
    ss.add_argument("--root", required=True)
    ss.add_argument(
        "--promote",
        action="store_true",
        help="Write preferred take path+mean into manifest.clips (never deletes takes)",
    )
    ss.add_argument(
        "--no-measure",
        action="store_true",
        help="Do not auto-measure missing mean sidecars",
    )

    # composition anti-hijack (stand-alone score / promote)
    ah = sub.add_parser(
        "anti-hijack",
        help=(
            "Composition anti-hijack: reject sand top-down / male torso steal; "
            "score multi-seed takes → receipts/anti-hijack-score.json"
        ),
    )
    ah.add_argument("--root", required=True)
    ah.add_argument("--shots", default="", help="Comma shot ids (default: all with takes)")
    ah.add_argument(
        "--promote",
        action="store_true",
        help="Promote composition-OK preferred into manifest.clips (never hijack)",
    )
    ah.add_argument("--no-write", action="store_true")

    # gate-auto: machine verification ladder (no human pilot/PK/review)
    ga = sub.add_parser(
        "gate-auto",
        help=(
            "Auto machine gates: measure means, write i2v-final, inject sex_sfx, "
            "five-track, true-video, variety, cinematic-gate "
            "(does NOT replace pilot / multi-take PK / review-final)"
        ),
    )
    ga.add_argument("--root", required=True)
    ga.add_argument("--no-write", action="store_true")
    ga.add_argument("--no-sex-sfx", action="store_true", help="Skip auto sex_sfx inject")
    ga.add_argument("--no-promote-single", action="store_true")
    ga.add_argument("--no-variety", action="store_true")
    ga.add_argument("--no-cinematic", action="store_true")
    ga.add_argument(
        "--force",
        action="store_true",
        help="Re-measure even when machine receipts already green (skip fast_path)",
    )

    # cinematic-gate composite (Wave ε)
    cg = sub.add_parser(
        "cinematic-gate",
        help=(
            "Composite cinema gate: true-video + inventory + i2v-final + variety "
            "+ five-track + edit-rhythm → receipts/cinematic-gate.json"
        ),
    )
    cg.add_argument("--root", required=True)
    cg.add_argument(
        "--ship-prep",
        action="store_true",
        help="Run ship-prep ladder first",
    )
    cg.add_argument("--skip-variety", action="store_true")
    cg.add_argument("--skip-five-track", action="store_true")
    cg.add_argument("--no-write", action="store_true")

    # ship-prep one-shot
    sp = sub.add_parser(
        "ship-prep",
        help=(
            "Pre-delivery ladder: means → variety → shortlist → pk(advisory) "
            "→ motion-gate → film_core"
        ),
    )
    sp.add_argument("--root", required=True)
    sp.add_argument("--no-measure", action="store_true", help="Skip ffmpeg mean scan")
    sp.add_argument(
        "--no-promote",
        action="store_true",
        help="Do not promote preferred takes into manifest.clips",
    )
    sp.add_argument(
        "--skip-variety",
        action="store_true",
        help="Skip variety hard door (or set AIFILM_SKIP_VARIETY_PREFLIGHT=1)",
    )
    sp.add_argument(
        "--skip-pk",
        action="store_true",
        help="Skip advisory pk-compare / fill-idle pending steps",
    )

    # gpu-lease
    gl = sub.add_parser("gpu-lease", help="5090 one-owner lease (global ~/.grok/run)")
    gl_sub = gl.add_subparsers(dest="lease_action", required=True)
    for action, help_text in (
        ("status", "Show lease free/owner"),
        ("acquire", "Acquire lease for this film root"),
        ("heartbeat", "Refresh heartbeat"),
        ("release", "Release if owned by this root"),
    ):
        p = gl_sub.add_parser(action, help=help_text)
        p.add_argument("--root", required=True)
        if action in {"acquire", "release"}:
            p.add_argument("--force", action="store_true")

    # tunnel-probe
    tp = sub.add_parser(
        "tunnel-probe",
        help="Probe localhost Comfy tunnel (18188→8188 system_stats)",
    )
    tp.add_argument("--port", type=int, default=18188)
    tp.add_argument("--timeout", type=float, default=3.0)

    # queue progress
    qp = sub.add_parser(
        "queue-progress",
        help="Honest progress: non-empty takes/clips file counts only",
    )
    qp.add_argument("--root", required=True)

    # P1 · agent assist for review-final (never auto-approves)
    ar = sub.add_parser(
        "agent-review-final",
        help="L0 assist draft for review-final scorecard (never auto-approves)",
    )
    ar.add_argument("--root", required=True)
    ar.add_argument("--reviewer", default="", help="Bind human reviewer into assist input JSON")
    ar.add_argument("--notes", default="", help="Notes stored in assist package")
    ar.add_argument(
        "--human-minutes",
        type=float,
        default=None,
        help="Screening minutes for review-file path (default from duration)",
    )
    ar.add_argument(
        "--no-assist-input",
        action="store_true",
        help="Only write agent-review-final.json (skip final-review-input.assist.json)",
    )
    ar.add_argument(
        "--apply",
        action="store_true",
        help="After L0 all-pass, run review-final with assist input (needs --reviewer + --user-phrase)",
    )
    ar.add_argument(
        "--user-phrase",
        default="",
        help='Verbatim user approval for --apply (e.g. "可以" / "做完"); never invent',
    )
    ar.add_argument(
        "--dry-run",
        action="store_true",
        help="With --apply: validate and write apply receipt without running review-final",
    )

    # Input fidelity (Wave F0–F3 · input→pixel correlation)
    fid = sub.add_parser(
        "fidelity",
        help="Input fidelity: status|check|apply (how plan still matches user source)",
    )
    fid_sub = fid.add_subparsers(dest="fidelity_action", required=True)
    for action, help_text in (
        ("status", "Recompute fidelity report (no force-write unless --write)"),
        ("check", "Write receipts/input-fidelity.json and exit 2 if not ok"),
        ("apply", "F1 stamp source_quote / must_keep / protected dialogue onto film-spec"),
    ):
        p = fid_sub.add_parser(action, help=help_text)
        p.add_argument("--root", required=True)
        p.add_argument(
            "--strict",
            action="store_true",
            help="Treat pollution/entity/protected/must_keep codes as blocking",
        )
        p.add_argument(
            "--soft",
            action="store_true",
            help="Force soft mode (never block on warning codes)",
        )
        if action == "status":
            p.add_argument(
                "--write",
                action="store_true",
                help="Also write receipts/input-fidelity.json",
            )
        if action == "check":
            p.add_argument(
                "--no-write",
                action="store_true",
                help="Do not write receipt (print only)",
            )
        if action == "apply":
            p.add_argument(
                "--force",
                action="store_true",
                help="Overwrite existing source_quote / spoken_text anchors",
            )

    dgo = sub.add_parser(
        "design-go",
        help="Design-phase GO pack: debrief + fidelity + variety (never signs pilot)",
    )
    dgo.add_argument("--root", required=True)


def run_workflow_cmd(args: argparse.Namespace) -> int:
    """Dispatch workflow-related top-level cmds. Returns process exit code."""
    cmd = str(getattr(args, "cmd", "") or "")
    try:
        if cmd == "fidelity":
            from input_fidelity import (
                InputFidelityError,
                apply_fidelity_to_spec,
                fidelity_check,
                fidelity_status,
            )

            action = str(getattr(args, "fidelity_action", "") or "")
            strict: bool | None = None
            if bool(getattr(args, "strict", False)):
                strict = True
            elif bool(getattr(args, "soft", False)):
                strict = False
            if action == "status":
                if bool(getattr(args, "write", False)):
                    report = fidelity_check(args.root, strict=strict, write=True)
                else:
                    report = fidelity_status(args.root)
                    if strict is not None:
                        report = fidelity_check(args.root, strict=strict, write=False)
                _emit(report)
                return 0 if report.get("ok") else 2
            if action == "check":
                report = fidelity_check(
                    args.root,
                    strict=strict,
                    write=not bool(getattr(args, "no_write", False)),
                )
                _emit(report)
                return 0 if report.get("ok") else 2
            if action == "apply":
                try:
                    report = apply_fidelity_to_spec(
                        args.root,
                        force=bool(getattr(args, "force", False)),
                    )
                except InputFidelityError as exc:
                    _emit({"ok": False, "error": str(exc)})
                    return 2
                _emit(report)
                return 0 if report.get("ok") is not False else 2
            _emit({"ok": False, "error": f"unknown fidelity action: {action}"})
            return 2

        if cmd == "design-go":
            from input_fidelity import design_go

            report = design_go(args.root, write=True)
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "pilot-pack":
            from pilot_pack import pilot_pack

            shots_raw = str(getattr(args, "shots", "") or "")
            shots = [s.strip() for s in shots_raw.split(",") if s.strip()] or None
            report = pilot_pack(args.root, shots=shots)
            _emit(report)
            return 0 if report.get("ok") or report.get("go_ready") else 2

        if cmd == "bulk-preflight":
            report = bulk_preflight(
                args.root,
                probe_tunnel=not bool(getattr(args, "no_tunnel", False)),
                tunnel_port=int(getattr(args, "tunnel_port", 18188) or 18188),
                check_lease=not bool(getattr(args, "no_lease", False)),
            )
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "variety-precheck":
            report = variety_precheck(args.root)
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "five-track":
            from five_track import FiveTrackError, audit_five_track, plan_five_track

            action = str(getattr(args, "five_track_action", None) or "plan").strip().lower()
            write = not bool(getattr(args, "no_write", False))
            if action == "audit":
                try:
                    report = audit_five_track(args.root, write=write)
                except FiveTrackError as exc:
                    _emit({"ok": False, "error": str(exc)})
                    return 2
            else:
                report = plan_five_track(args.root, write=write)
            _emit(report)
            return 0 if report.get("ok") or not report.get("enabled") else 2

        if cmd == "select-shortlist":
            report = select_shortlist(
                args.root,
                promote=bool(getattr(args, "promote", False)),
                measure_missing=not bool(getattr(args, "no_measure", False)),
            )
            _emit(report)
            return 0

        if cmd == "anti-hijack":
            from composition_anti_hijack import run_for_root

            shots_raw = str(getattr(args, "shots", "") or "")
            shots = [s.strip() for s in shots_raw.split(",") if s.strip()] or None
            report = run_for_root(
                args.root,
                shot_ids=shots,
                write=not bool(getattr(args, "no_write", False)),
                promote=bool(getattr(args, "promote", False)),
            )
            _emit(report)
            return 0 if report.get("ok") is not False else 2

        if cmd == "gate-auto":
            from gate_auto import run_gate_auto

            report = run_gate_auto(
                args.root,
                write=not bool(getattr(args, "no_write", False)),
                fix_sex_sfx=not bool(getattr(args, "no_sex_sfx", False)),
                promote_single=not bool(getattr(args, "no_promote_single", False)),
                run_variety=not bool(getattr(args, "no_variety", False)),
                run_cinematic=not bool(getattr(args, "no_cinematic", False)),
                force=bool(getattr(args, "force", False)),
            )
            _emit(report)
            # exit 0 when machine-verified; human_pending does not fail CI if hard ok
            return 0 if report.get("ok") else 2

        if cmd == "cinematic-gate":
            from cinematic_gate import run_cinematic_gate

            report = run_cinematic_gate(
                args.root,
                write=not bool(getattr(args, "no_write", False)),
                run_ship_prep=bool(getattr(args, "ship_prep", False)),
                skip_variety=bool(getattr(args, "skip_variety", False)),
                skip_five_track=bool(getattr(args, "skip_five_track", False)),
                auto_i2v=True,
            )
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "ship-prep":
            report = ship_prep(
                args.root,
                measure=not bool(getattr(args, "no_measure", False)),
                promote=not bool(getattr(args, "no_promote", False)),
                skip_variety=bool(getattr(args, "skip_variety", False)),
                skip_pk=bool(getattr(args, "skip_pk", False)),
            )
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "gpu-lease":
            action = str(getattr(args, "lease_action", "") or "")
            root = args.root
            force = bool(getattr(args, "force", False))
            if action == "status":
                report = gpu_lease_status(root)
            elif action == "acquire":
                report = gpu_lease_acquire(root, force=force)
            elif action == "heartbeat":
                report = gpu_lease_heartbeat(root)
            elif action == "release":
                report = gpu_lease_release(root, force=force)
            else:
                raise WorkflowPackError(f"unknown lease action: {action}")
            _emit(report)
            return 0 if report.get("ok") is not False else 2

        if cmd == "tunnel-probe":
            report = tunnel_probe(
                port=int(getattr(args, "port", 18188) or 18188),
                timeout=float(getattr(args, "timeout", 3.0) or 3.0),
            )
            _emit(report)
            return 0 if report.get("ok") else 2

        if cmd == "queue-progress":
            report = queue_progress_honest(args.root)
            _emit(report)
            return 0

        if cmd == "agent-review-final":
            from agent_review_final import (
                AgentReviewFinalError,
                apply_agent_review_final,
                build_agent_review_final,
            )

            try:
                if bool(getattr(args, "apply", False)):
                    report = apply_agent_review_final(
                        args.root,
                        reviewer=str(getattr(args, "reviewer", "") or ""),
                        user_phrase=str(getattr(args, "user_phrase", "") or ""),
                        notes=str(getattr(args, "notes", "") or "") or None,
                        human_minutes=getattr(args, "human_minutes", None),
                        dry_run=bool(getattr(args, "dry_run", False)),
                    )
                else:
                    report = build_agent_review_final(
                        args.root,
                        reviewer=str(getattr(args, "reviewer", "") or "") or None,
                        notes=str(getattr(args, "notes", "") or "") or None,
                        human_minutes=getattr(args, "human_minutes", None),
                        write=True,
                        write_assist_input=not bool(getattr(args, "no_assist_input", False)),
                    )
            except AgentReviewFinalError as exc:
                _emit({"ok": False, "error": str(exc), "auto_approved": False})
                return 2
            _emit(report)
            if bool(getattr(args, "apply", False)):
                return 0 if report.get("ok") else 2
            # draft-only: 0 = package written; final_complete still needs review-final
            return 0 if report.get("ok") else 2

    except WorkflowPackError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1

    print(f"unknown workflow cmd: {cmd}", file=sys.stderr)
    return 2


# Compatibility: allow `python cli_workflow.py` smoke (not the main entry)
if __name__ == "__main__":
    print("use: aifilm pilot-pack|bulk-preflight|variety-precheck|gpu-lease|…", file=sys.stderr)
    sys.exit(2)
