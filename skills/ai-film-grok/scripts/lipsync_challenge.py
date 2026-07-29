#!/usr/bin/env python3
"""Evidence-only control plane for the open-source lip-sync challenge."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any

from media_probe import probe_media, verify_full_decode
from runtime_policy import sha256
from util import read_json, utc_now, write_json

FIXTURE_IDS = (
    "front_closeup",
    "three_quarter",
    "occlusion_motion",
    "anime",
)
BACKEND_IDS = (
    "latentsync-1.6",
    "musetalk-1.5",
    "ltx-2.3-lipdub",
    "echomimic-v3-flash",
    "longcat-video-avatar-1.5",
)
PRESERVATION_BACKENDS = BACKEND_IDS[:3]
GENERATIVE_BACKENDS = BACKEND_IDS[3:]
PRODUCTION_DEFAULT = "latentsync-1.6"
BACKEND_REVIEW_LANES = {
    **{backend_id: "preservation" for backend_id in PRESERVATION_BACKENDS},
    **{backend_id: "whole_frame_generation" for backend_id in GENERATIVE_BACKENDS},
}
HARD_FAILURES = {
    "geometry_distortion",
    "square_force",
    "occluder_overpaint",
    "teeth_lip_color_drift",
    "outside_mouth_spill",
    "identity_failure",
    "decode_failure",
}
SCORE_METRICS = {
    "lip_sync_score",
    "lip_sync_confidence",
    "identity_similarity",
    "mouth_temporal_stability",
    "outside_mouth_similarity",
    "teeth_lip_color_stability",
}
REQUIRED_METRICS = SCORE_METRICS | {"lip_sync_offset_frames"}
SKILL_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = SKILL_ROOT / "registry" / "lipsync-challenge-models.json"


class LipsyncChallengeError(RuntimeError):
    """Challenge evidence is incomplete, inconsistent, or unsafe to trust."""


def _regular_file(path: Path | str, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size == 0:
        raise LipsyncChallengeError(f"{label} must be a non-empty regular file: {candidate}")
    return candidate.resolve()


def _json_object(path: Path | str, label: str) -> tuple[Path, dict[str, Any]]:
    candidate = _regular_file(path, label)
    payload = read_json(candidate)
    if not isinstance(payload, dict):
        raise LipsyncChallengeError(f"{label} must contain a JSON object: {candidate}")
    return candidate, payload


def _manifest(root: Path | str) -> tuple[Path, dict[str, Any]]:
    path = Path(root).expanduser().resolve() / "challenge.json"
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("kind") != "ai-film-lipsync-challenge":
        raise LipsyncChallengeError(f"challenge manifest is missing or invalid: {path}")
    return path, payload


def _registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    payload = read_json(REGISTRY_PATH)
    if not isinstance(payload, dict):
        raise LipsyncChallengeError(f"challenge registry is invalid: {REGISTRY_PATH}")
    items = payload.get("backends")
    if not isinstance(items, list):
        raise LipsyncChallengeError("challenge registry backends must be an array")
    by_id = {
        str(item["id"]): item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if tuple(by_id) != BACKEND_IDS:
        raise LipsyncChallengeError("challenge registry backend set or ordering changed")
    if payload.get("production_default") != PRODUCTION_DEFAULT:
        raise LipsyncChallengeError("challenge registry may not change the production default")
    return payload, by_id


def _fps(value: Any) -> float:
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(Fraction(value))
        except (ValueError, ZeroDivisionError) as exc:
            raise LipsyncChallengeError(f"invalid frame rate: {value}") from exc
    else:
        raise LipsyncChallengeError(f"invalid frame rate: {value}")
    if not math.isfinite(result) or result <= 0:
        raise LipsyncChallengeError(f"invalid frame rate: {value}")
    return result


def _duration(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise LipsyncChallengeError(f"{label} duration is invalid") from exc
    if not math.isfinite(result) or result <= 0:
        raise LipsyncChallengeError(f"{label} duration is invalid")
    return result


def _video_summary(path: Path) -> dict[str, Any]:
    report = probe_media(path)
    if {"width", "height", "fps", "duration_sec"} <= report.keys():
        return {
            "path": str(path),
            "duration_sec": _duration(report["duration_sec"], "video"),
            "width": int(report["width"]),
            "height": int(report["height"]),
            "fps": _fps(report["fps"]),
            "codec": report.get("codec"),
        }
    streams = report.get("streams")
    if not isinstance(streams, list):
        raise LipsyncChallengeError(f"video probe has no streams: {path}")
    video = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if not isinstance(video, dict):
        raise LipsyncChallengeError(f"video stream is missing: {path}")
    format_data = report.get("format") if isinstance(report.get("format"), dict) else {}
    duration_value = video.get("duration") or format_data.get("duration")
    return {
        "path": str(path),
        "duration_sec": _duration(duration_value, "video"),
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": _fps(video.get("avg_frame_rate")),
        "codec": video.get("codec_name"),
    }


def _audio_summary(path: Path) -> dict[str, Any]:
    report = probe_media(path)
    if "duration_sec" in report:
        return {
            "path": str(path),
            "duration_sec": _duration(report["duration_sec"], "audio"),
            "sample_rate": report.get("sample_rate"),
            "channels": report.get("channels"),
            "codec": report.get("codec"),
        }
    streams = report.get("streams")
    if not isinstance(streams, list):
        raise LipsyncChallengeError(f"audio probe has no streams: {path}")
    audio = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        None,
    )
    if not isinstance(audio, dict):
        raise LipsyncChallengeError(f"audio stream is missing: {path}")
    format_data = report.get("format") if isinstance(report.get("format"), dict) else {}
    duration_value = audio.get("duration") or format_data.get("duration")
    return {
        "path": str(path),
        "duration_sec": _duration(duration_value, "audio"),
        "sample_rate": audio.get("sample_rate"),
        "channels": audio.get("channels"),
        "codec": audio.get("codec_name"),
    }


def _probe_video(path: Path) -> dict[str, Any]:
    return _video_summary(path)


def _probe_audio(path: Path) -> dict[str, Any]:
    return _audio_summary(path)


def _verify_full_decode(path: Path) -> None:
    verify_full_decode(path)


def create_challenge(
    root: Path | str,
    *,
    fixtures: dict[str, Path],
    japanese_audio: Path,
    approval_receipt: Path,
) -> dict[str, Any]:
    """Create a no-execute challenge manifest bound to approved source media."""
    if tuple(fixtures) != FIXTURE_IDS:
        raise LipsyncChallengeError(
            f"fixtures must be exactly and in order: {', '.join(FIXTURE_IDS)}"
        )
    destination = Path(root).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    _, approval = _json_object(approval_receipt, "approval receipt")
    if approval.get("approved") is not True:
        raise LipsyncChallengeError("approval receipt does not approve these fixtures")
    audio_path = _regular_file(japanese_audio, "Japanese dialogue audio")
    audio_hash = sha256(audio_path)
    audio_approval = approval.get("audio")
    if (
        not isinstance(audio_approval, dict)
        or audio_approval.get("sha256") != audio_hash
        or audio_approval.get("language") != "ja"
        or audio_approval.get("role") != "final_character_dialogue"
    ):
        raise LipsyncChallengeError("approval receipt does not bind the Japanese dialogue audio")
    audio = {**_probe_audio(audio_path), "sha256": audio_hash, "language": "ja"}
    fixture_approvals = approval.get("fixtures")
    if not isinstance(fixture_approvals, dict):
        raise LipsyncChallengeError("approval receipt fixture bindings are missing")
    fixture_payload: dict[str, Any] = {}
    for fixture_id in FIXTURE_IDS:
        source = _regular_file(fixtures[fixture_id], f"{fixture_id} fixture")
        source_hash = sha256(source)
        binding = fixture_approvals.get(fixture_id)
        if (
            not isinstance(binding, dict)
            or binding.get("sha256") != source_hash
            or binding.get("role") != "lipsync_challenge_source"
        ):
            raise LipsyncChallengeError(f"approval receipt does not bind fixture {fixture_id}")
        probe = _probe_video(source)
        if not 3.0 <= float(probe["duration_sec"]) <= 5.0:
            raise LipsyncChallengeError(f"{fixture_id} must be 3-5 seconds")
        fixture_payload[fixture_id] = {
            "fixture_id": fixture_id,
            "source_media": {**probe, "sha256": source_hash},
        }
    registry, by_id = _registry()
    planned_cells = [
        {
            "fixture_id": fixture_id,
            "backend_id": backend_id,
            "lane": by_id[backend_id]["lane"],
            "state": "awaiting_external_result",
        }
        for fixture_id in FIXTURE_IDS
        for backend_id in BACKEND_IDS
    ]
    manifest = {
        "schema_version": 1,
        "kind": "ai-film-lipsync-challenge",
        "created_at": utc_now(),
        "ok": True,
        "auto_execute": False,
        "gpu_work_authorized": False,
        "production_default": PRODUCTION_DEFAULT,
        "registry": {"path": str(REGISTRY_PATH), "sha256": sha256(REGISTRY_PATH)},
        "approval_receipt": str(Path(approval_receipt).expanduser().resolve()),
        "fixtures": fixture_payload,
        "audio": audio,
        "planned_cells": planned_cells,
        "promotion_rules": {
            "minimum_fixture_wins": 3,
            "required_fixture_count": 4,
            "hard_failure_tolerance": 0,
            "ltx_license_review_required": True,
            "ltx_single_gpu_rtx5090_required": True,
            "generative_backends_final_auto_forbidden": True,
            "default_change_requires_separate_submission": True,
        },
        "registry_snapshot": registry,
    }
    write_json(destination / "challenge.json", manifest)
    return manifest


def _validate_metrics(
    payload: dict[str, Any],
    *,
    backend_id: str,
    output_hash: str,
    source_hash: str,
    audio_hash: str,
) -> dict[str, float]:
    if payload.get("kind") != "ai-film-lipsync-challenge-metrics":
        raise LipsyncChallengeError("metrics receipt kind is invalid")
    bindings = {
        "backend_id": backend_id,
        "output_sha256": output_hash,
        "source_video_sha256": source_hash,
        "audio_sha256": audio_hash,
    }
    if any(payload.get(key) != value for key, value in bindings.items()):
        raise LipsyncChallengeError("metrics receipt does not bind this result")
    evaluator = payload.get("evaluator")
    if not isinstance(evaluator, dict) or not all(
        isinstance(evaluator.get(key), str) and evaluator[key] for key in ("name", "version")
    ):
        raise LipsyncChallengeError("metrics receipt evaluator fingerprint is incomplete")
    model_hash = evaluator.get("model_sha256")
    if not isinstance(model_hash, str) or re.fullmatch(r"[0-9a-f]{64}", model_hash) is None:
        raise LipsyncChallengeError("metrics receipt evaluator model SHA-256 is invalid")
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict) or not metrics.keys() >= REQUIRED_METRICS:
        raise LipsyncChallengeError("metrics receipt is incomplete")
    normalized: dict[str, float] = {}
    for name in REQUIRED_METRICS:
        try:
            value = float(metrics[name])
        except (TypeError, ValueError) as exc:
            raise LipsyncChallengeError(f"metrics receipt {name} is invalid") from exc
        if not math.isfinite(value) or (name in SCORE_METRICS and not 0.0 <= value <= 1.0):
            raise LipsyncChallengeError(f"metrics receipt {name} is out of range")
        normalized[name] = value
    return normalized


def _validate_runtime(
    payload: dict[str, Any], *, backend_id: str, output_hash: str
) -> dict[str, Any]:
    if (
        payload.get("kind") != "ai-film-lipsync-challenge-runtime"
        or payload.get("backend_id") != backend_id
        or payload.get("output_sha256") != output_hash
    ):
        raise LipsyncChallengeError("runtime receipt does not bind this result")
    required = ("executor", "gpu_model", "gpu_count", "peak_vram_mb", "elapsed_sec")
    if payload.get("completed") is not True or any(payload.get(key) is None for key in required):
        raise LipsyncChallengeError("runtime receipt is incomplete")
    if not isinstance(payload["executor"], str) or not payload["executor"].strip():
        raise LipsyncChallengeError("runtime receipt executor is invalid")
    if (
        not isinstance(payload["gpu_model"], str)
        or re.fullmatch(
            r"NVIDIA\s+GeForce\s+RTX\s+5090", payload["gpu_model"].strip(), re.IGNORECASE
        )
        is None
    ):
        raise LipsyncChallengeError("runtime receipt GPU must be NVIDIA GeForce RTX 5090")
    if isinstance(payload["gpu_count"], bool):
        raise LipsyncChallengeError("runtime receipt GPU count is invalid")
    try:
        gpu_count = int(payload["gpu_count"])
        peak_vram = float(payload["peak_vram_mb"])
        elapsed = float(payload["elapsed_sec"])
    except (TypeError, ValueError) as exc:
        raise LipsyncChallengeError("runtime receipt numeric evidence is invalid") from exc
    if gpu_count < 1 or peak_vram < 0 or elapsed <= 0:
        raise LipsyncChallengeError("runtime receipt numeric evidence is out of range")
    return {
        "executor": str(payload["executor"]),
        "gpu_model": str(payload["gpu_model"]),
        "gpu_count": gpu_count,
        "peak_vram_mb": peak_vram,
        "elapsed_sec": elapsed,
        "completed": True,
    }


def register_result(
    root: Path | str,
    *,
    fixture_id: str,
    backend_id: str,
    output: Path,
    metrics_receipt: Path,
    runtime_receipt: Path,
) -> dict[str, Any]:
    """Import externally generated media and bind all measurements to its hash."""
    challenge_path, challenge = _manifest(root)
    _, by_id = _registry()
    if fixture_id not in FIXTURE_IDS or backend_id not in by_id:
        raise LipsyncChallengeError("unknown fixture or backend")
    media_path = _regular_file(output, "challenge output")
    output_hash = sha256(media_path)
    probe = _probe_video(media_path)
    _verify_full_decode(media_path)
    source = challenge["fixtures"][fixture_id]["source_media"]
    metrics_path, metrics_payload = _json_object(metrics_receipt, "metrics receipt")
    runtime_path, runtime_payload = _json_object(runtime_receipt, "runtime receipt")
    metrics = _validate_metrics(
        metrics_payload,
        backend_id=backend_id,
        output_hash=output_hash,
        source_hash=source["sha256"],
        audio_hash=challenge["audio"]["sha256"],
    )
    runtime = _validate_runtime(runtime_payload, backend_id=backend_id, output_hash=output_hash)
    geometry_match = int(probe["width"]) == int(source["width"]) and int(probe["height"]) == int(
        source["height"]
    )
    fps_match = abs(float(probe["fps"]) - float(source["fps"])) <= 0.01
    tolerance = max(0.08, 1.0 / float(source["fps"]))
    duration_match = abs(float(probe["duration_sec"]) - float(source["duration_sec"])) <= tolerance
    checks = {
        "full_decode": True,
        "geometry_match": geometry_match,
        "fps_match": fps_match,
        "duration_match": duration_match,
    }
    result = {
        "schema_version": 1,
        "kind": "ai-film-lipsync-challenge-result",
        "recorded_at": utc_now(),
        "ok": all(checks.values()),
        "challenge_manifest_sha256": sha256(challenge_path),
        "fixture_id": fixture_id,
        "backend_id": backend_id,
        "lane": by_id[backend_id]["lane"],
        "source_video_sha256": source["sha256"],
        "audio_sha256": challenge["audio"]["sha256"],
        "output_path": str(media_path),
        "output_sha256": output_hash,
        "output_media": probe,
        "automatic_hard_checks": checks,
        "metrics_receipt": {"path": str(metrics_path), "sha256": sha256(metrics_path)},
        "runtime_receipt": {"path": str(runtime_path), "sha256": sha256(runtime_path)},
        "metrics": metrics,
        "runtime": runtime,
    }
    output_path = Path(root).expanduser().resolve() / "results" / fixture_id / f"{backend_id}.json"
    write_json(output_path, result)
    return result


def _result(root: Path, fixture_id: str, backend_id: str) -> dict[str, Any] | None:
    payload = read_json(root / "results" / fixture_id / f"{backend_id}.json")
    return payload if isinstance(payload, dict) else None


def _verified_result(
    base: Path,
    challenge_path: Path,
    challenge: dict[str, Any],
    fixture_id: str,
    backend_id: str,
) -> dict[str, Any] | None:
    payload = _result(base, fixture_id, backend_id)
    if payload is None:
        return None
    if (
        payload.get("kind") != "ai-film-lipsync-challenge-result"
        or payload.get("fixture_id") != fixture_id
        or payload.get("backend_id") != backend_id
        or payload.get("challenge_manifest_sha256") != sha256(challenge_path)
    ):
        raise LipsyncChallengeError(
            f"result receipt identity binding is invalid: {fixture_id}/{backend_id}"
        )
    source = challenge["fixtures"][fixture_id]["source_media"]
    if (
        payload.get("source_video_sha256") != source["sha256"]
        or payload.get("audio_sha256") != challenge["audio"]["sha256"]
    ):
        raise LipsyncChallengeError(
            f"result receipt input binding is invalid: {fixture_id}/{backend_id}"
        )
    output = _regular_file(payload.get("output_path", ""), "registered challenge output")
    output_hash = sha256(output)
    if output_hash != payload.get("output_sha256"):
        raise LipsyncChallengeError(f"registered output hash changed: {fixture_id}/{backend_id}")
    metrics_reference = payload.get("metrics_receipt")
    runtime_reference = payload.get("runtime_receipt")
    if not isinstance(metrics_reference, dict) or not isinstance(runtime_reference, dict):
        raise LipsyncChallengeError(
            f"result sidecar references are invalid: {fixture_id}/{backend_id}"
        )
    metrics_path, metrics_payload = _json_object(
        metrics_reference.get("path", ""), "metrics receipt"
    )
    runtime_path, runtime_payload = _json_object(
        runtime_reference.get("path", ""), "runtime receipt"
    )
    if sha256(metrics_path) != metrics_reference.get("sha256") or sha256(
        runtime_path
    ) != runtime_reference.get("sha256"):
        raise LipsyncChallengeError(f"result sidecar hash changed: {fixture_id}/{backend_id}")
    metrics = _validate_metrics(
        metrics_payload,
        backend_id=backend_id,
        output_hash=output_hash,
        source_hash=source["sha256"],
        audio_hash=challenge["audio"]["sha256"],
    )
    runtime = _validate_runtime(runtime_payload, backend_id=backend_id, output_hash=output_hash)
    probe = _probe_video(output)
    _verify_full_decode(output)
    tolerance = max(0.08, 1.0 / float(source["fps"]))
    checks = {
        "full_decode": True,
        "geometry_match": int(probe["width"]) == int(source["width"])
        and int(probe["height"]) == int(source["height"]),
        "fps_match": abs(float(probe["fps"]) - float(source["fps"])) <= 0.01,
        "duration_match": abs(float(probe["duration_sec"]) - float(source["duration_sec"]))
        <= tolerance,
    }
    return {
        **payload,
        "ok": all(checks.values()),
        "output_path": str(output),
        "output_sha256": output_hash,
        "output_media": probe,
        "automatic_hard_checks": checks,
        "metrics": metrics,
        "runtime": runtime,
    }


def create_blind_package(root: Path | str) -> dict[str, Any]:
    """Build original-resolution neutral media names plus a private mapping."""
    base = Path(root).expanduser().resolve()
    challenge_path, challenge = _manifest(base)
    seed = int(sha256(challenge_path)[:16], 16)
    rng = random.Random(seed)
    private_fixtures: dict[str, Any] = {}
    public_fixtures: dict[str, Any] = {}
    media_root = base / "blind" / "media"
    generative_passing = sum(
        1
        for fixture_id in FIXTURE_IDS
        for backend_id in GENERATIVE_BACKENDS
        if (result := _verified_result(base, challenge_path, challenge, fixture_id, backend_id))
        and result.get("ok") is True
    )
    if generative_passing not in {0, len(FIXTURE_IDS) * len(GENERATIVE_BACKENDS)}:
        raise LipsyncChallengeError(
            "whole-frame blind lane requires all eight passing fixture/backend results"
        )
    lane_backends = {
        "preservation": PRESERVATION_BACKENDS,
    }
    if generative_passing:
        lane_backends["whole_frame_generation"] = GENERATIVE_BACKENDS
    for fixture_id in FIXTURE_IDS:
        private_fixtures[fixture_id] = {}
        public_fixtures[fixture_id] = {}
        for lane_name, backend_ids in lane_backends.items():
            lane_results = {
                backend_id: _verified_result(
                    base, challenge_path, challenge, fixture_id, backend_id
                )
                for backend_id in backend_ids
            }
            available = [
                backend_id
                for backend_id, result in lane_results.items()
                if result and result.get("ok") is True
            ]
            if len(available) != len(backend_ids):
                raise LipsyncChallengeError(
                    f"complete passing lane required before blind packaging: "
                    f"{fixture_id}/{lane_name}"
                )
            shuffled = list(backend_ids)
            rng.shuffle(shuffled)
            labels = [f"{lane_name}-candidate-{index + 1}" for index in range(len(shuffled))]
            mapping = dict(zip(labels, shuffled, strict=True))
            public_candidates: list[dict[str, Any]] = []
            for label, backend_id in mapping.items():
                result = lane_results[backend_id]
                assert isinstance(result, dict)
                source = _regular_file(result["output_path"], "registered challenge output")
                if sha256(source) != result.get("output_sha256"):
                    raise LipsyncChallengeError(
                        f"registered output hash changed: {fixture_id}/{backend_id}"
                    )
                target = media_root / fixture_id / f"{label}{source.suffix.lower()}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                public_candidates.append(
                    {
                        "label": label,
                        "path": str(target.relative_to(base / "blind")),
                        "sha256": result["output_sha256"],
                    }
                )
            private_fixtures[fixture_id][lane_name] = mapping
            public_fixtures[fixture_id][lane_name] = public_candidates
    mapping_payload = {
        "schema_version": 1,
        "kind": "ai-film-lipsync-challenge-private-mapping",
        "challenge_manifest_sha256": sha256(challenge_path),
        "fixtures": private_fixtures,
    }
    mapping_path = base / "blind" / "private-mapping.json"
    write_json(mapping_path, mapping_payload)
    mapping_hash = sha256(mapping_path)
    public_payload = {
        "schema_version": 1,
        "kind": "ai-film-lipsync-challenge-blind-review",
        "mapping_sha256": mapping_hash,
        "instructions": {
            "original_resolution_required": True,
            "compare_same_source_audio_fps_geometry": True,
            "hard_failures": sorted(HARD_FAILURES),
        },
        "fixtures": public_fixtures,
    }
    public_path = base / "blind" / "review-template.json"
    write_json(public_path, public_payload)
    return {
        "ok": True,
        "public_template_path": str(public_path),
        "private_mapping_path": str(mapping_path),
        "mapping_sha256": mapping_hash,
    }


def record_blind_review(
    root: Path | str, *, reviewer: str, review: dict[str, Any]
) -> dict[str, Any]:
    """Resolve neutral labels only after a named original-resolution review."""
    base = Path(root).expanduser().resolve()
    reviewer_name = reviewer.strip()
    if (
        not reviewer_name
        or reviewer_name in {".", ".."}
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in reviewer_name
        )
    ):
        raise LipsyncChallengeError("reviewer must be a non-empty path-safe name")
    mapping_path, mapping = _json_object(
        base / "blind" / "private-mapping.json", "private blind mapping"
    )
    mapping_hash = sha256(mapping_path)
    if review.get("mapping_sha256") != mapping_hash:
        raise LipsyncChallengeError("blind review does not bind the current mapping")
    decisions = review.get("decisions")
    if not isinstance(decisions, dict) or set(decisions) != set(FIXTURE_IDS):
        raise LipsyncChallengeError("blind review must decide all four fixtures")
    resolved: dict[str, Any] = {}
    for fixture_id in FIXTURE_IDS:
        fixture_decision = decisions[fixture_id]
        fixture_mapping = mapping["fixtures"][fixture_id]
        if not isinstance(fixture_decision, dict) or set(fixture_decision) != set(fixture_mapping):
            raise LipsyncChallengeError(
                f"blind review must decide every available lane for {fixture_id}"
            )
        resolved[fixture_id] = {}
        for lane_name, labels in fixture_mapping.items():
            lane = fixture_decision.get(lane_name)
            if not isinstance(lane, dict) or lane.get("watched_original_resolution") is not True:
                raise LipsyncChallengeError("blind review must be watched at original resolution")
            winner_label = lane.get("winner_label")
            hard_failures = lane.get("hard_failures")
            if winner_label not in labels or not isinstance(hard_failures, dict):
                raise LipsyncChallengeError(
                    f"blind review labels are invalid for {fixture_id}/{lane_name}"
                )
            resolved_failures: dict[str, list[str]] = {}
            for label, failures in hard_failures.items():
                if label not in labels or not isinstance(failures, list):
                    raise LipsyncChallengeError(
                        f"blind review hard failures are invalid for {fixture_id}/{lane_name}"
                    )
                unknown = set(failures) - HARD_FAILURES
                if unknown:
                    raise LipsyncChallengeError(f"unknown hard failures: {sorted(unknown)}")
                resolved_failures[labels[label]] = list(failures)
            resolved[fixture_id][lane_name] = {
                "winner_backend_id": labels[winner_label],
                "hard_failures": resolved_failures,
                "watched_original_resolution": True,
            }
    receipt = {
        "schema_version": 1,
        "kind": "ai-film-lipsync-challenge-review",
        "recorded_at": utc_now(),
        "reviewer": reviewer_name,
        "mapping_sha256": mapping_hash,
        "decisions": resolved,
    }
    path = base / "reviews" / f"{reviewer_name}.json"
    if path.exists():
        raise LipsyncChallengeError(f"reviewer receipt already exists: {path}")
    write_json(path, receipt)
    return receipt


def _license_approved(path: Path | None) -> bool:
    if path is None:
        return False
    _, payload = _json_object(path, "license receipt")
    return (
        payload.get("approved") is True
        and payload.get("backend_id") == "ltx-2.3-lipdub"
        and isinstance(payload.get("license_id"), str)
        and bool(payload["license_id"])
        and payload.get("commercial_scope_reviewed") is True
        and isinstance(payload.get("reviewer"), str)
        and bool(payload["reviewer"])
    )


def _validated_reviews(base: Path, challenge_path: Path) -> list[dict[str, Any]]:
    review_paths = sorted((base / "reviews").glob("*.json"))
    if not review_paths:
        return []
    mapping_path, mapping = _json_object(
        base / "blind" / "private-mapping.json", "private blind mapping"
    )
    mapping_hash = sha256(mapping_path)
    if (
        mapping.get("kind") != "ai-film-lipsync-challenge-private-mapping"
        or mapping.get("challenge_manifest_sha256") != sha256(challenge_path)
        or set(mapping.get("fixtures", {})) != set(FIXTURE_IDS)
    ):
        raise LipsyncChallengeError("private blind mapping binding is invalid")
    validated: list[dict[str, Any]] = []
    for path in review_paths:
        payload = read_json(path)
        if (
            not isinstance(payload, dict)
            or payload.get("kind") != "ai-film-lipsync-challenge-review"
            or payload.get("mapping_sha256") != mapping_hash
            or set(payload.get("decisions", {})) != set(FIXTURE_IDS)
        ):
            raise LipsyncChallengeError(f"blind review binding is invalid: {path}")
        for fixture_id in FIXTURE_IDS:
            fixture_mapping = mapping["fixtures"][fixture_id]
            fixture_decision = payload["decisions"][fixture_id]
            if not isinstance(fixture_decision, dict) or set(fixture_decision) != set(
                fixture_mapping
            ):
                raise LipsyncChallengeError(
                    f"blind review lane binding is invalid: {path}/{fixture_id}"
                )
            for lane_name, labels in fixture_mapping.items():
                lane = fixture_decision[lane_name]
                allowed_backends = set(labels.values())
                if (
                    not isinstance(lane, dict)
                    or lane.get("watched_original_resolution") is not True
                    or lane.get("winner_backend_id") not in allowed_backends
                    or not isinstance(lane.get("hard_failures"), dict)
                    or not set(lane["hard_failures"]) <= allowed_backends
                ):
                    raise LipsyncChallengeError(
                        f"blind review decision is invalid: {path}/{fixture_id}/{lane_name}"
                    )
                for failures in lane["hard_failures"].values():
                    if not isinstance(failures, list) or set(failures) - HARD_FAILURES:
                        raise LipsyncChallengeError(
                            f"blind review hard failures are invalid: "
                            f"{path}/{fixture_id}/{lane_name}"
                        )
        validated.append(payload)
    return validated


def build_challenge_report(
    root: Path | str, *, license_receipt: Path | None = None
) -> dict[str, Any]:
    """Aggregate receipts without ever authorizing a production default change."""
    base = Path(root).expanduser().resolve()
    challenge_path, challenge = _manifest(base)
    registry, by_id = _registry()
    review_errors: list[str] = []
    try:
        reviews = _validated_reviews(base, challenge_path)
    except LipsyncChallengeError as exc:
        reviews = []
        review_errors.append(str(exc))
    fixture_winners: dict[tuple[str, str], str | None] = {}
    lane_backends = {
        "preservation": PRESERVATION_BACKENDS,
        "whole_frame_generation": GENERATIVE_BACKENDS,
    }
    for fixture_id in FIXTURE_IDS:
        for lane_name, backend_ids in lane_backends.items():
            counts = {
                backend_id: sum(
                    1
                    for review in reviews
                    if review.get("decisions", {})
                    .get(fixture_id, {})
                    .get(lane_name, {})
                    .get("winner_backend_id")
                    == backend_id
                )
                for backend_id in backend_ids
            }
            highest = max(counts.values(), default=0)
            leaders = [backend_id for backend_id, count in counts.items() if count == highest]
            fixture_winners[(fixture_id, lane_name)] = (
                leaders[0] if highest > 0 and len(leaders) == 1 else None
            )
    backend_report: dict[str, Any] = {}
    for backend_id in BACKEND_IDS:
        registration = by_id[backend_id]
        all_results: list[dict[str, Any]] = []
        evidence_errors: list[str] = []
        for fixture_id in FIXTURE_IDS:
            try:
                result = _verified_result(base, challenge_path, challenge, fixture_id, backend_id)
            except LipsyncChallengeError as exc:
                evidence_errors.append(str(exc))
                continue
            if result is not None:
                all_results.append(result)
        results = [result for result in all_results if result.get("ok") is True]
        review_lane = BACKEND_REVIEW_LANES[backend_id]
        wins = sum(
            fixture_winners[(fixture_id, review_lane)] == backend_id for fixture_id in FIXTURE_IDS
        )
        human_hard_failures = [
            failure
            for review in reviews
            for fixture_decision in review.get("decisions", {}).values()
            for lane in fixture_decision.values()
            for failure in lane.get("hard_failures", {}).get(backend_id, [])
        ]
        automatic_hard_failures = sorted(
            {
                check
                for result in all_results
                for check, passed in result.get("automatic_hard_checks", {}).items()
                if passed is not True
            }
        )
        hard_failures = human_hard_failures + automatic_hard_failures
        single_gpu_count = sum(
            1
            for result in results
            if result.get("runtime", {}).get("gpu_count") == 1
            and "5090" in result.get("runtime", {}).get("gpu_model", "")
        )
        if backend_id == PRODUCTION_DEFAULT:
            state = "production_default"
        elif backend_id in GENERATIVE_BACKENDS:
            state = "pilot_only"
        elif evidence_errors or review_errors:
            state = "blocked_evidence"
        elif hard_failures:
            state = "blocked_hard_failure"
        elif len(results) < 4 or not reviews:
            state = "pending_evidence"
        elif wins < 3:
            state = "challenger"
        elif backend_id == "ltx-2.3-lipdub" and not _license_approved(license_receipt):
            state = "blocked_license_review"
        elif backend_id == "ltx-2.3-lipdub" and single_gpu_count < 4:
            state = "blocked_single_gpu_evidence"
        else:
            state = "production_candidate"
        metric_names = sorted(REQUIRED_METRICS)
        metric_averages = (
            {
                name: sum(float(result["metrics"][name]) for result in results) / len(results)
                for name in metric_names
            }
            if results
            else {}
        )
        backend_report[backend_id] = {
            "lane": registration["lane"],
            "task_type": registration["task_type"],
            "state": state,
            "passing_fixture_count": len(results),
            "recorded_fixture_count": len(all_results),
            "failure_rate": (4 - len(results)) / 4,
            "human_wins": wins,
            "hard_failures": hard_failures,
            "evidence_errors": evidence_errors + review_errors,
            "single_gpu_fixture_count": single_gpu_count,
            "metric_averages": metric_averages,
            "peak_vram_mb_max": max(
                (float(result["runtime"]["peak_vram_mb"]) for result in results),
                default=None,
            ),
            "elapsed_sec_total": sum(float(result["runtime"]["elapsed_sec"]) for result in results),
            "output_sha256": [result["output_sha256"] for result in all_results],
            "final_auto_route_eligible": registration["final_auto_route_eligible"],
        }
    ready = any(
        item["state"] == "production_candidate"
        for backend_id, item in backend_report.items()
        if backend_id != PRODUCTION_DEFAULT
    )
    report = {
        "schema_version": 1,
        "kind": "ai-film-lipsync-challenge-report",
        "generated_at": utc_now(),
        "production_default": registry["production_default"],
        "backends": backend_report,
        "route_change_submission_ready": ready,
        "default_route_change_authorized": False,
        "note": "A production candidate still requires a separate reviewed route-change submission.",
    }
    write_json(base / "report.json", report)
    return report


def _load_fixture_args(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "front_closeup": Path(args.front_closeup),
        "three_quarter": Path(args.three_quarter),
        "occlusion_motion": Path(args.occlusion_motion),
        "anime": Path(args.anime),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--root", required=True)
    create.add_argument("--front-closeup", required=True)
    create.add_argument("--three-quarter", required=True)
    create.add_argument("--occlusion-motion", required=True)
    create.add_argument("--anime", required=True)
    create.add_argument("--audio", required=True)
    create.add_argument("--approval-receipt", required=True)
    register = subparsers.add_parser("register-result")
    register.add_argument("--root", required=True)
    register.add_argument("--fixture-id", required=True, choices=FIXTURE_IDS)
    register.add_argument("--backend-id", required=True, choices=BACKEND_IDS)
    register.add_argument("--output", required=True)
    register.add_argument("--metrics-receipt", required=True)
    register.add_argument("--runtime-receipt", required=True)
    package = subparsers.add_parser("blind-package")
    package.add_argument("--root", required=True)
    review = subparsers.add_parser("review")
    review.add_argument("--root", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--review-json", required=True)
    report = subparsers.add_parser("report")
    report.add_argument("--root", required=True)
    report.add_argument("--license-receipt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "create":
        result = create_challenge(
            args.root,
            fixtures=_load_fixture_args(args),
            japanese_audio=Path(args.audio),
            approval_receipt=Path(args.approval_receipt),
        )
    elif args.action == "register-result":
        result = register_result(
            args.root,
            fixture_id=args.fixture_id,
            backend_id=args.backend_id,
            output=Path(args.output),
            metrics_receipt=Path(args.metrics_receipt),
            runtime_receipt=Path(args.runtime_receipt),
        )
    elif args.action == "blind-package":
        result = create_blind_package(args.root)
    elif args.action == "review":
        _, review = _json_object(args.review_json, "blind review")
        result = record_blind_review(args.root, reviewer=args.reviewer, review=review)
    else:
        result = build_challenge_report(
            args.root,
            license_receipt=Path(args.license_receipt) if args.license_receipt else None,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
