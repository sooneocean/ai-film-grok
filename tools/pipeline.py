#!/usr/bin/env python3
"""Unified operator entry point for the bgm pipeline.

Wraps the individual tools behind one discoverable CLI so operators don't have
to remember 20 script names / argument orders (see RUNBOOK.md). Every
subcommand just delegates to the existing, already-tested tools via
subprocess, so behavior is unchanged — only the interface is consolidated.

    python3 tools/pipeline.py check            # route check + reconcile audit
    python3 tools/pipeline.py coverage         # supply/demand report
    python3 tools/pipeline.py submit           # route open generate gaps (+tts)
    python3 tools/pipeline.py poll             # poll jobs, auto-approve+fill
    python3 tools/pipeline.py run-acestep      # trigger 5090 ACE-Step tickets
    python3 tools/pipeline.py fill-open        # close open fill gaps (--apply)
    python3 tools/pipeline.py reconcile        # --fix safe repairs
    python3 tools/pipeline.py one-shot         # fill-open -> reconcile -> submit
                                              #   -> run-acestep -> poll -> doctor
    python3 tools/pipeline.py status --json    # machine-readable health blob

one-shot with --demo uses the MockBackend end-to-end (no external service) so
you can verify the whole chain before pointing it at a real 5090 / API.
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
    print(f"\n$ pipeline -> {script} {' '.join(extra)}")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    return r


def cmd_check(args):
    _run("route.py", ["check"])
    _run("reconcile.py", [])
    return 0


def cmd_submit(args):
    return _run("generate_loop.py", ["--submit"]).returncode


def cmd_poll(args):
    return _run("generate_loop.py", ["--poll", "--auto-approve"]).returncode


def cmd_run_acestep(args):
    return _run("run_acestep.py", ["--pending"]).returncode


def cmd_fill_open(args):
    extra = ["--apply"] if args.apply else []
    return _run("fill_open_gaps.py", extra).returncode


def cmd_reconcile(args):
    extra = ["--fix"] if args.fix else []
    return _run("reconcile.py", extra).returncode


def cmd_coverage(args):
    extra = ["--json"] if args.json else []
    if args.emit_generate:
        extra.append("--emit-generate")
    if args.apply:
        extra.append("--apply")
    extra += ["--target-min", str(args.target_min), "--max", str(args.max)]
    return _run("coverage.py", extra).returncode


def cmd_one_shot(args):
    print("== one-shot pipeline run ==")
    # 1. close open fill gaps whose candidate is already approved
    _run("fill_open_gaps.py", ["--apply"] if args.apply else [])
    # 2. safe repairs (duration backfill etc.) — only writes when --apply
    _run("reconcile.py", ["--fix"] if args.apply else [])
    # 3+5. route + generate. demo => MockBackend end-to-end in one pass.
    if args.demo:
        _run("generate_loop.py", ["--demo", "--auto-approve"])
    else:
        _run("generate_loop.py", ["--submit"])
        _run("run_acestep.py", ["--pending"])  # no-op if cmd is REPLACE_ME
        _run("generate_loop.py", ["--poll", "--auto-approve"])
    # 6. final health
    _run("route.py", ["check"])
    _run("reconcile.py", [])
    print("\n== one-shot complete ==")
    return 0


def cmd_status(args):
    from coverage import analyze as cov_analyze
    import pipeline_lib
    cat = pipeline_lib.load_catalog()
    gaps = pipeline_lib.load_gaps()
    jobs = pipeline_lib.load_jobs()
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
    ap = argparse.ArgumentParser(prog="pipeline.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("check")
    sub.add_parser("doctor")
    sub.add_parser("submit")
    sub.add_parser("poll")
    sub.add_parser("run-acestep")
    p_fo = sub.add_parser("fill-open"); p_fo.add_argument("--apply", action="store_true")
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

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help(); sys.exit(2)
    handlers = {
        "check": cmd_check, "doctor": cmd_check, "submit": cmd_submit,
        "poll": cmd_poll, "run-acestep": cmd_run_acestep,
        "fill-open": cmd_fill_open, "reconcile": cmd_reconcile,
        "coverage": cmd_coverage, "one-shot": cmd_one_shot, "status": cmd_status,
    }
    rc = handlers[args.cmd](args)
    sys.exit(rc if rc is not None else 0)


if __name__ == "__main__":
    main()
