#!/usr/bin/env python3
"""State-machine contract + guardrail for the video pipeline.

Mirrors tools/route.py for the video lane. Validates the video catalog + gap
statuses against the shared routing contract (pipeline_lib ASSET/GAP states).

    python3 tools/video_route.py check
    python3 tools/video_route.py show
"""
import sys

from video_pipeline_lib import load_vcatalog, load_vgaps
from pipeline_lib import (ASSET_STATUSES, GAP_STATUSES, ASSET_TRANSITIONS,
                          GAP_TRANSITIONS)

ERR = []
WARN = []


def err(m):
    ERR.append(m)


def warn(m):
    WARN.append(m)


def check():
    cat = load_vcatalog()
    A = cat.get("assets", {})
    for aid, a in A.items():
        st = a.get("status")
        if st not in ASSET_STATUSES:
            err(f"[{aid}] asset status {st!r} not in {sorted(ASSET_STATUSES)}")
    gaps = load_vgaps()
    for g in gaps:
        st = g.get("status")
        if st not in GAP_STATUSES:
            err(f"[{g.get('gap_id', '?')[:12]}] gap status {st!r} not in {sorted(GAP_STATUSES)}")
        if st == "routed_generate" and not g.get("generation_job_id"):
            err(f"[{g.get('gap_id', '?')[:12]}] routed_generate but missing generation_job_id")
        if st == "filled" and not g.get("resolved_asset_id"):
            err(f"[{g.get('gap_id', '?')[:12]}] filled but missing resolved_asset_id")
        if g.get("action") == "generate" and "duration" not in g:
            warn(f"[{g.get('gap_id', '?')[:12]}] generate gap missing duration field")
    print(f"video route check: assets={len(A)} gaps={len(gaps)}")
    if ERR or WARN:
        print(f"  {'ERRORS' if ERR else 'WARNINGS'} ({len(ERR) + len(WARN)}):")
        for e in ERR:
            print("   - [ERR]", e)
        for w in WARN:
            print("   - [WARN]", w)
    if ERR:
        sys.exit(1)
    print("  OK: all video asset/gap statuses satisfy the routing contract ✓")


def show():
    print("asset state machine:")
    for s, to in ASSET_TRANSITIONS.items():
        print(f"  {s} -> {sorted(to) or '(terminal)'}")
    print("gap state machine:")
    for s, to in GAP_TRANSITIONS.items():
        print(f"  {s} -> {sorted(to) or '(terminal)'}")
    print("\nrun `python3 tools/video_route.py check` to validate on-disk state.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        check()
    elif cmd == "show":
        show()
    else:
        print("usage: video_route.py [check|show]")
        sys.exit(2)
