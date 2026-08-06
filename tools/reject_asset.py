#!/usr/bin/env python3
"""Reject a pending_human_review asset: route it out of the pipeline.

Terminal transition pending_human_review -> rejected. The media file is
moved to rejected/ so pending/ stays clean and the review queue cannot
re-show it. Re-runnable: a rejected asset cannot be re-approved without an
explicit (future) restore step.

    python3 tools/reject_asset.py --asset-id rnb-21004-5e683c78b7 \\
        --reviewer dex --reason "too muddy in dialogue band"
    python3 tools/reject_asset.py --asset-id ... --dry-run
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import (load_catalog, save_catalog, LIB, now_iso,
                          can_transition)

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset-id", required=True)
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--reason", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cat = load_catalog()
    A = cat["assets"]
    if args.asset_id not in A:
        print(f"ERROR: asset {args.asset_id} not in catalog", file=sys.stderr)
        sys.exit(2)
    a = A[args.asset_id]
    old = a.get("status")
    if old != "pending_human_review":
        print(f"ERROR: asset status is {old!r}, cannot reject (need pending_human_review)",
              file=sys.stderr)
        sys.exit(2)
    if not can_transition("asset", old, "rejected"):
        print(f"ERROR: illegal transition {old} -> rejected", file=sys.stderr)
        sys.exit(2)

    src = os.path.join(LIB, a["path"])
    ext = src.rsplit(".", 1)[-1] if os.path.exists(src) else "wav"
    dst = os.path.join(LIB, f"rejected/{args.asset_id}.{ext}")
    print(f"reject {args.asset_id}: {a['path']} -> rejected/")
    if args.dry_run:
        print("  (dry-run, no changes written)")
        return

    if os.path.exists(src):
        os.makedirs(os.path.join(LIB, "rejected"), exist_ok=True)
        shutil.move(src, dst)

    a["status"] = "rejected"
    a["rejected_at"] = now_iso()
    a["rejected_by"] = args.reviewer
    a["reject_reason"] = args.reason
    cat["revision"] = cat.get("revision", 0) + 1
    cat["updated_at"] = now_iso()
    save_catalog(cat)

    ok = subprocess.run([sys.executable, os.path.join(HERE, "validate_catalog.py"),
                         "--no-sha"], capture_output=True, text=True)
    if ok.returncode != 0:
        print("ERROR: catalog validation failed after reject; restoring backup",
              file=sys.stderr)
        shutil.copy(os.path.join(LIB, "catalog.json.bak"), os.path.join(LIB, "catalog.json"))
        sys.exit(1)
    print(f"  revision -> {cat['revision']}; validation OK ✓")


if __name__ == "__main__":
    main()
