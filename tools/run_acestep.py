#!/usr/bin/env python3
"""Operator trigger for the local ACE-Step (RTX 5090) backend.

generate_loop's submit only WRITES a job ticket — it deliberately never shells
out to a placeholder command (that would drop a garbage file in pending/).
This tool is the human step of the "scripted reflux" design: read the
acestep ticket(s) and actually run ACE-Step on the 5090, dropping the .wav
into bgm-library/pending/ where the loop's poll() finds it and ingests it.

    python3 tools/run_acestep.py --pending            # list + run all submitted
    python3 tools/run_acestep.py --job-id ace-xxxx    # run one ticket
    python3 tools/run_acestep.py --pending --dry-run  # only print the commands

After this, run `python3 tools/generate_loop.py --poll --auto-approve` to
ingest → QA-gate → approve → fill the gaps.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import LIB
from backends import _read_ticket

TICKETS = os.path.join(LIB, ".gen-tickets")


def _acestep_tickets():
    if not os.path.isdir(TICKETS):
        return []
    out = []
    for p in sorted(glob.glob(os.path.join(TICKETS, "*.json"))):
        try:
            t = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if t.get("backend") == "acestep":
            out.append(t)
    return out


def run(t, dry):
    job_id = t.get("job_id")
    cmd = t.get("cmd", "")
    if "REPLACE_ME" in cmd:
        print(f"  SKIP {job_id}: generators.json invocation.cmd is still a "
              f"placeholder — configure the real ACE-Step command first")
        return False
    print(f"  run {job_id}:\n    {cmd}")
    if dry:
        return True
    rc = subprocess.run(cmd, shell=True).returncode
    if rc != 0:
        print(f"  FAILED {job_id} (rc={rc})")
        return False
    out = t.get("out")
    if out and os.path.exists(out):
        print(f"  OK {job_id} -> {out}")
        return True
    print(f"  WARN {job_id}: command exited 0 but output not found at {out}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-id")
    ap.add_argument("--pending", action="store_true",
                    help="run all acestep tickets currently 'submitted'")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.job_id:
        t = _read_ticket(args.job_id)
        if not t or t.get("backend") != "acestep":
            print(f"no acestep ticket for {args.job_id}", file=sys.stderr)
            sys.exit(2)
        ok = run(t, args.dry_run)
        sys.exit(0 if ok else 1)

    if args.pending:
        ts = [t for t in _acestep_tickets() if t.get("status") == "submitted"]
        if not ts:
            print("no submitted acestep tickets")
            return
        print(f"{len(ts)} acestep ticket(s) to run:")
        any_fail = False
        for t in ts:
            if not run(t, args.dry_run):
                any_fail = True
        sys.exit(1 if any_fail else 0)

    print("pass --job-id <id> or --pending", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
