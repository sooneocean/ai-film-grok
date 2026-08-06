#!/usr/bin/env python3
"""Video quality gate for generated shots (film-ready check).

Runs before an ingested video asset is allowed to auto-approve into the library.
Pure stdlib + lazy ffmpeg/ffprobe (the video lane's one external dependency).
Mirrors tools/qa_audio.py's hard-gate / soft-advisory split:

HARD GATES (block auto-approve, set ok=False):
  - decodable: a real video stream (codec/width/height/fps present)
  - duration within [duration_min, requested +/- duration_tol]
  - black_frame_ratio <= black_max   (no mostly-black clip)
  - frozen_score > frozen_max        (not a static image passed off as video)

ADVISORY SIGNALS (reported, never block — need human eyes):
  - resolution mismatch vs the requested ladder (480p/720p/1080p/1440p)
  - has_audio  (the clip carries sound; assemble() will mix under BGM/TTS)
  - near_dup   cosine vs an already-approved shot fingerprint
  - frame analysis unavailable (ffmpeg/ffprobe missing) -> QA relaxed

Keeps bad generations (undecodable, wrong length, black, frozen) out of the
catalog, while surfacing the softer film-cut concerns to a human reviewer.

    python3 tools/qa_video.py pending/foo.mp4 --duration 12
    python3 tools/qa_video.py pending/foo.mp4 --strict   # non-zero exit on FAIL
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_pipeline_lib import analyze_video, extract_video_fingerprint, cosine

RES_HEIGHT = {"480p": 480, "720p": 720, "1080p": 1080, "1440p": 1440, "4k": 2160}

DEFAULTS = {
    "duration_min": 0.5,
    "duration_tol": 0.15,          # +/-15% of requested duration
    "black_max": 0.05,             # >5% black frames fails
    "frozen_max": 0.02,            # motion (YAVG delta) at/below this = static
    "near_dup_sim": 0.98,          # cosine >= this flagged (advisory)
}


def _frame_stats(path):
    """Per-frame average luma via ffmpeg signalstats; returns black ratio + a
    motion score (mean inter-frame YAVG delta). None if ffmpeg/parse fails."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    try:
        r = subprocess.run([ff, "-hide_banner", "-i", path,
                            "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                            "-f", "null", "-"],
                           capture_output=True, text=True, timeout=120)
        out = r.stderr
    except Exception:
        return None
    vals = []
    for line in out.splitlines():
        if "lavfi.signalstats.YAVG" in line:
            try:
                vals.append(float(line.split("YAVG=")[1].split()[0]))
            except Exception:
                pass
    if len(vals) < 2:
        return None
    # signalstats YAVG uses the limited luma range (black=16, white=235), so a
    # truly black frame reads 16, not 0 — count <= 16 as black.
    black = sum(1 for v in vals if v <= 16) / len(vals)
    diffs = [abs(vals[i + 1] - vals[i]) for i in range(len(vals) - 1)]
    frozen = sum(diffs) / len(diffs)
    return {"black_frame_ratio": black, "frozen_score": round(frozen, 4),
            "n_frames": len(vals)}


def qa_video(path, spec=None, thresholds=None, approved_fps=None):
    """Return {ok, metrics, issues, advisories, kind} for a video file."""
    th = dict(DEFAULTS)
    if thresholds:
        th.update(thresholds)
    spec = spec or {}
    issues = []
    advisories = []

    base = analyze_video(path)
    fs = _frame_stats(path)
    metrics = dict(base)
    if fs:
        metrics["black_frame_ratio"] = round(fs["black_frame_ratio"], 4)
        metrics["frozen_score"] = fs["frozen_score"]
    else:
        metrics["black_frame_ratio"] = None
        metrics["frozen_score"] = None
        advisories.append("frame analysis unavailable (ffmpeg/ffprobe missing or "
                          "undecodable) — QA relaxed to decodability + duration only")

    # --- HARD GATES ---
    if not (base["codec"] and base["width"] > 0 and base["height"] > 0 and base["fps"] > 0):
        issues.append("video not decodable / missing stream info")
    dur = base["duration_sec"]
    requested = spec.get("duration")
    metrics["requested_duration"] = requested
    if requested:
        if dur < th["duration_min"]:
            issues.append(f"duration {dur}s < min {th['duration_min']}s")
        lo, hi = requested * (1 - th["duration_tol"]), requested * (1 + th["duration_tol"])
        if not (lo <= dur <= hi):
            issues.append(f"duration {dur}s outside requested {requested}s "
                          f"±{int(th['duration_tol'] * 100)}%")
    else:
        if dur < th["duration_min"]:
            issues.append(f"duration {dur}s < min {th['duration_min']}s")
    if fs and fs["black_frame_ratio"] > th["black_max"]:
        issues.append(f"black frames {fs['black_frame_ratio']:.2%} > {th['black_max']:.2%}")
    if fs and fs["frozen_score"] <= th["frozen_max"]:
        issues.append(f"frozen/static video (motion {fs['frozen_score']} <= "
                      f"{th['frozen_max']}) — not real footage")

    # --- SOFT ADVISORIES ---
    res = spec.get("resolution")
    if res:
        target_h = RES_HEIGHT.get(res)
        if target_h and base["height"] and base["height"] != target_h:
            advisories.append(f"resolution mismatch: requested {res} ({target_h}h) "
                              f"got {base['height']}h")
    if base["has_audio"]:
        advisories.append("video carries an audio track (assemble() mixes under "
                          "BGM/TTS, so this is usually fine)")

    # near-duplicate vs approved shots
    if approved_fps:
        fp = extract_video_fingerprint(path)
        sims = [cosine(fp, a) for a in approved_fps if a]
        if sims:
            mx = max(sims)
            metrics["near_dup_sim"] = round(mx, 3)
            if mx >= th["near_dup_sim"]:
                advisories.append(f"near-duplicate of an existing approved shot "
                                  f"(cosine={mx:.3f})")

    ok = len(issues) == 0
    return {"ok": ok, "metrics": metrics, "issues": issues,
            "advisories": advisories, "kind": "video"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--resolution", default=None)
    ap.add_argument("--strict", action="store_true", help="non-zero exit on FAIL")
    args = ap.parse_args()
    if not os.path.exists(args.path):
        print(f"FATAL: {args.path} not found", file=sys.stderr)
        sys.exit(2)
    spec = {"duration": args.duration, "resolution": args.resolution}
    res = qa_video(args.path, spec=spec)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if args.strict and not res["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
