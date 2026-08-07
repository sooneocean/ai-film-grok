"""Real-ESRGAN formal upscale — selects-after clip/path tool (default off).

Backends (priority):
1. realesrgan-ncnn-vulkan (portable; Mac Metal / Vulkan)
2. inference_realesrgan_video.py under AIFILM_REALESRGAN_ROOT (optional)

Never auto-downloads weights. Never auto-promotes. GPU-busy → zero submit.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from util import read_json, sha256_file, utc_now, write_json

SCHEMA_VERSION = 1
DEFAULT_MODEL = "realesr-animevideov3"
DEFAULT_SCALE = 2
DEFAULT_MIN_W = 704
DEFAULT_MIN_H = 1280
NCNN_CACHE = Path.home() / ".cache" / "realesrgan" / "ncnn"
WEIGHTS_CACHE = Path.home() / ".cache" / "realesrgan" / "weights"
DURATION_TOL_SEC = 0.12
FPS_TOL = 0.15


class UpscaleError(RuntimeError):
    """Formal upscale failed or was blocked by policy."""


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def resolve_ncnn_binary() -> Path | None:
    env = _env_path("AIFILM_REALESRGAN_NCNN")
    if env and env.is_file():
        return env
    which = shutil.which("realesrgan-ncnn-vulkan")
    if which:
        return Path(which).resolve()
    cand = NCNN_CACHE / "realesrgan-ncnn-vulkan"
    if cand.is_file() and os.access(cand, os.X_OK):
        return cand.resolve()
    return None


def resolve_ncnn_models_dir() -> Path | None:
    env = _env_path("AIFILM_REALESRGAN_NCNN_MODELS")
    if env and env.is_dir():
        return env
    cand = NCNN_CACHE / "models"
    if cand.is_dir():
        return cand.resolve()
    return None


def resolve_weights_dir() -> Path | None:
    env = _env_path("AIFILM_REALESRGAN_WEIGHTS")
    if env and env.is_dir():
        return env
    if WEIGHTS_CACHE.is_dir():
        return WEIGHTS_CACHE.resolve()
    return None


def backend_status() -> dict[str, Any]:
    ncnn = resolve_ncnn_binary()
    models = resolve_ncnn_models_dir()
    weights = resolve_weights_dir()
    py_script = None
    root = _env_path("AIFILM_REALESRGAN_ROOT")
    if root:
        s = root / "inference_realesrgan_video.py"
        if s.is_file():
            py_script = str(s)
    ready = bool(ncnn and models)
    return {
        "ncnn_binary": str(ncnn) if ncnn else None,
        "ncnn_models": str(models) if models else None,
        "weights_dir": str(weights) if weights else None,
        "inference_script": py_script,
        "backend_ready": ready,
        "preferred_backend": "ncnn" if ready else None,
    }


def fingerprint_assets() -> dict[str, Any]:
    """SHA-256 of known weight / ncnn model files if present."""
    out: dict[str, str] = {}
    wdir = resolve_weights_dir()
    if wdir:
        for name in (
            "realesr-animevideov3.pth",
            "RealESRGAN_x4plus_anime_6B.pth",
            "RealESRGAN_x4plus.pth",
        ):
            p = wdir / name
            if p.is_file():
                out[name] = sha256_file(p)
    mdir = resolve_ncnn_models_dir()
    if mdir:
        for name in (
            "realesr-animevideov3-x2.bin",
            "realesr-animevideov3-x2.param",
            "realesr-animevideov3-x4.bin",
            "realesrgan-x4plus-anime.bin",
        ):
            p = mdir / name
            if p.is_file():
                out[name] = sha256_file(p)
    return out


def gpu_busy(*, root: Path | None = None) -> tuple[bool, str]:
    """Soft busy gate. Env AIFILM_GPU_BUSY=1 forces busy; own-gpu env bypasses soft lease."""
    if os.environ.get("AIFILM_I_OWN_THE_GPU", "").strip() in {"1", "true", "yes"}:
        return False, "i_own_the_gpu"
    if os.environ.get("AIFILM_GPU_BUSY", "").strip() in {"1", "true", "yes"}:
        return True, "AIFILM_GPU_BUSY"
    if root is not None:
        try:
            from workflow_pack import gpu_lease_status

            st = gpu_lease_status(root)
            if isinstance(st, Mapping) and st.get("held") and not st.get("owned_by_self"):
                return True, "gpu_lease_held_by_other"
        except Exception:  # noqa: BLE001
            pass
    return False, "free"


def probe_media(path: Path) -> dict[str, Any]:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise UpscaleError(f"media missing: {path}")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height,r_frame_rate,duration:format=duration",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise UpscaleError(f"ffprobe failed: {(proc.stderr or '')[:200]}")
    data = json.loads(proc.stdout or "{}")
    width = height = 0
    fps = 0.0
    has_audio = False
    duration = 0.0
    for stream in data.get("streams") or []:
        if not isinstance(stream, Mapping):
            continue
        if stream.get("codec_type") == "video" and not width:
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            rate = str(stream.get("r_frame_rate") or "0/1")
            if "/" in rate:
                num, den = rate.split("/", 1)
                try:
                    fps = float(num) / float(den) if float(den) else 0.0
                except ValueError:
                    fps = 0.0
            with contextlib.suppress(TypeError, ValueError):
                duration = float(stream.get("duration") or duration or 0)
        if stream.get("codec_type") == "audio":
            has_audio = True
    fmt = data.get("format") if isinstance(data.get("format"), Mapping) else {}
    if not duration:
        try:
            duration = float(fmt.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "fps": fps,
        "duration_sec": duration,
        "has_audio": has_audio,
        "sha256": sha256_file(path),
    }


def _pad_to_canvas(
    src: Path,
    dest: Path,
    *,
    width: int,
    height: int,
) -> None:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
    if proc.returncode != 0 or not dest.is_file():
        cmd_a = cmd[:-3] + ["-c:a", "aac", "-b:a", "192k", str(dest)]
        # rebuild carefully
        cmd_a = [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(dest),
        ]
        proc = subprocess.run(cmd_a, capture_output=True, text=True, check=False, timeout=600)
    if proc.returncode != 0 or not dest.is_file():
        raise UpscaleError(f"pad/scale failed: {(proc.stderr or '')[:300]}")


def ffmpeg_geometry_upscale(
    src: Path,
    dest: Path,
    *,
    min_width: int = DEFAULT_MIN_W,
    min_height: int = DEFAULT_MIN_H,
) -> dict[str, Any]:
    """Baseline A for canary — same policy as H3 geometry floor."""
    src = Path(src).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    _pad_to_canvas(src, dest, width=min_width, height=min_height)
    meta = probe_media(dest)
    meta.update(
        {
            "backend": "ffmpeg_geometry",
            "wall_sec": round(time.perf_counter() - t0, 3),
            "source": str(src),
        }
    )
    return meta


def _extract_frames(src: Path, frames_dir: Path, *, fps: float) -> int:
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "frame%08d.png")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vsync",
        "0",
        "-qscale:v",
        "1",
        pattern,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
    if proc.returncode != 0:
        raise UpscaleError(f"frame extract failed: {(proc.stderr or '')[:300]}")
    n = len(list(frames_dir.glob("frame*.png")))
    if n < 1:
        raise UpscaleError("frame extract produced zero frames")
    return n


def _merge_frames(
    frames_dir: Path,
    audio_src: Path,
    dest: Path,
    *,
    fps: float,
    has_audio: bool,
) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "frame%08d.png")
    rate = f"{fps:.6f}".rstrip("0").rstrip(".") if fps > 0 else "24"
    if has_audio:
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            rate,
            "-i",
            pattern,
            "-i",
            str(audio_src),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-shortest",
            str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
        if proc.returncode == 0 and dest.is_file():
            return "copy"
        cmd_a = [
            "ffmpeg",
            "-y",
            "-framerate",
            rate,
            "-i",
            pattern,
            "-i",
            str(audio_src),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(dest),
        ]
        proc = subprocess.run(cmd_a, capture_output=True, text=True, check=False, timeout=600)
        if proc.returncode == 0 and dest.is_file():
            return "aac_reencode"
        # fall through strip
    cmd_v = [
        "ffmpeg",
        "-y",
        "-framerate",
        rate,
        "-i",
        pattern,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(dest),
    ]
    proc = subprocess.run(cmd_v, capture_output=True, text=True, check=False, timeout=600)
    if proc.returncode != 0 or not dest.is_file():
        raise UpscaleError(f"frame merge failed: {(proc.stderr or '')[:300]}")
    return "strip_partial" if has_audio else "none"


def _ncnn_upscale_frames(
    in_dir: Path,
    out_dir: Path,
    *,
    model: str,
    scale: int,
) -> None:
    binary = resolve_ncnn_binary()
    models = resolve_ncnn_models_dir()
    if not binary or not models:
        raise UpscaleError("ncnn backend not ready (binary or models missing)")
    out_dir.mkdir(parents=True, exist_ok=True)
    # map friendly names
    model_name = model
    if model in {"RealESRGAN_x4plus_anime_6B", "realesrgan-x4plus-anime"}:
        model_name = "realesrgan-x4plus-anime"
    elif model in {"RealESRGAN_x4plus", "realesrgan-x4plus"}:
        model_name = "realesrgan-x4plus"
    elif model.startswith("realesr-animevideov3"):
        model_name = "realesr-animevideov3"
    cmd = [
        str(binary),
        "-i",
        str(in_dir),
        "-o",
        str(out_dir),
        "-n",
        model_name,
        "-s",
        str(scale),
        "-m",
        str(models),
        "-f",
        "png",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=3600)
    if proc.returncode != 0:
        raise UpscaleError(f"ncnn upscale failed: {(proc.stderr or proc.stdout or '')[:400]}")
    # normalize names: some builds preserve names, ensure frame%08d.png sequence
    outs = sorted(out_dir.glob("*.png"))
    if not outs:
        raise UpscaleError("ncnn produced no png frames")
    # if names already frame*, ok; else rename sorted order
    if not all(re.match(r"frame\d+\.png", p.name) for p in outs):
        for i, p in enumerate(outs, start=1):
            target = out_dir / f"frame{i:08d}.png"
            if p.resolve() != target.resolve():
                p.rename(target)


def upscale_video(
    src: Path,
    dest: Path,
    *,
    model: str = DEFAULT_MODEL,
    scale: int = DEFAULT_SCALE,
    target_width: int | None = DEFAULT_MIN_W,
    target_height: int | None = DEFAULT_MIN_H,
    root: Path | None = None,
    force_gpu: bool = False,
) -> dict[str, Any]:
    """Upscale one video; optional pad to target canvas. Does not promote."""
    src = Path(src).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    if not force_gpu:
        busy, reason = gpu_busy(root=root)
        if busy:
            return {
                "ok": False,
                "gpu_busy_skipped": True,
                "reason": reason,
                "source": str(src),
            }
    status = backend_status()
    if not status["backend_ready"]:
        raise UpscaleError("Real-ESRGAN backend not ready; run realesrgan_probe / install ncnn")

    src_meta = probe_media(src)
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="aifilm-esrgan-") as tmp:
        tmp_path = Path(tmp)
        in_frames = tmp_path / "in"
        out_frames = tmp_path / "out"
        n = _extract_frames(src, in_frames, fps=float(src_meta["fps"] or 24))
        _ncnn_upscale_frames(in_frames, out_frames, model=model, scale=scale)
        raw_out = tmp_path / "raw.mp4"
        audio_policy = _merge_frames(
            out_frames,
            src,
            raw_out,
            fps=float(src_meta["fps"] or 24),
            has_audio=bool(src_meta["has_audio"]),
        )
        if target_width and target_height:
            _pad_to_canvas(raw_out, dest, width=int(target_width), height=int(target_height))
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw_out, dest)

    out_meta = probe_media(dest)
    # conservation checks
    d_src = float(src_meta["duration_sec"] or 0)
    d_out = float(out_meta["duration_sec"] or 0)
    if d_src > 0 and abs(d_out - d_src) > max(DURATION_TOL_SEC, d_src * 0.05):
        raise UpscaleError(
            f"duration drift src={d_src:.3f}s out={d_out:.3f}s exceeds tolerance"
        )
    receipt = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "kind": "ai-film-upscale-receipt",
        "created_at": utc_now(),
        "backend": "ncnn",
        "model": model,
        "scale": scale,
        "source_path": str(src),
        "source_sha256": src_meta["sha256"],
        "source_width": src_meta["width"],
        "source_height": src_meta["height"],
        "output_path": str(dest),
        "output_sha256": out_meta["sha256"],
        "width": out_meta["width"],
        "height": out_meta["height"],
        "fps": out_meta["fps"],
        "duration_sec": out_meta["duration_sec"],
        "audio_policy": audio_policy,
        "frames": n,
        "wall_sec": round(time.perf_counter() - t0, 3),
        "gpu_busy_skipped": False,
        "promoted": False,
        "fingerprints": fingerprint_assets(),
        "target_width": target_width,
        "target_height": target_height,
    }
    return receipt


def _iter_clip_paths(root: Path) -> list[dict[str, Any]]:
    """Collect candidate media from manifest preferred paths + takes/."""
    root = Path(root).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(path: Path, *, shot_id: str | None, role: str) -> None:
        p = path.expanduser().resolve()
        key = str(p)
        if key in seen or not p.is_file():
            return
        if p.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
            return
        seen.add(key)
        try:
            meta = probe_media(p)
        except UpscaleError:
            return
        below = int(meta["width"] or 0) < DEFAULT_MIN_W or int(meta["height"] or 0) < DEFAULT_MIN_H
        rows.append(
            {
                "shot_id": shot_id,
                "path": str(p),
                "role": role,
                "width": meta["width"],
                "height": meta["height"],
                "duration_sec": meta["duration_sec"],
                "below_floor": below,
                "sha256": meta["sha256"],
            }
        )

    manifest_path = root / "manifest.json"
    man = read_json(manifest_path) if manifest_path.is_file() else None
    if isinstance(man, Mapping):
        clips = man.get("clips") or {}
        if isinstance(clips, Mapping):
            for sid, clip in clips.items():
                if not isinstance(clip, Mapping):
                    continue
                for key in ("path", "preferred_path", "media_path", "file"):
                    raw = clip.get(key)
                    if raw:
                        add(root / str(raw) if not Path(str(raw)).is_absolute() else Path(str(raw)),
                            shot_id=str(sid), role=f"manifest.{key}")
        # list form
        if isinstance(clips, list):
            for clip in clips:
                if not isinstance(clip, Mapping):
                    continue
                sid = str(clip.get("shot_id") or clip.get("id") or "")
                raw = clip.get("path") or clip.get("preferred_path")
                if raw:
                    p = Path(str(raw))
                    add(p if p.is_absolute() else root / p, shot_id=sid or None, role="manifest.list")

    takes = root / "takes"
    if takes.is_dir():
        for p in sorted(takes.rglob("*.mp4")):
            # skip already esrgan outputs as sources by default
            if "_esrgan_" in p.name:
                continue
            sid = p.parent.name if p.parent != takes else p.stem
            add(p, shot_id=sid, role="takes")

    # preferred-only filter flag applied by plan
    return rows


def plan_upscale(
    root: Path | str,
    *,
    preferred_only: bool = True,
    include_at_floor: bool = False,
    paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    status = backend_status()
    candidates: list[dict[str, Any]] = []
    if paths:
        for raw in paths:
            p = Path(raw).expanduser().resolve()
            meta = probe_media(p)
            below = int(meta["width"] or 0) < DEFAULT_MIN_W or int(meta["height"] or 0) < DEFAULT_MIN_H
            candidates.append(
                {
                    "shot_id": p.stem,
                    "path": str(p),
                    "role": "explicit",
                    "width": meta["width"],
                    "height": meta["height"],
                    "duration_sec": meta["duration_sec"],
                    "below_floor": below,
                    "sha256": meta["sha256"],
                }
            )
    else:
        candidates = _iter_clip_paths(root_p)
        if preferred_only:
            candidates = [c for c in candidates if str(c.get("role", "")).startswith("manifest")]
        if not include_at_floor:
            candidates = [c for c in candidates if c.get("below_floor")]

    busy, busy_reason = gpu_busy(root=root_p)
    return {
        "ok": True,
        "kind": "ai-film-upscale-plan",
        "schema_version": SCHEMA_VERSION,
        "root": str(root_p),
        "created_at": utc_now(),
        "backend": status,
        "gpu_busy": busy,
        "gpu_busy_reason": busy_reason,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "defaults": {
            "model": DEFAULT_MODEL,
            "scale": DEFAULT_SCALE,
            "target": f"{DEFAULT_MIN_W}x{DEFAULT_MIN_H}",
            "gfpgan": False,
            "auto_promote": False,
        },
        "fingerprints": fingerprint_assets(),
    }


def run_upscale_batch(
    root: Path | str,
    *,
    paths: Sequence[str] | None = None,
    shot_ids: Sequence[str] | None = None,
    max_items: int = 1,
    model: str = DEFAULT_MODEL,
    scale: int = DEFAULT_SCALE,
    target_width: int = DEFAULT_MIN_W,
    target_height: int = DEFAULT_MIN_H,
    preferred_only: bool = True,
    include_at_floor: bool = False,
    execute: bool = False,
    force_gpu: bool = False,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    plan = plan_upscale(
        root_p,
        preferred_only=preferred_only,
        include_at_floor=include_at_floor,
        paths=paths,
    )
    cands = list(plan.get("candidates") or [])
    if shot_ids:
        want = {str(s) for s in shot_ids}
        cands = [c for c in cands if str(c.get("shot_id")) in want]
    max_items = max(0, int(max_items))
    cands = cands[:max_items]
    if not execute:
        return {
            "ok": True,
            "kind": "ai-film-upscale-run",
            "dry_run": True,
            "would_run": cands,
            "count": len(cands),
            "backend": plan.get("backend"),
            "gpu_busy": plan.get("gpu_busy"),
        }

    busy, reason = gpu_busy(root=root_p)
    if busy and not force_gpu:
        return {
            "ok": False,
            "kind": "ai-film-upscale-run",
            "gpu_busy_skipped": True,
            "reason": reason,
            "count": 0,
            "results": [],
        }

    out_dir = root_p / "takes" / "_upscale"
    receipt_dir = root_p / "receipts" / "upscale"
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for row in cands:
        src = Path(str(row["path"]))
        sid = str(row.get("shot_id") or src.stem)
        dest = out_dir / f"{sid}_esrgan_s{scale}.mp4"
        try:
            rec = upscale_video(
                src,
                dest,
                model=model,
                scale=scale,
                target_width=target_width,
                target_height=target_height,
                root=root_p,
                force_gpu=force_gpu,
            )
        except UpscaleError as exc:
            rec = {"ok": False, "error": str(exc), "source": str(src), "shot_id": sid}
        rec["shot_id"] = sid
        rpath = receipt_dir / f"{sid}.json"
        write_json(rpath, rec)
        rec["receipt_path"] = str(rpath)
        results.append(rec)

    batch = {
        "ok": all(r.get("ok") for r in results) if results else False,
        "kind": "ai-film-upscale-batch",
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "root": str(root_p),
        "model": model,
        "scale": scale,
        "count": len(results),
        "results": results,
        "promoted": False,
    }
    write_json(root_p / "receipts" / "upscale-batch.json", batch)
    return batch


def promote_upscale(
    root: Path | str,
    *,
    shot_id: str,
    source: Path | str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Human promote: copy esrgan output into takes/<shot>/ as preferred candidate file.

    Does not silently rewrite manifest.clips — writes promote receipt for register-clip.
    """
    root_p = Path(root).expanduser().resolve()
    sid = str(shot_id).strip()
    if source:
        src = Path(source).expanduser().resolve()
    else:
        cand = root_p / "takes" / "_upscale" / f"{sid}_esrgan_s{DEFAULT_SCALE}.mp4"
        # also accept any scale
        if not cand.is_file():
            hits = sorted((root_p / "takes" / "_upscale").glob(f"{sid}_esrgan_s*.mp4"))
            if not hits:
                raise UpscaleError(f"no upscale output for shot {sid}")
            src = hits[-1]
        else:
            src = cand
    if not src.is_file():
        raise UpscaleError(f"promote source missing: {src}")
    dest_dir = root_p / "takes" / sid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    meta = probe_media(dest)
    receipt = {
        "ok": True,
        "kind": "ai-film-upscale-promote",
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "shot_id": sid,
        "source_path": str(src),
        "promoted_path": str(dest),
        "sha256": meta["sha256"],
        "width": meta["width"],
        "height": meta["height"],
        "note": note,
        "next_step": (
            f'aifilm register-clip --root "{root_p}" --shot-id {sid} '
            f'--path "{dest}" --status approved --review-receipt <human>'
        ),
        "auto_register": False,
    }
    rpath = root_p / "receipts" / "upscale" / f"{sid}.promote.json"
    rpath.parent.mkdir(parents=True, exist_ok=True)
    write_json(rpath, receipt)
    receipt["receipt_path"] = str(rpath)
    return receipt


def run_canary_ab(
    src: Path | str,
    out_dir: Path | str,
    *,
    scale: int = 2,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """A/B: ffmpeg geometry vs Real-ESRGAN; writes receipts under out_dir."""
    src_p = Path(src).expanduser().resolve()
    out_p = Path(out_dir).expanduser().resolve()
    out_p.mkdir(parents=True, exist_ok=True)
    a_path = out_p / "a_ffmpeg_704x1280.mp4"
    b_path = out_p / "b_realesrgan_s2.mp4"
    a_meta = ffmpeg_geometry_upscale(src_p, a_path)
    b_rec = upscale_video(
        src_p,
        b_path,
        model=model,
        scale=scale,
        target_width=DEFAULT_MIN_W,
        target_height=DEFAULT_MIN_H,
        force_gpu=True,
    )
    report = {
        "ok": bool(b_rec.get("ok")),
        "kind": "ai-film-upscale-canary-ab",
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "source": probe_media(src_p),
        "A_ffmpeg": a_meta,
        "B_realesrgan": b_rec,
        "fingerprints": fingerprint_assets(),
        "backend": backend_status(),
        "verdict_notes": [
            "Human must compare sharpness/flicker/face; mean should not drive promote",
            "B should be >=704x1280 after pad; native SR may be 704x1216 before pad",
        ],
    }
    write_json(out_p / "canary-ab.json", report)
    # also drop under registry/evidence when path is skill-local
    return report


def film_upscale_enabled(root: Path | str) -> bool:
    root_p = Path(root).expanduser().resolve()
    for name in ("film-spec.json", "film_spec.json"):
        data = read_json(root_p / name)
        if isinstance(data, Mapping):
            up = data.get("upscale")
            if isinstance(up, Mapping) and up.get("enabled") is True:
                return True
            if data.get("upscale_enabled") is True:
                return True
    if os.environ.get("AIFILM_UPSCALE", "").strip() in {"1", "true", "yes"}:
        return True
    return False
