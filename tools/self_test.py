#!/usr/bin/env python3
"""End-to-end self-test of the closed generate loop, on a throwaway copy.

Copies the repo to a temp dir (no media, fresh empty catalog), then runs the
real tools with --demo (MockBackend) + --auto-approve so the full chain
submit -> poll -> ingest -> approve -> fill executes without any external
service. It also exercises Round 6 additions:

  - reconcile --fix backfills `duration` onto the generate gaps
  - fill_open_gaps.py --apply closes open `fill` gaps that already have an
    approved candidate, while --dry-run leaves everything untouched

Proves the routing + reflux logic is correct before you point it at a real
5090 / API. Leaves nothing in the real repo.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _ignore(src, names):
    drop = {".git", "approved", "melo-cache", "piper-voices", "tts-evaluations", "__pycache__"}
    out = set()
    for n in names:
        if n in drop:
            out.add(n); continue
        if n.endswith((".bak", ".flac", ".mp3", ".onnx", ".wav")):
            out.add(n)
    return out


def _run(args, cwd):
    r = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FAILED {args}:\n{r.stdout}\n{r.stderr}")
        sys.exit(1)
    return r


def _load_gaps(T):
    p = os.path.join(T, "bgm-library", "gap-queue.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def _save_gaps(T, gaps):
    p = os.path.join(T, "bgm-library", "gap-queue.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for g in gaps:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")


def main():
    T = tempfile.mkdtemp(prefix="aifilm-self-test-")
    print(f"self-test workspace: {T}")
    try:
        shutil.copytree(REPO, T, ignore=_ignore, dirs_exist_ok=True)
        # fresh empty catalog so validation only sees generated assets
        cat = {"schema": "aifilm-bgm-library-v1", "revision": 0,
               "updated_at": "2026-08-05T00:00:00+00:00", "assets": {}}
        with open(os.path.join(T, "bgm-library", "catalog.json"), "w", encoding="utf-8") as f:
            json.dump(cat, f, indent=2)
        os.makedirs(os.path.join(T, "bgm-library", "pending"), exist_ok=True)

        # Reset generate gaps to open so the demo loop actually exercises the
        # full submit->poll->ingest->approve->fill chain. The real repo may
        # already have them routed_generate + a job ledger; without this reset
        # the demo would have nothing to do and the test would pass trivially.
        gaps = _load_gaps(T)
        for g in gaps:
            if g.get("action") == "generate":
                g["status"] = "open"
                g.pop("routed_backend", None)
                g.pop("generation_job_id", None)
        _save_gaps(T, gaps)

        # Round 6-B: reconcile --fix should backfill `duration` onto generate gaps
        _run(["tools/reconcile.py", "--fix"], cwd=T)
        gaps = _load_gaps(T)
        gen = [g for g in gaps if g.get("action") == "generate"]
        missing = [g for g in gen if "duration" not in g]
        print(f"  generate gaps: {len(gen)}; missing duration after --fix: {len(missing)}")
        if gen and missing:
            print("  FAIL: reconcile --fix did not backfill duration")
            sys.exit(1)

        # Inject a TTS gap to prove the dual pipeline: it must be ROUTED (logged)
        # but never generated or filled by the BGM generate loop.
        gaps = _load_gaps(T)
        tts_gap = {"gap_id": "tts-demo-0001", "asset_kind": "tts",
                   "action": "generate", "status": "open", "mood": "narration",
                   "stem_profile": "voice", "energy": 0.5, "duration": 8,
                   "text": "示例旁白台词（由 TTS 引擎评估样本池提供）"}
        gaps.append(tts_gap)
        _save_gaps(T, gaps)
        # clear any pre-existing job ledger so submit isn't blocked by `taken`
        jpath = os.path.join(T, "bgm-library", "generation-jobs.jsonl")
        if os.path.exists(jpath):
            os.remove(jpath)

        # only BGM (non-tts) generate gaps are expected to close via generation
        expect = sum(1 for g in gaps
                     if g.get("action") == "generate" and g.get("asset_kind") != "tts")
        tts_ids = [g["gap_id"] for g in gaps if g.get("asset_kind") == "tts"]
        # capture the generate-gap ids before the demo run (fill_gap.py rewrites
        # action->"fill" on close, so we must track by id, not by action)
        gen_ids = [g["gap_id"] for g in gaps if g.get("action") == "generate"]
        print(f"expected generate gaps to close: {expect}")

        r = _run(["tools/pipeline.py", "one-shot", "--demo"], cwd=T)

        # assertions
        cat = json.load(open(os.path.join(T, "bgm-library", "catalog.json"), encoding="utf-8"))
        gaps = _load_gaps(T)
        jobs = [json.loads(l) for l in open(os.path.join(T, "bgm-library", "generation-jobs.jsonl"), encoding="utf-8") if l.strip()]

        gen_ids_set = set(gen_ids)
        gen_filled = sum(1 for g in gaps
                         if g.get("gap_id") in gen_ids_set and g.get("status") == "filled")
        total_filled = sum(1 for g in gaps if g.get("status") == "filled")
        jobs_done = sum(1 for j in jobs if j.get("status") == "done")
        approved = sum(1 for a in cat["assets"].values() if a["status"] == "approved")
        new_assets = len(cat["assets"])
        # Two gaps can legitimately resolve to the SAME approved asset (eligibility
        # dedup, or the mock backend producing byte-identical clips), so the
        # invariant is distinct generated assets, not 1-per-gap.
        distinct_assets = len({j.get("output_asset_id") for j in jobs
                               if j.get("output_asset_id")})

        print(f"  assets created : {new_assets} (distinct generated: {distinct_assets})")
        print(f"  approved       : {approved}")
        print(f"  jobs done      : {jobs_done}")
        print(f"  generate gaps filled: {gen_filled} (of {expect} tracked by id)")
        print(f"  total filled incl. pre-existing: {total_filled}")

        ok = (approved == new_assets == distinct_assets
              and jobs_done >= distinct_assets and gen_filled == expect)
        # TTS gap must have been routed (logged) but NOT generated/filled
        tts_routed = "tts gap" in r.stdout
        tts_still_open = all(g.get("status") == "open" for g in gaps if g.get("gap_id") in tts_ids)
        print(f"  tts gap routed (logged, not generated): {tts_routed}; still open: {tts_still_open}")
        ok = ok and tts_routed and tts_still_open

        # Round 6-A: fill_open_gaps --apply should close open `fill` gaps whose
        # candidate is already approved, and leave dead-ends untouched.
        approved_ids = [aid for aid, a in cat["assets"].items() if a["status"] == "approved"]
        aid = approved_ids[0]
        rev_before = cat["revision"]
        uc_before = cat["assets"][aid]["use_count"]
        gaps = _load_gaps(T)
        for i in range(3):
            gaps.append({"gap_id": f"fill-demo-{i}", "action": "fill", "status": "open",
                         "suggested_asset_id": aid})
        gaps.append({"gap_id": "fill-demo-dead", "action": "fill", "status": "open",
                     "suggested_asset_id": "zzz-missing-asset"})
        _save_gaps(T, gaps)
        _run(["tools/fill_open_gaps.py", "--apply"], cwd=T)
        cat = json.load(open(os.path.join(T, "bgm-library", "catalog.json"), encoding="utf-8"))
        gaps = _load_gaps(T)
        closed = [g for g in gaps if g.get("gap_id", "").startswith("fill-demo-") and g.get("status") == "filled"]
        dead = [g for g in gaps if g.get("gap_id") == "fill-demo-dead"]
        print(f"  fill_open closed: {len(closed)}; dead-end still open: {len(dead)}")
        print(f"  revision {rev_before} -> {cat['revision']}; "
              f"use_count({aid}) {uc_before} -> {cat['assets'][aid]['use_count']}")
        ok = ok and len(closed) == 3 and len(dead) == 1 and dead[0]["status"] == "open"
        ok = ok and cat["revision"] == rev_before + 3
        ok = ok and cat["assets"][aid]["use_count"] == uc_before + 3

        # Round 6-A: --dry-run must NOT mutate anything.
        gaps = _load_gaps(T)
        rev_after_apply = cat["revision"]
        gaps.append({"gap_id": "fill-demo-dry1", "action": "fill", "status": "open",
                     "suggested_asset_id": aid})
        gaps.append({"gap_id": "fill-demo-dry2", "action": "fill", "status": "open",
                     "suggested_asset_id": aid})
        _save_gaps(T, gaps)
        _run(["tools/fill_open_gaps.py"], cwd=T)  # no --apply
        cat = json.load(open(os.path.join(T, "bgm-library", "catalog.json"), encoding="utf-8"))
        gaps = _load_gaps(T)
        dry_still_open = all(g.get("status") == "open"
                             for g in gaps if g.get("gap_id", "").startswith("fill-demo-dry"))
        print(f"  dry-run left revision at {cat['revision']} (unchanged={cat['revision']==rev_after_apply}); "
              f"dry gaps still open: {dry_still_open}")
        ok = ok and dry_still_open and cat["revision"] == rev_after_apply

        # also confirm the routing contract still holds (soft WARN allowed)
        rc = _run(["tools/route.py", "check"], cwd=T)
        ok = ok and rc.returncode == 0
        # Round 7-C: the unified dispatcher must delegate `check` correctly
        rc2 = _run(["tools/pipeline.py", "check"], cwd=T)
        ok = ok and rc2.returncode == 0

        # ---- VIDEO lane end-to-end (MockVideoBackend) + lane isolation ----
        # Fresh empty video library so validation only sees generated shots,
        # plus 3 open video generate gaps (t2v/i2v/r2v). The video one-shot must
        # close them via generation WITHOUT touching the bgm catalog or the
        # tts gap (three lanes stay isolated).
        vlib = os.path.join(T, "video-library")
        os.makedirs(os.path.join(vlib, "pending"), exist_ok=True)
        json.dump({"schema": "aifilm-video-library-v1", "revision": 0,
                   "updated_at": "2026-08-06T00:00:00+00:00", "assets": {}},
                  open(os.path.join(vlib, "catalog.json"), "w", encoding="utf-8"))
        vgaps = [
            {"gap_id": f"vgap-{i}", "action": "generate", "status": "open",
             "asset_kind": "video", "mood": "cinematic", "mode": m,
             "scene": f"sc{i}", "style": "filmic", "energy": 0.5,
             "duration": 12, "resolution": "1080p"}
            for i, m in enumerate(["t2v", "i2v", "r2v"])]
        with open(os.path.join(vlib, "gap-queue.jsonl"), "w", encoding="utf-8") as f:
            for g in vgaps:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")
        bgm_before = len(json.load(open(os.path.join(T, "bgm-library", "catalog.json"),
                                        encoding="utf-8"))["assets"])
        r = _run(["tools/video_pipeline.py", "one-shot", "--demo"], cwd=T)
        vcat = json.load(open(os.path.join(vlib, "catalog.json"), encoding="utf-8"))
        vgaps_out = [json.loads(l) for l in open(os.path.join(vlib, "gap-queue.jsonl"),
                                                 encoding="utf-8") if l.strip()]
        vjobs = [json.loads(l) for l in open(os.path.join(vlib, "generation-jobs.jsonl"),
                                             encoding="utf-8") if l.strip()]
        v_approved = sum(1 for a in vcat["assets"].values() if a["status"] == "approved")
        v_filled = sum(1 for g in vgaps_out if g.get("status") == "filled")
        bgm_after = len(json.load(open(os.path.join(T, "bgm-library", "catalog.json"),
                                       encoding="utf-8"))["assets"])
        tts_still_open = all(g.get("status") == "open"
                              for g in _load_gaps(T) if g.get("asset_kind") == "tts")
        print(f"  video assets created : {len(vcat['assets'])} (approved {v_approved})")
        print(f"  video gaps filled    : {v_filled}/3")
        print(f"  video jobs done      : {sum(1 for j in vjobs if j.get('status')=='done')}")
        print(f"  bgm catalog assets before/after: {bgm_before}/{bgm_after} "
              f"(must be equal — no leak)")
        print(f"  tts gap still open    : {tts_still_open} (lane isolation)")
        ok = (ok and len(vcat["assets"]) == 3 and v_approved == 3 and v_filled == 3
              and bgm_after == bgm_before and tts_still_open)
        rc3 = _run(["tools/video_pipeline.py", "check"], cwd=T)
        ok = ok and rc3.returncode == 0

        if ok:
            print("\nSELF-TEST PASS ✓ — closed loop + TTS dual-pipeline + Round6 fill-open/duration verified")
            sys.exit(0)
        else:
            print("\nSELF-TEST FAIL ✗")
            sys.exit(1)
    finally:
        pass  # keep workspace for inspection; delete manually if desired


if __name__ == "__main__":
    main()
