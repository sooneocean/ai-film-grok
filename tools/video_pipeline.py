#!/usr/bin/env python3
"""Unified operator entry point for the VIDEO pipeline lane.

Wraps the individual video tools behind one discoverable CLI (mirror of
tools/pipeline.py for the bgm lane) so operators don't have to remember the
video script names / argument orders (see RUNBOOK-video.md). Every subcommand
just delegates to the existing, already-tested video tools via subprocess, so
behavior is unchanged — only the interface is consolidated.

    python3 tools/video_pipeline.py check            # route check + reconcile audit
    python3 tools/video_pipeline.py coverage         # supply/demand report
    python3 tools/video_pipeline.py submit           # route open video generate gaps
    python3 tools/video_pipeline.py poll             # poll jobs, auto-approve+fill
    python3 tools/video_pipeline.py run-h3           # print the 5090 H3 commands to run
    python3 tools/video_pipeline.py reconcile        # --fix safe repairs
    python3 tools/video_pipeline.py one-shot         # reconcile -> submit -> run-h3
                                                      #   -> poll -> doctor
    python3 tools/video_pipeline.py status --json    # machine-readable health blob

one-shot with --demo uses the MockVideoBackend end-to-end (no external service)
so you can verify the whole chain before pointing it at a real 5090 / API.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _run(script, extra, cwd=ROOT):
    cmd = [sys.executable, os.path.join(HERE, script)] + list(extra)
    print(f"\n$ video-pipeline -> {script} {' '.join(extra)}")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r


def cmd_check(args):
    _run("video_route.py", ["check"])
    _run("reconcile_video.py", [])
    return 0


def cmd_submit(args):
    return _run("generate_loop_video.py", ["--submit"]).returncode


def cmd_poll(args):
    return _run("generate_loop_video.py", ["--poll", "--auto-approve"]).returncode


def cmd_run_h3(args):
    """Print the H3 (5090) commands to run for every pending video ticket.

    The scripted-reflux model: submit() wrote a ticket under
    video-library/.gen-tickets recording the exact H3 command; the operator runs
    it on the 5090; once the .mp4 lands in video-library/pending, poll() ingests
    it. This command just surfaces those tickets (and warns on REPLACE_ME
    placeholders).
    """
    import glob
    VTICKETS = os.path.join(ROOT, "video-library", ".gen-tickets")
    tickets = sorted(glob.glob(os.path.join(VTICKETS, "*.json")))
    pending = []
    for tp in tickets:
        try:
            t = json.load(open(tp, encoding="utf-8"))
        except Exception:
            continue
        if t.get("backend") != "h3":
            continue
        out = t.get("out")
        if out and os.path.exists(out):
            continue  # already produced; poll will pick it up
        pending.append(t)
    if not pending:
        print("no pending H3 (5090) tickets — nothing to run on the GPU")
        return 0
    print(f"== {len(pending)} H3 ticket(s) to run on the 5090 ==")
    for t in pending:
        cmdline = t.get("cmd", "")
        if "REPLACE_ME" in cmdline or cmdline.startswith("echo H3_PLACEHOLDER"):
            print(f"  [JOB {t.get('job_id')}] ⚠ placeholder cmd not configured — "
                  f"edit generators.json `h3.invocation.cmd` then re-submit.")
            print(f"     (current: {cmdline})")
        else:
            print(f"  [JOB {t.get('job_id')}] run on 5090:\n    {cmdline}")
    print("\nAfter the .mp4 lands in video-library/pending, run "
          "`video_pipeline.py poll` to ingest + auto-approve.")
    return 0


def cmd_reconcile(args):
    extra = ["--fix"] if args.fix else []
    return _run("reconcile_video.py", extra).returncode


def cmd_coverage(args):
    extra = ["--json"] if args.json else []
    if args.emit_generate:
        extra.append("--emit-generate")
    if args.apply:
        extra.append("--apply")
    extra += ["--target-min", str(args.target_min), "--max", str(args.max)]
    return _run("coverage_video.py", extra).returncode


def cmd_assemble(args):
    """Composite approved video + matched BGM (+ optional TTS) into a film."""
    extra = ["--auto", "--segments", str(args.segments), "--out", args.out]
    if args.film_id:
        extra += ["--film-id", args.film_id]
    if args.dry_run:
        extra.append("--dry-run")
    return _run("assemble.py", extra).returncode


def cmd_one_shot(args):
    print("== one-shot video pipeline run ==")
    # 1. safe repairs (only writes when --apply)
    _run("reconcile_video.py", ["--fix"] if args.apply else [])
    # 2+4. route + generate. demo => MockVideoBackend end-to-end in one pass.
    if args.demo:
        _run("generate_loop_video.py", ["--demo", "--auto-approve"])
    else:
        _run("generate_loop_video.py", ["--submit"])
        _run("video_pipeline.py", ["run-h3"])  # operator runs the 5090 step
        _run("generate_loop_video.py", ["--poll", "--auto-approve"])
    # 5. final health
    _run("video_route.py", ["check"])
    _run("reconcile_video.py", [])
    print("\n== one-shot complete ==")
    return 0


def cmd_status(args):
    from coverage_video import analyze as cov_analyze
    import video_pipeline_lib
    cat = video_pipeline_lib.load_vcatalog()
    gaps = video_pipeline_lib.load_vgaps()
    jobs = video_pipeline_lib.load_vjobs()
    analysis = cov_analyze(cat, gaps)
    by_status = {}
    for g in gaps:
        by_status[g.get("status")] = by_status.get(g.get("status"), 0) + 1
    jb = {}
    for j in jobs:
        k = f"{j.get('backend')}:{j.get('status')}"
        jb[k] = jb.get(k, 0) + 1
    blob = {
        "catalog_revision": cat.get("revision"),
        "assets": len(cat.get("assets", {})),
        "gaps_by_status": by_status,
        "coverage": {
            "target_min": analysis["target_min"],
            "starved": sum(1 for r in analysis["rows"] if r["status"] == "STARVED"),
            "thin": sum(1 for r in analysis["rows"] if r["status"] == "THIN"),
        },
        "jobs": jb,
    }
    print(json.dumps(blob, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="video_pipeline.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("check")
    sub.add_parser("doctor")
    sub.add_parser("submit")
    sub.add_parser("poll")
    sub.add_parser("run-h3")
    p_rec = sub.add_parser("reconcile"); p_rec.add_argument("--fix", action="store_true")
    p_cov = sub.add_parser("coverage")
    p_cov.add_argument("--json", action="store_true")
    p_cov.add_argument("--emit-generate", action="store_true")
    p_cov.add_argument("--apply", action="store_true")
    p_cov.add_argument("--target-min", type=int, default=4)
    p_cov.add_argument("--max", type=int, default=30)
    p_os = sub.add_parser("one-shot")
    p_os.add_argument("--apply", action="store_true")
    p_os.add_argument("--demo", action="store_true")
    p_st = sub.add_parser("status"); p_st.add_argument("--json", action="store_true")
    p_as = sub.add_parser("assemble")
    p_as.add_argument("--segments", type=int, default=3)
    p_as.add_argument("--film-id", default="film-auto")
    p_as.add_argument("--out", default=os.path.join(ROOT, "films", "demo.mp4"))
    p_as.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help(); sys.exit(2)
    handlers = {
        "check": cmd_check, "doctor": cmd_check, "submit": cmd_submit,
        "poll": cmd_poll, "run-h3": cmd_run_h3, "reconcile": cmd_reconcile,
        "coverage": cmd_coverage, "one-shot": cmd_one_shot, "status": cmd_status,
        "assemble": cmd_assemble,
    }
    rc = handlers[args.cmd](args)
    sys.exit(rc if rc is not None else 0)


if __name__ == "__main__":
    main()
