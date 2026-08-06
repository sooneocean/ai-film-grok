#!/usr/bin/env python3
"""Batch-close open `fill` gaps whose candidate is already approved.

The generate loop routes `generate` gaps and the per-gap `fill_gap.py`
closes one gap at a time, but the open `fill` gaps in gap-queue.jsonl
(each carrying a `suggested_asset_id`) have no automated path — a human
must run `fill_gap.py --gap-id ...` for every one. This tool closes that
open loop in one pass:

  - scans gaps where action==fill and status==open
  - for each, requires suggested_asset_id to point at an APPROVED asset
  - closes it by delegating to fill_gap.py (which bumps revision, writes
    backups via pipeline_lib, and maintains use_count / last_used_*)

Default is --dry-run (no writes). Pass --apply to actually mutate the
catalog + gap-queue. Safe to re-run: already-filled gaps are skipped, and
each close is independent (a failure on one does not roll back the others).

    python3 tools/fill_open_gaps.py            # dry-run, show the backlog
    python3 tools/fill_open_gaps.py --apply    # close every eligible gap
    python3 tools/fill_open_gaps.py --apply --limit 5  # close first 5 only
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAT = os.path.join(ROOT, "bgm-library", "catalog.json")
GAP = os.path.join(ROOT, "bgm-library", "gap-queue.jsonl")


def load_gaps():
    return [json.loads(l) for l in open(GAP, encoding="utf-8") if l.strip()]


def eligible(gaps, cat):
    """Split open `fill` gaps into closeable (approved candidate) and dead-end.

    Args:
        gaps: list of gap dicts (from gap-queue.jsonl)
        cat:  catalog dict with an "assets" mapping

    Returns:
        (closeable, dead_end) two lists of gap dicts.

    A gap is closeable only when action==fill, status==open, and its
    suggested_asset_id references an asset whose status is "approved".
    Anything else (missing id, asset absent, not approved) is a dead-end
    that needs generation rather than a fill.
    """
    assets = cat.get("assets", {})
    closeable, dead = [], []
    for g in gaps:
        if g.get("action") != "fill" or g.get("status") != "open":
            continue
        sid = g.get("suggested_asset_id")
        a = assets.get(sid) if sid else None
        if a and a.get("status") == "approved":
            closeable.append(g)
        else:
            dead.append(g)
    return closeable, dead


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually close eligible gaps (default: dry-run)")
    ap.add_argument("--limit", type=int, default=0,
                    help="max gaps to close this run (0 = all)")
    args = ap.parse_args()

    cat = json.load(open(CAT, encoding="utf-8"))
    gaps = load_gaps()
    open_fill = [g for g in gaps if g.get("action") == "fill" and g.get("status") == "open"]
    closeable, dead = eligible(gaps, cat)

    print(f"open fill gaps: {len(open_fill)}")
    print(f"  closeable (approved candidate): {len(closeable)}")
    print(f"  dead-end (no approved candidate): {len(dead)}")

    if not args.apply:
        print("  (dry-run) pass --apply to close the closeable set")
        for g in closeable[:50]:
            print(f"    would fill {g['gap_id'][:12]}… -> {g.get('suggested_asset_id')}")
        if len(closeable) > 50:
            print(f"    …and {len(closeable) - 50} more")
        for g in dead[:20]:
            print(f"    dead-end  {g['gap_id'][:12]}… -> {g.get('suggested_asset_id')} "
                  f"(asset not approved/missing)")
        return

    if not closeable:
        print("  nothing to close")
        return

    n = 0
    for g in closeable:
        if args.limit and n >= args.limit:
            print(f"  reached --limit {args.limit}; stopping")
            break
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "fill_gap.py"),
             "--gap-id", g["gap_id"]],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAILED {g['gap_id'][:12]}…:\n", r.stdout, r.stderr)
            continue
        n += 1
        print(f"  closed {g['gap_id'][:12]}… -> {g.get('suggested_asset_id')}")
    print(f"  closed {n} gap(s); each close bumped the catalog revision via fill_gap.py")


if __name__ == "__main__":
    main()
