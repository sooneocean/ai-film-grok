#!/usr/bin/env python3
"""Observability for the bgm pipeline + orphan audit (read-only).

One command to see where the routing is congested: asset status mix, gap
lifecycle, per-backend job health, use_count distribution, similarity
clusters, TTS engine health, and a list of orphans that indicate drift.

    python3 tools/report.py            # summary + audit
    python3 tools/report.py --no-audit # skip the orphan scan
"""
import argparse
import json
import os
import collections
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import (load_catalog, load_gaps, load_jobs, LIB, load_generators)
from tts import gap_asset_kind

MANIFEST = os.path.join(LIB, "..", "tts-evaluations", "manifest.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-audit", action="store_true")
    args = ap.parse_args()

    cat = load_catalog()
    A = cat["assets"]
    gaps = load_gaps()
    jobs = load_jobs()
    gens = load_generators()

    print(f"catalog revision {cat['revision']} · assets {len(A)}")
    print("─ assets by status ─")
    for k, v in sorted(collections.Counter(a["status"] for a in A.values()).items()):
        print(f"  {k:22} {v}")

    print("─ gaps by status ─")
    gst = collections.Counter(g["status"] for g in gaps)
    for k, v in sorted(gst.items()):
        print(f"  {k:22} {v}")
    open_gen = [g for g in gaps if g["status"] == "open" and g.get("action") == "generate"]
    print(f"  open generate gaps (need a backend): {len(open_gen)}")
    tts_gaps = [g for g in gaps if gap_asset_kind(g) == "tts"]
    print(f"  tts gaps (separate voice pipeline): {len(tts_gaps)}")

    # open fill-gap backlog: how many can be auto-closed right now?
    open_fill = [g for g in gaps if g.get("action") == "fill" and g.get("status") == "open"]
    closeable = [g for g in open_fill
                 if g.get("suggested_asset_id") in A
                 and A[g["suggested_asset_id"]].get("status") == "approved"]
    dead = [g for g in open_fill if g not in closeable]
    print(f"  open fill gaps (have candidate): {len(open_fill)}")
    print(f"    closeable now (approved candidate): {len(closeable)}")
    print(f"    dead-end (need generation): {len(dead)}")
    gen_missing_dur = [g for g in gaps if g.get("action") == "generate" and "duration" not in g]
    print(f"  generate gaps missing duration: {len(gen_missing_dur)}")

    print("─ generation jobs by backend/status ─")
    jb = collections.Counter(j["backend"] for j in jobs)
    js = collections.Counter(j["status"] for j in jobs)
    for b, n in sorted(jb.items()):
        print(f"  backend {b:10} jobs={n}  status={dict(js)}")

    print("─ use_count distribution ─")
    uc = collections.Counter(a.get("use_count", 0) for a in A.values())
    used = sum(1 for a in A.values() if a.get("use_count", 0) > 0)
    print(f"  assets used at least once: {used}/{len(A)}")
    print(f"  zero-use: {uc.get(0,0)}")

    print("─ similarity clusters ─")
    cl = collections.Counter(a.get("similarity_cluster") for a in A.values())
    multi = [r for r, n in cl.items() if n > 1]
    print(f"  clusters={len(cl)}  near-dup groups={len(multi)}")

    print("─ backends (generators.json) ─")
    for bid, cfg in gens.get("backends", {}).items():
        print(f"  {bid:10} {cfg.get('status'):14} kind={cfg.get('kind')}")

    # TTS engine health (parallel pipeline, P5 candidate)
    mpath = os.path.join(LIB, "..", "tts-evaluations", "manifest.json")
    if os.path.exists(mpath):
        m = json.load(open(mpath, encoding="utf-8"))
        print("─ TTS engines ─")
        for eid, e in m.get("engines", {}).items():
            print(f"  {eid:12} {e.get('status'):16} samples={len(e.get('samples', []))}")

    if not args.no_audit:
        print("─ audit (orphans / drift) ─")
        pending_dir = os.path.join(LIB, "pending")
        pfiles = set(os.listdir(pending_dir)) if os.path.isdir(pending_dir) else set()
        rep = {os.path.basename(a["path"]) for a in A.values() if a["path"].startswith("pending/")}
        for o in sorted(pfiles - rep):
            print(f"  ORPHAN pending file not in catalog: {o}")
        for aid, a in A.items():
            fp = os.path.join(LIB, a["path"])
            if not os.path.exists(fp):
                print(f"  MISSING media for catalog asset: {aid} ({a['path']})")
        for g in gaps:
            if g["status"] == "open" and g.get("action") == "fill" and not g.get("suggested_asset_id"):
                print(f"  OPEN fill-gap with no candidate: {g['gap_id'][:12]}…")
        for g in gaps:
            if g["status"] == "routed_generate":
                j = next((x for x in jobs if x.get("job_id") == g.get("generation_job_id")), None)
                if not j or j.get("status") == "failed":
                    print(f"  STUCK routed_generate gap {g['gap_id'][:12]}… (job {j.get('status') if j else 'missing'})")


if __name__ == "__main__":
    main()
