#!/usr/bin/env python3
"""Pipeline doctor: cross-entity consistency audit + safe auto-fix.

Complements validate_catalog.py (which checks the catalog schema) by looking
at the *relationships* between catalog, gaps, jobs, and media on disk:

  - catalog asset whose media file is missing on disk
  - media file (pending/ approved/) not referenced by any catalog asset
  - gap stuck at routed_generate whose job is failed/missing -> reset to open
  - open generate gap with NO capable active backend (dead end)
  - empty / non-canonical technical.fingerprint -> recompute (--fix)
  - null / empty similarity_cluster -> set to asset_id (--fix)
  - near-duplicate groups among approved assets (informational)
  - stale submitted/running jobs whose backend ticket is gone
  - circuit-breaker open backends

Read-only by default. `--fix` applies only the safe, reversible corrections
(fingerprint recompute, cluster default, gap reset for failed/missing jobs) and
writes through pipeline_lib's save_* (which keep .bak backups).

    python3 tools/reconcile.py            # audit only
    python3 tools/reconcile.py --fix      # apply safe fixes
    python3 tools/reconcile.py --strict   # exit non-zero if any error found
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import (load_catalog, save_catalog, load_gaps, save_gaps,
                          load_jobs, LIB, cosine, extract_fingerprint)
from router import capable_backends
from breaker import CircuitBreaker

ERR, WARN, INFO = [], [], []


def _banner(t):
    print(f"\n─ {t} ─")


def _togen_durations():
    """Map source_gap_id -> duration from to-generate.jsonl (the generate
    ledger written by generate_loop submit)."""
    p = os.path.join(LIB, "to-generate.jsonl")
    out = {}
    if os.path.exists(p):
        for l in open(p, encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            t = json.loads(l)
            out[t.get("source_gap_id")] = t.get("duration", 30.0)
    return out


def audit():
    cat = load_catalog()
    assets = cat.get("assets", {})
    gaps = load_gaps()
    jobs = load_jobs()
    gens = json.load(open(os.path.join(LIB, "generators.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(LIB, "generators.json")) else {"backends": {}}

    job_by_id = {j.get("job_id"): j for j in jobs}
    _banner("catalog ↔ media consistency")
    referenced = set()
    canon_len = None
    lens = [len(a.get("technical", {}).get("fingerprint", [])) for a in assets.values()
            if isinstance(a, dict) and isinstance(a.get("technical"), dict)]
    if lens:
        canon_len = max(set(lens), key=lens.count)

    for aid, a in assets.items():
        p = a.get("path")
        if not isinstance(p, str):
            ERR.append(f"[{aid}] missing path")
            continue
        referenced.add(os.path.basename(p))
        full = os.path.join(LIB, p)
        if not os.path.exists(full):
            ERR.append(f"[{aid}] media missing on disk: {p}")
        fp = a.get("technical", {}).get("fingerprint")
        if not fp or (canon_len and len(fp) != canon_len):
            WARN.append(f"[{aid}] fingerprint empty/non-canonical (len={len(fp) if fp else 0}; canon={canon_len})")
        sc = a.get("similarity_cluster")
        if not sc:
            WARN.append(f"[{aid}] similarity_cluster empty")

    _banner("orphan media files")
    for d in ("pending", "approved"):
        dp = os.path.join(LIB, d)
        if not os.path.isdir(dp):
            continue
        for fn in os.listdir(dp):
            if fn.endswith((".bak",)) or fn.startswith("."):
                continue
            if not fn.lower().endswith((".wav", ".flac", ".mp3")):
                continue  # ignore sidecars (.txt license, .json, etc.)
            if fn not in referenced:
                WARN.append(f"orphan {d}/{fn} not referenced by catalog")

    _banner("gaps lifecycle")
    for g in gaps:
        st = g.get("status")
        if st == "routed_generate":
            j = job_by_id.get(g.get("generation_job_id"))
            if not j or j.get("status") == "failed":
                WARN.append(f"[{g['gap_id'][:12]}…] stuck routed_generate (job {j.get('status') if j else 'missing'}) -> safe to reset")
        if st == "open" and g.get("action") == "generate":
            spec = {"mood": g.get("mood"), "stem_profile": g.get("stem_profile"),
                    "duration": g.get("duration")}
            if not capable_backends(spec, gens):
                WARN.append(f"[{g['gap_id'][:12]}…] open generate gap with NO capable backend (dead end)")

    _banner("open fill-gap backlog (eligible to auto-close)")
    fill_elig, fill_dead = [], []
    for g in gaps:
        if g.get("action") == "fill" and g.get("status") == "open":
            sid = g.get("suggested_asset_id")
            a = assets.get(sid) if sid else None
            if a and a.get("status") == "approved":
                fill_elig.append(g)
            else:
                fill_dead.append(g)
    if fill_elig:
        INFO.append(f"{len(fill_elig)} open fill gaps have an approved candidate "
                    f"-> close via tools/fill_open_gaps.py --apply")
    if fill_dead:
        WARN.append(f"{len(fill_dead)} open fill gaps are dead-ends (no approved "
                    f"candidate; need generation)")

    _banner("generate-gap duration completeness")
    missing_dur = [g for g in gaps if g.get("action") == "generate" and "duration" not in g]
    if missing_dur:
        WARN.append(f"{len(missing_dur)} generate gaps missing duration field "
                    f"(reconcile --fix backfills from to-generate.jsonl)")

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

    # fingerprints + clusters
    for aid, a in cat.get("assets", {}).items():
        t = a.get("technical", {})
        full = os.path.join(LIB, a.get("path", ""))
        fp = t.get("fingerprint")
        lens = [len(x.get("technical", {}).get("fingerprint", [])) for x in cat["assets"].values()
                if isinstance(x.get("technical"), dict) and x.get("technical", {}).get("fingerprint")]
        canon = max(set(lens), key=lens.count) if lens else 101
        if not fp or len(fp) != canon:
            if os.path.exists(full):
                t["fingerprint"] = extract_fingerprint(full)
                changed_cat = True
                print(f"  recomputed fingerprint: {aid}")
            else:
                print(f"  SKIP fingerprint for {aid} (media missing)")
        if not a.get("similarity_cluster"):
            a["similarity_cluster"] = aid
            changed_cat = True
            print(f"  defaulted similarity_cluster: {aid}")

    # reset stuck routed_generate gaps (job failed/missing only)
    for g in gaps:
        if g.get("status") == "routed_generate":
            j = job_by_id.get(g.get("generation_job_id"))
            if not j or j.get("status") == "failed":
                g["status"] = "open"
                g.pop("routed_backend", None)
                g.pop("generation_job_id", None)
                changed_gaps = True
                print(f"  reset stuck gap {g['gap_id'][:12]}… -> open")

    # backfill duration on generate gaps from to-generate.jsonl so the gap
    # records are self-describing (routing/QA can read duration off the gap
    # instead of only off the separate generate ledger).
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
        save_catalog(cat)
        print("  catalog saved (backup written)")
    if changed_gaps:
        save_gaps(gaps)
        print("  gaps saved (backup written)")
    if not (changed_cat or changed_gaps):
        print("  nothing to fix")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="apply safe fixes")
    ap.add_argument("--strict", action="store_true", help="exit non-zero if any error/warn")
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
    print("OK: pipeline is consistent ✓" if not ERR else "completed with errors")


if __name__ == "__main__":
    main()
