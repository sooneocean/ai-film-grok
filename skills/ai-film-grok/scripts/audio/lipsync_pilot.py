"""Three-shot, receipt-bound near-dialogue lip-sync pilot.

The pilot is deliberately separate from a film manifest: it proves a narrow
route without allowing candidate media to become production footage.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from runtime_policy import sha256
from util import read_json, write_json


class LipsyncPilotError(RuntimeError):
    pass


PILOT_NAME = "lipsync-near-dialogue-pilot.json"
SAMPLES = ("front_closeup", "three_quarter_closeup", "moving_closeup")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _root(root: Path | str) -> Path:
    value = Path(root).expanduser().resolve()
    value.mkdir(parents=True, exist_ok=True)
    return value


def _receipt(root: Path) -> Path:
    return root / "receipts" / PILOT_NAME


def _regular_file(path: Path | str, label: str) -> Path:
    value = Path(path).expanduser()
    if value.is_symlink():
        raise LipsyncPilotError(f"{label} must be a regular non-symlink file")
    value = value.resolve()
    if not value.is_file() or value.stat().st_size <= 0:
        raise LipsyncPilotError(f"{label} is missing or empty")
    return value


def create_pilot(
    root: Path | str,
    *,
    front_video: Path | str,
    three_quarter_video: Path | str,
    moving_video: Path | str,
    japanese_audio: Path | str,
    approval_receipt: Path | str,
) -> dict[str, Any]:
    """Register immutable inputs; this never starts GPU work."""
    base = _root(root)
    destination = _receipt(base)
    if destination.exists():
        raise LipsyncPilotError(f"pilot receipt already exists: {destination}")
    audio = _regular_file(japanese_audio, "Chinese dialogue audio")
    videos = {
        "front_closeup": _regular_file(front_video, "front close-up video"),
        "three_quarter_closeup": _regular_file(three_quarter_video, "three-quarter close-up video"),
        "moving_closeup": _regular_file(moving_video, "moving close-up video"),
    }
    if len({sha256(value) for value in videos.values()}) != len(videos):
        raise LipsyncPilotError("the three standard pilot videos must be distinct")
    approval = read_json(_regular_file(approval_receipt, "approved-input receipt"))
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise LipsyncPilotError("approved-input receipt must explicitly set approved=true")
    approved_videos = approval.get("videos") if isinstance(approval.get("videos"), dict) else {}
    approved_audio = approval.get("audio") if isinstance(approval.get("audio"), dict) else {}
    if (
        str(approved_audio.get("language") or "").lower() not in {"zh", "cn", "chinese", "zh-cn"}
        or approved_audio.get("role") != "final_character_dialogue"
    ):
        raise LipsyncPilotError("approved-input receipt must bind Chinese final character dialogue")
    if approved_audio.get("sha256") != sha256(audio):
        raise LipsyncPilotError("approved-input receipt audio checksum does not match")
    for name, video in videos.items():
        entry = approved_videos.get(name) if isinstance(approved_videos.get(name), dict) else {}
        if entry.get("role") != "approved_character_reference" or entry.get("sha256") != sha256(
            video
        ):
            raise LipsyncPilotError(
                f"approved-input receipt does not bind {name} to approved character media"
            )
    input_media = {"audio": _input_media(audio, "audio")}
    input_media["videos"] = {name: _input_media(video, "video") for name, video in videos.items()}
    payload = {
        "schema_version": 1,
        "kind": "ai-film-lipsync-near-dialogue-pilot",
        "created_at": _now(),
        "state": "planned",
        "production_promotion": "forbidden_pending_human_review",
        "scope": {
            "allowed": "single visible face, close-up or medium close-up, short dialogue",
            "excluded": "wide shots, profile/occluded faces, multi-speaker shots, whole-frame avatar regeneration",
        },
        "audio": {"path": str(audio), "sha256": sha256(audio), "language": "ja"},
        "approval_receipt": {
            "path": str(Path(approval_receipt).expanduser().resolve()),
            "sha256": sha256(Path(approval_receipt).expanduser().resolve()),
        },
        "input_media": input_media,
        "samples": {
            name: {
                "video": str(video),
                "video_sha256": sha256(video),
                "backend": "latentsync",
                "status": "pending",
            }
            for name, video in videos.items()
        },
        "fallback": {
            "backend": "musetalk",
            "rule": "only_after_classified_latentsync_technical_failure_and_ready_approval",
        },
    }
    write_json(destination, payload)
    payload["receipt_path"] = str(destination)
    return payload


def _load(root: Path | str) -> tuple[Path, Path, dict[str, Any]]:
    base = _root(root)
    path = _receipt(base)
    payload = read_json(path)
    if (
        not isinstance(payload, dict)
        or payload.get("kind") != "ai-film-lipsync-near-dialogue-pilot"
    ):
        raise LipsyncPilotError("near-dialogue pilot has not been created")
    return base, path, payload


def _comfy_is_idle() -> dict[str, Any]:
    from comfy_video import ComfyVideoError, queue_status
    from config_loader import get_config

    base_url = str(get_config().comfyui_base_url or "").strip()
    if not base_url:
        raise LipsyncPilotError(
            "AIFILM_COMFYUI_BASE_URL is required to prove the shared GPU is idle"
        )
    try:
        queue = queue_status(base_url)
    except ComfyVideoError as exc:
        raise LipsyncPilotError(f"could not verify ComfyUI queue: {exc}") from exc
    if queue["running"] or queue["pending"]:
        raise LipsyncPilotError("shared ComfyUI queue is not empty; refusing to occupy the 5090")
    return queue


def _input_media(path: Path, kind: str) -> dict[str, Any]:
    selector = "a:0" if kind == "audio" else "v:0"
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                selector,
                "-show_entries",
                "stream=codec_name,sample_rate,channels,width,height,avg_frame_rate:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(result.stdout)
        stream = (payload.get("streams") or [None])[0]
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        IndexError,
    ) as exc:
        raise LipsyncPilotError(f"{kind} input failed ffprobe") from exc
    if not isinstance(stream, dict) or duration <= 0:
        raise LipsyncPilotError(f"{kind} input has invalid media metadata")
    return {
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "duration": duration,
        "stream": stream,
    }


def _technical_failure(error: str) -> dict[str, str | bool]:
    text = error.lower()
    if "unreachable" in text or "timed out" in text or "timeout" in text:
        return {"technical": True, "code": "TRANSPORT_TIMEOUT"}
    if "lip-sync node http 5" in text or "lip-sync node http 429" in text:
        return {"technical": True, "code": "NODE_TRANSIENT_HTTP"}
    if "job failed" in text or "did not produce a completed local mp4" in text:
        return {"technical": True, "code": "LATENTSYNC_EXECUTION_FAILURE"}
    return {"technical": False, "code": "NONTECHNICAL_OR_UNCLASSIFIED"}


def _node_evidence(node: dict[str, Any]) -> dict[str, Any]:
    gpu = node.get("gpu") if isinstance(node.get("gpu"), dict) else {}
    backends = node.get("backends") if isinstance(node.get("backends"), dict) else {}
    latent = backends.get("latentsync") if isinstance(backends.get("latentsync"), dict) else {}
    required = ("model", "checkpoint_sha256", "repo_commit")
    if not node.get("ok") or not all(
        isinstance(latent.get(key), str) and latent[key] for key in required
    ):
        raise LipsyncPilotError("LatentSync node fingerprint is incomplete")
    if not isinstance(gpu.get("free_vram_mib"), int) or not isinstance(
        gpu.get("total_vram_mib"), int
    ):
        raise LipsyncPilotError("LatentSync node VRAM telemetry is incomplete")
    return {
        "gpu": gpu,
        "latentsync": {key: latent[key] for key in required},
        "measured": latent.get("measured"),
    }


def _media_evidence(path: Path, frame_dir: Path) -> dict[str, Any]:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=width,height,avg_frame_rate,codec_name",
            "-select_streams",
            "v:0",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(probe.stdout)
    stream = (payload.get("streams") or [None])[0]
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if not isinstance(stream, dict) or duration <= 0:
        raise LipsyncPilotError("pilot output has invalid media metadata")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-map", "0", "-f", "null", "-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    frame_dir.mkdir(parents=True, exist_ok=True)
    timestamps = [round(index * 0.25, 3) for index in range(int(duration / 0.25) + 1)]
    frames: list[str] = []
    for index, timestamp in enumerate(timestamps):
        out = frame_dir / f"{index:04d}-{timestamp:.3f}.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                str(timestamp),
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-y",
                str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if not out.is_file():
            raise LipsyncPilotError(f"could not extract review frame at {timestamp:.3f}s")
        frames.append(str(out))
    return {
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "duration": duration,
        "stream": stream,
        "full_decode": "passed",
        "review_interval_sec": 0.25,
        "review_frames": frames,
    }


def run_pilot(root: Path | str) -> dict[str, Any]:
    """Run LatentSync sequentially after proving the shared GPU is unused."""
    base, receipt_path, pilot = _load(root)
    if pilot.get("state") not in {"planned", "blocked_queue"}:
        raise LipsyncPilotError(f"pilot cannot run from state {pilot.get('state')!r}")
    try:
        pilot["comfy_queue_before"] = _comfy_is_idle()
    except LipsyncPilotError as exc:
        pilot["state"] = "blocked_queue"
        pilot["blocker"] = str(exc)
        write_json(receipt_path, pilot)
        return {
            "ok": False,
            "state": pilot["state"],
            "blocker": pilot["blocker"],
            "receipt_path": str(receipt_path),
        }

    from lipsync_backend import lipsync_one, probe

    node = probe().get("node") or {}
    backends = node.get("backends") if isinstance(node.get("backends"), dict) else {}
    latent = backends.get("latentsync") if isinstance(backends.get("latentsync"), dict) else {}
    if not latent.get("ready"):
        raise LipsyncPilotError("LatentSync is not approved and ready")
    muse = backends.get("musetalk") if isinstance(backends.get("musetalk"), dict) else {}
    pilot["node_before"] = _node_evidence(node)
    pilot["state"] = "running"
    write_json(receipt_path, pilot)
    audio = Path(str((pilot.get("audio") or {}).get("path") or ""))
    out_dir = receipt_path.parent / "lipsync-near-dialogue-pilot"
    all_ok = True
    for sample_id in SAMPLES:
        item = pilot["samples"][sample_id]
        source = Path(str(item["video"]))
        output = out_dir / f"{sample_id}-latentsync.mp4"
        started = time.monotonic()
        try:
            result = lipsync_one(
                video=source,
                audio=audio,
                out=output,
                backend="latentsync",
                allow_node_fallback=False,
            )
            completed = result.get("ok") is True or result.get("status") == "completed"
            if not completed or not output.is_file():
                raise LipsyncPilotError("LatentSync did not produce a completed local MP4")
            item.update(
                {
                    "status": "pending_human_review",
                    "backend_used": result.get("chosen_backend") or "latentsync",
                    "elapsed_sec": round(time.monotonic() - started, 3),
                    "result": result,
                    "output": str(output),
                    "media": _media_evidence(output, out_dir / "review_frames" / sample_id),
                }
            )
        except Exception as exc:  # preserve the concrete failure without auto-promoting a fallback
            error = str(exc)[:500]
            item.update(
                {
                    "status": "latentsync_failed",
                    "elapsed_sec": round(time.monotonic() - started, 3),
                    "error": error,
                }
            )
            classification = _technical_failure(error)
            item["failure"] = classification
            if classification["technical"] and muse.get("ready"):
                item["fallback_status"] = "eligible_musetalk_manual_rerun_required"
            elif classification["technical"]:
                item["fallback_status"] = "blocked_musetalk_not_approved"
            else:
                item["fallback_status"] = "not_eligible_nontechnical_failure"
            all_ok = False
        write_json(receipt_path, pilot)
    pilot["node_after"] = _node_evidence(probe().get("node") or {})
    pilot["state"] = "pending_human_review" if all_ok else "completed_with_failures"
    pilot["production_promotion"] = "forbidden_pending_human_review"
    write_json(receipt_path, pilot)
    return {
        "ok": all_ok,
        "state": pilot["state"],
        "receipt_path": str(receipt_path),
        "samples": pilot["samples"],
    }


def rerun_musetalk(root: Path | str, *, sample_id: str) -> dict[str, Any]:
    """Explicit human-invoked fallback; no global automatic fallback is permitted."""
    if sample_id not in SAMPLES:
        raise LipsyncPilotError("unknown pilot sample")
    base, receipt_path, pilot = _load(root)
    item = (pilot.get("samples") or {}).get(sample_id)
    if (
        not isinstance(item, dict)
        or item.get("fallback_status") != "eligible_musetalk_manual_rerun_required"
    ):
        raise LipsyncPilotError("MuseTalk rerun is not eligible for this sample")
    pilot["comfy_queue_before_musetalk"] = _comfy_is_idle()
    from lipsync_backend import lipsync_one, probe

    node = probe().get("node") or {}
    muse = (node.get("backends") or {}).get("musetalk") or {}
    if not muse.get("ready"):
        raise LipsyncPilotError("MuseTalk is not approved and ready")
    output = receipt_path.parent / "lipsync-near-dialogue-pilot" / f"{sample_id}-musetalk.mp4"
    started = time.monotonic()
    result = lipsync_one(
        video=Path(str(item["video"])),
        audio=Path(str((pilot.get("audio") or {}).get("path") or "")),
        out=output,
        backend="musetalk",
        allow_node_fallback=False,
    )
    if (
        not (result.get("ok") is True or result.get("status") == "completed")
        or not output.is_file()
    ):
        raise LipsyncPilotError("MuseTalk did not produce a completed local MP4")
    item["musetalk_manual_rerun"] = {
        "status": "pending_human_review",
        "elapsed_sec": round(time.monotonic() - started, 3),
        "result": result,
        "output": str(output),
        "media": _media_evidence(output, output.parent / "review_frames" / f"{sample_id}-musetalk"),
    }
    write_json(receipt_path, pilot)
    return {
        "ok": True,
        "state": "pending_human_review",
        "receipt_path": str(receipt_path),
        "sample": item,
    }


def review_template(root: Path | str) -> dict[str, Any]:
    base, _, pilot = _load(root)
    template_path = base / "receipts" / "lipsync-near-dialogue-review.json"
    if template_path.exists():
        raise LipsyncPilotError(f"review template already exists: {template_path}")
    template = {
        "schema_version": 1,
        "kind": "ai-film-lipsync-near-dialogue-review",
        "pilot_receipt_sha256": sha256(_receipt(base)),
        "state": "pending_human_review",
        "instructions": "Review each output and set every check to approved or rejected with a concrete note. This never promotes candidate media into a film.",
        "samples": {
            sample_id: {
                "status": "pending",
                "checks": {
                    "lip_sync": "pending",
                    "outside_mouth_stability": "pending",
                    "identity_costume_background": "pending",
                    "angle_or_motion_distortion": "pending",
                },
                "note": "",
                "if_rejected": "Record the unusable condition and reshoot recommendation.",
            }
            for sample_id in SAMPLES
            if (pilot.get("samples") or {}).get(sample_id, {}).get("status")
            == "pending_human_review"
        },
    }
    write_json(template_path, template)
    template["path"] = str(template_path)
    return template
