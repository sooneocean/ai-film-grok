#!/usr/bin/env python3
"""Scene assembly bridge: combine approved video shots + matched BGM + optional
TTS voiceover into a final film cut via ffmpeg.

The three generation lanes live in separate libraries:
  - video shots  -> video-library/approved/<shot>.mp4   (Grok Video 1.5 / H3)
  - BGM bed      -> bgm-library/approved/<bgm>.flac      (ACE-Step)
  - voiceover    -> tts-evaluations/<sample>.mp3         (TTS engine samples)

assemble() is the bridge that mints a film_manifest.json timeline and composites
each segment with ffmpeg: the video track, a BGM bed matched by mood + energy
bucket (lowered under the dialogue), and an optional TTS voiceover overlaid on
top. Segments are then concatenated into the final film.

    python3 tools/assemble.py --auto --out films/demo.mp4
    python3 tools/assemble.py --auto --segments 3 --film-id ep01 --dry-run
    python3 tools/assemble.py --manifest film_manifest.json --out films/demo.mp4

Requires ffmpeg (the video lane's one external dep). On a machine without it,
--dry-run still builds + validates the manifest so the plan is inspectable.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from pipeline_lib import load_catalog, LIB as BGM_LIB, sha256_file
from video_pipeline_lib import load_vcatalog, VIDEO_LIB
from tts import choose_tts_engine

FILMS = os.path.join(ROOT, "films")
BGMS = os.path.join(BGM_LIB, "approved")
VIDS = os.path.join(VIDEO_LIB, "approved")
TTSDIR = os.path.join(ROOT, "tts-evaluations")


def energy_bucket(e):
    if e is None:
        return "mid"
    if e < 0.34:
        return "low"
    if e < 0.67:
        return "mid"
    return "high"


def _basename(p):
    return os.path.basename(p)


def match_bgm(mood, energy, bgm_cat):
    """Pick the best approved BGM bed for a shot: same mood + energy_bucket
    first, then same bucket, then closest energy. Returns asset dict or None."""
    approved = [a for a in bgm_cat.get("assets", {}).values()
                if a.get("status") == "approved"]
    if not approved:
        return None
    eb = energy_bucket(energy)
    same_mood = [a for a in approved if a.get("mood") == mood]
    pool = same_mood or approved
    same_bucket = [a for a in pool if energy_bucket(a.get("energy")) == eb]
    cand = same_bucket or pool
    cand.sort(key=lambda a: abs((a.get("energy") or 0) - (energy or 0)))
    return cand[0]


def match_tts(tts_manifest):
    """Pick an active TTS engine sample to use as voiceover (or None)."""
    eng = choose_tts_engine()
    if not eng:
        return None
    eid = eng[0]
    e = tts_manifest.get("engines", {}).get(eid, {})
    samples = e.get("samples", [])
    if not samples:
        return None
    s = samples[0]
    path = s.get("path") or os.path.join(TTSDIR, f"{eid}", _basename(s.get("file", "")))
    return {"engine": eid, "sample_id": s.get("sample_id"), "path": path}


def auto_manifest(segments, film_id="film-auto", bgm_cat=None, vcat=None,
                  tts_manifest=None):
    """Build a film_manifest.json from the approved libraries.

    Each segment pulls one approved video shot and matches a BGM bed (and an
    optional TTS voiceover). Returns the manifest dict.
    """
    bgm_cat = bgm_cat or load_catalog()
    vcat = vcat or load_vcatalog()
    tts_manifest = tts_manifest or _load_tts_manifest()
    v_approved = [a for a in vcat.get("assets", {}).values()
                  if a.get("status") == "approved"]
    if not v_approved:
        raise RuntimeError("no approved video shots in video-library; nothing to assemble")
    tts = match_tts(tts_manifest)
    segs = []
    for i in range(min(segments, len(v_approved))):
        a = v_approved[i]
        mood = a.get("mood", "cinematic")
        energy = a.get("energy", 0.5)
        bgm = match_bgm(mood, energy, bgm_cat)
        dur = (a.get("technical", {}) or {}).get("duration_sec") or 12.0
        segs.append({
            "index": i,
            "video_asset_id": a.get("asset_id"),
            "video_path": a.get("path"),
            "mood": mood,
            "energy": energy,
            "duration": dur,
            "bgm_asset_id": bgm.get("asset_id") if bgm else None,
            "bgm_path": bgm.get("path") if bgm else None,
            "tts": tts,
        })
    return {
        "schema": "aifilm-film-manifest-v1",
        "film_id": film_id,
        "created_at": _now(),
        "segments": segs,
        "outputs": {},
    }


def _load_tts_manifest():
    p = os.path.join(TTSDIR, "manifest.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _seg_ffmpeg(seg, tmpdir, dry_run, ff):
    """Composite one segment -> tmpdir/seg<i>.mp4. Returns the path or None."""
    vpath = os.path.join(VIDEO_LIB, seg["video_path"]) if seg.get("video_path") else None
    if not vpath or not os.path.exists(vpath):
        print(f"  [seg {seg['index']}] skip: video missing {vpath}")
        return None
    inputs = ["-i", vpath]
    audio_streams = []  # ffmpeg input labels like "[1:a]"
    ai = 1
    if seg.get("bgm_path"):
        bpath = os.path.join(BGM_LIB, seg["bgm_path"])
        if os.path.exists(bpath):
            inputs += ["-i", bpath]
            audio_streams.append(f"[{ai}:a]")
            ai += 1
    if seg.get("tts") and seg["tts"].get("path") and os.path.exists(seg["tts"]["path"]):
        inputs += ["-i", seg["tts"]["path"]]
        audio_streams.append(f"[{ai}:a]")
        ai += 1
    # build the audio mix filter (bgm quiet under, tts loud on top)
    if not audio_streams:
        af_filter = None
    elif len(audio_streams) == 1:
        af_filter = f"{audio_streams[0]}volume=0.35,apad[outa]"
    else:
        parts, labels = [], []
        for k, s in enumerate(audio_streams):
            lbl = f"[a{k}]"
            vol = "0.35" if k == 0 else "1.0"
            parts.append(f"{s}volume={vol},apad{lbl}")
            labels.append(lbl)
        af_filter = "".join(parts) + f"{''.join(labels)}amix=inputs={len(audio_streams)}:duration=first[outa]"
    dur = seg.get("duration", 12.0)
    out = os.path.join(tmpdir, f"seg{seg['index']}.mp4")
    if dry_run:
        print(f"  [seg {seg['index']}] (dry-run) ffmpeg -> {_basename(out)} "
              f"(dur={dur}s, bgm={bool(seg.get('bgm_path'))}, tts={bool(seg.get('tts'))})")
        return out
    cmd = [ff, "-y"] + inputs
    if af_filter:
        cmd += ["-filter_complex", af_filter, "-map", "0:v", "-map", "[outa]"]
    else:
        cmd += ["-map", "0:v"]
    cmd += ["-t", str(dur), "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [seg {seg['index']}] ffmpeg failed:\n{r.stderr[-400:]}")
        return None
    return out


def assemble(manifest, out, dry_run=False):
    """Composite the manifest's segments into `out` (a final film mp4)."""
    ff = shutil.which("ffmpeg")
    segs = manifest.get("segments", [])
    if not segs:
        print("manifest has no segments; nothing to assemble")
        return None
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if dry_run:
        print(f"(dry-run) would assemble {len(segs)} segments -> {out}")
        tmp = tempfile.mkdtemp()
        clips = [_seg_ffmpeg(s, tmp, True, ff) for s in segs]
        return None
    if not ff:
        print("ffmpeg not found; cannot composite. Build the manifest only (--dry-run).")
        return None
    tmp = tempfile.mkdtemp(prefix="aifilm-assemble-")
    try:
        clips = [_seg_ffmpeg(s, tmp, False, ff) for s in segs]
        clips = [c for c in clips if c]
        if not clips:
            print("no segments produced; aborting assemble")
            return None
        if len(clips) == 1:
            shutil.copy(clips[0], out)
        else:
            lst = os.path.join(tmp, "list.txt")
            with open(lst, "w", encoding="utf-8") as f:
                for c in clips:
                    f.write(f"file '{os.path.abspath(c)}'\n")
            r = subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                "-c:a", "aac", out], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"concat failed:\n{r.stderr[-400:]}")
                return None
        sha = sha256_file(out)
        manifest["outputs"] = {
            "file": os.path.relpath(out, ROOT),
            "sha256": sha,
            "segments": len(clips),
        }
        print(f"assembled {len(clips)} segments -> {out} (sha256 {sha[:12]}…)")
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true",
                    help="build manifest from approved libraries")
    ap.add_argument("--segments", type=int, default=3)
    ap.add_argument("--manifest", default=None, help="existing film_manifest.json")
    ap.add_argument("--out", default=os.path.join(FILMS, "demo.mp4"))
    ap.add_argument("--film-id", default="film-auto")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.manifest:
        manifest = json.load(open(args.manifest, encoding="utf-8"))
    elif args.auto:
        manifest = auto_manifest(args.segments, film_id=args.film_id)
    else:
        print("specify --auto or --manifest", file=sys.stderr)
        sys.exit(2)

    # always (re)write the manifest alongside the output for traceability
    mdir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(mdir, exist_ok=True)
    mpath = os.path.join(mdir, "film_manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"manifest ({len(manifest.get('segments', []))} segments) -> {mpath}")

    out = assemble(manifest, os.path.abspath(args.out), dry_run=args.dry_run)
    if out and not args.dry_run:
        print(f"FILM READY: {out}")


if __name__ == "__main__":
    main()
