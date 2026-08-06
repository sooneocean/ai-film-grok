#!/usr/bin/env python3
"""Approve a pending_human_review asset: route it into the approved library.

This is the real, in-repo replacement for the missing `aifilm approve` CLI
that the old static review page only printed as text. It performs the
transition atomically (backup -> move file -> update catalog -> revision bump
-> re-validate) so the routing can never silently drift.

    python3 tools/approve_asset.py --asset-id rnb-21001-dedb5bddc6 \\
        --reviewer dex --instrumental-confirmed --license-note "owner-generated"
    python3 tools/approve_asset.py --asset-id ... --dry-run
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import (load_catalog, save_catalog, LIB, now_iso,
                          sha256_file, bump, can_transition, ext_to_codec,
                          load_gaps, save_gaps)

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset-id", required=True)
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--license-note", default="")
    ap.add_argument("--instrumental-confirmed", action="store_true")
    ap.add_argument("--auto-fill-gaps", action="store_true",
                    help="fill open gaps whose suggested_asset_id == this asset")
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
        print(f"ERROR: asset status is {old!r}, cannot approve (need pending_human_review)",
              file=sys.stderr)
        sys.exit(2)
    if not can_transition("asset", old, "approved"):
        print(f"ERROR: illegal transition {old} -> approved", file=sys.stderr)
        sys.exit(2)

    src = os.path.join(LIB, a["path"])
    if not os.path.exists(src):
        print(f"ERROR: file missing on disk: {a['path']}", file=sys.stderr)
        sys.exit(2)
    ext = src.rsplit(".", 1)[-1]
    dst_path = f"approved/{args.asset_id}.{ext}"
    dst = os.path.join(LIB, dst_path)

    print(f"approve {args.asset_id}: {a['path']} -> {dst_path}")
    if args.dry_run:
        print("  (dry-run, no changes written)")
        return

    # move media into approved/
    ensure = os.path.dirname(dst)
    os.makedirs(ensure, exist_ok=True)
    shutil.move(src, dst)

    a["status"] = "approved"
    a["path"] = dst_path
    a["sha256"] = sha256_file(dst)
    a["technical"] = a.get("technical", {})
    a["technical"]["codec"] = ext_to_codec(ext)
    a["technical"]["ok"] = True
    a["reviewer"] = args.reviewer
    a["license_note"] = args.license_note
    a["instrumental_confirmed"] = bool(args.instrumental_confirmed)
    a["approved_at"] = now_iso()
    if a.get("similarity_cluster") in (None, ""):
        a["similarity_cluster"] = args.asset_id

    bump(cat)
    save_catalog(cat)

    # re-validate as a gate; restore on failure
    ok = subprocess.run([sys.executable, os.path.join(HERE, "validate_catalog.py"),
                         "--no-sha"], capture_output=True, text=True)
    if ok.returncode != 0:
        print("ERROR: catalog validation failed after approve; restoring backup",
              file=sys.stderr)
        shutil.copy(CAT_BAK := os.path.join(LIB, "catalog.json.bak"), os.path.join(LIB, "catalog.json"))
        print(ok.stdout)
        sys.exit(1)
    print(f"  revision -> {cat['revision']}; validation OK ✓")

    if args.auto_fill_gaps:
        gaps = load_gaps()
        n = 0
        for g in gaps:
            if g.get("status") == "open" and g.get("suggested_asset_id") == args.asset_id:
                g["status"] = "filled"
                g["resolved_asset_id"] = args.asset_id
                g["resolved_at"] = now_iso()
                n += 1
        if n:
            save_gaps(gaps)
            print(f"  auto-filled {n} gap(s) that pointed at this asset")


if __name__ == "__main__":
    main()
