#!/usr/bin/env python3
"""Auditable 15–60 second directing package for topic, A-roll and C-roll.

This is deliberately provider-neutral.  It owns timing, editorial decisions and
evidence; existing still/I2V/TTS/LatentSync commands remain the renderers.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from dialogue_broll import default_dialogue_broll
from util import utc_now, write_json

PACKAGE_NAME = "shortform-package.json"
MIN_SHOT_SEC, MAX_SHOT_SEC = 3.0, 6.0
MAX_AROLL_BEAT_SEC, MIN_AROLL_BEAT_SEC, PAUSE_GAP_SEC = 9.5, 6.0, 0.35
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ShortformError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pcm_sha256(path: Path) -> str:
    """Hash decoded samples so A-roll receipts prove source-audio preservation."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-f",
                "s16le",
                "pipe:1",
            ],
            capture_output=True,
            check=False,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise ShortformError(
            f"cannot decode source audio for {path.name} (ffmpeg timed out)"
        ) from exc
    if result.returncode != 0 or not result.stdout:
        raise ShortformError(f"cannot decode source audio for {path.name}")
    return hashlib.sha256(result.stdout).hexdigest()


def _inside(root: Path, value: Path, *, label: str) -> Path:
    raw = value.expanduser()
    if raw.is_symlink():
        raise ShortformError(f"{label} must not be a symlink")
    candidate = raw.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ShortformError(f"{label} must live inside the project root") from exc
    if not candidate.is_file():
        raise ShortformError(f"{label} must be a regular project file")
    return candidate


def _relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _safe_output(root: Path, value: Path, *, label: str) -> Path:
    """Resolve an output before side effects and reject symlinked path components."""
    raw = value.expanduser()
    if raw.is_symlink():
        raise ShortformError(f"{label} must not be a symlink")
    absolute = raw if raw.is_absolute() else root / raw
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise ShortformError(f"{label} must live inside project root") from exc
    current = root
    for component in relative.parts[:-1]:
        current = current / component
        if current.is_symlink():
            raise ShortformError(f"{label} parent must not be a symlink")
    resolved = absolute.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ShortformError(f"{label} escapes project root") from exc
    return resolved


def _load_package(root: Path | str) -> tuple[Path, dict[str, Any]]:
    root = Path(root).expanduser().resolve()
    path = root / PACKAGE_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShortformError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("kind") != "shortform-director-package":
        raise ShortformError("invalid shortform package")
    return root, value


def _save(root: Path, package: dict[str, Any]) -> dict[str, Any]:
    package["updated_at"] = utc_now()
    write_json(root / PACKAGE_NAME, package)
    return package


def _words(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment in transcript.get("segments") or []:
        if isinstance(segment, dict):
            rows.extend(segment.get("words") or [])
    rows.extend(transcript.get("words") or [])
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            start, end = float(row.get("start")), float(row.get("end"))
        except (TypeError, ValueError):
            continue
        text = str(row.get("text") or row.get("word") or "").strip()
        if text and end >= start:
            normalized.append({"start": start, "end": end, "text": text})
    normalized.sort(key=lambda row: row["start"])
    if not normalized:
        raise ShortformError("A-roll transcript needs word-level timestamps")
    return normalized


def segment_aroll_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Segment only at word boundaries, sentence ends or natural pauses."""
    beats: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for index, word in enumerate(words):
        current.append(word)
        duration = word["end"] - current[0]["start"]
        next_start = words[index + 1]["start"] if index + 1 < len(words) else None
        gap = next_start - word["end"] if next_start is not None else 0.0
        sentence_end = word["text"].rstrip().endswith((".", "!", "?", "。", "！", "？"))
        if (
            index + 1 == len(words)
            or duration >= MAX_AROLL_BEAT_SEC
            or (duration >= MIN_AROLL_BEAT_SEC and (sentence_end or gap >= PAUSE_GAP_SEC))
        ):
            beats.append(current)
            current = []
    if len(beats) > 1 and beats[-1][-1]["end"] - beats[-1][0]["start"] < MIN_AROLL_BEAT_SEC:
        beats[-2].extend(beats.pop())
    rows = [
        {
            "start_sec": round(group[0]["start"], 3),
            "end_sec": round(group[-1]["end"], 3),
            "text": " ".join(word["text"] for word in group),
        }
        for group in beats
    ]
    for index in range(len(rows) - 1):
        rows[index]["end_sec"] = rows[index + 1]["start_sec"]
    return rows


def _duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ShortformError(
            f"cannot probe duration for {path.name} (ffprobe timed out)"
        ) from exc
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise ShortformError(f"cannot probe duration for {path.name}") from exc
    if result.returncode != 0 or duration <= 0:
        raise ShortformError(f"cannot probe duration for {path.name}")
    return duration


def _script_beats(text: str) -> list[dict[str, Any]]:
    sentences = [item.strip() for item in re.split(r"(?<=[。！？.!?])\s*", text) if item.strip()]
    if not sentences:
        raise ShortformError("approved script must contain text")
    beats: list[dict[str, Any]] = []
    for index, sentence in enumerate(sentences):
        # 2.6 words/sec is a conservative VO estimate; each beat gets two visual shots.
        duration = max(2 * MIN_SHOT_SEC, min(2 * MAX_SHOT_SEC, len(sentence.split()) / 2.6))
        beats.append({"text": sentence, "duration_sec": round(duration, 2)})
    return beats


def _visual_shots(beat_id: str, duration: float, *, mode: str, text: str) -> list[dict[str, Any]]:
    first = round(min(MAX_SHOT_SEC, max(MIN_SHOT_SEC, duration / 2)), 2)
    second = round(max(MIN_SHOT_SEC, duration - first), 2)
    if first + second > duration + 0.01:
        duration = first + second
    speaking = mode in {"topic", "croll"} and bool(text.strip())
    return [
        {
            "id": f"{beat_id}_a",
            "role": "primary",
            "duration_sec": first,
            "screen_mode": "on_camera" if speaking else "off_camera",
            "camera": {"shot_size": "medium close-up" if speaking else "wide", "angle": "front"},
            "lipsync": False,
        },
        {
            "id": f"{beat_id}_b",
            "role": "detail_cover",
            "duration_sec": second,
            "screen_mode": "action_cover",
            "camera": {"shot_size": "close-up", "angle": "front"},
            "lipsync": False,
        },
    ]


def create_package(
    root: Path | str,
    *,
    mode: str,
    approved_script: Path | None = None,
    source_video: Path | None = None,
    transcript: Path | None = None,
    anchor: Path | None = None,
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if mode not in {"topic", "aroll", "croll"}:
        raise ShortformError("mode must be topic, aroll, or croll")
    source: dict[str, Any] = {}
    if mode == "aroll":
        if source_video is None or transcript is None:
            raise ShortformError("A-roll requires --source-video and --transcript")
        video = _inside(root, source_video, label="source video")
        transcript_path = _inside(root, transcript, label="transcript")
        try:
            words = _words(json.loads(transcript_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ShortformError("A-roll transcript must be JSON") from exc
        raw_beats = segment_aroll_words(words)
        source_duration = _duration(video)
        raw_beats[0]["start_sec"] = 0.0
        raw_beats[-1]["end_sec"] = round(source_duration, 3)
        source = {
            "video_path": _relative(root, video),
            "video_sha256": _sha256(video),
            "transcript_path": _relative(root, transcript_path),
            "transcript_sha256": _sha256(transcript_path),
            "audio_policy": "source_audio_is_lipsync_truth",
        }
    else:
        if approved_script is None:
            raise ShortformError("topic/C-roll requires --approved-script")
        script = _inside(root, approved_script, label="approved script")
        raw_beats = _script_beats(script.read_text(encoding="utf-8"))
        source = {"script_path": _relative(root, script), "script_sha256": _sha256(script)}
    anchor_info: dict[str, Any] | None = None
    if mode == "croll":
        if anchor is None:
            raise ShortformError("C-roll requires --anchor")
        anchor_path = _inside(root, anchor, label="anchor")
        anchor_info = {
            "path": _relative(root, anchor_path),
            "sha256": _sha256(anchor_path),
            "freeze_identity": True,
        }
    beats: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_beats, 1):
        beat_id = f"beat{index:02d}"
        duration = float(raw.get("duration_sec") or (raw["end_sec"] - raw["start_sec"]))
        beat = {
            "id": beat_id,
            **raw,
            "duration_sec": round(duration, 3),
            "shots": _visual_shots(beat_id, duration, mode=mode, text=str(raw.get("text") or "")),
        }
        if mode == "aroll":
            beat["audio_policy"] = "remux_source_segment"
            beat["shots"] = [
                {
                    **shot,
                    "screen_mode": "on_camera",
                    "source_start_sec": raw["start_sec"],
                    "source_end_sec": raw["end_sec"],
                }
                for shot in beat["shots"]
            ]
        beats.append(beat)
    package = {
        "schema_version": 1,
        "kind": "shortform-director-package",
        "mode": mode,
        "status": "pending_plan_review",
        "created_at": utc_now(),
        "source": source,
        "anchor": anchor_info,
        "beats": beats,
        "reviews": {"plan": {"status": "pending"}, "sample": {"status": "pending"}},
        "provider_policy": {"atlas_cloud": "disabled", "external_paid_routes": "disabled"},
    }
    _save(root, package)
    return package


def validate_package(root: Path | str, *, require_approved: bool = False) -> dict[str, Any]:
    root, package = _load_package(root)
    issues: list[str] = []
    mode = package.get("mode")
    if mode not in {"topic", "aroll", "croll"}:
        issues.append("invalid mode")
    source = package.get("source") if isinstance(package.get("source"), dict) else {}
    for key in ("video", "transcript", "script"):
        path_key, hash_key = f"{key}_path", f"{key}_sha256"
        if path_key in source:
            try:
                file = _inside(root, root / str(source[path_key]), label=key)
                if _sha256(file) != source.get(hash_key):
                    issues.append(f"{key} hash changed")
            except ShortformError as exc:
                issues.append(str(exc))
    if mode == "aroll" and source.get("audio_policy") != "source_audio_is_lipsync_truth":
        issues.append("A-roll must retain source audio as lip-sync truth")
    if mode == "croll":
        anchor = package.get("anchor") or {}
        if not anchor.get("freeze_identity"):
            issues.append("C-roll anchor identity must be frozen")
        else:
            try:
                anchor_file = _inside(root, root / str(anchor.get("path") or ""), label="anchor")
                if _sha256(anchor_file) != anchor.get("sha256"):
                    issues.append("anchor hash changed")
            except ShortformError as exc:
                issues.append(str(exc))
    for beat in package.get("beats") or []:
        if mode == "aroll" and float(beat.get("duration_sec") or 0) > MAX_AROLL_BEAT_SEC:
            issues.append(f"{beat.get('id')} exceeds the 9.5 sec A-roll limit")
        shots = beat.get("shots") if isinstance(beat, dict) else []
        if not isinstance(shots, list) or len(shots) != 2:
            issues.append(f"{beat.get('id', 'beat')} must have primary and detail coverage")
            continue
        for shot in shots:
            duration = float(shot.get("duration_sec") or 0)
            if duration < MIN_SHOT_SEC or duration > MAX_SHOT_SEC:
                issues.append(f"{shot.get('id')} duration must be 3–6 sec")
            if shot.get("role") == "detail_cover" and shot.get("lipsync") is not False:
                issues.append(f"{shot.get('id')} detail coverage cannot lip-sync")
            if shot.get("lipsync") is True and mode == "aroll":
                issues.append(f"{shot.get('id')} A-roll cannot rerun lip-sync")
    if require_approved:
        reviews = package.get("reviews") or {}
        if reviews.get("plan", {}).get("status") != "approved":
            issues.append("plan review missing")
        if reviews.get("sample", {}).get("status") != "approved":
            issues.append("sample review missing")
    return {
        "ok": not issues,
        "issues": issues,
        "mode": mode,
        "status": package.get("status"),
        "path": str(root / PACKAGE_NAME),
    }


def review(
    root: Path | str, *, stage: str, reviewer: str, note: str, approve: bool
) -> dict[str, Any]:
    root, package = _load_package(root)
    if stage not in {"plan", "sample"} or not reviewer.strip() or not note.strip():
        raise ShortformError("stage, reviewer, and note are required")
    if stage == "sample" and package.get("reviews", {}).get("plan", {}).get("status") != "approved":
        raise ShortformError("approve plan review before sample review")
    package["reviews"][stage] = {
        "status": "approved" if approve else "rejected",
        "reviewer": reviewer,
        "note": note,
        "reviewed_at": utc_now(),
    }
    if stage == "plan" and approve:
        package["status"] = "pending_sample_review"
    if stage == "sample" and approve:
        package["status"] = "approved_for_production"
    return _save(root, package)


def enable_lipsync(
    root: Path | str, *, shot_id: str, speaker: str, face_target: str, audio_sha256: str
) -> dict[str, Any]:
    root, package = _load_package(root)
    if package.get("mode") == "aroll":
        raise ShortformError("A-roll preserves source lip-sync and cannot enable a new backend")
    if not _SHA256.fullmatch(audio_sha256):
        raise ShortformError("audio_sha256 must be SHA-256")
    for beat in package.get("beats") or []:
        for shot in beat.get("shots") or []:
            if shot.get("id") != shot_id:
                continue
            camera = shot.get("camera") or {}
            if (
                shot.get("screen_mode") != "on_camera"
                or camera.get("shot_size")
                not in {"medium close-up", "close-up", "extreme close-up"}
                or camera.get("angle") not in {"front", "three-quarter"}
            ):
                raise ShortformError("lip-sync requires on-camera front/three-quarter near shot")
            shot.update(
                {
                    "lipsync": True,
                    "speaker": speaker,
                    "face_target": face_target,
                    "audio_sha256": audio_sha256,
                    "requires_sample_review": True,
                }
            )
            package["reviews"]["sample"] = {
                "status": "pending",
                "invalidated_at": utc_now(),
                "reason": "lip-sync binding changed",
            }
            package["status"] = "pending_sample_review"
            return _save(root, package)
    raise ShortformError(f"unknown shot {shot_id}")


def render_lipsync(
    root: Path | str,
    *,
    shot_id: str,
    video: Path,
    audio: Path,
    out: Path | None = None,
    backend: str = "auto",
) -> dict[str, Any]:
    """Render one explicitly-bound B/C candidate through the locked backend.

    This is intentionally an explicit command: planning or binding a shortform
    package never submits RTX work. The rendered result remains a sample
    candidate until the second human review gate is recorded.
    """
    root, package = _load_package(root)
    if package.get("mode") == "aroll":
        raise ShortformError("A-roll preserves source lip-sync and cannot render a new backend")
    if package.get("reviews", {}).get("plan", {}).get("status") != "approved":
        raise ShortformError("approve the shortform plan before rendering a lip-sync sample")
    target_shot = next(
        (
            shot
            for beat in package.get("beats") or []
            for shot in beat.get("shots") or []
            if shot.get("id") == shot_id
        ),
        None,
    )
    if not isinstance(target_shot, dict) or target_shot.get("lipsync") is not True:
        raise ShortformError("shot is not an explicitly enabled lip-sync target")
    input_video = _inside(root, video, label="lip-sync video")
    input_audio = _inside(root, audio, label="lip-sync audio")
    if _sha256(input_audio) != target_shot.get("audio_sha256"):
        raise ShortformError("lip-sync audio hash does not match the bound final audio")
    if out is None:
        target = _safe_output(
            root,
            root / "candidates" / "shortform-lipsync" / f"{shot_id}.mp4",
            label="lip-sync output",
        )
    else:
        target = _safe_output(root, Path(out), label="lip-sync output")
    from lipsync_backend import LipSyncError, lipsync_one

    try:
        backend_receipt = lipsync_one(
            video=input_video,
            audio=input_audio,
            out=target,
            backend=backend,
            allow_unapproved=False,
            allow_node_fallback=False,
        )
    except LipSyncError as exc:
        raise ShortformError(str(exc)) from exc
    if not target.is_file() or target.is_symlink() or target.stat().st_size <= 0:
        raise ShortformError("locked lip-sync backend produced no safe candidate")
    candidate = {
        "path": _relative(root, target),
        "sha256": _sha256(target),
        "video_sha256": _sha256(input_video),
        "audio_sha256": _sha256(input_audio),
        "backend": backend_receipt.get("chosen_backend")
        or backend_receipt.get("backend")
        or backend,
        "status": "pending_human_review",
        "created_at": utc_now(),
    }
    target_shot["lipsync_candidate"] = candidate
    package["reviews"]["sample"] = {
        "status": "pending",
        "invalidated_at": utc_now(),
        "reason": "new lip-sync candidate requires viewing",
    }
    package["status"] = "pending_sample_review"
    _save(root, package)
    write_json(root / "receipts" / "shortform-lipsync" / f"{shot_id}.json", candidate)
    return {"ok": True, "shot_id": shot_id, "candidate": candidate}


def aroll_broll(root: Path | str, *, beat_id: str) -> list[dict[str, Any]]:
    root, package = _load_package(root)
    if package.get("mode") != "aroll":
        raise ShortformError("A-roll B-roll is only available in A-roll mode")
    beat = next((item for item in package.get("beats") or [] if item.get("id") == beat_id), None)
    if not beat:
        raise ShortformError(f"unknown beat {beat_id}")
    parent = {
        "id": f"{beat_id}_a",
        "duration_sec": beat["duration_sec"],
        "screen_mode": "on_camera",
        "dialogue": beat.get("text", ""),
        "dsl": {"motion": "source performance"},
    }
    return default_dialogue_broll(parent)


def assemble_aroll(
    root: Path | str, *, visual_dir: Path, out: Path | None = None
) -> dict[str, Any]:
    """Re-mux generated visuals with original A-roll audio, never model audio."""
    root, package = _load_package(root)
    if package.get("mode") != "aroll":
        raise ShortformError("assemble-aroll requires A-roll package")
    validation = validate_package(root, require_approved=True)
    if not validation["ok"]:
        raise ShortformError("cannot assemble: " + "; ".join(validation["issues"]))
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ShortformError("ffmpeg and ffprobe are required")
    visual_dir = Path(visual_dir).expanduser().resolve()
    try:
        visual_dir.relative_to(root)
    except ValueError as exc:
        raise ShortformError("visual-dir must live inside project root") from exc
    source = _inside(root, root / package["source"]["video_path"], label="source video")
    work = root / "shortform" / "aroll-assemble"
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for beat in package["beats"]:
        visual_raw = visual_dir / f"{beat['id']}.mp4"
        if visual_raw.is_symlink():
            raise ShortformError(f"visual candidate {visual_raw.name} must not be a symlink")
        visual = visual_raw.resolve()
        try:
            visual.relative_to(root)
        except ValueError as exc:
            raise ShortformError(
                f"visual candidate {visual_raw.name} escapes project root"
            ) from exc
        if not visual.is_file():
            raise ShortformError(f"missing visual candidate {visual.name}")
        part = work / f"{beat['id']}.mp4"
        duration = float(beat["end_sec"]) - float(beat["start_sec"])
        if _duration(visual) < duration - 0.05:
            raise ShortformError(
                f"visual candidate {visual.name} is shorter than its source beat; "
                "regenerate it to the approved source clock"
            )
        command = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            str(beat["start_sec"]),
            "-i",
            str(source),
            "-i",
            str(visual),
            "-t",
            str(duration),
            "-map",
            "1:v:0",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(part),
        ]
        try:
            remux = subprocess.run(
                command, capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired as exc:
            raise ShortformError(
                f"ffmpeg timed out remuxing {beat['id']}"
            ) from exc
        if remux.returncode != 0:
            raise ShortformError(f"ffmpeg failed to remux {beat['id']}")
        parts.append(part)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{part}'\n" for part in parts), encoding="utf-8")
    visual_master = work / "visual-master.mp4"
    try:
        concat_vis = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c:v",
                "copy",
                "-an",
                str(visual_master),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise ShortformError(
            "ffmpeg timed out concatenating A-roll visuals"
        ) from exc
    if concat_vis.returncode != 0:
        raise ShortformError("ffmpeg failed to concatenate A-roll visuals")
    source_duration = _duration(source)
    if abs(_duration(visual_master) - source_duration) > 0.05:
        raise ShortformError("assembled visual clock differs from source audio clock")
    target = out or root / "out" / "shortform-aroll-candidate.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        mux = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(visual_master),
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-shortest",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise ShortformError("ffmpeg timed out concatenating A-roll") from exc
    if mux.returncode != 0:
        raise ShortformError("ffmpeg failed to concatenate A-roll")
    source_audio_pcm_sha256 = _pcm_sha256(source)
    output_audio_pcm_sha256 = _pcm_sha256(target)
    if source_audio_pcm_sha256 != output_audio_pcm_sha256:
        raise ShortformError(
            "A-roll output audio samples differ from the source; candidate is blocked"
        )
    receipt = {
        "kind": "shortform-aroll-assembly",
        "status": "candidate_only",
        "output": _relative(root, target),
        "output_sha256": _sha256(target),
        "source_audio_pcm_sha256": source_audio_pcm_sha256,
        "output_audio_pcm_sha256": output_audio_pcm_sha256,
        "audio_policy": "source_audio_is_lipsync_truth",
        "beat_count": len(parts),
        "created_at": utc_now(),
    }
    write_json(root / "receipts" / "shortform-aroll-assembly.json", receipt)
    package["status"] = "candidate_assembled"
    _save(root, package)
    return receipt
