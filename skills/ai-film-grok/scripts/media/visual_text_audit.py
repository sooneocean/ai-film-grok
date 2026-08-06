"""Fail-closed, hash-bound inspection for provider-burned visual text.

The detector deliberately treats a visual-model finding as a rejection, never
as approval.  A clean result is only an input to the existing human review.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from local_llm import LocalLLMError, _request_json, normalize_base_url
from security_policy import safe_existing_file
from util import sha256_file, write_json

SCHEMA_VERSION = 1
BATCH_SIZE = 5
REPORT_NAME = "visual-text-audit.json"
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["issues"],
    "properties": {
        "issues": {
            "type": "array",
            "maxItems": BATCH_SIZE,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["frame_index", "location", "confidence"],
                "properties": {
                    "frame_index": {"type": "integer", "minimum": 0, "maximum": BATCH_SIZE - 1},
                    "location": {"type": "string", "minLength": 1, "maxLength": 240},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        }
    },
}


class VisualTextAuditError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _probe_media(clip: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,avg_frame_rate,nb_frames:format=duration",
                "-of",
                "json",
                str(clip),
            ],
            text=True,
            capture_output=True,
            check=True,
            timeout=60,
        )
        data = json.loads(result.stdout)
        stream = (data.get("streams") or [{}])[0]
        rate = str(stream.get("avg_frame_rate") or "")
        numerator, denominator = (int(part) for part in rate.split("/", 1))
        fps = numerator / denominator if denominator else 0.0
        duration = float((data.get("format") or {}).get("duration") or 0.0)
    except (OSError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
        raise VisualTextAuditError("could not inspect input video") from exc
    if not all(
        (
            fps > 0,
            duration > 0,
            int(stream.get("width") or 0) > 0,
            int(stream.get("height") or 0) > 0,
        )
    ):
        raise VisualTextAuditError("input video has incomplete geometry or frame rate")
    return {
        "fps": fps,
        "duration_sec": duration,
        "width": int(stream["width"]),
        "height": int(stream["height"]),
    }


def _extract_all_frames(clip: Path, destination: Path) -> list[Path]:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(clip),
                "-map",
                "0:v:0",
                "-vsync",
                "0",
                str(destination / "frame_%08d.png"),
            ],
            text=True,
            capture_output=True,
            check=True,
            timeout=1800,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise VisualTextAuditError("could not extract every video frame") from exc
    frames = sorted(destination.glob("frame_*.png"))
    if not frames:
        raise VisualTextAuditError("video produced no review frames")
    return frames


def _image_part(path: Path) -> dict[str, Any]:
    import base64

    return {
        "type": "image_url",
        "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        },
    }


def _review_batch(
    base_url: str, model: str, token: str | None, frames: list[Path]
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Inspect every full-size frame independently. Flag every provider-burned visual text, "
                "watermark, subtitle, logo, malformed/garbled glyph, pseudo-text, or unreadable character-like mark. "
                "Ignore natural textures only when clearly not text. Return strict JSON only."
            ),
        }
    ]
    content.extend(_image_part(frame) for frame in frames)
    try:
        response = _request_json(
            normalize_base_url(base_url),
            "/chat/completions",
            token=token,
            timeout=120,
            body={
                "model": model,
                "temperature": 0,
                "max_tokens": 700,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "visual_text_audit",
                        "strict": True,
                        "schema": _RESPONSE_SCHEMA,
                    },
                },
                "messages": [
                    {"role": "system", "content": "Return only strict JSON."},
                    {"role": "user", "content": content},
                ],
            },
        )
    except LocalLLMError as exc:
        raise VisualTextAuditError(f"visual reviewer unavailable: {exc.code}") from exc
    choices = response.get("choices") if isinstance(response, dict) else None
    choice = (
        choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    )
    message = choice.get("message") if isinstance(choice, dict) else {}
    try:
        payload = json.loads(message.get("content"))
        Draft202012Validator(_RESPONSE_SCHEMA).validate(payload)
    except (TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise VisualTextAuditError("visual reviewer returned invalid audit JSON") from exc
    return list(payload["issues"])


def audit_clip(
    root: Path | str,
    clip: Path | str,
    *,
    base_url: str,
    model: str,
    token: str | None = None,
    review_batch: Callable[
        [str, str, str | None, list[Path]], list[dict[str, Any]]
    ] = _review_batch,
) -> dict[str, Any]:
    """Fully scan one workspace video and persist a hash-bound, fail-closed report."""
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise VisualTextAuditError("film root must exist")
    try:
        source = safe_existing_file(root_path, Path(clip).expanduser(), field="visual text clip")
    except Exception as exc:
        raise VisualTextAuditError(
            "visual text clip must be a regular file inside the film workspace"
        ) from exc
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise VisualTextAuditError("ffmpeg and ffprobe are required")
    media = _probe_media(source)
    source_sha = sha256_file(source)
    frames = _extract_all_frames(source, root_path / "work" / "visual-text-audit" / source_sha)
    frame_records = [
        {
            "index": index,
            "path": str(frame.relative_to(root_path)),
            "sha256": sha256_file(frame),
            "timestamp_sec": round(index / media["fps"], 6),
        }
        for index, frame in enumerate(frames)
    ]
    findings: list[dict[str, Any]] = []
    for start in range(0, len(frames), BATCH_SIZE):
        batch = frames[start : start + BATCH_SIZE]
        issues = review_batch(base_url, model, token, batch)
        for issue in issues:
            local_index = int(issue["frame_index"])
            if local_index >= len(batch):
                raise VisualTextAuditError("visual reviewer referenced an invalid frame")
            record = frame_records[start + local_index]
            findings.append(
                {
                    **record,
                    "location": str(issue["location"]),
                    "confidence": float(issue["confidence"]),
                }
            )
    if sha256_file(source) != source_sha or any(
        sha256_file(
            Path(item["path"]) if Path(item["path"]).is_absolute() else root_path / item["path"]
        )
        != item["sha256"]
        for item in frame_records
    ):
        raise VisualTextAuditError("input video or extracted frames changed during audit")
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "visual-text-audit",
        "at": _now(),
        "status": "rejected" if findings else "clean",
        "reason": "PROVIDER_VISUAL_TEXT_REJECTED" if findings else None,
        "clip": {"path": str(source.relative_to(root_path)), "sha256": source_sha, **media},
        "sampling": {
            "mode": "every_decoded_frame",
            "frame_count": len(frame_records),
            "batch_size": BATCH_SIZE,
        },
        "reviewer": {"base_url": normalize_base_url(base_url), "model": model},
        "frames": frame_records,
        "findings": findings,
        "human_review_required": True,
    }
    receipts = root_path / "receipts"
    receipts.mkdir(exist_ok=True)
    path = receipts / REPORT_NAME
    write_json(path, report)
    return {**report, "path": str(path)}


def require_clean_audit(
    root: Path | str, clip: Path | str, receipt: Path | str | None = None
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    source = safe_existing_file(root_path, Path(clip).expanduser(), field="visual text clip")
    path = Path(receipt).expanduser().resolve() if receipt else root_path / "receipts" / REPORT_NAME
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualTextAuditError("current clean visual-text audit receipt is required") from exc
    if report.get("kind") != "visual-text-audit" or report.get("status") != "clean":
        raise VisualTextAuditError("PROVIDER_VISUAL_TEXT_REJECTED")
    if ((report.get("clip") or {}).get("sha256")) != sha256_file(source):
        raise VisualTextAuditError("visual-text audit receipt is stale for this clip")
    return report
