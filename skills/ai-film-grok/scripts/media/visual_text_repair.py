"""Repair a rejected provider clip with bounded Qwen I2I frame replacements."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from comfy_armory import compile_weapon_workflow
from comfy_video import (
    ComfyVideoError,
    assert_submission_capacity,
    download_result,
    submit,
    upload_image,
    wait_for_result,
)
from security_policy import safe_existing_file
from util import sha256_file, utc_now, write_json

WINDOW_PADDING_FRAMES = 2
WEAPON_ID = "qwen-image-edit-2511-local"
POSITIVE_PROMPT = (
    "Preserve the source frame exactly: same identity, pose, action, composition, lighting, "
    "camera, background and geometry. Remove only accidental provider-burned visual text."
)
NEGATIVE_PROMPT = "text, subtitle, watermark, logo, glyph, garbled characters, pseudo-text"


class VisualTextRepairError(ValueError):
    pass


def repair_windows(
    indices: list[int], *, frame_count: int, padding: int = WINDOW_PADDING_FRAMES
) -> list[tuple[int, int]]:
    if frame_count < 1:
        raise VisualTextRepairError("frame count must be positive")
    windows: list[tuple[int, int]] = []
    for index in sorted(set(indices)):
        if not 0 <= index < frame_count:
            raise VisualTextRepairError("audit finding contains an invalid frame index")
        start, end = max(0, index - padding), min(frame_count - 1, index + padding)
        if windows and start <= windows[-1][1] + 1:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
    return windows


def _load_rejected_audit(root: Path, audit_path: Path | None) -> dict[str, Any]:
    path = audit_path or root / "receipts" / "visual-text-audit.json"
    try:
        safe_path = safe_existing_file(root, path, field="visual text audit receipt")
        report = json.loads(safe_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise VisualTextRepairError("a rejected visual-text audit receipt is required") from exc
    if report.get("kind") != "visual-text-audit" or report.get("status") != "rejected":
        raise VisualTextRepairError("repair requires a rejected visual-text audit")
    return report


def _replace_frames(source: Path, repaired: dict[int, Path], output: Path, fps: float) -> None:
    # ffmpeg's image sequence has no source audio, so preserve source audio and source timing.
    staging = output.parent / f".{output.stem}-frames"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-vsync",
                "0",
                str(staging / "frame_%08d.png"),
            ],
            text=True,
            capture_output=True,
            check=True,
            timeout=1800,
        )
        del result
        for index, frame in repaired.items():
            target = staging / f"frame_{index + 1:08d}.png"
            if not target.is_file():
                raise VisualTextRepairError("repair target frame is missing")
            shutil.copy2(frame, target)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                f"{fps:.12g}",
                "-i",
                str(staging / "frame_%08d.png"),
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-shortest",
                str(output),
            ],
            text=True,
            capture_output=True,
            check=True,
            timeout=1800,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise VisualTextRepairError("could not rebuild repaired video") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _qwen_i2i(base_url: str, frame: Path, output: Path, seed: int) -> dict[str, Any]:
    try:
        capacity = assert_submission_capacity(base_url)
        uploaded = upload_image(base_url, frame)
        graph = compile_weapon_workflow(
            WEAPON_ID,
            prompt=POSITIVE_PROMPT,
            seed=seed,
            input_image_name=uploaded["name"],
            filename_prefix=f"aifilm/visual-text-repair/{frame.stem}",
        )
        graph["negative_encode"]["inputs"]["prompt"] = NEGATIVE_PROMPT
        prompt_id = submit(base_url, graph, weapon_id=WEAPON_ID)
        result = wait_for_result(base_url, prompt_id)
        downloaded = download_result(base_url, result, output)
    except (ComfyVideoError, KeyError) as exc:
        raise VisualTextRepairError(f"repair_blocked: {exc}") from exc
    return {
        "provider": "comfy_qwen_i2i",
        "capacity": capacity,
        "upload": uploaded,
        "prompt_id": prompt_id,
        "output": downloaded,
    }


def repair_clip(
    root: Path | str,
    clip: Path | str,
    *,
    base_url: str,
    audit_path: Path | str | None = None,
    i2i: Callable[[str, Path, Path, int], dict[str, Any]] = _qwen_i2i,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    try:
        source = safe_existing_file(root_path, Path(clip).expanduser(), field="repair clip")
    except Exception as exc:
        raise VisualTextRepairError(
            "repair clip must be a regular file inside the film workspace"
        ) from exc
    audit = _load_rejected_audit(
        root_path, Path(audit_path).expanduser().resolve() if audit_path else None
    )
    if ((audit.get("clip") or {}).get("sha256")) != sha256_file(source):
        raise VisualTextRepairError("visual-text audit receipt is stale for this clip")
    frames = audit.get("frames") or []
    findings = audit.get("findings") or []
    if not isinstance(frames, list) or not isinstance(findings, list):
        raise VisualTextRepairError("visual-text audit receipt is malformed")
    windows = repair_windows([int(item["index"]) for item in findings], frame_count=len(frames))
    existing_path = root_path / "receipts" / "visual-text-repair.json"
    if existing_path.is_file():
        try:
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
            existing_source = (existing.get("source") or {}).get("sha256")
            existing_output = (existing.get("output") or {}).get("path")
            if existing_source == sha256_file(source) and isinstance(existing_output, str):
                output = safe_existing_file(
                    root_path, root_path / existing_output, field="existing repaired clip"
                )
                if sha256_file(output) == (existing.get("output") or {}).get("sha256"):
                    return {**existing, "path": str(existing_path), "deduplicated": True}
        except Exception:
            pass
    lock = root_path / "work" / f".visual-text-repair-{sha256_file(source)[:16]}.lock"
    lock.parent.mkdir(exist_ok=True)
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise VisualTextRepairError("repair_blocked: matching repair is already running") from exc
    os.close(lock_fd)
    try:
        return _repair_locked(root_path, source, audit, frames, findings, windows, base_url, i2i)
    finally:
        lock.unlink(missing_ok=True)


def _repair_locked(
    root_path: Path,
    source: Path,
    audit: dict[str, Any],
    frames: list[Any],
    findings: list[Any],
    windows: list[tuple[int, int]],
    base_url: str,
    i2i: Callable[[str, Path, Path, int], dict[str, Any]],
) -> dict[str, Any]:
    """Perform the single admitted repair after a source-hash keyed lock is held."""
    rejected = root_path / "rejected"
    rejected.mkdir(exist_ok=True)
    retained = rejected / f"{source.stem}-{sha256_file(source)[:12]}{source.suffix}"
    if not retained.exists():
        shutil.copy2(source, retained)
        retained.chmod(0o444)
    repair_dir = root_path / "work" / "visual-text-repair" / sha256_file(source)
    repair_dir.mkdir(parents=True, exist_ok=True)
    repaired: dict[int, Path] = {}
    frame_receipts: list[dict[str, Any]] = []
    for start, end in windows:
        for index in range(start, end + 1):
            declared_path = Path(str(frames[index]["path"]))
            if declared_path.is_absolute():
                raise VisualTextRepairError("audit frame path must be relative to film workspace")
            try:
                input_path = safe_existing_file(
                    root_path, root_path / declared_path, field="audited frame"
                )
            except Exception as exc:
                raise VisualTextRepairError("audited source frame is missing or unsafe") from exc
            if sha256_file(input_path) != frames[index]["sha256"]:
                raise VisualTextRepairError("audited source frame is missing or changed")
            output = repair_dir / f"repaired_{index:08d}.png"
            receipt = i2i(base_url, input_path, output, index)
            if not output.is_file() or output.stat().st_size < 32:
                raise VisualTextRepairError("repair_blocked: I2I did not create an image")
            repaired[index] = output
            frame_receipts.append(
                {
                    "index": index,
                    "input_sha256": sha256_file(input_path),
                    "output_sha256": sha256_file(output),
                    **receipt,
                }
            )
    repair_output = root_path / "clips" / f"{source.stem}-text-repaired.mp4"
    repair_output.parent.mkdir(exist_ok=True)
    fps = float((audit.get("clip") or {}).get("fps") or 0)
    if fps <= 0:
        raise VisualTextRepairError("repair audit lacks a valid frame rate")
    _replace_frames(source, repaired, repair_output, fps)
    report = {
        "schema_version": 1,
        "kind": "visual-text-repair",
        "at": utc_now(),
        "status": "pending_reaudit",
        "source": {"path": str(source.relative_to(root_path)), "sha256": sha256_file(source)},
        "retained_rejected_source": str(retained.relative_to(root_path)),
        "output": {
            "path": str(repair_output.relative_to(root_path)),
            "sha256": sha256_file(repair_output),
        },
        "windows": [{"start_frame": start, "end_frame": end} for start, end in windows],
        "frame_repairs": frame_receipts,
        "requires": ["visual-text-audit rerun", "human review"],
    }
    path = root_path / "receipts" / "visual-text-repair.json"
    write_json(path, report)
    return {**report, "path": str(path)}
