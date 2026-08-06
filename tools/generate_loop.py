#!/usr/bin/env python3
"""The generate loop: route open gaps to backends and close them.

Phases (run in order unless you pass one):
  submit       for each open gap with action=generate and no job yet:
                 - P5: a tts gap is noted + skipped (handled by the tts pipeline)
                 - shortcut: if an approved asset already matches (mood/stem/
                   energy or near-dup), FILL it instead of regenerating
                 - else choose a backend via router.py (capability matrix with
                   automatic fail-over to the next capable backend on submit
                   error) and hand off the job to generation-jobs.jsonl.
  poll         for each submitted job, ask its backend if it is done; on done,
               ingest the audio (ingest_generated.py, which runs the qa_audio
               gate and records the result) and mark the gap routed_generate;
               with --auto-approve also approve + fill it (unless QA held it).
  approve-fill for done jobs whose asset is still pending, approve + fill.

The 5090/LTX/Grok step is the ONLY external part. ACE-Step submit only writes
a ticket + prints the command; once you run it and the .wav lands in
pending/, poll ingests it automatically. Cloud backends (once wired) need no
human in the loop. --no-qa-gate forces auto-approve even when an asset failed
the audio quality check (operator override; default is to hold it).

    python3 tools/generate_loop.py                 # submit + poll
    python3 tools/generate_loop.py --auto-approve  # also close approved gaps
    python3 tools/generate_loop.py --submit        # route only
    python3 tools/generate_loop.py --demo          # use MockBackend end-to-end
    python3 tools/generate_loop.py --no-qa-gate    # bypass the QA hold
    python3 tools/generate_loop.py --dry-run       # show decisions, no writes
"""
import argparse
import json
import os
import subprocess
import sys
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import (load_generators, load_gaps, save_gaps, load_jobs,
                          save_jobs, load_catalog, LIB, now_iso)
from router import (choose_backend, capable_backends, find_existing_candidate,
                    choose_route)
from backends import get_backend
from breaker import CircuitBreaker
from tts import gap_asset_kind, choose_tts_engine


def _seed_from(gap_id):
    return int(hashlib.sha256(gap_id.encode()).hexdigest()[:8], 16) % 10_000_000


def _build_spec(gap, togen):
    t = togen.get(gap["gap_id"], {})
    return {
        "gap_id": gap["gap_id"],
        "asset_kind": "bgm",
        "mood": gap.get("mood"),
        "stem_profile": gap.get("stem_profile"),
        "energy": gap.get("energy", 0.35),
        # prefer the gap's own duration (backfilled by reconcile --fix), then
        # the separate generate ledger, then a 30s default.
        "duration": gap.get("duration") or t.get("duration", 30.0),
        "prompt_hint": t.get("prompt_hint", f"{gap.get('mood')} {gap.get('stem_profile')} bed"),
        "recipe_id": t.get("recipe_id", ""),
        "seed": _seed_from(gap["gap_id"]),
        "film_id": gap.get("film_id"),
        "shot_id": gap.get("shot_id"),
    }


def _try_submit(bid, cfg, spec):
    """Submit to one backend; raises on failure so callers can fail over."""
    return get_backend(bid, cfg).submit(spec)


def _fill_from_existing(g, cand):
    """Close a gap by reusing an already-approved asset (no new generation)."""
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "fill_gap.py"),
         "--gap-id", g["gap_id"], "--asset-id", cand],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  fill-from-existing failed for {g['gap_id'][:12]}…:\n",
              r.stdout, r.stderr)
        return False
    # mutate in-memory so the final save_gaps() doesn't clobber fill_gap's write
    g["status"] = "filled"
    g["resolved_asset_id"] = cand
    g["resolved_at"] = now_iso()
    g["action"] = "fill"
    print(f"  filled gap {g['gap_id'][:12]}… with existing approved asset {cand}")
    return True


def do_submit(args, gens, togen):
    gaps = load_gaps()
    jobs = load_jobs()
    taken = {j.get("source_gap_id") for j in jobs if j.get("status") in ("submitted", "running")}
    backends = gens.get("backends", {})
    cat = load_catalog()
    # circuit-breaker: skip backends currently tripped open (cooling down)
    breaker = CircuitBreaker()
    open_bk = breaker.open_set()
    if open_bk:
        print(f"  breaker open (cooling down): {', '.join(sorted(open_bk))}")
    n = 0
    for g in gaps:
        if g.get("action") != "generate" or g.get("status") != "open":
            continue
        if g["gap_id"] in taken:
            continue

        # P5 — TTS gaps belong to a separate (evaluated-engine) pipeline; this
        # loop only generates BGM beds. Note the route and skip so it isn't
        # orphaned, but do NOT hand it to a sound-generation backend.
        if gap_asset_kind(g) == "tts":
            eng = choose_tts_engine()
            tid = eng[0] if eng else None
            print(f"  tts gap {g['gap_id'][:12]}… routed to tts engine {tid} "
                  f"(handled by tts pipeline, not generated here)")
            continue

        # Eligibility shortcut: an approved asset already matches this gap's
        # mood/stem/energy (or is a near-duplicate) — FILL it, don't regenerate.
        cand = find_existing_candidate(g, cat)
        if cand:
            print(f"  {g['gap_id'][:12]}… already covered by {cand} -> fill (skip generate)")
            if args.dry_run:
                continue
            if _fill_from_existing(g, cand):
                n += 1
            continue

        spec = _build_spec(g, togen)

        # Choose a backend: demo override, explicit override, or the capability
        # matrix with automatic fail-over to the next capable backend when one
        # raises at submit time (e.g. an API backend missing its auth env).
        # job_id / spec are set before submit because backends (mock, acestep,
        # api) embed it in ticket paths and payloads. A backend that fails is
        # recorded on the breaker so repeated failures trip a cooldown.
        bid = None
        ext_id = None
        if args.demo:
            bid = "mock"
            job_id = f"{bid}-{g['gap_id'][:8]}"
            spec["job_id"] = job_id
            spec["source_gap_id"] = g["gap_id"]
            ext_id = _try_submit(bid, {"id": "mock"}, spec)
            breaker.record_success(bid)
        elif args.backend:
            bid = args.backend
            job_id = f"{bid}-{g['gap_id'][:8]}"
            spec["job_id"] = job_id
            spec["source_gap_id"] = g["gap_id"]
            cfg = backends.get(bid, {})
            try:
                ext_id = _try_submit(bid, cfg, spec)
                breaker.record_success(bid)
            except Exception as ex:
                print(f"  backend {bid} failed submit: {ex}")
                breaker.record_failure(bid)
                bid = None
        else:
            exclude = []
            for _ in range(8):
                cands = capable_backends(spec, gens, exclude=exclude, breaker=breaker)
                if not cands:
                    break
                cb = cands[0]
                job_id = f"{cb}-{g['gap_id'][:8]}"
                spec["job_id"] = job_id
                spec["source_gap_id"] = g["gap_id"]
                try:
                    ext_id = _try_submit(cb, backends.get(cb, {}), spec)
                    bid = cb
                    breaker.record_success(cb)
                    break
                except Exception as ex:
                    print(f"  backend {cb} failed submit: {ex}; excluding + retry")
                    exclude.append(cb)
                    breaker.record_failure(cb)
            if not bid:
                print(f"  skip {g['gap_id'][:12]}…: no active backend can serve "
                      f"mood={spec['mood']} stem={spec['stem_profile']}")
                continue

        print(f"route {g['gap_id'][:12]}… -> {bid} (job {job_id})")
        if args.dry_run:
            continue
        jobs.append({
            "job_id": job_id, "source_gap_id": g["gap_id"], "backend": bid,
            "ext_id": ext_id, "status": "submitted", "spec": spec,
            "submitted_at": now_iso(), "done_at": None,
            "output_asset_id": None, "error": None,
        })
        g["status"] = "routed_generate"
        g["routed_backend"] = bid
        g["generation_job_id"] = job_id
        n += 1
    if not args.dry_run and n:
        save_jobs(jobs); save_gaps(gaps)
        print(f"  submitted {n} job(s); gaps routed_generate")
    elif args.dry_run:
        print(f"  (dry-run) would route {n} gap(s)")


def do_poll(args, gens):
    jobs = load_jobs()
    gaps = load_gaps()
    backends = gens.get("backends", {})
    changed = False
    gaps_changed = False
    gate = not args.no_qa_gate

    def _revert_gap(gap_id):
        # return a failed/aborted gap to `open` so it can be retried or
        # re-routed by a later submit pass. Mutates the in-memory list; caller
        # persists via save_gaps.
        for g in gaps:
            if g.get("gap_id") == gap_id:
                g["status"] = "open"
                g.pop("routed_backend", None)
                g.pop("generation_job_id", None)
                return True
        return False

    for j in jobs:
        if j.get("status") != "submitted":
            continue
        bid = j["backend"]
        cfg = {"id": "mock"} if bid == "mock" else backends.get(bid, {})
        be = get_backend(bid, cfg)
        try:
            status, audio, err = be.poll(j["ext_id"])
        except Exception as ex:
            status, audio, err = "failed", None, str(ex)
        if status == "done" and audio:
            print(f"job {j['job_id']}: done -> {os.path.basename(audio)}")
            if args.dry_run:
                continue
            asset_id = subprocess.run(
                [sys.executable, os.path.join(HERE, "ingest_generated.py"),
                 "--audio", audio, "--source-gap-id", j["source_gap_id"],
                 "--backend", bid, "--job-id", j["job_id"],
                 "--mood", j["spec"]["mood"], "--stem-profile", j["spec"]["stem_profile"],
                 "--energy", str(j["spec"]["energy"]), "--duration", str(j["spec"]["duration"]),
                 "--recipe-id", j["spec"].get("recipe_id", "") or "",
                 "--seed", str(j["spec"]["seed"])],
                capture_output=True, text=True)
            if asset_id.returncode != 0:
                print("  ingest failed:\n", asset_id.stdout, asset_id.stderr)
                j["status"] = "failed"; j["error"] = asset_id.stderr[:200]
                changed = True
                # a bad ingest must release the gap so it isn't stuck at
                # routed_generate forever
                if _revert_gap(j["source_gap_id"]):
                    gaps_changed = True
                continue
            for line in asset_id.stdout.splitlines():
                if line.startswith("ASSET_ID="):
                    new_id = line.split("=", 1)[1].strip()
                    break
            else:
                new_id = None
            j["status"] = "done"; j["done_at"] = now_iso(); j["output_asset_id"] = new_id
            changed = True
            if args.auto_approve and new_id:
                _approve_and_fill(new_id, j["source_gap_id"], gate_qa=gate)
        elif status == "failed":
            print(f"job {j['job_id']}: failed ({err})")
            if not args.dry_run:
                j["status"] = "failed"; j["error"] = str(err)[:200]
                if _revert_gap(j["source_gap_id"]):
                    gaps_changed = True
                changed = True
    if changed and not args.dry_run:
        save_jobs(jobs)
    if gaps_changed and not args.dry_run:
        save_gaps(gaps)


def _approve_and_fill(asset_id, gap_id, gate_qa=True):
    # QA gate: hold assets that failed the audio quality check for human review
    # instead of blindly auto-approving bad generations into the library.
    if gate_qa:
        cat = load_catalog()
        a = cat["assets"].get(asset_id)
        qa = (a or {}).get("technical", {}).get("qa")
        if qa is not None and not qa.get("ok"):
            print(f"  QA HOLD {asset_id}: {qa.get('issues')} — not auto-approved; "
                  f"needs human review")
            return
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "approve_asset.py"), "--asset-id", asset_id,
         "--reviewer", "auto-ingest", "--instrumental-confirmed",
         "--license-note", "auto-ingested via generate_loop"],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  auto-approve failed for {asset_id}:\n", r.stdout, r.stderr); return
    f = subprocess.run(
        [sys.executable, os.path.join(HERE, "fill_gap.py"), "--gap-id", gap_id,
         "--asset-id", asset_id],
        capture_output=True, text=True)
    print(f"  approved + filled gap {gap_id[:12]}… with {asset_id}")


def do_approve_fill(args):
    jobs = load_jobs()
    gate = not args.no_qa_gate
    for j in jobs:
        if j.get("status") == "done" and j.get("output_asset_id"):
            _approve_and_fill(j["output_asset_id"], j["source_gap_id"], gate_qa=gate)


def main():
    global HERE
    HERE = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--poll", action="store_true")
    ap.add_argument("--approve-fill", action="store_true")
    ap.add_argument("--auto-approve", action="store_true")
    ap.add_argument("--backend", default=None, help="override router for submit")
    ap.add_argument("--demo", action="store_true", help="use MockBackend end-to-end")
    ap.add_argument("--no-qa-gate", action="store_true",
                    help="bypass the QA hold and force auto-approve of generated assets")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gens = load_generators()
    togen = {}
    tg_path = os.path.join(LIB, "to-generate.jsonl")
    if os.path.exists(tg_path):
        for l in open(tg_path, encoding="utf-8"):
            l = l.strip()
            if l:
                t = json.loads(l)
                togen[t["source_gap_id"]] = t

    only_submit = args.submit or args.poll or args.approve_fill
    if args.submit or not only_submit:
        print("== submit =="); do_submit(args, gens, togen)
    if args.poll or not only_submit:
        print("== poll =="); do_poll(args, gens)
    if args.approve_fill:
        print("== approve-fill =="); do_approve_fill(args)


if __name__ == "__main__":
    main()
