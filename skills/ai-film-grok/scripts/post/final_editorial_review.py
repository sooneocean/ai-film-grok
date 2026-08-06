#!/usr/bin/env python3
"""Checksum-bound, no-spend editorial preflight for the finished film."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from delivery_artifact import DeliveryArtifactError, resolve_final_artifact
from media_qa import analyze_media
from util import read_json, utc_now, write_json

RECEIPT_NAME = "final-editorial-review.json"


def _hash(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _first(root: Path, *names: str) -> Path | None:
    return next((root / name for name in names if (root / name).is_file()), None)


def _final_path(root: Path, manifest: dict[str, Any]) -> Path | None:
    try:
        return resolve_final_artifact(root, manifest).path
    except DeliveryArtifactError:
        return _first(root, "out/film_final.mp4", "out/film_hyperframes.mp4", "out/final.mp4")


def _post_tts_dialogue_shots(spec: dict[str, Any]) -> set[str]:
    """Return dialogue that explicitly replaces provider sound with post TTS."""
    result: set[str] = set()
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            for contract in shot.get("dialogue_contracts") or []:
                if not isinstance(contract, dict):
                    continue
                for line in contract.get("lines") or []:
                    if isinstance(line, dict) and line.get("audio_origin") == "post_vo":
                        result.add(str(shot.get("id") or ""))
    return result - {""}


def _inputs(root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, str | None]]:
    final = _final_path(root, manifest)
    return {
        "final": {"path": str(final) if final else None, "sha256": _hash(final)},
        "mix_report": {
            "path": str(root / "audio" / "mix_report.json"),
            "sha256": _hash(root / "audio" / "mix_report.json"),
        },
        "subtitles": {
            "path": str(_first(root, "out/final.srt", "final.srt")),
            "sha256": _hash(_first(root, "out/final.srt", "final.srt")),
        },
        "timeline": {
            "path": str(root / "timeline.json"),
            "sha256": _hash(root / "timeline.json"),
        },
        "film_spec": {
            "path": str(root / "film-spec.json"),
            "sha256": _hash(root / "film-spec.json"),
        },
    }


def audit(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Inspect current finished-film evidence without generating or uploading media."""
    root = Path(root).expanduser().resolve()
    manifest = read_json(root / "manifest.json") or {}
    spec = read_json(root / "film-spec.json") or {}
    inputs = _inputs(root, manifest)
    final = _final_path(root, manifest)
    issues: list[dict[str, Any]] = []

    if final is None:
        issues.append({"code": "FINAL_MP4_MISSING", "message": "final MP4 is missing"})
    else:
        media = analyze_media(final, require_audio=True, require_motion=True)
        if not media.get("ok"):
            issues.append(
                {
                    "code": "FINAL_MEDIA_QA_FAILED",
                    "message": "; ".join(media.get("errors") or ["media QA failed"]),
                }
            )

    from cinematic_audit import audit as cinematic_audit

    cinematic = cinematic_audit(root, require_authored_contract=True, require_media_evidence=True)
    for item in cinematic.get("issues") or []:
        issues.append(
            {
                "code": "CINEMATIC_" + str(item.get("code") or "FAILED"),
                "message": str(item.get("message") or "cinematic audit failed"),
                "shot_ids": item.get("shot_ids") or [],
            }
        )

    from audio_provenance import build_audio_provenance
    from speech_performance_timing import build_speech_performance_timing
    from subtitle_dialogue_alignment import build_subtitle_dialogue_alignment

    audio_provenance = build_audio_provenance(root, write=False)
    speech_timing = build_speech_performance_timing(root, write=False)
    subtitle_alignment = build_subtitle_dialogue_alignment(root, write=False)
    for name, report in (
        ("AUDIO_PROVENANCE", audio_provenance),
        ("SPEECH_TIMING", speech_timing),
        ("SUBTITLE_ALIGNMENT", subtitle_alignment),
    ):
        if report.get("required") and not report.get("ok"):
            for item in report.get("errors") or []:
                issues.append(
                    {
                        "code": f"{name}_{item.get('code') or 'FAILED'}",
                        "message": str(item.get("message") or name.lower() + " failed"),
                        "shot_id": item.get("shot_id") or None,
                    }
                )

    expected_suppression = _post_tts_dialogue_shots(spec)
    mix = read_json(root / "audio" / "mix_report.json") or {}
    native = mix.get("native_audio") if isinstance(mix.get("native_audio"), dict) else {}
    suppressed = {str(item) for item in native.get("suppressed_for_tts_shots") or []}
    preserved = {str(item) for item in native.get("preserved_shots") or []}
    for shot_id in sorted(expected_suppression - suppressed):
        issues.append(
            {
                "code": "POST_TTS_NATIVE_AUDIO_NOT_SUPPRESSED",
                "message": "post-TTS dialogue did not suppress its generated native audio",
                "shot_id": shot_id,
            }
        )
    for shot_id in sorted(expected_suppression & preserved):
        issues.append(
            {
                "code": "DUPLICATE_DIALOGUE_RISK",
                "message": "post TTS and generated native dialogue are both preserved in the final mix",
                "shot_id": shot_id,
            }
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "final-editorial-review",
        "created_at": utc_now(),
        "ok": not issues,
        "decision": "pass" if not issues else "recut_required",
        "inputs": inputs,
        "issues": issues,
        "cinematic_audit": {
            "ok": cinematic.get("ok"),
            "blocking_codes": cinematic.get("blocking_codes"),
        },
        "audio_provenance": {
            "required": audio_provenance.get("required"),
            "ok": audio_provenance.get("ok"),
        },
        "speech_performance_timing": {
            "required": speech_timing.get("required"),
            "ok": speech_timing.get("ok"),
        },
        "subtitle_dialogue_alignment": {
            "required": subtitle_alignment.get("required"),
            "ok": subtitle_alignment.get("ok"),
        },
        "asr": {
            "status": "advisory_only",
            "note": "ASR never approves or rejects delivery by itself",
        },
    }
    if write:
        path = root / "receipts" / RECEIPT_NAME
        write_json(path, report)
        report["path"] = str(path)
    return report


def is_current(root: Path | str, receipt: object) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    stored = receipt if isinstance(receipt, dict) else {}
    manifest = read_json(root / "manifest.json") or {}
    current = _inputs(root, manifest)
    bound = stored.get("inputs") if isinstance(stored.get("inputs"), dict) else {}
    mismatches = [
        name
        for name, item in current.items()
        if (bound.get(name) or {}).get("sha256") != item.get("sha256")
    ]
    return {"ok": not mismatches, "stale": bool(mismatches), "mismatches": mismatches}
