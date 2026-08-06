#!/usr/bin/env python3
"""Validate video-library/catalog.json against the aifilm-video-* contract.

Self-contained (no third-party deps; uses ffprobe only lazily/optionally).
Exits non-zero on any violation so it can be used as a pre-commit / pre-write
gate. A freshly-initialized video library may have zero assets (unlike the bgm
validator, which requires a non-empty library) — that is reported as a WARNING,
not an error, so a new lane can be validated before its first ingest.

    python3 tools/validate_video_catalog.py                 # full check
    python3 tools/validate_video_catalog.py --no-sha        # skip file hashing
    python3 tools/validate_video_catalog.py path/to/cat.json
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime

LIB_SCHEMA = "aifilm-video-library-v1"
ASSET_SCHEMA = "aifilm-video-asset-v1"
VALID_STATUSES = {"approved", "pending_human_review", "rejected"}
VALID_MODES = {"t2v", "i2v", "r2v"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def is_iso(s):
    return isinstance(s, str) and bool(ISO.match(s))


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_asset(aid, a, root):
    if not isinstance(a, dict):
        err(f"[{aid}] asset is not an object"); return
    if a.get("asset_id") != aid:
        err(f"[{aid}] asset_id {a.get('asset_id')!r} != dict key")
    if a.get("schema") != ASSET_SCHEMA:
        err(f"[{aid}] schema {a.get('schema')!r} != {ASSET_SCHEMA}")
    st = a.get("status")
    if st not in VALID_STATUSES:
        err(f"[{aid}] status {st!r} not in {sorted(VALID_STATUSES)}")
    p = a.get("path")
    if not isinstance(p, str) or not p.endswith(".mp4"):
        err(f"[{aid}] path {p!r} must be a .mp4 path")
    else:
        fp = os.path.join(root, p)
        if not os.path.exists(fp):
            err(f"[{aid}] file missing on disk: {p}")
    if not isinstance(a.get("sha256"), str) or not HEX64.match(a.get("sha256", "")):
        err(f"[{aid}] sha256 not 64-hex")
    if not isinstance(a.get("model"), str) or not a.get("model"):
        err(f"[{aid}] model missing")
    if not isinstance(a.get("seed"), int) or isinstance(a.get("seed"), bool):
        err(f"[{aid}] seed must be int")
    mode = a.get("mode")
    if mode not in VALID_MODES:
        err(f"[{aid}] mode {mode!r} not in {sorted(VALID_MODES)}")
    si = a.get("source_image")
    if si is not None and not isinstance(si, str):
        err(f"[{aid}] source_image must be str or null")
    for f in ("mood", "scene", "style"):
        if not isinstance(a.get(f), str):
            err(f"[{aid}] {f} missing")
    e = a.get("energy")
    if not is_num(e) or not (0.0 <= e <= 1.0):
        err(f"[{aid}] energy {e!r} must be 0..1")
    uc = a.get("use_count")
    if not isinstance(uc, int) or isinstance(uc, bool) or uc < 0:
        err(f"[{aid}] use_count must be int>=0")
    if not is_iso(a.get("created_at", "")):
        err(f"[{aid}] created_at not ISO")
    # recipe
    r = a.get("recipe")
    if not isinstance(r, dict):
        err(f"[{aid}] recipe missing")
    else:
        for f in ("recipe_id", "mode", "mood", "scene", "style"):
            if not isinstance(r.get(f), str) or (f in ("recipe_id", "mood", "scene", "style") and not r.get(f)):
                err(f"[{aid}] recipe.{f} missing")
        if r.get("mode") not in VALID_MODES:
            err(f"[{aid}] recipe.mode not valid")
        if not is_num(r.get("energy")) or not (0.0 <= r.get("energy", -1) <= 1.0):
            err(f"[{aid}] recipe.energy must be 0..1")
        if not isinstance(r.get("resolution"), str) or not r.get("resolution"):
            err(f"[{aid}] recipe.resolution missing")
        if not is_num(r.get("duration")) or r.get("duration", 0) <= 0:
            err(f"[{aid}] recipe.duration must be >0")
    # technical
    t = a.get("technical")
    if not isinstance(t, dict):
        err(f"[{aid}] technical missing")
    else:
        if not isinstance(t.get("ok"), bool):
            err(f"[{aid}] technical.ok must be bool")
        if not isinstance(t.get("errors"), list):
            err(f"[{aid}] technical.errors must be list")
        if not isinstance(t.get("advisories"), list):
            err(f"[{aid}] technical.advisories must be list")
        if not isinstance(t.get("codec"), str):
            err(f"[{aid}] technical.codec missing")
        for f in ("width", "height"):
            if not isinstance(t.get(f), int) or isinstance(t.get(f), bool):
                err(f"[{aid}] technical.{f} must be int")
        if not is_num(t.get("fps")):
            err(f"[{aid}] technical.fps must be number")
        for f in ("duration_sec", "black_frame_ratio", "frozen_score"):
            if not is_num(t.get(f)):
                err(f"[{aid}] technical.{f} must be number")
        fp = t.get("fingerprint")
        if not isinstance(fp, list) or not all(is_num(x) for x in fp):
            err(f"[{aid}] technical.fingerprint must be list[number]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("catalog", nargs="?", default="video-library/catalog.json")
    ap.add_argument("--no-sha", action="store_true", help="skip sha256 file verification")
    args = ap.parse_args()

    root = os.path.dirname(os.path.abspath(args.catalog))
    try:
        cat = json.load(open(args.catalog))
    except Exception as ex:
        print(f"FATAL cannot read {args.catalog}: {ex}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(cat, dict):
        err("catalog root is not an object")
    else:
        if cat.get("schema") != LIB_SCHEMA:
            err(f"top.schema {cat.get('schema')!r} != {LIB_SCHEMA}")
        if not isinstance(cat.get("revision"), int) or isinstance(cat.get("revision"), bool):
            err("top.revision must be int")
        if not is_iso(cat.get("updated_at", "")):
            err("top.updated_at not ISO")
        assets = cat.get("assets")
        if not isinstance(assets, dict):
            err("top.assets must be an object")
        elif not assets:
            warn("top.assets is empty (fresh library is OK; ingest to populate)")
        else:
            fplens = [len(a.get("technical", {}).get("fingerprint", [])) for a in assets.values()
                      if isinstance(a, dict) and isinstance(a.get("technical"), dict)]
            canon = max(set(fplens), key=fplens.count) if fplens else 0
            for aid, a in assets.items():
                check_asset(aid, a, root)
                fp = a.get("technical", {}).get("fingerprint") if isinstance(a, dict) else None
                if isinstance(fp, list) and canon and len(fp) != canon:
                    warn(f"[{aid}] fingerprint len {len(fp)} != canonical {canon}")
            if not args.no_sha:
                for aid, a in assets.items():
                    if not isinstance(a, dict):
                        continue
                    p = a.get("path")
                    if not isinstance(p, str):
                        continue
                    fp = os.path.join(root, p)
                    if not os.path.exists(fp):
                        continue
                    h = hashlib.sha256(open(fp, "rb").read()).hexdigest()
                    if h != a.get("sha256"):
                        err(f"[{aid}] sha256 mismatch: file={h[:12]}… catalog={str(a.get('sha256'))[:12]}…")

    print(f"validated {args.catalog}")
    print(f"  assets: {len(cat.get('assets', {})) if isinstance(cat, dict) else 0}")
    if warnings:
        print(f"  warnings ({len(warnings)}):")
        for w in warnings:
            print(f"   - {w}")
    if errors:
        print(f"  ERRORS ({len(errors)}):")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    print("  OK: catalog satisfies the aifilm-video contract ✓")
    sys.exit(0)


if __name__ == "__main__":
    main()
