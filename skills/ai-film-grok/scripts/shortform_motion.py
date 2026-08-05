#!/usr/bin/env python3
"""Deterministic layer-motion plans for approved shortform stills and cutouts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from util import canonical_json_sha256, utc_now, write_json


class ShortformMotionError(ValueError):
    pass


_SHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
_PACKAGE_NAME = "shortform-package.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file(root: Path, value: str, *, label: str) -> Path:
    """Resolve existing evidence without allowing symlinks or root escapes."""
    raw = Path(value).expanduser()
    absolute = raw if raw.is_absolute() else root / raw
    resolved = absolute.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ShortformMotionError(f"{label} must be a regular file inside root") from exc
    lexical_root = next(
        (parent for parent in absolute.parents if parent.exists() and parent.samefile(root)), None
    )
    if lexical_root is None:
        raise ShortformMotionError(f"{label} must be a regular file inside root")
    relative = absolute.relative_to(lexical_root)
    current = lexical_root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ShortformMotionError(f"{label} must not use a symlinked path component")
    if not resolved.is_file():
        raise ShortformMotionError(f"{label} must be a regular project file")
    return resolved


def _safe_output(root: Path, value: Path, *, label: str) -> Path:
    raw = value.expanduser()
    absolute = raw if raw.is_absolute() else root / raw
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise ShortformMotionError(f"{label} must live inside project root") from exc
    current = root
    for component in relative.parts[:-1]:
        current = current / component
        if current.is_symlink():
            raise ShortformMotionError(f"{label} parent must not be a symlink")
    if absolute.is_symlink():
        raise ShortformMotionError(f"{label} must not be a symlink")
    resolved = absolute.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ShortformMotionError(f"{label} escapes project root") from exc
    return resolved


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShortformMotionError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ShortformMotionError(f"{label} must be a JSON object")
    return value


def build_plan(
    root: Path | str, *, base: Path, layers: list[dict[str, Any]], shot_id: str
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    if not _SHOT_ID.fullmatch(shot_id):
        raise ShortformMotionError("shot_id must be a safe filename token")
    base = _safe_file(root, str(base), label="base")
    normalized: list[dict[str, Any]] = []
    allowed = {"fly_in", "drop", "pop_settle", "slap"}
    for index, layer in enumerate(layers, 1):
        path = _safe_file(root, str(layer.get("path") or ""), label=f"layer {index}")
        entrance = str(layer.get("entrance") or "pop_settle")
        if entrance not in allowed:
            raise ShortformMotionError(f"unsupported entrance {entrance}")
        normalized.append(
            {
                "id": str(layer.get("id") or f"layer{index}"),
                "path": str(path.relative_to(root)),
                "sha256": _sha256(path),
                "entrance": entrance,
                "rest_position": layer.get("rest_position") or [0.5, 0.5],
                "scale": float(layer.get("scale") or 0.35),
                "sway": float(layer.get("sway") or 0.0),
                "pulse": float(layer.get("pulse") or 0.0),
            }
        )
    plan = {
        "schema_version": 1,
        "kind": "shortform-motion-plan",
        "shot_id": shot_id,
        "base": {"path": str(base.relative_to(root)), "sha256": _sha256(base)},
        "layers": normalized,
        "backdrop_policy": "base_with_local_blur_under_unsettled_layers",
        "camera": {"zoom": "slow", "impact_shake": True, "overscan_required": True},
        "created_at": utc_now(),
    }
    path = root / "receipts" / "shortform-motion" / f"{shot_id}.json"
    write_json(path, plan)
    plan["path"] = str(path)
    return plan


def _motion_position(layer: dict[str, Any], *, width: int, height: int) -> tuple[str, str]:
    position = layer.get("rest_position") or [0.5, 0.5]
    if (
        not isinstance(position, list)
        or len(position) != 2
        or any(not isinstance(value, (int, float)) or value < 0 or value > 1 for value in position)
    ):
        raise ShortformMotionError("layer rest_position must be two normalized values")
    x = float(position[0]) * width
    y = float(position[1]) * height
    entrance = layer["entrance"]
    if entrance == "fly_in":
        x_expr = f"if(lt(t,0.55),-w+({x:.3f}+w)*t/0.55,{x:.3f})"
        y_expr = f"{y:.3f}"
    elif entrance == "drop":
        x_expr = f"{x:.3f}"
        y_expr = f"if(lt(t,0.55),-h+({y:.3f}+h)*t/0.55,{y:.3f})"
    elif entrance == "slap":
        x_expr = f"{x:.3f}+if(lt(t,0.35),sin(t*55)*24*(1-t/0.35),0)"
        y_expr = f"{y:.3f}"
    else:  # pop_settle
        x_expr = f"{x:.3f}"
        y_expr = f"{y:.3f}+if(lt(t,0.45),sin(t*35)*18*(1-t/0.45),0)"
    sway = float(layer.get("sway") or 0.0)
    if sway:
        x_expr += f"+sin(t*2.4)*{sway * width:.3f}"
    return x_expr, y_expr


def render_plan(
    root: Path | str,
    *,
    plan: Path,
    duration_sec: float,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    out: Path | None = None,
) -> dict[str, Any]:
    """Render one local, deterministic motion candidate from approved image layers."""
    root = Path(root).expanduser().resolve()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ShortformMotionError("ffmpeg and ffprobe are required for local motion")
    if not 1.0 <= duration_sec <= 9.5:
        raise ShortformMotionError("motion duration must be between 1 and 9.5 seconds")
    if not 24 <= fps <= 60 or min(width, height) < 256 or max(width, height) > 4096:
        raise ShortformMotionError("fps must be 24–60 and canvas dimensions 256–4096")
    if width % 2 or height % 2:
        raise ShortformMotionError("canvas dimensions must be even")
    plan_path = _safe_file(root, str(plan), label="motion plan")
    plan_data = _load_json(plan_path, label="motion plan")
    if plan_data.get("kind") != "shortform-motion-plan" or not _SHOT_ID.fullmatch(
        str(plan_data.get("shot_id") or "")
    ):
        raise ShortformMotionError("invalid shortform motion plan")
    package_path = root / _PACKAGE_NAME
    package = _load_json(package_path, label="shortform package")
    if package.get("kind") != "shortform-director-package":
        raise ShortformMotionError("invalid shortform package")
    if package.get("reviews", {}).get("plan", {}).get("status") != "approved":
        raise ShortformMotionError("approve the shortform plan before rendering local motion")
    shot_ids = {
        str(shot.get("id"))
        for beat in package.get("beats") or []
        if isinstance(beat, dict)
        for shot in beat.get("shots") or []
        if isinstance(shot, dict)
    }
    shot_id = str(plan_data["shot_id"])
    if shot_id not in shot_ids:
        raise ShortformMotionError("motion plan shot_id is not in the shortform package")
    base_data = plan_data.get("base") if isinstance(plan_data.get("base"), dict) else {}
    base = _safe_file(root, str(base_data.get("path") or ""), label="motion base")
    if _sha256(base) != base_data.get("sha256"):
        raise ShortformMotionError("motion base hash changed")
    layers = plan_data.get("layers")
    if not isinstance(layers, list):
        raise ShortformMotionError("motion layers must be a list")
    layer_files: list[Path] = []
    for index, layer in enumerate(layers, 1):
        if not isinstance(layer, dict):
            raise ShortformMotionError(f"layer {index} is invalid")
        scale = layer.get("scale")
        if not isinstance(scale, (int, float)) or not 0.05 <= scale <= 1.0:
            raise ShortformMotionError(f"layer {index} scale must be between 0.05 and 1.0")
        layer_path = _safe_file(root, str(layer.get("path") or ""), label=f"layer {index}")
        if _sha256(layer_path) != layer.get("sha256"):
            raise ShortformMotionError(f"layer {index} hash changed")
        layer_files.append(layer_path)
    target = _safe_output(
        root,
        out or root / "candidates" / "shortform-motion" / f"{shot_id}.mp4",
        label="motion output",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.stem}.rendering.mp4")
    if temporary.exists():
        temporary.unlink()
    inputs = [
        "-loop",
        "1",
        "-framerate",
        str(fps),
        "-i",
        str(base),
    ]
    for layer_path in layer_files:
        inputs.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(fps),
                "-i",
                str(layer_path),
            ]
        )
    filters = [
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"scale=w='trunc({width}*(1+0.04*t/{duration_sec:.3f})/2)*2':"
        f"h='trunc({height}*(1+0.04*t/{duration_sec:.3f})/2)*2':eval=frame,"
        f"crop={width}:{height}:x='(in_w-out_w)/2':y='(in_h-out_h)/2',setsar=1[v0]"
    ]
    current = "v0"
    for index, layer in enumerate(layers, 1):
        layer_width = max(2, round(width * float(layer["scale"]) / 2) * 2)
        x_expr, y_expr = _motion_position(layer, width=width, height=height)
        filters.append(
            f"[{index}:v]format=rgba,scale={layer_width}:-2,"
            "fade=t=in:st=0:d=0.22:alpha=1[layer" + str(index) + "]"
        )
        next_label = f"v{index}"
        filters.append(
            f"[{current}][layer{index}]overlay=x='{x_expr}':y='{y_expr}':"
            f"eof_action=pass:shortest=1[{next_label}]"
        )
        current = next_label
    filters.append(f"[{current}]trim=duration={duration_sec:.3f},setpts=PTS-STARTPTS[out]")
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-frames:v",
        str(max(1, round(duration_sec * fps))),
        "-r",
        str(fps),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(temporary),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
    except subprocess.TimeoutExpired as exc:
        temporary.unlink(missing_ok=True)
        raise ShortformMotionError("ffmpeg local motion render timed out") from exc
    if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size <= 0:
        temporary.unlink(missing_ok=True)
        raise ShortformMotionError(f"ffmpeg local motion render failed: {result.stderr[-400:]}")
    try:
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(temporary), "-f", "null", "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        temporary.unlink(missing_ok=True)
        raise ShortformMotionError("local motion candidate decode timed out") from exc
    if decoded.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise ShortformMotionError("local motion candidate failed full decode")
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=width,height,avg_frame_rate:format=duration",
                "-of",
                "json",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        temporary.unlink(missing_ok=True)
        raise ShortformMotionError("local motion candidate probe timed out") from exc
    if probe.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise ShortformMotionError("cannot ffprobe local motion candidate")
    os.replace(temporary, target)
    candidate = {
        "path": str(target.relative_to(root)),
        "sha256": _sha256(target),
        "plan_sha256": canonical_json_sha256(plan_data),
        "duration_sec": duration_sec,
        "fps": fps,
        "canvas": {"width": width, "height": height},
        "probe": json.loads(probe.stdout),
        "status": "pending_human_review",
        "created_at": utc_now(),
    }
    package["reviews"]["sample"] = {
        "status": "pending",
        "invalidated_at": utc_now(),
        "reason": "new local motion candidate requires viewing",
    }
    package["status"] = "pending_sample_review"
    write_json(package_path, package)
    write_json(root / "receipts" / "shortform-motion" / f"{shot_id}.render.json", candidate)
    return {"ok": True, "shot_id": shot_id, "candidate": candidate}
