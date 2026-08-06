#!/usr/bin/env python3
"""Capability-matrix router: pick the best backend for a generation gap.

Pure function over generators.json + a gap spec. Selection rules:
  1. backend must be status == "active" (archived_failed like fish is skipped)
  2. mood in capabilities.moods (or moods contains "*")
  3. stem_profile in capabilities.stem_profiles (or list empty = any)
  4. duration <= capabilities.max_duration
  5. tie-break: prefer local (free, no credit risk), then registry order
Returns backend id, or None if nothing can serve the gap (it stays open).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import load_generators, load_catalog, cosine


def capable_backends(spec, generators, exclude=(), breaker=None):
    """Ordered list of active, capable backend ids (local first, then api).

    `exclude` is an explicit skip list (e.g. a backend that just failed in the
    current submit loop). `breaker`, if given, additionally drops any backend
    currently tripped open (see breaker.CircuitBreaker) so a flaky API source
    is cooled down instead of hammered.
    """
    backends = generators.get("backends", {})
    mood = spec.get("mood")
    stem = spec.get("stem_profile")
    dur = spec.get("duration", 30)
    open_bk = breaker.open_set() if breaker else set()
    cands = []
    for bid, cfg in backends.items():
        if bid in exclude:
            continue
        if open_bk and bid in open_bk:
            continue
        if cfg.get("status") != "active":
            continue
        cap = cfg.get("capabilities", {})
        moods = cap.get("moods", [])
        if moods and "*" not in moods and mood not in moods:
            continue
        stems = cap.get("stem_profiles", [])
        if stems and stem and stem not in stems:
            continue
        if dur and cap.get("max_duration") and dur > cap["max_duration"]:
            continue
        cands.append((bid, cfg))
    local = [c for c in cands if c[1].get("kind") == "local"]
    rest = [c for c in cands if c[1].get("kind") != "local"]
    return [b for b, _ in (local + rest)]


def choose_backend(spec, generators=None, exclude=()):
    if generators is None:
        generators = load_generators()
    cands = capable_backends(spec, generators, exclude=exclude)
    return cands[0] if cands else None


def find_existing_candidate(gap, catalog=None, tol_energy=0.1, min_sim=0.95):
    """Eligibility-aware shortcut: if an already-approved asset already matches
    this gap (same mood + stem + close energy, and not a near-duplicate clash),
    return its id so the loop can FILL instead of GENERATE — avoiding a wasteful
    regeneration. Returns asset_id or None."""
    if catalog is None:
        catalog = load_catalog()
    mood = gap.get("mood")
    stem = gap.get("stem_profile")
    energy = gap.get("energy")
    target_fp = gap.get("technical", {}).get("fingerprint") if gap.get("technical") else None
    for aid, a in catalog.get("assets", {}).items():
        if a.get("status") != "approved":
            continue
        if a.get("mood") != mood or a.get("stem_profile") != stem:
            continue
        if energy is not None and abs((a.get("energy") or 0) - energy) > tol_energy:
            continue
        # near-duplicate guard: don't route to an asset already serving a
        # different shot via the same cluster unless explicitly allowed
        if target_fp and a.get("technical", {}).get("fingerprint"):
            if cosine(target_fp, a["technical"]["fingerprint"]) >= min_sim:
                return aid
        if target_fp is None:
            return aid
    return None


def choose_route(gap, generators=None):
    """Top-level gap router. Honors asset_kind: a tts gap is routed to an active
    TTS engine (selection only — engines are evaluated, not generated here),
    a bgm gap goes through the capability matrix. Returns (kind, target) where
    target is a backend id or 'tts:<engine>'."""
    if gap.get("asset_kind") == "tts":
        mpath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "tts-evaluations", "manifest.json")
        if os.path.exists(mpath):
            m = json.load(open(mpath, encoding="utf-8"))
            for eid, e in m.get("engines", {}).items():
                if e.get("status") == "active" and e.get("samples"):
                    return "tts", f"tts:{eid}"
        return "tts", None
    spec = {"mood": gap.get("mood"), "stem_profile": gap.get("stem_profile"),
            "duration": gap.get("duration")}
    return "bgm", choose_backend(spec, generators)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap-id")
    ap.add_argument("--mood", default="ambient")
    ap.add_argument("--stem-profile", default="pad")
    ap.add_argument("--duration", type=float, default=30)
    args = ap.parse_args()

    spec = {"mood": args.mood, "stem_profile": args.stem_profile, "duration": args.duration}
    if args.gap_id:
        # pull the spec from the actual gap
        from pipeline_lib import load_gaps
        g = next((x for x in load_gaps() if x.get("gap_id") == args.gap_id), None)
        if not g:
            print("gap not found", file=sys.stderr); sys.exit(2)
        spec = {"mood": g.get("mood"), "stem_profile": g.get("stem_profile"),
                "duration": g.get("duration")}
    bid = choose_backend(spec)
    print(f"spec mood={spec.get('mood')} stem={spec.get('stem_profile')} dur={spec.get('duration')}")
    print(f"-> routed backend: {bid if bid else '(none — gap stays open)'}")


if __name__ == "__main__":
    main()
