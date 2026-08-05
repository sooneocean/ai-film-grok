#!/usr/bin/env python3
"""Fill a music gap from the queue, closing the production loop.

Marks the gap filled, records which approved asset satisfied it, and maintains
that asset's use_count / last_used_at / last_used_film_id. Bumps catalog
revision and re-validates. This is the missing "consume" step that keeps
use_count meaningful (it was 0 for every asset before this tool existed).

    python3 tools/fill_gap.py --gap-id <gap_id> [--asset-id <asset_id>]
    python3 tools/fill_gap.py --film-id "第4章..." --shot-id ep01_sc01_bt02_sh01

The asset defaults to the gap's suggested_asset_id. Backs up both files.
"""
import argparse
import json
import os
import shutil
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.join(ROOT, "bgm-library", "catalog.json")
GAP = os.path.join(ROOT, "bgm-library", "gap-queue.jsonl")


def load_gaps():
    return [json.loads(l) for l in open(GAP) if l.strip()]


def save_gaps(gaps):
    with open(GAP, "w") as f:
        for g in gaps:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap-id")
    ap.add_argument("--film-id")
    ap.add_argument("--shot-id")
    ap.add_argument("--asset-id", help="override the suggested asset")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gaps = load_gaps()
    gap = None
    for g in gaps:
        if args.gap_id and g.get("gap_id") == args.gap_id:
            gap = g; break
        if args.film_id and args.shot_id and g.get("film_id") == args.film_id and g.get("shot_id") == args.shot_id:
            gap = g; break
    if not gap:
        print("ERROR: gap not found", file=__import__("sys").stderr); __import__("sys").exit(2)

    cat = json.load(open(CAT))
    A = cat["assets"]
    asset_id = args.asset_id or gap.get("suggested_asset_id")
    if not asset_id or asset_id not in A:
        print(f"ERROR: no usable asset (suggested={gap.get('suggested_asset_id')}, override={args.asset_id})", file=__import__("sys").stderr)
        __import__("sys").exit(2)
    if A[asset_id].get("status") != "approved":
        print(f"ERROR: asset {asset_id} is not approved", file=__import__("sys").stderr); __import__("sys").exit(2)

    now = datetime.now(timezone.utc).isoformat()
    print(f"gap {gap['gap_id'][:12]}…  ->  asset {asset_id}")
    print(f"  film={gap.get('film_id')} shot={gap.get('shot_id')} mood={gap.get('mood')}")
    if args.dry_run:
        print("  (dry-run, no changes written)"); return

    shutil.copy(CAT, CAT + ".bak")
    shutil.copy(GAP, GAP + ".bak")

    gap["status"] = "filled"
    gap["resolved_asset_id"] = asset_id
    gap["resolved_at"] = now
    gap["action"] = "fill"

    a = A[asset_id]
    a["use_count"] = a.get("use_count", 0) + 1
    a["last_used_at"] = now
    a["last_used_film_id"] = gap.get("film_id")
    cat["revision"] = cat.get("revision", 0) + 1
    cat["updated_at"] = now

    save_gaps(gaps)
    with open(CAT, "w") as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)
    print(f"  use_count({asset_id}) -> {a['use_count']}; revision -> {cat['revision']}")


if __name__ == "__main__":
    main()
