#!/usr/bin/env python3
"""Checksum provenance from canonical lipsync dialogue to the delivered audio carrier."""

import hashlib
from pathlib import Path
from typing import Any

from performance_evidence import find_shot, performance_contract
from util import read_json, write_json


def _hash(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timeline_shot_ids(root: Path) -> list[str]:
    timeline = read_json(root / "timeline.json") or {}
    return [
        str(shot.get("id"))
        for shot in timeline.get("shots") or []
        if isinstance(shot, dict) and str(shot.get("id") or "").strip()
    ]


def _voice_carrier(root: Path) -> Path | None:
    return next(
        (
            path
            for path in (
                root / "audio" / "narration.wav",
                root / "out" / "voice.wav",
                root / "audio" / "voice.wav",
                root / "out" / "_final_work" / "voice_cat.wav",
            )
            if path.is_file()
        ),
        None,
    )


def _artifact(path: Path | None) -> dict[str, str | None]:
    return {"path": str(path) if path else None, "sha256": _hash(path)}


def _reported_artifact(root: Path, value: Any) -> dict[str, str | None]:
    if isinstance(value, dict):
        raw_path = value.get("path")
        expected = value.get("sha256")
    else:
        raw_path, expected = value, None
    if not raw_path:
        return {"path": None, "sha256": expected}
    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = root / path
    return {"path": str(path), "sha256": _hash(path) or expected}


def build_audio_provenance(root: Path, *, write: bool = True) -> dict[str, Any]:
    """Create a no-spend evidence receipt; it does not identify audio by listening."""
    root = Path(root).expanduser().resolve()
    rehearsal_path = root / "receipts" / "tts-rehearsal.json"
    rehearsal = read_json(rehearsal_path) or {}
    rows = {
        str(item.get("shot_id")): item
        for item in rehearsal.get("shots") or []
        if isinstance(item, dict) and str(item.get("shot_id") or "").strip()
    }
    errors: list[dict[str, str]] = []
    dialogue: list[dict[str, Any]] = []
    for shot_id in _timeline_shot_ids(root):
        shot, required = find_shot(root, shot_id)
        contract = performance_contract(shot, required=required)
        voice = contract.get("channels", {}).get("voice", {})
        if voice.get("kind") != "dialogue" or voice.get("lipsync") is not True:
            continue
        item = rows.get(shot_id)
        if not item:
            errors.append(
                {
                    "code": "DIALOGUE_AUDIO_SOURCE_MISSING",
                    "shot_id": shot_id,
                    "message": "lipsync dialogue lacks a local rehearsal audio source",
                }
            )
            continue
        audio_path = Path(str(item.get("path") or ""))
        actual_hash = _hash(audio_path)
        expected_hash = item.get("audio_sha256")
        dialogue.append(
            {
                "shot_id": shot_id,
                "text": voice.get("text"),
                "rehearsal_path": str(audio_path),
                "audio_sha256": actual_hash,
                "receipt_audio_sha256": expected_hash,
            }
        )
        if not actual_hash or not expected_hash:
            errors.append(
                {
                    "code": "DIALOGUE_AUDIO_HASH_MISSING",
                    "shot_id": shot_id,
                    "message": "rehearsal audio must exist locally and carry a receipt hash",
                }
            )
        elif actual_hash != expected_hash:
            errors.append(
                {
                    "code": "DIALOGUE_AUDIO_HASH_STALE",
                    "shot_id": shot_id,
                    "message": "rehearsal audio bytes no longer match their TTS receipt",
                }
            )
    carrier = _voice_carrier(root)
    manifest = read_json(root / "manifest.json") or {}
    final = (manifest.get("outputs") or {}).get("final_film") or {}
    delivery = (
        read_json(root / "receipts" / "final-delivery.json")
        or read_json(root / "out" / "final-delivery.json")
        or {}
    )
    mix = read_json(root / "audio" / "mix_report.json") or {}
    srt = next((p for p in (root / "out" / "final.srt", root / "final.srt") if p.is_file()), None)
    channels = {
        "dialogue": {"events": dialogue, "stems": []},
        "vo": {"events": [], "stems": [_artifact(carrier)] if carrier else []},
        "native": {
            "events": [],
            "stems": [_reported_artifact(root, delivery.get("native_audio"))]
            if delivery.get("native_audio")
            else [],
        },
        "ambience": {
            "events": list(mix.get("ambience_events") or []),
            "stems": list(mix.get("ambience_stems") or []),
        },
        "foley": {
            "events": list(mix.get("foley_events") or []),
            "stems": list(mix.get("foley_stems") or []),
        },
        "sfx": {
            "events": list(mix.get("sfx_events") or []),
            "stems": list(mix.get("sfx_stems") or []),
        },
        "bgm": {
            "events": list(mix.get("music_cues") or []),
            "stems": [_reported_artifact(root, delivery.get("music"))]
            if delivery.get("music")
            else [],
        },
        "captions": {**_artifact(srt), "events": [], "stems": []},
    }
    required = bool(dialogue or errors)
    if required and not carrier:
        errors.append(
            {
                "code": "FINAL_VOICE_CARRIER_MISSING",
                "shot_id": "",
                "message": "final dialogue delivery needs a local narration/voice carrier artifact",
            }
        )
    if required and not final.get("sha256"):
        errors.append(
            {
                "code": "FINAL_AUDIO_DELIVERY_UNBOUND",
                "shot_id": "",
                "message": "final MP4 must be registered before dialogue provenance can close",
            }
        )
    report = {
        "schema_version": 1,
        "kind": "audio-provenance",
        "required": required,
        "ok": not errors,
        "tts_rehearsal": {"path": str(rehearsal_path), "sha256": _hash(rehearsal_path)},
        "dialogue_sources": dialogue,
        "channels": channels,
        "voice_carrier": {"path": str(carrier) if carrier else None, "sha256": _hash(carrier)},
        "final_delivery": {"sha256": final.get("sha256"), "path": final.get("path")},
        "errors": errors,
        "limitation": "Hashes prove that registered files have not changed. They do not automatically prove semantic audio equivalence or lip-sync quality.",
    }
    path = root / "receipts" / "audio-provenance.json"
    if write:
        write_json(path, report)
    report["path"] = str(path)
    report["sha256"] = _hash(path)
    return report
