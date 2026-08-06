#!/usr/bin/env python3
"""Video lane doctor: cross-entity audit + safe auto-fix (mirrors reconcile.py).

Checks catalog↔media, orphans, stuck routed_generate gaps, dead-end open
generate gaps (no capable video backend), empty fingerprints, gap duration
backfill from to-generate.jsonl, near-dup groups, stale jobs, breakers.

    python3 tools/reconcile_video.py            # audit
    python3 tools/reconcile_video.py --fix      # safe fixes
    python3 tools/reconcile_video.py --strict   # exit non-zero on errors
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_pipeline_lib import (load_vcatalog, save_vcatalog, load_vgaps, save_vgaps,
                                load_vjobs, VIDEO_LIB, cosine, extract_video_fingerprint)
from router import capable_backends
from breaker import CircuitBreaker

ERR, WARN, INFO = [], [], []


def _togen_durations():
    p = os.path.join(VIDEO_LIB, "to-generate.jsonl")
    out = {}
    if os.path.exists(p):
        for l in open(p, encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            t = json.loads(l)
            out[t.get("source_gap_id")] = t.get("duration", 12.0)
    return out


def _banner(t):
    print(f"\n─ {t} ─")


def audit():
    cat = load_vcatalog()
    assets = cat.get("assets", {})
    gaps = load_vgaps()
    jobs = load_vjobs()
    gens = json.load(open(os.path.join("bgm-library", "generators.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join("bgm-library", "generators.json")) else {"backends": {}}
    job_by_id = {j.get("job_id"): j for j in jobs}

    _banner("catalog ↔ media consistency")
    referenced = set()
    lens = [len(a.get("technical", {}).get("fingerprint", [])) for a in assets.values()
            if isinstance(a, dict) and isinstance(a.get("technical"), dict)]
    canon_len = max(set(lens), key=lens.count) if lens else None
    for aid, a in assets.items():
        p = a.get("path")
        if not isinstance(p, str):
            ERR.append(f"[{aid}] missing path"); continue
        referenced.add(os.path.basename(p))
        full = os.path.join(VIDEO_LIB, p)
        if not os.path.exists(full):
            ERR.append(f"[{aid}] media missing on disk: {p}")
        fp = a.get("technical", {}).get("fingerprint")
        if not fp or (canon_len and len(fp) != canon_len):
            WARN.append(f"[{aid}] fingerprint empty/non-canonical")

    _banner("orphan media files")
    for d in ("pending", "approved"):
        dp = os.path.join(VIDEO_LIB, d)
        if not os.path.isdir(dp):
            continue
        for fn in os.listdir(dp):
            if fn.endswith((".bak",)) or fn.startswith("."):
                continue
            if not fn.lower().endswith(".mp4"):
                continue
            if fn not in referenced:
                WARN.append(f"orphan {d}/{fn} not referenced by catalog")

    _banner("gaps lifecycle")
    for g in gaps:
        st = g.get("status")
        if st == "routed_generate":
            j = job_by_id.get(g.get("generation_job_id"))
            if not j or j.get("status") == "failed":
                WARN.append(f"[{g['gap_id'][:12]}…] stuck routed_generate "
                             f"(job {j.get('status') if j else 'missing'}) -> safe to reset")
        if st == "open" and g.get("action") == "generate":
            spec = {"asset_kind": "video", "mood": g.get("mood"),
                    "mode": g.get("mode", "t2v"), "duration": g.get("duration"),
                    "resolution": g.get("resolution")}
            if not capable_backends(spec, gens):
                WARN.append(f"[{g['gap_id'][:12]}…] open generate gap with NO capable "
                            f"video backend (dead end)")

    _banner("generate-gap duration completeness")
    missing_dur = [g for g in gaps if g.get("action") == "generate" and "duration" not in g]
    if missing_dur:
        WARN.append(f"{len(missing_dur)} generate gaps missing duration field "
                    f"(reconcile --fix backfills)")

    _banner("near-duplicate groups (approved)")
    approved = [(aid, a.get("technical", {}).get("fingerprint"))
                for aid, a in assets.items()
                if a.get("status") == "approved" and a.get("technical", {}).get("fingerprint")]
    seen = set()
    for i in range(len(approved)):
        ai, fi = approved[i]
        if ai in seen:
            continue
        grp = [ai]
        for j in range(i + 1, len(approved)):
            aj, fj = approved[j]
            if fj and cosine(fi, fj) >= 0.98:
                grp.append(aj); seen.add(aj)
        if len(grp) > 1:
            INFO.append(f"near-dup group: {grp}")

    _banner("stale jobs / breakers")
    for j in jobs:
        if j.get("status") in ("submitted", "running"):
            INFO.append(f"job {j.get('job_id')} still {j.get('status')} (in-flight)")
    bk = CircuitBreaker()
    for bid, s in bk.status().items():
        if s["open"]:
            INFO.append(f"breaker OPEN for {bid} (cooling down)")

    return cat, gaps, gens, job_by_id


def fix(cat, gaps, gens, job_by_id):
    changed_cat = False
    changed_gaps = False

    for aid, a in cat.get("assets", {}).items():
        t = a.get("technical", {})
        full = os.path.join(VIDEO_LIB, a.get("path", ""))
        fp = t.get("fingerprint")
        lens = [len(x.get("technical", {}).get("fingerprint", [])) for x in cat["assets"].values()
                if isinstance(x.get("technical"), dict) and x.get("technical", {}).get("fingerprint")]
        canon = max(set(lens), key=lens.count) if lens else 64
        if not fp or len(fp) != canon:
            if os.path.exists(full):
                t["fingerprint"] = extract_video_fingerprint(full)
                changed_cat = True
                print(f"  recomputed fingerprint: {aid}")
            else:
                print(f"  SKIP fingerprint for {aid} (media missing)")

    for g in gaps:
        if g.get("status") == "routed_generate":
            j = job_by_id.get(g.get("generation_job_id"))
            if not j or j.get("status") == "failed":
                g["status"] = "open"
                g.pop("routed_backend", None)
                g.pop("generation_job_id", None)
                changed_gaps = True
                print(f"  reset stuck gap {g['gap_id'][:12]}… -> open")

    dur = _togen_durations()
    for g in gaps:
        if g.get("action") == "generate" and "duration" not in g:
            d = dur.get(g.get("gap_id"))
            if d is not None:
                g["duration"] = d
                changed_gaps = True
                print(f"  backfilled duration={d} on generate gap {g['gap_id'][:12]}…")
            else:
                print(f"  SKIP duration for {g['gap_id'][:12]}… (no to-generate entry)")

    if changed_cat:
        save_vcatalog(cat)
        print("  catalog saved (backup written)")
    if changed_gaps:
        save_vgaps(gaps)
        print("  gaps saved (backup written)")
    if not (changed_cat or changed_gaps):
        print("  nothing to fix")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    cat, gaps, gens, job_by_id = audit()
    print(f"\nSUMMARY: errors={len(ERR)} warnings={len(WARN)} info={len(INFO)}")
    for e in ERR:
        print(f"  ERROR  {e}")
    for w in WARN:
        print(f"  WARN   {w}")
    for i in INFO:
        print(f"  INFO   {i}")
    if args.fix:
        print("\n== applying safe fixes ==")
        fix(cat, gaps, gens, job_by_id)
    if ERR or (args.strict and WARN):
        sys.exit(1)
    print("OK: video pipeline is consistent ✓" if not ERR else "completed with errors")


if __name__ == "__main__":
    main()
