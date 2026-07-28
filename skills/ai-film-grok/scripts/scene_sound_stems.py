"""Render checksum-bound local scene-sound assets into an independent stem."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


class SceneSoundError(ValueError):
    pass


def _approved_performance(root: Path, event: dict[str, Any], asset: Path, actual: str) -> None:
    """Bind a performance timeline entry to its human-approved local receipt."""
    raw = str(event.get("approval_receipt") or "")
    if not raw.startswith("local:"):
        raise SceneSoundError(f"{event.get('id')}: approved performance receipt is required")
    try:
        receipt_path = (root / raw.removeprefix("local:")).resolve()
        receipt_path.relative_to(root)
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SceneSoundError(
            f"{event.get('id')}: approved performance receipt is unreadable"
        ) from exc
    if not isinstance(data, dict):
        raise SceneSoundError(f"{event.get('id')}: approved performance receipt is invalid")
    try:
        source_rel = str(asset.relative_to(root))
    except ValueError as exc:
        raise SceneSoundError(f"{event.get('id')}: performance asset escapes film root") from exc
    if (
        data.get("schema") != "aifilm-performance-candidate-v1"
        or data.get("status") != "approved"
        or data.get("approved_path") != source_rel
        or data.get("sha256") != actual
        or data.get("adult_confirmed") is not True
        or data.get("source_authorization") not in {"original", "authorized_reference"}
        or data.get("take_seed") != event.get("take_seed")
        or data.get("model_version") != event.get("model_version")
    ):
        raise SceneSoundError(
            f"{event.get('id')}: performance approval receipt does not bind asset"
        )


def _apply_event_controls(
    samples: np.ndarray, event: dict[str, Any], sample_rate: int
) -> np.ndarray:
    """Apply the signed event gain, pan and fades before it enters the bed."""
    out = samples.astype(np.float32, copy=True)
    out *= float(event.get("gain", 1.0))
    pan = float(event.get("pan", 0.0))
    left, right = (1.0 - pan) / 2.0, (1.0 + pan) / 2.0
    out[:, 0] *= left
    out[:, 1] *= right
    for key, edge in (("fade_in_sec", "in"), ("fade_out_sec", "out")):
        count = min(len(out), int(round(float(event.get(key, 0.0)) * sample_rate)))
        if count <= 0:
            continue
        ramp = np.linspace(0.0, 1.0, count, dtype=np.float32)
        if edge == "in":
            out[:count] *= ramp[:, None]
        else:
            out[-count:] *= ramp[::-1, None]
    return out


def _local_asset(root: Path, event: dict[str, Any]) -> Path:
    source = str(event.get("source") or event.get("asset") or "")
    if not source.startswith("local:"):
        raise SceneSoundError(f"{event.get('id')}: final only accepts local: scene-sound assets")
    raw = source.removeprefix("local:")
    path = (root / raw).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SceneSoundError(f"{event.get('id')}: asset escapes film root") from exc
    if not path.is_file():
        raise SceneSoundError(f"{event.get('id')}: asset not found: {raw}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != str(event.get("source_sha256") or ""):
        raise SceneSoundError(f"{event.get('id')}: asset checksum changed")
    if event.get("type") == "performance":
        _approved_performance(root, event, path, actual)
    return path


def render_scene_sound_stem(
    root: Path, timeline: dict[str, Any], *, duration_sec: float, out: Path, sample_rate: int
) -> dict[str, Any]:
    """Mix local foley/SFX/ambience/music assets at their signed cue times."""
    samples = np.zeros((max(1, int(round(duration_sec * sample_rate))), 2), dtype=np.float32)
    executed: list[dict[str, Any]] = []
    asset_types = {"action_sfx", "ambience", "music", "performance"}
    for event in timeline.get("events") or []:
        if (
            not isinstance(event, dict)
            or event.get("muted")
            or event.get("type") not in asset_types
        ):
            continue
        asset = _local_asset(root, event)
        duration = float(event["duration_sec"])
        proc = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-stream_loop",
                "-1",
                "-i",
                str(asset),
                "-t",
                f"{duration:.3f}",
                "-ar",
                str(sample_rate),
                "-ac",
                "2",
                "-f",
                "f32le",
                "pipe:1",
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode:
            raise SceneSoundError(f"{event.get('id')}: cannot decode asset")
        decoded = np.frombuffer(proc.stdout, dtype=np.float32).reshape((-1, 2))
        start = max(0, int(round(float(event["start_sec"]) * sample_rate)))
        end = min(len(samples), start + len(decoded))
        if end > start:
            samples[start:end] += _apply_event_controls(decoded[: end - start], event, sample_rate)
        executed.append(
            {
                "id": event.get("id"),
                "track": event.get("track"),
                "source": event.get("source"),
                "executed": True,
                "gain": event.get("gain", 1.0),
                "pan": event.get("pan", 0.0),
                "fade_in_sec": event.get("fade_in_sec", 0.0),
                "fade_out_sec": event.get("fade_out_sec", 0.0),
            }
        )
    samples = np.clip(samples, -1.0, 1.0)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "f32le",
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            "-i",
            "pipe:0",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        input=samples.tobytes(),
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise SceneSoundError("cannot write scene-sound stem")
    return {
        "path": str(out),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "event_count": len(executed),
        "events": executed,
    }
