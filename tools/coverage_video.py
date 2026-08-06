#!/usr/bin/env python3
"""Video library supply/demand coverage analyzer + proactive generation planner.

Mirrors tools/coverage.py for the video lane. Groups supply/demand by
(mood, mode, energy_bucket) — the dimensions a video backend actually varies on
(scene/style are descriptive, carried on the gap but not used for bucketing).
Classifies STARVED/THIN/OK and emits open generate gaps + a video to-generate
ledger (to-generate.jsonl in video-library) for generate_loop_video to consume.

    python3 tools/coverage_video.py                       # human report
    python3 tools/coverage_video.py --json                # machine-readable
    python3 tools/coverage_video.py --emit-generate --apply --max 12
"""
import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_pipeline_lib import load_vcatalog, load_vgaps, VIDEO_LIB

VTOGEN = os.path.join(VIDEO_LIB, "to-generate.jsonl")


def energy_bucket(e):
    if e is None:
        return "mid"
    if e < 0.34:
        return "low"
    if e < 0.67:
        return "mid"
    return "high"


def _load():
    return load_vcatalog(), load_vgaps()


def analyze(cat, gaps, target_min=4):
    assets = cat.get("assets", {})
    supply = Counter()
    for a in assets.values():
        if a.get("status") == "approved":
            key = (a.get("mood"), a.get("mode"), energy_bucket(a.get("energy")))
            supply[key] += 1
    inflight = Counter()
    demand = Counter()
    for g in gaps:
        key = (g.get("mood"), g.get("mode", "t2v"), energy_bucket(g.get("energy")))
        demand[key] += 1
        if g.get("status") == "routed_generate" and g.get("action") == "generate":
            inflight[key] += 1
    combos = set(supply) | set(inflight) | set(demand)
    rows = []
    for k in sorted(combos):
        mood, mode, eb = k
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
        rows.append({"mood": mood, "mode": mode, "energy_bucket": eb,
                     "approved": appr, "inflight": infl, "demand": dem,
                     "effective": eff, "deficit": deficit, "status": status})
    return {"target_min": target_min, "rows": rows,
            "supply_total": sum(supply.values()),
            "demand_total": sum(demand.values())}


def priority_queue(analysis, target_min=None, max_total=30, per_cap=10):
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
    return hashlib.sha256(f"{r['mood']}|{r['mode']}|{r['energy_bucket']}|{i}|{now}".encode()).hexdigest()


def _rep_energy(bucket):
    return {"low": 0.2, "mid": 0.5, "high": 0.8}[bucket]


def _emit(prio, gaps, target_min):
    if not prio:
        print("  nothing to emit"); return
    shutil.copy(os.path.join(VIDEO_LIB, "gap-queue.jsonl"),
                os.path.join(VIDEO_LIB, "gap-queue.jsonl") + ".bak")
    if os.path.exists(VTOGEN):
        shutil.copy(VTOGEN, VTOGEN + ".bak")
    now = datetime.now(timezone.utc).isoformat()
    new_gaps, new_togen = [], []
    for r, n in prio:
        for i in range(n):
            gid = _gid(r, i, now)
            dedup = f"coverage|{r['mood']}|{r['mode']}|{r['energy_bucket']}"
            e = _rep_energy(r["energy_bucket"])
            new_gaps.append({
                "gap_id": gid, "action": "generate", "status": "open",
                "asset_kind": "video", "mood": r["mood"], "mode": r["mode"],
                "scene": "", "style": "", "energy": e,
                "film_id": "", "shot_id": "", "series_id": "", "motif_id": "",
                "reason": "coverage_gap", "dedup_key": dedup,
                "suggested_asset_id": None, "created_at": now,
            })
            new_togen.append({
                "job_id": gid[:16], "source_gap_id": gid,
                "film_id": "", "shot_id": "", "mood": r["mood"], "mode": r["mode"],
                "energy": e, "motif_id": "",
                "recipe_id": f"baseline-v1-{r['mood']}-{r['mode']}",
                "duration": 12.0, "resolution": "1080p",
                "prompt_hint": f"{r['mood']} {r['mode']} shot, cinematic, energy {e}",
            })
    gaps.extend(new_gaps)
    with open(os.path.join(VIDEO_LIB, "gap-queue.jsonl"), "w", encoding="utf-8") as f:
        for g in gaps:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    existing = []
    if os.path.exists(VTOGEN):
        existing = [json.loads(l) for l in open(VTOGEN, encoding="utf-8") if l.strip()]
    existing.extend(new_togen)
    with open(VTOGEN, "w", encoding="utf-8") as f:
        for t in existing:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"  queued {len(new_gaps)} generate gaps + {len(new_togen)} to-generate "
          f"entries (backups written)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--target-min", type=int, default=4)
    ap.add_argument("--emit-generate", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max", type=int, default=30)
    args = ap.parse_args()

    cat, gaps = _load()
    analysis = analyze(cat, gaps, target_min=args.target_min)
    prio = priority_queue(analysis, max_total=args.max)

    if args.json:
        out = dict(analysis)
        out["priority"] = [{"mood": r["mood"], "mode": r["mode"], "energy_bucket": r["energy_bucket"],
                            "effective": r["effective"], "demand": r["demand"], "emit": n}
                           for r, n in prio]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"video coverage target-min per combo: {args.target_min}")
    print(f"supply(approved)={analysis['supply_total']} demand={analysis['demand_total']}")
    print(f"{'mood':10} {'mode':5} {'bucket':5} {'appr':4} {'infl':4} {'dem':4} {'eff':4} status")
    for r in analysis["rows"]:
        print(f"{r['mood']:10} {r['mode']:5} {r['energy_bucket']:5} "
              f"{r['approved']:4} {r['inflight']:4} {r['demand']:4} {r['effective']:4} {r['status']}")
    starved = [r for r in analysis["rows"] if r["status"] == "STARVED"]
    thin = [r for r in analysis["rows"] if r["status"] == "THIN"]
    print(f"\nSTARVED: {len(starved)}  THIN: {len(thin)}")
    if prio:
        print(f"\npriority generation queue (emit up to {args.max}):")
        for r, n in prio:
            print(f"  +{n}  {r['mood']}/{r['mode']}/{r['energy_bucket']} "
                  f"(effective {r['effective']} -> {r['effective'] + n}, demand {r['demand']})")
    else:
        print("\nno deficits to generate — library coverage healthy")

    if args.emit_generate:
        if not args.apply:
            print("\n(emit-generate dry-run) pass --apply to queue these gaps")
            return
        _emit(prio, gaps, args.target_min)


if __name__ == "__main__":
    main()
