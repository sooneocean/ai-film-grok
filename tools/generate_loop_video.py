#!/usr/bin/env python3
"""The video generate loop: route open video gaps to backends and close them.

Mirrors tools/generate_loop.py for the video lane. Phases:
  submit  for each open gap with action=generate: eligibility shortcut FILLs if
          an approved shot already matches (mood/scene/mode/energy); else route
          via the capability matrix (video backends only) with fail-over + the
          circuit breaker, and hand off to generation-jobs.jsonl.
  poll    for each submitted job, ask its backend; on done, ingest the video
          (ingest_video.py runs the qa_video gate) and mark routed_generate;
          with --auto-approve also approve + fill (unless QA held it).

The 5090/H3 step is the ONLY external part (scripted reflux: submit writes a
ticket + prints the command; once you run H3 and the .mp4 lands, poll ingests).
Cloud Grok Video 1.5 needs no human in the loop once wired (endpoint + auth).

    python3 tools/generate_loop_video.py                 # submit + poll
    python3 tools/generate_loop_video.py --auto-approve  # also close approved
    python3 tools/generate_loop_video.py --submit        # route only
    python3 tools/generate_loop_video.py --demo          # use MockVideoBackend
    python3 tools/generate_loop_video.py --no-qa-gate    # bypass QA hold
    python3 tools/generate_loop_video.py --dry-run
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import load_generators, now_iso
from video_pipeline_lib import (load_vcatalog, load_vgaps, save_vgaps,
                                load_vjobs, save_vjobs, VIDEO_LIB)
from router import capable_backends, find_existing_video_candidate
from backends import get_backend
from breaker import CircuitBreaker

HERE = os.path.dirname(os.path.abspath(__file__))


def _seed_from(gap_id):
    return int(hashlib.sha256(gap_id.encode()).hexdigest()[:8], 16) % 10_000_000


def _build_spec(gap, vtogen):
    t = vtogen.get(gap["gap_id"], {})
    return {
        "gap_id": gap["gap_id"],
        "asset_kind": "video",
        "mood": gap.get("mood"),
        "mode": gap.get("mode", "t2v"),
        "scene": gap.get("scene"),
        "style": gap.get("style"),
        "energy": gap.get("energy", 0.35),
        "duration": gap.get("duration") or t.get("duration", 12.0),
        "resolution": gap.get("resolution") or t.get("resolution", "1080p"),
        "source_image": gap.get("source_image"),
        "reference": gap.get("reference"),
        "prompt_hint": t.get("prompt_hint", f"{gap.get('mood')} {gap.get('mode')} shot"),
        "recipe_id": t.get("recipe_id", ""),
        "seed": _seed_from(gap["gap_id"]),
        "film_id": gap.get("film_id"),
        "shot_id": gap.get("shot_id"),
    }


def _try_submit(bid, cfg, spec):
    return get_backend(bid, cfg).submit(spec)


def _fill_from_existing(g, cand):
    r = subprocess.run([sys.executable, os.path.join(HERE, "fill_gap_video.py"),
                        "--gap-id", g["gap_id"], "--asset-id", cand],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  fill-from-existing failed for {g['gap_id'][:12]}…:\n", r.stdout, r.stderr)
        return False
    g["status"] = "filled"
    g["resolved_asset_id"] = cand
    g["resolved_at"] = now_iso()
    g["action"] = "fill"
    print(f"  filled gap {g['gap_id'][:12]}… with existing approved asset {cand}")
    return True


def do_submit(args, gens, vtogen):
    gaps = load_vgaps()
    jobs = load_vjobs()
    taken = {j.get("source_gap_id") for j in jobs if j.get("status") in ("submitted", "running")}
    backends = gens.get("backends", {})
    vcat = load_vcatalog()
    breaker = CircuitBreaker()
    open_bk = breaker.open_set()
    if open_bk:
        print(f"  breaker open (cooling down): {', '.join(sorted(open_bk))}")
    n = 0
    n_jobs = 0
    for g in gaps:
        if g.get("action") != "generate" or g.get("status") != "open":
            continue
        if g["gap_id"] in taken:
            continue
        cand = find_existing_video_candidate(g, vcat)
        if cand:
            print(f"  {g['gap_id'][:12]}… already covered by {cand} -> fill (skip generate)")
            if args.dry_run:
                continue
            if _fill_from_existing(g, cand):
                n += 1
            continue
        # (fill-from-existing already printed its own line; not a job)
        spec = _build_spec(g, vtogen)
        bid = None
        ext_id = None
        if args.demo:
            bid = "mock-video"
            job_id = f"{bid}-{g['gap_id'][:8]}"
            spec["job_id"] = job_id
            spec["source_gap_id"] = g["gap_id"]
            ext_id = _try_submit(bid, {"_mock_video": True}, spec)
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
                print(f"  skip {g['gap_id'][:12]}…: no active video backend can serve "
                      f"mood={spec['mood']} mode={spec['mode']}")
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
        n_jobs += 1
    if not args.dry_run and (n_jobs or n):
        save_vjobs(jobs); save_vgaps(gaps)
        parts = []
        if n_jobs:
            parts.append(f"submitted {n_jobs} job(s)")
        if n - n_jobs:
            parts.append(f"filled {n - n_jobs} from existing")
        print(f"  {'; '.join(parts)}; gaps updated")
    elif args.dry_run:
        print(f"  (dry-run) would act on {n} gap(s)")


def do_poll(args, gens):
    jobs = load_vjobs()
    gaps = load_vgaps()
    backends = gens.get("backends", {})
    changed = False
    gaps_changed = False
    gate = not args.no_qa_gate

    def _revert_gap(gap_id):
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
        cfg = {"_mock_video": True} if bid == "mock-video" else backends.get(bid, {})
        be = get_backend(bid, cfg)
        try:
            status, video, err = be.poll(j["ext_id"])
        except Exception as ex:
            status, video, err = "failed", None, str(ex)
        if status == "done" and video:
            print(f"job {j['job_id']}: done -> {os.path.basename(video)}")
            if args.dry_run:
                continue
            spec = j["spec"]
            cmd = [sys.executable, os.path.join(HERE, "ingest_video.py"),
                   "--video", video, "--source-gap-id", j["source_gap_id"],
                   "--backend", bid, "--job-id", j["job_id"],
                   "--mood", spec.get("mood", ""), "--mode", spec.get("mode", "t2v"),
                   "--scene", spec.get("scene", ""), "--style", spec.get("style", ""),
                   "--energy", str(spec.get("energy", 0.35)),
                   "--duration", str(spec.get("duration", 12.0)),
                   "--resolution", spec.get("resolution", "1080p"),
                   "--seed", str(spec.get("seed", 0))]
            if spec.get("source_image"):
                cmd += ["--source-image", spec["source_image"]]
            if spec.get("reference"):
                cmd += ["--reference", spec["reference"]]
            ing = subprocess.run(cmd, capture_output=True, text=True)
            if ing.returncode != 0:
                print("  ingest failed:\n", ing.stdout, ing.stderr)
                j["status"] = "failed"; j["error"] = ing.stderr[:200]
                changed = True
                if _revert_gap(j["source_gap_id"]):
                    gaps_changed = True
                continue
            for line in ing.stdout.splitlines():
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
        save_vjobs(jobs)
    if gaps_changed and not args.dry_run:
        save_vgaps(gaps)


def _approve_and_fill(asset_id, gap_id, gate_qa=True):
    if gate_qa:
        vcat = load_vcatalog()
        a = vcat["assets"].get(asset_id)
        qa = (a or {}).get("technical", {}).get("qa")
        if qa is not None and not qa.get("ok"):
            print(f"  QA HOLD {asset_id}: {qa.get('issues')} — not auto-approved; "
                  f"needs human review")
            return
    r = subprocess.run([sys.executable, os.path.join(HERE, "approve_asset_video.py"),
                        "--asset-id", asset_id, "--reviewer", "auto-ingest",
                        "--license-note", "auto-ingested via generate_loop_video"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  auto-approve failed for {asset_id}:\n", r.stdout, r.stderr); return
    f = subprocess.run([sys.executable, os.path.join(HERE, "fill_gap_video.py"),
                        "--gap-id", gap_id, "--asset-id", asset_id],
                       capture_output=True, text=True)
    print(f"  approved + filled gap {gap_id[:12]}… with {asset_id}")


def main():
    global HERE
    HERE = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--poll", action="store_true")
    ap.add_argument("--auto-approve", action="store_true")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--no-qa-gate", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gens = load_generators()
    vtogen = {}
    vt_path = os.path.join(VIDEO_LIB, "to-generate.jsonl")
    if os.path.exists(vt_path):
        for l in open(vt_path, encoding="utf-8"):
            l = l.strip()
            if l:
                t = json.loads(l)
                vtogen[t["source_gap_id"]] = t

    only_submit = args.submit or args.poll
    if args.submit or not only_submit:
        print("== submit =="); do_submit(args, gens, vtogen)
    if args.poll or not only_submit:
        print("== poll =="); do_poll(args, gens)


if __name__ == "__main__":
    main()
