#!/usr/bin/env python3
"""Shared, self-contained helpers for the aifilm VIDEO lane.

Mirrors tools/pipeline_lib.py (bgm lane) but for video shot assets. No
third-party deps (stdlib only); ffprobe/ffmpeg are used lazily by analyze_video
and qa_video when present — the one external dependency the video lane needs.
Absent on a bare machine, the pipeline degrades to advisory QA instead of
crashing. Centralises paths, load/save with backup, sha256, a stdlib-only
video fingerprint fallback, and ffprobe stream analysis.
"""
import json
import os
import shutil
import hashlib
import subprocess

from pipeline_lib import (VCAT, VGAP, VJOBS, now_iso)

VALID_MODES = {"t2v", "i2v", "r2v"}


def load_vcatalog():
    if not os.path.exists(VCAT):
        return {"schema": "aifilm-video-library-v1", "revision": 0, "assets": {}}
    return json.load(open(VCAT, encoding="utf-8"))


def save_vcatalog(cat, backup=True):
    if backup:
        shutil.copy(VCAT, VCAT + ".bak")
    with open(VCAT, "w", encoding="utf-8") as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)


def load_vgaps():
    if not os.path.exists(VGAP):
        return []
    return [json.loads(l) for l in open(VGAP, encoding="utf-8") if l.strip()]


def save_vgaps(gaps, backup=True):
    if backup:
        shutil.copy(VGAP, VGAP + ".bak")
    with open(VGAP, "w", encoding="utf-8") as f:
        for g in gaps:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")


def load_vjobs():
    if not os.path.exists(VJOBS):
        return []
    return [json.loads(l) for l in open(VJOBS, encoding="utf-8") if l.strip()]


def save_vjobs(jobs, backup=True):
    if backup and os.path.exists(VJOBS):
        shutil.copy(VJOBS, VJOBS + ".bak")
    with open(VJOBS, "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")


def bump(cat):
    cat["revision"] = cat.get("revision", 0) + 1
    cat["updated_at"] = now_iso()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def extract_video_fingerprint(path, bins=64):
    """Stdlib-only crude byte-envelope fingerprint (fallback).

    Real generators should return a proper perceptual video fingerprint; this
    is the deterministic, cosine-comparable fallback so ingested assets still
    satisfy the catalog contract (technical.fingerprint must be list[number]).
    Samples the file at fixed offsets and normalizes byte means to 0..1.
    """
    try:
        sz = os.path.getsize(path)
    except OSError:
        return [0.0] * bins
    if sz == 0:
        return [0.0] * bins
    step = max(1, sz // (bins * 2))
    feats = []
    with open(path, "rb") as f:
        for i in range(bins):
            f.seek(min(sz - 1, i * step))
            chunk = f.read(max(1, step))
            feats.append(sum(chunk) / len(chunk) / 255.0 if chunk else 0.0)
    mx = max(feats) or 1.0
    return [x / mx for x in feats]


def analyze_video(path):
    """ffprobe-based stream analysis: codec, width, height, fps, duration, audio.

    Returns a dict; if ffprobe is missing or the file is undecodable, returns
    zeroed fields (callers surface that as an advisory, never a crash)."""
    ff = shutil.which("ffprobe")
    base = {"codec": None, "width": 0, "height": 0, "fps": 0.0,
            "duration_sec": 0.0, "has_audio": False}
    if not ff:
        return base
    try:
        r = subprocess.run([ff, "-v", "quiet", "-print_format", "json",
                            "-show_format", "-show_streams", path],
                           capture_output=True, text=True, timeout=60)
        info = json.loads(r.stdout)
    except Exception:
        return base
    fmt = info.get("format", {})
    try:
        dur = float(fmt.get("duration", 0))
    except (TypeError, ValueError):
        dur = 0.0
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    width = int(v.get("width", 0)) if v else 0
    height = int(v.get("height", 0)) if v else 0
    codec = v.get("codec_name") if v else None
    fps = 0.0
    if v:
        fr = v.get("avg_frame_rate", "0/1")
        try:
            n, d = fr.split("/")
            fps = float(n) / float(d) if float(d) else 0.0
        except (ValueError, ZeroDivisionError):
            fps = 0.0
    return {"codec": codec, "width": width, "height": height,
            "fps": round(fps, 3), "duration_sec": round(dur, 3),
            "has_audio": has_audio}
