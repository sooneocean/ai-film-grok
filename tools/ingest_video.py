#!/usr/bin/env python3
"""Ingest a generated video file into the video catalog as a pending asset.

Mirrors tools/ingest_generated.py for the video lane: recomputes sha256 + a
stdlib fingerprint, runs the qa_video gate, bumps revision, re-validates, and
marks the source gap routed_generate. --normalize re-encodes to H.264/yuv420p
(fixes odd codecs/resolutions from some generators) before ingest.

    python3 tools/ingest_video.py --video pending/<job>.mp4 \\
        --source-gap-id <gap_id> --backend h3 --job-id <job_id> \\
        --mood cinematic --mode t2v --scene city_night --style filmic \\
        --energy 0.3 --duration 12 --resolution 1080p --seed 123
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_pipeline_lib import (load_vcatalog, save_vcatalog, load_vgaps, save_vgaps,
                                VIDEO_LIB, now_iso, sha256_file, bump,
                                extract_video_fingerprint, analyze_video)
from qa_video import qa_video

HERE = os.path.dirname(os.path.abspath(__file__))


def _normalize_video(path, target="yuv420p", vcodec="libx264"):
    """Re-encode to a standard, broadly-decodable mp4 in place. Returns path."""
    ff = shutil.which("ffmpeg")
    if not ff:
        print("  (ffmpeg unavailable; skipping normalize)", file=sys.stderr)
        return path
    tmp = path + ".norm.mp4"
    r = subprocess.run([ff, "-y", "-i", path, "-c:v", vcodec, "-pix_fmt", target,
                        "-movflags", "+faststart", tmp],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("  normalize failed:", r.stderr[-300:], file=sys.stderr)
        return path
    shutil.move(tmp, path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--source-gap-id", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--job-id", default="")
    ap.add_argument("--mood", required=True)
    ap.add_argument("--mode", required=True, choices=("t2v", "i2v", "r2v"))
    ap.add_argument("--scene", default="")
    ap.add_argument("--style", default="")
    ap.add_argument("--energy", type=float, default=0.35)
    ap.add_argument("--duration", type=float, default=12.0)
    ap.add_argument("--resolution", default="1080p")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--source-image", default=None, help="i2v reference image")
    ap.add_argument("--reference", default=None, help="r2v reference image")
    ap.add_argument("--recipe-id", default="")
    ap.add_argument("--normalize", action="store_true",
                    help="re-encode to H.264/yuv420p before ingest")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    video = os.path.abspath(args.video)
    if not os.path.exists(video):
        print(f"ERROR: video not found: {video}", file=sys.stderr); sys.exit(2)

    cat = load_vcatalog()
    approved_fps = [a.get("technical", {}).get("fingerprint")
                    for a in cat.get("assets", {}).values()
                    if a.get("status") == "approved"]

    if args.normalize and not args.dry_run:
        video = _normalize_video(video)
        print(f"  normalized -> {os.path.basename(video)}")

    sha = sha256_file(video)
    hid = sha[:8]
    asset_id = f"{args.mode}-{args.mood}-{hid}"
    ext = "mp4"
    dst_path = f"pending/{asset_id}.{ext}"
    dst = os.path.join(VIDEO_LIB, dst_path)

    m = analyze_video(video)
    fp = extract_video_fingerprint(video)
    qa = qa_video(video, spec={"duration": args.duration, "resolution": args.resolution},
                  approved_fps=approved_fps)
    recipe_id = args.recipe_id or f"ingest-{args.backend}-{args.mode}-{args.mood}"
    now = now_iso()

    asset = {
        "schema": "aifilm-video-asset-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "path": dst_path,
        "sha256": sha,
        "model": args.backend,
        "seed": args.seed,
        "mode": args.mode,
        "source_image": args.source_image,
        "prompt_sha256": "",
        "recipe": {
            "recipe_id": recipe_id,
            "mode": args.mode,
            "mood": args.mood,
            "scene": args.scene,
            "style": args.style,
            "energy": args.energy,
            "duration": args.duration,
            "resolution": args.resolution,
        },
        "mood": args.mood,
        "scene": args.scene,
        "style": args.style,
        "energy": args.energy,
        "mode": args.mode,
        "technical": {
            "ok": True,
            "errors": [],
            "advisories": [],
            "codec": m.get("codec") or "unknown",
            "width": m.get("width", 0),
            "height": m.get("height", 0),
            "fps": m.get("fps", 0),
            "duration_sec": m.get("duration_sec", 0),
            "has_audio": m.get("has_audio", False),
            "black_frame_ratio": qa["metrics"].get("black_frame_ratio"),
            "frozen_score": qa["metrics"].get("frozen_score"),
            "fingerprint": fp,
            "qa": {
                "ok": qa["ok"],
                "issues": qa["issues"],
                "advisories": qa["advisories"],
                "metrics": qa["metrics"],
            },
        },
        "use_count": 0,
        "asset_kind": "video",
        "created_at": now,
        "generated_by": args.backend,
        "generated_from_gap": args.source_gap_id,
    }

    print(f"ingest -> {asset_id} ({dst_path}) from {os.path.basename(video)}")
    qa_tag = "PASS" if qa["ok"] else f"HOLD ({'; '.join(qa['issues'])})"
    print(f"  qa_video: {qa_tag}")
    if qa["advisories"]:
        print(f"  qa advisories ({len(qa['advisories'])}):")
        for adv in qa["advisories"]:
            print(f"    - {adv}")
    if args.dry_run:
        print("  (dry-run, no changes written)"); return

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.abspath(dst) != video:
        shutil.move(video, dst)

    cat["assets"][asset_id] = asset
    bump(cat)
    save_vcatalog(cat)

    ok = subprocess.run([sys.executable, os.path.join(HERE, "validate_video_catalog.py"),
                         "--no-sha"], capture_output=True, text=True)
    if ok.returncode != 0:
        print("ERROR: video catalog validation failed after ingest; restoring backup",
              file=sys.stderr)
        shutil.copy(os.path.join(VIDEO_LIB, "catalog.json.bak"),
                    os.path.join(VIDEO_LIB, "catalog.json"))
        print(ok.stdout); sys.exit(1)

    gaps = load_vgaps()
    for g in gaps:
        if g.get("gap_id") == args.source_gap_id:
            g["status"] = "routed_generate"
            g["routed_backend"] = args.backend
            g["generation_job_id"] = args.job_id
            g["generated_asset_id"] = asset_id
    save_vgaps(gaps)
    print(f"  revision -> {cat['revision']}; gap {args.source_gap_id[:12]}… -> "
          f"routed_generate; validation OK ✓")
    print(f"ASSET_ID={asset_id}")
    return asset_id


if __name__ == "__main__":
    main()
