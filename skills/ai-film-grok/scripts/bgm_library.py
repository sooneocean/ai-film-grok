"""Shared, approval-gated ACE-Step BGM library with anti-repetition routing."""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import shutil
import uuid
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from audio_node_client import AudioNodeError, render_batch
from util import canonical_json_sha256, exclusive_file_lock, read_json, sha256_file, write_json

SCHEMA = "aifilm-bgm-library-v1"
SELECTION_SCHEMA = "aifilm-bgm-selection-v1"
MOODS = ("rnb", "sensual", "dark", "warm", "playful")
STEM_PROFILES = ("pad", "thin", "pulse", "full")
HARD_DUPLICATE_SIMILARITY = 0.98
CLUSTER_SIMILARITY = 0.90
READY_MIN_TOTAL = 20
READY_MIN_PER_MOOD = 4


class BGMLibraryError(RuntimeError):
    pass


def default_library_root() -> Path:
    raw = os.environ.get("AIFILM_BGM_LIBRARY_ROOT", "").strip()
    return (
        Path(raw).expanduser().resolve() if raw else Path.home() / ".grok/ai-film-grok/bgm-library"
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _catalog_path(root: Path) -> Path:
    return root / "catalog.json"


def _empty_catalog() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "revision": 0,
        "updated_at": _now(),
        "assets": {},
    }


def _load_catalog(root: Path) -> dict[str, Any]:
    data = read_json(_catalog_path(root))
    if data is None:
        return _empty_catalog()
    if data.get("schema") != SCHEMA or not isinstance(data.get("assets"), dict):
        raise BGMLibraryError("BGM library catalog is invalid")
    return data


def _write_catalog(root: Path, catalog: dict[str, Any]) -> None:
    catalog["revision"] = int(catalog.get("revision") or 0) + 1
    catalog["updated_at"] = _now()
    write_json(_catalog_path(root), catalog)


def _safe_asset_path(root: Path, relative: str) -> Path:
    path = root / relative
    try:
        resolved_root = root.resolve()
        resolved_parent = path.parent.resolve()
        if not resolved_parent.is_relative_to(resolved_root):
            raise BGMLibraryError("BGM asset path escapes the library")
        current = resolved_root
        for part in path.relative_to(root).parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise BGMLibraryError("BGM asset path contains a symlink")
    except (OSError, ValueError) as exc:
        if isinstance(exc, BGMLibraryError):
            raise
        raise BGMLibraryError("BGM asset path is invalid") from exc
    return path


def _read_wav(path: Path) -> tuple[np.ndarray, int, int]:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frames = handle.getnframes()
            raw = handle.readframes(frames)
    except (OSError, EOFError, wave.Error) as exc:
        raise BGMLibraryError("BGM candidate is not a readable WAV") from exc
    if channels != 2 or sample_width != 2 or sample_rate != 44100 or frames <= 0:
        raise BGMLibraryError("BGM candidate must be 44.1kHz stereo PCM s16le WAV")
    pcm = np.frombuffer(raw, dtype="<i2")
    if pcm.size != frames * channels:
        raise BGMLibraryError("BGM candidate WAV is truncated")
    stereo = pcm.reshape(-1, channels).astype(np.float64) / 32768.0
    return stereo, sample_rate, frames


def _audio_fingerprint(stereo: np.ndarray, sample_rate: int) -> list[float]:
    """Build a gain-invariant spectral/temporal fingerprint with NumPy only."""
    mono = stereo.mean(axis=1)
    if mono.size > sample_rate * 60:
        mono = mono[: sample_rate * 60]
    mono = mono[::4]
    if mono.size < 2048:
        mono = np.pad(mono, (0, 2048 - mono.size))
    mono = mono - float(np.mean(mono))
    peak = float(np.max(np.abs(mono)))
    if peak > 1e-9:
        mono = mono / peak

    block_count = 24
    blocks = np.array_split(mono, block_count)
    rms = np.array([math.sqrt(float(np.mean(block * block)) + 1e-12) for block in blocks])
    rms = rms / max(float(np.mean(rms)), 1e-9)
    zcr = np.array(
        [
            float(np.mean(np.signbit(block[:-1]) != np.signbit(block[1:])))
            if block.size > 1
            else 0.0
            for block in blocks
        ]
    )

    window_size = 4096
    step = 2048
    windows: list[np.ndarray] = []
    for start in range(0, max(1, mono.size - window_size + 1), step):
        chunk = mono[start : start + window_size]
        if chunk.size < window_size:
            chunk = np.pad(chunk, (0, window_size - chunk.size))
        spectrum = np.abs(np.fft.rfft(chunk * np.hanning(window_size))) + 1e-9
        windows.append(spectrum / float(np.sum(spectrum)))
        if len(windows) >= 96:
            break
    mean_spectrum = np.mean(windows, axis=0)
    edges = np.unique(
        np.clip(
            np.geomspace(1, len(mean_spectrum) - 1, num=65).astype(int),
            1,
            len(mean_spectrum) - 1,
        )
    )
    bands = []
    for start, end in zip(edges[:-1], edges[1:], strict=False):
        bands.append(float(np.sum(mean_spectrum[start:end])))
    band_array = np.asarray(bands, dtype=np.float64)
    band_array /= max(float(np.linalg.norm(band_array)), 1e-9)

    # Spectral identity carries more duplicate signal than the generic envelope;
    # otherwise two steady but differently pitched beds look artificially alike.
    vector = np.concatenate((rms * 0.5, zcr, band_array * 3.0))
    vector /= max(float(np.linalg.norm(vector)), 1e-9)
    return [round(float(value), 8) for value in vector]


def _similarity(left: list[float], right: list[float]) -> float:
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if a.shape != b.shape or not a.size:
        return 0.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def _technical(path: Path) -> dict[str, Any]:
    stereo, sample_rate, frames = _read_wav(path)
    peak = float(np.max(np.abs(stereo)))
    rms = math.sqrt(float(np.mean(stereo * stereo)) + 1e-12)
    block = max(1, sample_rate // 2)
    silence = []
    for start in range(0, len(stereo), block):
        chunk = stereo[start : start + block]
        silence.append(math.sqrt(float(np.mean(chunk * chunk)) + 1e-12) < 0.001)
    duration = frames / sample_rate
    errors: list[str] = []
    if duration < 0.5:
        errors.append("duration_too_short")
    if rms < 0.001:
        errors.append("mostly_silent")
    if peak >= 0.9999:
        errors.append("clipping_risk")
    return {
        "ok": not errors,
        "errors": errors,
        "codec": "pcm_s16le",
        "sample_rate": sample_rate,
        "channels": 2,
        "duration_sec": round(duration, 6),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "silence_ratio": round(sum(silence) / max(1, len(silence)), 6),
        "fingerprint": _audio_fingerprint(stereo, sample_rate),
    }


def stage_candidate(
    library_root: Path | str,
    source: Path | str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    source_input = Path(source).expanduser()
    if source_input.is_symlink():
        raise BGMLibraryError("BGM candidate source is missing or symlinked")
    source_path = source_input.resolve()
    if not source_path.is_file():
        raise BGMLibraryError("BGM candidate source is missing or symlinked")
    mood = str(metadata.get("mood") or "").strip().lower()
    if mood not in MOODS:
        raise BGMLibraryError(f"BGM mood must be one of {MOODS}")
    technical = _technical(source_path)
    if not technical["ok"]:
        raise BGMLibraryError(
            "BGM candidate failed technical checks: " + ", ".join(technical["errors"])
        )
    asset_id = f"{mood}-{int(metadata.get('seed') or 0)}-{uuid.uuid4().hex[:10]}"
    relative = f"pending/{asset_id}.wav"
    destination = _safe_asset_path(root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial.wav")
    shutil.copyfile(source_path, temporary)
    if sha256_file(temporary) != sha256_file(source_path):
        temporary.unlink(missing_ok=True)
        raise BGMLibraryError("BGM candidate changed while staging")
    temporary.replace(destination)

    recipe = metadata.get("recipe") if isinstance(metadata.get("recipe"), dict) else {}
    recipe = {key: value for key, value in recipe.items() if key != "prompt"}
    record = {
        "schema": "aifilm-bgm-asset-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "path": relative,
        "sha256": sha256_file(destination),
        "model": str(metadata.get("model") or "ACE-Step-1.5"),
        "checkpoint_fingerprint": str(metadata.get("checkpoint_fingerprint") or "unknown"),
        "node_job_id": str(metadata.get("node_job_id") or ""),
        "seed": int(metadata.get("seed") or 0),
        "prompt_sha256": str(metadata.get("prompt_sha256") or ""),
        "recipe": recipe,
        "mood": mood,
        "dramatic_tags": sorted(
            {
                str(tag).strip().lower()
                for tag in metadata.get("dramatic_tags") or recipe.get("dramatic_tags") or []
                if str(tag).strip()
            }
        ),
        "energy": max(0.0, min(1.0, float(metadata.get("energy") or recipe.get("energy") or 0.5))),
        "stem_profile": str(
            metadata.get("stem_profile") or recipe.get("stem_profile") or "pad"
        ).lower(),
        "bpm": int(metadata.get("bpm") or recipe.get("bpm") or 0) or None,
        "keyscale": str(metadata.get("keyscale") or recipe.get("keyscale") or ""),
        "timesignature": str(metadata.get("timesignature") or recipe.get("timesignature") or "4/4"),
        "motif_family": str(
            metadata.get("motif_family") or recipe.get("motif_family") or ""
        ).strip(),
        "series_id": str(metadata.get("series_id") or recipe.get("series_id") or "").strip(),
        "parent_asset_id": metadata.get("parent_asset_id"),
        "technical": technical,
        "instrumental": False,
        "similarity_cluster": None,
        "human_review": None,
        "license_note": "",
        "use_count": 0,
        "last_used_at": None,
        "last_used_film_id": None,
        "created_at": _now(),
    }
    catalog_path = _catalog_path(root)
    with exclusive_file_lock(catalog_path):
        catalog = _load_catalog(root)
        catalog["assets"][asset_id] = record
        _write_catalog(root, catalog)
    write_json(root / "receipts" / f"{asset_id}.json", record)
    return dict(record)


def _lineage_allows_similarity(
    candidate: dict[str, Any], existing: dict[str, Any], assets: dict[str, Any]
) -> bool:
    parent_id = str(candidate.get("parent_asset_id") or "")
    motif = str(candidate.get("motif_family") or "")
    if not parent_id or not motif:
        return False
    parent = assets.get(parent_id)
    if not isinstance(parent, dict) or parent.get("status") != "approved":
        return False
    # A direct parent binding is the explicit lineage proof. Baseline masters
    # intentionally have no series motif until a series pack derives one.
    return existing.get("asset_id") == parent_id or (
        str(existing.get("motif_family") or "") == motif
        and str(existing.get("series_id") or "") == str(candidate.get("series_id") or "")
        and str(existing.get("parent_asset_id") or "") == parent_id
    )


def approve_candidate(
    library_root: Path | str,
    asset_id: str,
    *,
    reviewer: str,
    license_note: str,
    instrumental_confirmed: bool,
) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    reviewer = reviewer.strip()
    license_note = license_note.strip()
    if not reviewer or not license_note or not instrumental_confirmed:
        raise BGMLibraryError(
            "approval requires reviewer, license note, and instrumental confirmation"
        )
    catalog_path = _catalog_path(root)
    with exclusive_file_lock(catalog_path):
        catalog = _load_catalog(root)
        assets = catalog["assets"]
        record = assets.get(asset_id)
        if not isinstance(record, dict) or record.get("status") != "pending_human_review":
            raise BGMLibraryError("only pending BGM candidates can be approved")
        source = _safe_asset_path(root, str(record.get("path") or ""))
        if (
            not source.is_file()
            or source.is_symlink()
            or sha256_file(source) != record.get("sha256")
        ):
            raise BGMLibraryError("BGM candidate is missing or its hash changed")
        technical = _technical(source)
        if not technical["ok"]:
            raise BGMLibraryError("BGM candidate no longer passes technical checks")
        nearest: dict[str, Any] | None = None
        nearest_similarity = 0.0
        for existing in assets.values():
            if not isinstance(existing, dict) or existing.get("status") != "approved":
                continue
            if existing.get("sha256") == record.get("sha256"):
                raise BGMLibraryError("BGM candidate is an exact duplicate")
            similarity = _similarity(
                technical["fingerprint"], (existing.get("technical") or {}).get("fingerprint") or []
            )
            if similarity > nearest_similarity:
                nearest, nearest_similarity = existing, similarity
        if (
            nearest is not None
            and nearest_similarity >= HARD_DUPLICATE_SIMILARITY
            and not _lineage_allows_similarity(record, nearest, assets)
        ):
            raise BGMLibraryError(
                f"BGM candidate is a near duplicate of {nearest['asset_id']} "
                f"({nearest_similarity:.4f})"
            )
        if nearest is not None and nearest_similarity >= CLUSTER_SIMILARITY:
            cluster = str(nearest.get("similarity_cluster") or nearest["asset_id"])
        else:
            cluster = asset_id
        destination_rel = f"approved/{asset_id}.wav"
        destination = _safe_asset_path(root, destination_rel)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
        record.update(
            {
                "status": "approved",
                "path": destination_rel,
                "technical": technical,
                "instrumental": True,
                "similarity_cluster": cluster,
                "license_note": license_note,
                "human_review": {
                    "reviewer": reviewer,
                    "instrumental_confirmed": True,
                    "approved_at": _now(),
                },
            }
        )
        _write_catalog(root, catalog)
    write_json(root / "receipts" / f"{asset_id}.json", record)
    return dict(record)


def reject_candidate(
    library_root: Path | str, asset_id: str, *, reviewer: str, reason: str
) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    if not reviewer.strip() or not reason.strip():
        raise BGMLibraryError("rejection requires reviewer and reason")
    catalog_path = _catalog_path(root)
    with exclusive_file_lock(catalog_path):
        catalog = _load_catalog(root)
        record = catalog["assets"].get(asset_id)
        if not isinstance(record, dict) or record.get("status") != "pending_human_review":
            raise BGMLibraryError("only pending BGM candidates can be rejected")
        record.update(
            {
                "status": "rejected",
                "human_review": {
                    "reviewer": reviewer.strip(),
                    "reason": reason.strip(),
                    "rejected_at": _now(),
                },
            }
        )
        _write_catalog(root, catalog)
    write_json(root / "receipts" / f"{asset_id}.json", record)
    return dict(record)


def _usage_events(root: Path) -> list[dict[str, Any]]:
    path = root / "usage.jsonl"
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def library_status(library_root: Path | str) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    catalog = _load_catalog(root)
    assets = catalog["assets"]
    counts = {status: 0 for status in ("pending_human_review", "approved", "rejected")}
    by_mood = {mood: 0 for mood in MOODS}
    for record in assets.values():
        if not isinstance(record, dict):
            continue
        status = str(record.get("status") or "")
        if status in counts:
            counts[status] += 1
        if status == "approved" and record.get("mood") in by_mood:
            by_mood[str(record["mood"])] += 1
    ready = counts["approved"] >= READY_MIN_TOTAL and all(
        by_mood[mood] >= READY_MIN_PER_MOOD for mood in MOODS
    )
    return {
        "schema": SCHEMA,
        "root": str(root),
        "catalog_revision": int(catalog.get("revision") or 0),
        "catalog_sha256": canonical_json_sha256(catalog),
        "counts": counts,
        "approved_by_mood": by_mood,
        "ready_for_default": ready,
        "minimum": {"total": READY_MIN_TOTAL, "per_mood": READY_MIN_PER_MOOD},
        "assets": assets,
    }


def audit_library(library_root: Path | str) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    catalog = _load_catalog(root)
    errors: list[dict[str, str]] = []
    approved_hashes: dict[str, str] = {}
    for asset_id, record in catalog["assets"].items():
        if not isinstance(record, dict):
            errors.append({"asset_id": str(asset_id), "code": "INVALID_RECORD"})
            continue
        try:
            path = _safe_asset_path(root, str(record.get("path") or ""))
        except BGMLibraryError:
            errors.append({"asset_id": asset_id, "code": "UNSAFE_PATH"})
            continue
        if not path.is_file() or path.is_symlink():
            errors.append({"asset_id": asset_id, "code": "MISSING_ASSET"})
            continue
        if sha256_file(path) != record.get("sha256"):
            errors.append({"asset_id": asset_id, "code": "CHECKSUM_MISMATCH"})
        if record.get("status") == "approved":
            if (
                not record.get("license_note")
                or record.get("instrumental") is not True
                or not (record.get("human_review") or {}).get("instrumental_confirmed")
            ):
                errors.append({"asset_id": asset_id, "code": "APPROVAL_INCOMPLETE"})
            checksum = str(record.get("sha256") or "")
            if checksum in approved_hashes:
                errors.append({"asset_id": asset_id, "code": "DUPLICATE_APPROVED_HASH"})
            approved_hashes[checksum] = asset_id
    return {
        "ok": not errors,
        "schema": SCHEMA,
        "catalog_revision": catalog.get("revision"),
        "asset_count": len(catalog["assets"]),
        "errors": errors,
    }


def _recent_assets(events: list[dict[str, Any]], *, film_id: str) -> set[str]:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    recent_films: list[str] = []
    for event in reversed(events):
        prior_film = str(event.get("film_id") or "")
        if prior_film and prior_film != film_id and prior_film not in recent_films:
            recent_films.append(prior_film)
        if len(recent_films) >= 5:
            break
    result: set[str] = set()
    for event in events:
        used_at_raw = str(event.get("used_at") or "")
        try:
            used_at = datetime.fromisoformat(used_at_raw)
            if used_at.tzinfo is None:
                used_at = used_at.replace(tzinfo=UTC)
        except ValueError:
            used_at = datetime.min.replace(tzinfo=UTC)
        if str(event.get("film_id") or "") in recent_films or used_at >= cutoff:
            result.add(str(event.get("asset_id") or ""))
    return result


def _selection_score(
    record: dict[str, Any], cue: dict[str, Any], *, series_id: str, recent: bool
) -> tuple[float, list[str]]:
    score = 0.0
    reasons = ["approved", f"mood={record['mood']}"]
    motif = str(cue.get("motif_id") or "")
    if series_id and record.get("series_id") == series_id:
        score += 40
        reasons.append("series_pack")
    if motif and record.get("motif_family") == motif:
        score += 35
        reasons.append("motif_match")
    cue_tags = {str(tag).lower() for tag in cue.get("dramatic_tags") or []}
    record_tags = {str(tag).lower() for tag in record.get("dramatic_tags") or []}
    overlap = len(cue_tags & record_tags)
    score += overlap * 8
    if overlap:
        reasons.append(f"dramatic_tags={overlap}")
    energy_delta = abs(float(cue.get("energy") or 0.5) - float(record.get("energy") or 0.5))
    score += max(0.0, 15.0 * (1.0 - energy_delta))
    reasons.append(f"energy_delta={energy_delta:.3f}")
    if str(record.get("stem_profile") or "") == str(cue.get("stem_profile") or ""):
        score += 10
        reasons.append("stem_match")
    score -= min(20, int(record.get("use_count") or 0)) * 1.5
    if recent:
        score -= 30
    return score, reasons


def select_timeline(
    library_root: Path | str,
    *,
    film_id: str,
    timeline: list[dict[str, Any]],
    series_id: str = "",
    require_complete: bool = True,
) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    status = library_status(root)
    catalog = _load_catalog(root)
    approved = []
    for record in catalog["assets"].values():
        if not (
            isinstance(record, dict)
            and record.get("status") == "approved"
            and (record.get("technical") or {}).get("ok")
            and record.get("instrumental") is True
            and record.get("license_note")
            and (record.get("human_review") or {}).get("instrumental_confirmed")
        ):
            continue
        asset_id = str(record.get("asset_id") or "")
        path = _safe_asset_path(root, str(record.get("path") or ""))
        if not path.is_file() or path.is_symlink() or sha256_file(path) != record.get("sha256"):
            raise BGMLibraryError(f"approved BGM asset failed integrity check: {asset_id}")
        approved.append(record)
    events = _usage_events(root)
    recent_assets = _recent_assets(events, film_id=film_id)
    used_assets: set[str] = set()
    previous_cluster = ""
    selections: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    diversity_relaxed = False
    for cue in timeline:
        mood = str(cue.get("mood") or "rnb").lower()
        eligible = [
            record
            for record in approved
            if record.get("mood") == mood
            and record.get("asset_id") not in used_assets
            and str(record.get("similarity_cluster") or "") != previous_cluster
        ]
        non_recent = [
            record for record in eligible if str(record.get("asset_id") or "") not in recent_assets
        ]
        if non_recent:
            eligible = non_recent
        elif eligible and any(
            str(record.get("asset_id") or "") in recent_assets for record in eligible
        ):
            diversity_relaxed = True
        if not eligible:
            gaps.append(
                {
                    "shot_id": str(cue.get("shot_id") or ""),
                    "mood": mood,
                    "motif_id": str(cue.get("motif_id") or ""),
                    "energy": float(cue.get("energy") or 0.5),
                    "stem_profile": str(cue.get("stem_profile") or ""),
                    "reason": "no_eligible_approved_asset",
                }
            )
            continue
        ranked = []
        for record in eligible:
            score, reasons = _selection_score(
                record,
                cue,
                series_id=series_id,
                recent=str(record.get("asset_id") or "") in recent_assets,
            )
            ranked.append((score, str(record["asset_id"]), record, reasons))
        ranked.sort(key=lambda row: (-row[0], int(row[2].get("use_count") or 0), row[1]))
        top = ranked[: min(3, len(ranked))]
        digest = hashlib.sha256(
            f"{film_id}|{cue.get('shot_id')}|{cue.get('motif_id')}".encode()
        ).digest()
        chosen = top[int.from_bytes(digest[:4], "big") % len(top)]
        score, asset_id, record, reasons = chosen
        used_assets.add(asset_id)
        previous_cluster = str(record.get("similarity_cluster") or asset_id)
        selections.append(
            {
                "shot_id": str(cue.get("shot_id") or ""),
                "start_sec": cue.get("start_sec"),
                "end_sec": cue.get("end_sec"),
                "asset_id": asset_id,
                "sha256": record["sha256"],
                "path": str((root / record["path"]).resolve()),
                "relative": f"bgm_library/{record['path']}",
                "source": "approved_library",
                "mode": "approved_library",
                "mood": record["mood"],
                "motif_id": str(cue.get("motif_id") or ""),
                "motif_family": record.get("motif_family") or "",
                "parent_asset_id": record.get("parent_asset_id"),
                "similarity_cluster": previous_cluster,
                "license_note": record["license_note"],
                "selection_score": round(score, 4),
                "selection_reason": reasons,
                "transition": str(cue.get("transition") or "crossfade"),
                "take_seed": int(cue.get("seed") or 0),
                "catalog_revision": status["catalog_revision"],
                "catalog_sha256": status["catalog_sha256"],
            }
        )
    receipt = {
        "schema": SELECTION_SCHEMA,
        "film_id": film_id,
        "series_id": series_id,
        "catalog_revision": status["catalog_revision"],
        "catalog_sha256": status["catalog_sha256"],
        "selected_at": _now(),
        "diversity_relaxed": diversity_relaxed,
        "selections": selections,
        "gaps": gaps,
        "usage_committed": False,
    }
    if gaps and require_complete:
        raise BGMLibraryError(
            "no eligible approved BGM for: "
            + ", ".join(f"{gap['shot_id']}:{gap['mood']}" for gap in gaps)
        )
    return receipt


def _event_id(film_id: str, shot_id: str, asset_id: str, final_sha256: str) -> str:
    return hashlib.sha256(f"{film_id}|{shot_id}|{asset_id}|{final_sha256}".encode()).hexdigest()


def commit_usage(
    library_root: Path | str,
    selection_receipt: dict[str, Any],
    *,
    final_sha256: str,
) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    if selection_receipt.get("schema") != SELECTION_SCHEMA or len(final_sha256) != 64:
        raise BGMLibraryError("invalid BGM selection usage receipt")
    usage_path = root / "usage.jsonl"
    catalog_path = _catalog_path(root)
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_file_lock(usage_path), exclusive_file_lock(catalog_path):
        existing_events = _usage_events(root)
        existing_ids = {str(event.get("event_id") or "") for event in existing_events}
        catalog = _load_catalog(root)
        new_events = []
        film_id = str(selection_receipt.get("film_id") or "")
        for selection in selection_receipt.get("selections") or []:
            asset_id = str(selection.get("asset_id") or "")
            shot_id = str(selection.get("shot_id") or "")
            event_id = _event_id(film_id, shot_id, asset_id, final_sha256)
            if event_id in existing_ids:
                continue
            record = catalog["assets"].get(asset_id)
            if not isinstance(record, dict) or record.get("status") != "approved":
                raise BGMLibraryError(f"selected BGM asset is no longer approved: {asset_id}")
            path = _safe_asset_path(root, str(record.get("path") or ""))
            if (
                selection.get("sha256") != record.get("sha256")
                or not path.is_file()
                or path.is_symlink()
                or sha256_file(path) != record.get("sha256")
            ):
                raise BGMLibraryError(f"selected BGM asset failed checksum binding: {asset_id}")
            event = {
                "event_id": event_id,
                "film_id": film_id,
                "series_id": str(selection_receipt.get("series_id") or ""),
                "shot_id": shot_id,
                "asset_id": asset_id,
                "asset_sha256": record["sha256"],
                "final_sha256": final_sha256,
                "used_at": _now(),
            }
            new_events.append(event)
            record["use_count"] = int(record.get("use_count") or 0) + 1
            record["last_used_at"] = event["used_at"]
            record["last_used_film_id"] = film_id
        if new_events:
            with usage_path.open("a", encoding="utf-8") as handle:
                for event in new_events:
                    handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            _write_catalog(root, catalog)
    return {"ok": True, "appended": len(new_events), "final_sha256": final_sha256}


def write_review_pack(library_root: Path | str) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    catalog = _load_catalog(root)
    pending = [
        record
        for record in catalog["assets"].values()
        if isinstance(record, dict) and record.get("status") == "pending_human_review"
    ]
    rows = []
    for record in sorted(pending, key=lambda item: (item.get("mood"), item.get("created_at"))):
        audio_rel = "../" + html.escape(str(record["path"]), quote=True)
        asset_id = html.escape(str(record["asset_id"]))
        recipe = html.escape(
            json.dumps(record.get("recipe") or {}, ensure_ascii=False, indent=2, sort_keys=True)
        )
        technical = record.get("technical") or {}
        rows.append(
            "<article>"
            f"<h2>{asset_id}</h2>"
            f"<p>{html.escape(str(record['mood']))} · energy {record['energy']} · "
            f"{html.escape(str(record['stem_profile']))} · seed {record['seed']}</p>"
            f"<p>duration {technical.get('duration_sec')}s · peak {technical.get('peak')} · "
            f"RMS {technical.get('rms')} · silence {technical.get('silence_ratio')}</p>"
            f'<audio controls preload="none" src="{audio_rel}"></audio>'
            f"<details><summary>标准化配方</summary><pre>{recipe}</pre></details>"
            f"<pre>aifilm bgm-library approve --asset-id {asset_id} "
            '--reviewer dex --instrumental-confirmed --license-note "..."</pre>'
            f"<pre>aifilm bgm-library reject --asset-id {asset_id} "
            '--reviewer dex --reason "..."</pre>'
            "</article>"
        )
    document = (
        "<!doctype html><html lang='zh'><meta charset='utf-8'>"
        "<title>ACE-Step BGM Review</title>"
        "<style>body{max-width:960px;margin:auto;font:16px system-ui;background:#111;color:#eee}"
        "article{padding:18px;border-bottom:1px solid #444}audio{width:100%}pre{white-space:pre-wrap}</style>"
        f"<h1>ACE-Step BGM 候选（{len(rows)}）</h1>{''.join(rows)}</html>"
    )
    output = root / "review" / "index.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".partial.html")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(output)
    return {"ok": True, "path": str(output), "candidate_count": len(rows)}


def baseline_recipes() -> list[dict[str, Any]]:
    mood_prompts = {
        "rnb": ("late-night neo-soul", ["relationship", "intimacy"], 72, "A minor"),
        "sensual": ("restrained sensual ambient R&B", ["intimacy", "tension"], 68, "D minor"),
        "dark": ("cinematic dark suspense underscore", ["crisis", "threat"], 86, "E minor"),
        "warm": ("warm cinematic human drama underscore", ["setup", "aftermath"], 76, "C major"),
        "playful": ("playful light cinematic groove", ["comedy", "release"], 104, "G major"),
    }
    profiles = (
        ("pad", 0.20, "sparse pads, minimal percussion"),
        ("thin", 0.40, "light pulse, restrained low end"),
        ("pulse", 0.68, "rhythmic pulse, controlled drums"),
        ("full", 0.88, "full arrangement, strong but dialogue-safe dynamics"),
    )
    recipes: list[dict[str, Any]] = []
    for mood in MOODS:
        identity, tags, bpm, keyscale = mood_prompts[mood]
        for stem_profile, energy, texture in profiles:
            recipes.append(
                {
                    "recipe_id": f"baseline-v1-{mood}-{stem_profile}",
                    "mood": mood,
                    "dramatic_tags": tags,
                    "energy": energy,
                    "stem_profile": stem_profile,
                    "bpm": bpm,
                    "keyscale": keyscale,
                    "timesignature": "4/4",
                    "duration": 60.0,
                    "prompt": (
                        f"{identity}, {texture}, instrumental film background music, "
                        "no vocals, no singing, narration-safe mix"
                    ),
                }
            )
    return recipes


def series_recipes(
    library_root: Path | str,
    *,
    series_id: str,
) -> list[dict[str, Any]]:
    """Build three lineage-bound intensity arrangements for three series motifs."""
    root = Path(library_root).expanduser().resolve()
    series_id = series_id.strip()
    if not series_id:
        raise BGMLibraryError("series_id is required")
    catalog = _load_catalog(root)
    approved = [
        record
        for record in catalog["assets"].values()
        if isinstance(record, dict) and record.get("status") == "approved"
    ]
    definitions = (
        ("protagonist", "warm", ["character", "identity"]),
        ("relationship", "rnb", ["relationship", "intimacy"]),
        ("threat", "dark", ["threat", "crisis"]),
    )
    profiles = (
        ("low", "pad", 0.22, "sparse and restrained"),
        ("mid", "pulse", 0.58, "clear rhythmic development"),
        ("high", "full", 0.88, "full dramatic arrangement"),
    )
    recipes: list[dict[str, Any]] = []
    for motif, mood, tags in definitions:
        parents = sorted(
            (record for record in approved if record.get("mood") == mood),
            key=lambda item: (int(item.get("use_count") or 0), str(item.get("asset_id") or "")),
        )
        if not parents:
            raise BGMLibraryError(f"series pack needs one approved {mood} parent for {motif}")
        parent = parents[0]
        parent_path = _safe_asset_path(root, str(parent["path"]))
        for level, stem_profile, energy, texture in profiles:
            recipes.append(
                {
                    "recipe_id": f"series-{series_id}-{motif}-{level}",
                    "mood": mood,
                    "dramatic_tags": tags,
                    "energy": energy,
                    "stem_profile": stem_profile,
                    "bpm": parent.get("bpm"),
                    "keyscale": parent.get("keyscale"),
                    "timesignature": parent.get("timesignature") or "4/4",
                    "duration": 60.0,
                    "motif_family": motif,
                    "series_id": series_id,
                    "parent_asset_id": parent["asset_id"],
                    "task_type": "cover",
                    "reference_audio": str(parent_path),
                    "cover_strength": 0.7,
                    "prompt": (
                        f"instrumental cinematic {mood} arrangement of the supplied motif, "
                        f"{texture}, {stem_profile} profile, no vocals, dialogue-safe mix"
                    ),
                }
            )
    return recipes


def record_gaps(
    library_root: Path | str,
    selection_receipt: dict[str, Any],
) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    gaps = selection_receipt.get("gaps")
    if selection_receipt.get("schema") != SELECTION_SCHEMA or not isinstance(gaps, list):
        raise BGMLibraryError("invalid BGM selection gap receipt")
    path = root / "gap-queue.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    appended = 0
    with exclusive_file_lock(path):
        existing_ids: set[str] = set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    existing_ids.add(str(json.loads(line).get("gap_id") or ""))
                except (AttributeError, json.JSONDecodeError):
                    continue
        with path.open("a", encoding="utf-8") as handle:
            for gap in gaps:
                gap_id = hashlib.sha256(
                    (
                        f"{selection_receipt.get('film_id')}|{gap.get('shot_id')}|"
                        f"{gap.get('mood')}|{gap.get('motif_id')}"
                    ).encode()
                ).hexdigest()
                if gap_id in existing_ids:
                    continue
                event = {
                    "gap_id": gap_id,
                    "film_id": selection_receipt.get("film_id"),
                    "series_id": selection_receipt.get("series_id"),
                    "created_at": _now(),
                    **gap,
                }
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                appended += 1
            handle.flush()
            os.fsync(handle.fileno())
    return {"ok": True, "appended": appended, "path": str(path)}


def generate_candidates(
    library_root: Path | str,
    *,
    base_url: str,
    token: str,
    recipe: dict[str, Any],
    batch_size: int = 4,
    seeds: list[int],
) -> dict[str, Any]:
    root = Path(library_root).expanduser().resolve()
    prompt = str(recipe.get("prompt") or "").strip()
    if not prompt or len(prompt) > 512:
        raise BGMLibraryError("BGM recipe prompt must contain 1-512 characters")
    payload = {
        "prompt": prompt,
        "duration": float(recipe.get("duration") or 60.0),
        "batch_size": int(batch_size),
        "seeds": [int(seed) for seed in seeds],
        "bpm": recipe.get("bpm"),
        "keyscale": recipe.get("keyscale"),
        "timesignature": recipe.get("timesignature") or "4/4",
        "task_type": recipe.get("task_type") or "text2music",
    }
    if recipe.get("reference_audio"):
        payload["reference_audio"] = recipe["reference_audio"]
        payload["cover_strength"] = float(recipe.get("cover_strength") or 0.7)
    batch_dir = root / ".batch-downloads" / uuid.uuid4().hex
    try:
        node = render_batch(
            base_url,
            token,
            payload=payload,
            out_dir=batch_dir,
        )
    except AudioNodeError as exc:
        raise BGMLibraryError(f"private ACE-Step batch failed: {exc}") from exc
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    public_recipe = {
        key: value for key, value in recipe.items() if key not in {"prompt", "reference_audio"}
    }
    candidates = []
    try:
        # Preflight the entire downloaded batch before catalog mutation.
        for artifact in node["artifacts"]:
            _technical(Path(str(artifact["path"])))
        for artifact in node["artifacts"]:
            metadata = {
                **public_recipe,
                "recipe": public_recipe,
                "seed": artifact["seed"],
                "model": node.get("model") or "ACE-Step-1.5",
                "checkpoint_fingerprint": node.get("checkpoint_fingerprint") or "unknown",
                "node_job_id": node["job_id"],
                "prompt_sha256": prompt_hash,
            }
            candidates.append(stage_candidate(root, artifact["path"], metadata))
    except Exception:
        staged_ids = {str(candidate.get("asset_id") or "") for candidate in candidates}
        if staged_ids:
            catalog_path = _catalog_path(root)
            with exclusive_file_lock(catalog_path):
                catalog = _load_catalog(root)
                for staged_id in staged_ids:
                    record = catalog["assets"].pop(staged_id, None)
                    if isinstance(record, dict):
                        _safe_asset_path(root, str(record.get("path") or "")).unlink(
                            missing_ok=True
                        )
                    (root / "receipts" / f"{staged_id}.json").unlink(missing_ok=True)
                _write_catalog(root, catalog)
        raise
    finally:
        if batch_dir.is_dir():
            for path in batch_dir.glob("*"):
                path.unlink(missing_ok=True)
            batch_dir.rmdir()
            parent = batch_dir.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
    return {
        "ok": True,
        "recipe_id": recipe.get("recipe_id"),
        "node_job_id": node["job_id"],
        "candidates": candidates,
    }
