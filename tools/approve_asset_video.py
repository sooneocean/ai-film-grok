#!/usr/bin/env python3
"""Approve a pending_human_review video asset: route into the approved library.

Mirrors tools/approve_asset.py for the video lane (atomic: backup -> move file
-> update catalog -> revision bump -> re-validate).
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_pipeline_lib import (load_vcatalog, save_vcatalog, load_vgaps, save_vgaps,
                                VIDEO_LIB, now_iso, sha256_file, bump)

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset-id", required=True)
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--license-note", default="")
    ap.add_argument("--auto-fill-gaps", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cat = load_vcatalog()
    A = cat["assets"]
    if args.asset_id not in A:
        print(f"ERROR: asset {args.asset_id} not in catalog", file=sys.stderr); sys.exit(2)
    a = A[args.asset_id]
    old = a.get("status")
    if old != "pending_human_review":
        print(f"ERROR: asset status is {old!r}, cannot approve", file=sys.stderr); sys.exit(2)
    src = os.path.join(VIDEO_LIB, a["path"])
    if not os.path.exists(src):
        print(f"ERROR: file missing on disk: {a['path']}", file=sys.stderr); sys.exit(2)
    ext = src.rsplit(".", 1)[-1]
    dst_path = f"approved/{args.asset_id}.{ext}"
    dst = os.path.join(VIDEO_LIB, dst_path)

    print(f"approve {args.asset_id}: {a['path']} -> {dst_path}")
    if args.dry_run:
        print("  (dry-run, no changes written)"); return

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)

    a["status"] = "approved"
    a["path"] = dst_path
    a["sha256"] = sha256_file(dst)
    a["technical"] = a.get("technical", {})
    a["technical"]["codec"] = a["technical"].get("codec") or ext
    a["technical"]["ok"] = True
    a["reviewer"] = args.reviewer
    a["license_note"] = args.license_note
    a["approved_at"] = now_iso()

    bump(cat)
    save_vcatalog(cat)

    ok = subprocess.run([sys.executable, os.path.join(HERE, "validate_video_catalog.py"),
                         "--no-sha"], capture_output=True, text=True)
    if ok.returncode != 0:
        print("ERROR: video catalog validation failed; restoring backup", file=sys.stderr)
        shutil.copy(os.path.join(VIDEO_LIB, "catalog.json.bak"),
                    os.path.join(VIDEO_LIB, "catalog.json"))
        print(ok.stdout); sys.exit(1)
    print(f"  revision -> {cat['revision']}; validation OK ✓")

    if args.auto_fill_gaps:
        gaps = load_vgaps()
        n = 0
        for g in gaps:
            if g.get("status") == "open" and g.get("suggested_asset_id") == args.asset_id:
                g["status"] = "filled"
                g["resolved_asset_id"] = args.asset_id
                g["resolved_at"] = now_iso()
                n += 1
        if n:
            save_vgaps(gaps)
            print(f"  auto-filled {n} gap(s) that pointed at this asset")


if __name__ == "__main__":
    main()
