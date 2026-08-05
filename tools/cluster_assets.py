#!/usr/bin/env python3
"""Recompute similarity_cluster for all bgm assets.

Within each mood, greedily group assets by acoustic similarity of their
technical.fingerprint (cosine similarity >= --threshold). Existing
similarity_cluster values are respected as seeds, so re-running only extends
new assets instead of reshuffling everything.

    python3 tools/cluster_assets.py            # threshold 0.95
    python3 tools/cluster_assets.py --threshold 0.92

Backs up catalog.json to catalog.json.bak and bumps revision. Safe to re-run.
"""
import argparse
import json
import math
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "bgm-library", "catalog.json")


def cos(a, b):
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.95)
    args = ap.parse_args()

    cat = json.load(open(SRC))
    A = cat["assets"]
    by_mood = defaultdict(list)
    for k, v in A.items():
        by_mood[v["mood"]].append(k)

    assign = {}
    for mood, ids in by_mood.items():
        reps = {}
        for k in ids:
            c = A[k].get("similarity_cluster")
            if c and c in ids and c not in reps:
                reps[c] = A[c]["technical"]["fingerprint"]
        for k in ids:
            fp = A[k]["technical"]["fingerprint"]
            best, bs = None, -1
            for r, rf in reps.items():
                s = cos(fp, rf)
                if s > bs:
                    bs, best = s, r
            if best and bs >= args.threshold:
                assign[k] = best
            else:
                assign[k] = k
                reps[k] = fp

    shutil.copy(SRC, SRC + ".bak")
    for k, v in A.items():
        v["similarity_cluster"] = assign[k]
    cat["revision"] = cat.get("revision", 0) + 1
    cat["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(SRC, "w") as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)

    sizes = defaultdict(list)
    for k, v in assign.items():
        sizes[v].append(k)
    multi = sorted(((len(v), r) for r, v in sizes.items() if len(v) > 1), reverse=True)
    print(f"clusters={len(sizes)} assets={len(A)} threshold={args.threshold}")
    print(f"near-dup groups: {len(multi)}")
    for sz, r in multi:
        print(f"  {r}: {sz}")
    print(f"revision -> {cat['revision']}")


if __name__ == "__main__":
    main()
