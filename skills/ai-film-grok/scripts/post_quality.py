"""Film-post contracts: VFX registry, audio delivery and premium Master QC."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from util import read_json, write_json


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_vfx_shot(
    root: Path | str,
    *,
    shot_id: str,
    plate: str,
    status: str,
    reviewer: str,
    notes: str = "",
) -> dict[str, Any]:
    if status not in {"pending", "wip", "review", "approved", "rejected"}:
        raise ValueError("status must be pending|wip|review|approved|rejected")
    if not shot_id.strip() or not reviewer.strip():
        raise ValueError("shot_id and reviewer are required")
    base = Path(root).expanduser().resolve()
    path = base / "receipts" / "vfx-shots.json"
    report = read_json(path) or {"schema_version": 1, "kind": "vfx-shots", "shots": {}}
    plate_path = Path(plate).expanduser()
    if not plate_path.is_absolute():
        plate_path = base / plate_path
    report.setdefault("shots", {})[shot_id] = {
        "shot_id": shot_id,
        "plate": str(plate_path),
        "plate_sha256": _sha(plate_path),
        "status": status,
        "reviewer": reviewer.strip(),
        "notes": notes.strip(),
    }
    report["ok"] = all(item.get("status") == "approved" for item in report["shots"].values())
    write_json(path, report)
    return report


def vfx_gate(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    report = read_json(base / "receipts" / "vfx-shots.json") or {}
    blockers: list[dict[str, str]] = []
    for shot_id, item in (report.get("shots") or {}).items():
        plate = Path(str(item.get("plate") or ""))
        if not plate.is_absolute():
            plate = base / plate
        if item.get("status") != "approved":
            blockers.append(
                {"code": "VFX_NOT_APPROVED", "message": f"{shot_id} has unresolved VFX status"}
            )
        if not plate.is_file() or item.get("plate_sha256") != _sha(plate):
            blockers.append(
                {"code": "VFX_PLATE_STALE", "message": f"{shot_id} plate hash is stale"}
            )
    if not report:
        blockers.append(
            {
                "code": "VFX_REGISTRY_MISSING",
                "message": "VFX registry is required before Master Lock",
            }
        )
    return {
        "ok": not blockers,
        "kind": "vfx-gate",
        "blockers": blockers,
        "shot_count": len(report.get("shots") or {}),
    }


def audio_delivery_gate(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    mix = (
        read_json(base / "audio" / "mix_report.json")
        or read_json(base / "receipts" / "mix_report.json")
        or {}
    )
    blockers: list[dict[str, str]] = []
    if not mix:
        blockers.append({"code": "MIX_REPORT_MISSING", "message": "mix_report.json is required"})
    if mix:
        for stem in ("dialogue", "adr", "ambience", "foley", "sfx", "music"):
            if stem not in mix.get("stems", {}) and not mix.get(f"{stem}_stems"):
                blockers.append(
                    {"code": "AUDIO_STEM_MISSING", "message": f"missing professional stem: {stem}"}
                )
        lufs = mix.get("integrated_lufs")
        peak = mix.get("true_peak_dbtp")
        if lufs is None or not -18 <= float(lufs) <= -14:
            blockers.append(
                {
                    "code": "LOUDNESS_OUT_OF_RANGE",
                    "message": "integrated loudness must be -16 LUFS ±2",
                }
            )
        if peak is None or float(peak) > -1:
            blockers.append(
                {"code": "TRUE_PEAK_TOO_HIGH", "message": "true peak must be <= -1 dBTP"}
            )
        if mix.get("dialogue_intelligibility_ok") is not True:
            blockers.append(
                {
                    "code": "DIALOGUE_INTELLIGIBILITY_MISSING",
                    "message": "dialogue intelligibility review is required",
                }
            )
    return {"ok": not blockers, "kind": "audio-delivery-gate", "blockers": blockers}


def premium_master_qc(root: Path | str, *, final: str | None = None) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    final_path = Path(final).expanduser() if final else base / "out" / "film_final.mp4"
    if not final_path.is_absolute():
        final_path = base / final_path
    blockers: list[dict[str, str]] = []
    if not final_path.is_file():
        blockers.append({"code": "MASTER_MISSING", "message": "final master MP4 is missing"})
    else:
        try:
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(final_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            data = json.loads(proc.stdout or "{}")
            streams = data.get("streams") or []
            video = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
            if not video or int(video.get("height") or 0) <= int(video.get("width") or 0):
                blockers.append(
                    {"code": "MASTER_NOT_VERTICAL", "message": "master must be 9:16 vertical"}
                )
            if not audio:
                blockers.append(
                    {"code": "MASTER_AUDIO_MISSING", "message": "master audio stream is missing"}
                )
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            blockers.append({"code": "MASTER_READBACK_FAILED", "message": str(exc)})
    vfx = vfx_gate(base)
    audio = audio_delivery_gate(base)
    if not vfx["ok"]:
        blockers.extend(vfx["blockers"])
    if not audio["ok"]:
        blockers.extend(audio["blockers"])
    caption = read_json(base / "receipts" / "final-stages.json") or {}
    if caption.get("burned_in") is not True:
        blockers.append(
            {
                "code": "CAPTION_BURN_MISSING",
                "message": "pixel-visible burned captions are required",
            }
        )
    report = {
        "schema_version": 1,
        "kind": "premium-master-qc",
        "final": str(final_path),
        "final_sha256": _sha(final_path),
        "ok": not blockers,
        "human_review_required": True,
        "blockers": blockers,
        "vfx": vfx,
        "audio": audio,
    }
    write_json(base / "receipts" / "premium-master-qc.json", report)
    return report
