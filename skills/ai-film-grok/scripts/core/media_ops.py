"""Shared media probe / register / normalize / frame-chain promote helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.film_io import load_manifest, save_manifest
from core.paths import valid_shot_id
from runtime_policy import sha256
from security_policy import SecurityPolicyError, safe_output_path
from util import require_json as read_json
from util import utc_now
from util.errors import FilmError
from util.subprocess import run


def media_duration(path: Path) -> float:
    """Fail-loud duration probe (shared with final/compose — no silent defaults)."""
    try:
        from media_duration import MediaDurationError, probe_duration_sec
    except ImportError:
        p = Path(path)
        if not p.is_file():
            raise FilmError(f"media missing for duration probe: {p}") from None
        result = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ]
        )
        raw = (result.stdout or "").strip()
        if not raw:
            raise FilmError(f"unreadable duration (empty ffprobe): {path}") from None
        return float(raw)
    try:
        return probe_duration_sec(path, label="aifilm")
    except MediaDurationError as exc:
        raise FilmError(str(exc)) from exc


_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")


def parse_mean_volume_db(text: str) -> float | None:
    """Parse ffmpeg volumedetect mean_volume from combined stdout/stderr text."""
    match = _MEAN_VOLUME_RE.search(text or "")
    return float(match.group(1)) if match else None


def probe_native_audio_mean_volume(
    path: Path,
    *,
    sample_sec: float | None = None,
    start_sec: float | None = None,
    strip_video: bool = False,
    timeout: float | None = 60.0,
    run_fn: Any | None = None,
) -> float | None:
    """Return media mean volume (dB), or None when ffmpeg cannot measure it.

    Single implementation for native-audio honesty and loudness probes.
    Pass ``run_fn`` (e.g. hub ``run``) so tests can patch the caller module.
    Optional ``sample_sec`` / ``start_sec`` limit decode window (compose path).
    """
    runner = run_fn or run
    cmd: list[str] = ["ffmpeg", "-hide_banner"]
    if start_sec is not None and float(start_sec) > 0:
        cmd.extend(["-ss", f"{float(start_sec):.3f}"])
    cmd.extend(["-i", str(path)])
    if sample_sec is not None and float(sample_sec) > 0:
        cmd.extend(["-t", f"{float(sample_sec):.3f}"])
    if strip_video:
        cmd.append("-vn")
    cmd.extend(["-af", "volumedetect", "-f", "null", "-"])
    try:
        if timeout is not None:
            try:
                result = runner(cmd, check=False, timeout=timeout)
            except TypeError:
                result = runner(cmd, check=False)
        else:
            result = runner(cmd, check=False)
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired, TimeoutError):
        return None
    text = f"{getattr(result, 'stderr', '') or ''}{getattr(result, 'stdout', '') or ''}"
    return parse_mean_volume_db(text)


def _register_media(
    *,
    shot_id: str,
    source: Path,
    dest_dir: Path,
    role: str,
    status: str,
    prompt_file: Path | None,
) -> dict[str, Any]:
    shot_id = valid_shot_id(shot_id)
    if not source.is_file():
        raise FilmError(f"Source missing: {source}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        dest = safe_output_path(
            dest_dir,
            f"{shot_id}{source.suffix.lower()}",
            suffixes={source.suffix.lower()},
            field="registered media filename",
        )
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    # Same-path short-circuit (source already at keyframes/shotXX or clips/shotXX)
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    record = {
        "shot_id": shot_id,
        "role": role,
        "status": status,
        "path": str(dest),
        "sha256": sha256(dest),
        "bytes": dest.stat().st_size,
        "registered_at": utc_now(),
        "provider": "grok-imagine",
    }
    if prompt_file and prompt_file.is_file():
        record["prompt_file"] = str(prompt_file)
        record["prompt_sha256"] = sha256(prompt_file)
    return record


def _auto_promote_last_to_next(
    root: Path,
    *,
    shot_id: str,
    clip_path: Path,
) -> dict[str, Any] | None:
    """After I2V register: promote last frame → next shot first keyframe when story serial.

    Lesson 2026-07-21: generation must follow actual last→first frames (wardrobe/pose),
    never re-open next still from full cast master on continue/undress chains.
    """
    try:
        from continuity_chain import (
            flatten_shots,
            next_shot_after,
            should_auto_promote_next,
            upsert_join,
        )
        from util import sha256_file as chain_sha
    except Exception:
        return None
    spec_path = root / "film-spec.json"
    if not spec_path.is_file() or not clip_path.is_file():
        return None
    try:
        spec = read_json(spec_path)
    except Exception:
        return None
    shots = flatten_shots(spec)
    prev = next((s for s in shots if str(s.get("id")) == str(shot_id)), None)
    nxt = next_shot_after(spec, shot_id)
    if not nxt:
        return {"ok": True, "skipped": True, "reason": "last shot — no promote"}
    next_id = str(nxt.get("id") or "")
    heat = str(spec.get("heat_scale") or "")
    do, why = should_auto_promote_next(prev, nxt, heat_scale=heat)
    # allow force off
    if spec.get("auto_promote_next") is False:
        return {"ok": True, "skipped": True, "reason": "auto_promote_next:false"}
    if not do:
        return {"ok": True, "skipped": True, "reason": why}
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return {"ok": False, "error": "ffmpeg/ffprobe required for auto promote"}
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(clip_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        duration = float((probe.stdout or "0").strip() or "0")
    except (subprocess.CalledProcessError, ValueError) as exc:
        return {"ok": False, "error": f"ffprobe: {exc}"}
    t = max(0.0, duration - 0.05) if duration > 0.1 else 0.0
    kf_dir = root / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    last_path = kf_dir / f"_last_{shot_id}.png"
    next_kf = kf_dir / f"{next_id}.png"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{t:.4f}",
                "-i",
                str(clip_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(last_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": f"ffmpeg extract last failed: {(exc.stderr or '')[-300:]}",
        }
    if not last_path.is_file() or last_path.stat().st_size < 32:
        return {"ok": False, "error": "empty last frame"}
    shutil.copy2(last_path, next_kf)
    seed = kf_dir / f"{next_id}-seed.png"
    shutil.copy2(last_path, seed)
    last_sha = chain_sha(last_path)
    first_sha = chain_sha(next_kf)
    join = upsert_join(
        root,
        from_id=str(shot_id),
        to_id=next_id,
        mode="continue",
        last_sha=last_sha,
        first_sha=first_sha,
        last_path=str(last_path),
        first_path=str(next_kf),
        checklist={
            "wardrobe": "carry last-frame costume (no re-dress)",
            "pose": "start from actual last frame pose",
            "note": why,
        },
    )
    # Register still seed as approved frame-chain input (not final art yet)
    try:
        manifest = load_manifest(root)
        stills = manifest.setdefault("stills", {})
        stills[next_id] = {
            "shot_id": next_id,
            "role": "keyframe",
            "status": "frame_chain_seed",
            "path": str(next_kf),
            "sha256": first_sha,
            "bytes": next_kf.stat().st_size,
            "registered_at": utc_now(),
            "provider": "frame-chain-promote",
            "identity_approved": True,
            "review_note": (
                f"AUTO promote last frame of {shot_id} → first of {next_id}; "
                f"{why}; do NOT regenerate from full cast; I2V input={next_kf}"
            ),
            "promoted_from": str(shot_id),
            "byte_identical_to_prev_last": True,
        }
        save_manifest(root, manifest)
    except Exception:
        pass
    return {
        "ok": True,
        "skipped": False,
        "reason": why,
        "from": shot_id,
        "to": next_id,
        "last_frame": str(last_path),
        "next_keyframe": str(next_kf),
        "byte_identical": last_sha == first_sha,
        "join": join,
        "agent_next": (
            f"I2V {next_id} MUST use image={next_kf} (actual last frame of {shot_id}). "
            "Forbidden: image_edit from full cast master (causes re-dress / pose break). "
            "Only image_edit the promoted frame for micro pose if cut required — keep wardrobe."
        ),
    }


def normalize_clip(
    src: Path, dest: Path, *, width: int, height: int, fps: int, duration: float | None
) -> None:
    """Re-encode to a common profile for safe concat."""
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p,setpts=PTS-STARTPTS"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
    ]
    if duration is not None and duration > 0:
        # If source shorter, slow slightly up to 1.33x then freeze-pad via tpad if needed.
        try:
            src_dur = media_duration(src)
        except Exception:
            src_dur = duration
        if src_dur > 0 and duration > src_dur * 1.001:
            factor = min(duration / src_dur, 1.34)
            # Apply setpts slowdown then trim/pad
            vf2 = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p,"
                f"setpts={factor}*PTS,tpad=stop_mode=clone:stop_duration={max(0.0, duration - src_dur * factor)}"
            )
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-vf",
                vf2,
                "-an",
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                str(dest),
            ]
            run(cmd)
            return
        cmd.extend(["-t", str(duration)])
    cmd.append(str(dest))
    run(cmd)
