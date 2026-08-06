#!/usr/bin/env python3
"""Fill a video gap from the queue, closing the production loop.

Mirrors tools/fill_gap.py for the video lane: marks the gap filled, records the
resolved asset, and maintains use_count/last_used_at/last_used_film_id.

    python3 tools/fill_gap_video.py --gap-id <gap_id> [--asset-id <asset_id>]
    python3 tools/fill_gap_video.py --film-id "第4章..." --shot-id ep01_sc01_bt02_sh01
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_pipeline_lib import (load_vcatalog, save_vcatalog, load_vgaps,
                                save_vgaps, VIDEO_LIB)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap-id")
    ap.add_argument("--film-id")
    ap.add_argument("--shot-id")
    ap.add_argument("--asset-id", help="override the suggested asset")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gaps = load_vgaps()
    gap = None
    for g in gaps:
        if args.gap_id and g.get("gap_id") == args.gap_id:
            gap = g; break
        if args.film_id and args.shot_id and g.get("film_id") == args.film_id and g.get("shot_id") == args.shot_id:
            gap = g; break
    if not gap:
        print("ERROR: gap not found", file=sys.stderr); sys.exit(2)

    cat = load_vcatalog()
    A = cat["assets"]
    asset_id = args.asset_id or gap.get("suggested_asset_id")
    if not asset_id or asset_id not in A:
        print(f"ERROR: no usable asset (suggested={gap.get('suggested_asset_id')}, "
              f"override={args.asset_id})", file=sys.stderr)
        sys.exit(2)
    if A[asset_id].get("status") != "approved":
        print(f"ERROR: asset {asset_id} is not approved", file=sys.stderr); sys.exit(2)

    now = datetime.now(timezone.utc).isoformat()
    print(f"gap {gap['gap_id'][:12]}…  ->  asset {asset_id}")
    print(f"  film={gap.get('film_id')} shot={gap.get('shot_id')} mood={gap.get('mood')} mode={gap.get('mode')}")
    if args.dry_run:
        print("  (dry-run, no changes written)"); return

    shutil.copy(os.path.join(VIDEO_LIB, "catalog.json"), os.path.join(VIDEO_LIB, "catalog.json.bak"))
    shutil.copy(os.path.join(VIDEO_LIB, "gap-queue.jsonl"), os.path.join(VIDEO_LIB, "gap-queue.jsonl.bak"))

    gap["status"] = "filled"
    gap["resolved_asset_id"] = asset_id
    gap["resolved_at"] = now
    gap["action"] = "fill"

    a = A[asset_id]
    a["use_count"] = a.get("use_count", 0) + 1
    a["last_used_at"] = now
    a["last_used_film_id"] = gap.get("film_id")

    save_vgaps(gaps)
    save_vcatalog(cat)
    print(f"  use_count({asset_id}) -> {a['use_count']}; revision -> {cat['revision']}")


if __name__ == "__main__":
    main()
