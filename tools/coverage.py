#!/usr/bin/env python3
"""Library supply/demand coverage analyzer + proactive generation planner.

The pipeline used to be purely reactive: it fills gaps with whatever approved
asset exists, which hid a real problem — the library is lopsided. Audit showed
`rnb-full` was demanded by 59 of 70 gaps but only 2 approved assets exist (so
60 fill gaps had to reuse those 2 beds), and `ambient` had 0 supply (the 10
gaps stuck at routed_generate are exactly its first batch being generated).

This tool makes the shortage visible and turns it into the next batch of work:

  - supply  = approved assets, grouped by (mood, stem, energy_bucket)
  - inflight= gaps currently routed_generate (beds being made) — counted as
              supply-in-progress so we don't double-order what's already queued
  - demand  = all gaps (filled + routed + open), grouped the same way

  classify each combo: STARVED (approved 0 & inflight 0), THIN (effective <
  demand or < --target-min), OK otherwise. Priority queue = combos sorted by
  deficit (demand - effective) desc; --emit-generate turns the top-N into open
  generate gaps + to-generate.jsonl ledger entries so generate_loop can consume
  them immediately. Default is dry-run; --apply writes.

    python3 tools/coverage.py                       # human report
    python3 tools/coverage.py --json                # machine-readable
    python3 tools/coverage.py --emit-generate       # show what WOULD be queued
    python3 tools/coverage.py --emit-generate --apply --max 12
"""
import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAT = os.path.join(ROOT, "bgm-library", "catalog.json")
GAP = os.path.join(ROOT, "bgm-library", "gap-queue.jsonl")
TOGEN = os.path.join(ROOT, "bgm-library", "to-generate.jsonl")


def energy_bucket(e):
    if e is None:
        return "mid"
    if e < 0.34:
        return "low"
    if e < 0.67:
        return "mid"
    return "high"


def _load():
    cat = json.load(open(CAT, encoding="utf-8"))
    gaps = [json.loads(l) for l in open(GAP, encoding="utf-8") if l.strip()]
    return cat, gaps


def analyze(cat, gaps, target_min=4):
    """Structured coverage analysis (pure given cat/gaps)."""
    assets = cat.get("assets", {})
    supply = Counter()
    for a in assets.values():
        if a.get("status") == "approved":
            key = (a.get("mood"), a.get("stem_profile"), energy_bucket(a.get("energy")))
            supply[key] += 1
    inflight = Counter()
    demand = Counter()
    for g in gaps:
        key = (g.get("mood"), g.get("stem_profile"), energy_bucket(g.get("energy")))
        demand[key] += 1
        if g.get("status") == "routed_generate" and g.get("action") == "generate":
            inflight[key] += 1
    combos = set(supply) | set(inflight) | set(demand)
    rows = []
    for k in sorted(combos):
        mood, stem, eb = k
        appr = supply.get(k, 0)
        infl = inflight.get(k, 0)
        dem = demand.get(k, 0)
        eff = appr + infl
        deficit = max(0, dem - eff)
        if appr == 0 and infl == 0:
            status = "STARVED"
        elif eff < dem or eff < target_min:
            status = "THIN"
        else:
            status = "OK"
        rows.append({
            "mood": mood, "stem": stem, "energy_bucket": eb,
            "approved": appr, "inflight": infl, "demand": dem,
            "effective": eff, "deficit": deficit, "status": status,
        })
    return {"target_min": target_min, "rows": rows,
            "supply_total": sum(supply.values()),
            "demand_total": sum(demand.values())}


def priority_queue(analysis, target_min=None, max_total=30, per_cap=10):
    """Combos needing more stock, ordered by deficit desc, with emit counts."""
    tmin = target_min if target_min is not None else analysis["target_min"]
    need = []
    for r in analysis["rows"]:
        if r["status"] in ("STARVED", "THIN"):
            n = max(0, tmin - r["effective"])
            if n > 0:
                need.append((r, min(n, per_cap)))
    need.sort(key=lambda x: (-x[0]["deficit"], -x[1]))
    out, used = [], 0
    for r, n in need:
        if used >= max_total:
            break
        take = min(n, max_total - used)
        out.append((r, take)); used += take
    return out


def _gid(r, i, now):
    import hashlib
    return hashlib.sha256(
        f"{r['mood']}|{r['stem']}|{r['energy_bucket']}|{i}|{now}".encode()).hexdigest()


def _rep_energy(bucket):
    return {"low": 0.2, "mid": 0.5, "high": 0.8}[bucket]


def _emit(prio, cat, gaps, target_min):
    if not prio:
        print("  nothing to emit"); return
    shutil.copy(GAP, GAP + ".bak")
    if os.path.exists(TOGEN):
        shutil.copy(TOGEN, TOGEN + ".bak")
    now = datetime.now(timezone.utc).isoformat()
    new_gaps, new_togen = [], []
    for r, n in prio:
        for i in range(n):
            gid = _gid(r, i, now)
            dedup = f"coverage|{r['mood']}|{r['stem']}|{r['energy_bucket']}"
            e = _rep_energy(r["energy_bucket"])
            new_gaps.append({
                "gap_id": gid, "action": "generate", "status": "open",
                "mood": r["mood"], "stem_profile": r["stem"], "energy": e,
                "film_id": "", "shot_id": "", "series_id": "", "motif_id": "",
                "reason": "coverage_gap", "dedup_key": dedup,
                "suggested_asset_id": None, "created_at": now,
            })
            new_togen.append({
                "job_id": gid[:16], "source_gap_id": gid,
                "film_id": "", "shot_id": "", "mood": r["mood"], "energy": e,
                "stem_profile": r["stem"], "motif_id": "",
                "recipe_id": f"baseline-v1-{r['mood']}-{r['stem']}",
                "duration": 30.0,
                "prompt_hint": f"{r['mood']} {r['stem']} bed, energy {e}, no vocals, loopable",
            })
    gaps.extend(new_gaps)
    with open(GAP, "w", encoding="utf-8") as f:
        for g in gaps:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    existing = []
    if os.path.exists(TOGEN):
        existing = [json.loads(l) for l in open(TOGEN, encoding="utf-8") if l.strip()]
    existing.extend(new_togen)
    with open(TOGEN, "w", encoding="utf-8") as f:
        for t in existing:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"  queued {len(new_gaps)} generate gaps + {len(new_togen)} to-generate "
          f"entries (backups written)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--target-min", type=int, default=4,
                    help="healthy minimum stock per (mood,stem,bucket) combo")
    ap.add_argument("--emit-generate", action="store_true",
                    help="queue open generate gaps for the top deficits")
    ap.add_argument("--apply", action="store_true",
                    help="with --emit-generate, actually write gaps + to-generate")
    ap.add_argument("--max", type=int, default=30, help="max gaps to emit total")
    args = ap.parse_args()

    cat, gaps = _load()
    analysis = analyze(cat, gaps, target_min=args.target_min)
    prio = priority_queue(analysis, max_total=args.max)

    if args.json:
        out = dict(analysis)
        out["priority"] = [{
            "mood": r["mood"], "stem": r["stem"], "energy_bucket": r["energy_bucket"],
            "effective": r["effective"], "demand": r["demand"], "emit": n,
        } for r, n in prio]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"coverage target-min per combo: {args.target_min}")
    print(f"supply(approved)={analysis['supply_total']} demand={analysis['demand_total']}")
    print(f"{'mood':10} {'stem':8} {'bucket':5} {'appr':4} {'infl':4} {'dem':4} {'eff':4} status")
    for r in analysis["rows"]:
        print(f"{r['mood']:10} {r['stem']:8} {r['energy_bucket']:5} "
              f"{r['approved']:4} {r['inflight']:4} {r['demand']:4} {r['effective']:4} {r['status']}")
    starved = [r for r in analysis["rows"] if r["status"] == "STARVED"]
    thin = [r for r in analysis["rows"] if r["status"] == "THIN"]
    print(f"\nSTARVED: {len(starved)}  THIN: {len(thin)}")
    if prio:
        print(f"\npriority generation queue (emit up to {args.max}):")
        for r, n in prio:
            print(f"  +{n}  {r['mood']}/{r['stem']}/{r['energy_bucket']} "
                  f"(effective {r['effective']} -> {r['effective'] + n}, demand {r['demand']})")
    else:
        print("\nno deficits to generate — library coverage healthy")

    if args.emit_generate:
        if not args.apply:
            print("\n(emit-generate dry-run) pass --apply to queue these gaps")
            return
        _emit(prio, cat, gaps, args.target_min)


if __name__ == "__main__":
    main()
