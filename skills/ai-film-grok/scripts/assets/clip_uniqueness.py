"""Fail closed when two shots try to promote the same I2V segment."""

from __future__ import annotations

import subprocess
from itertools import combinations
from pathlib import Path
from typing import Any

from security_policy import minimal_subprocess_env
from util import sha256_file

_WIDTH = 17
_HEIGHT = 9
_FRAME_BYTES = _WIDTH * _HEIGHT


class ClipUniquenessError(ValueError):
    pass


def _frame_hashes(path: Path) -> list[int]:
    """Return low-cost perceptual hashes sampled at 1fps across the whole clip."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-an",
            "-vf",
            f"fps=1,scale={_WIDTH}:{_HEIGHT}:flags=area,format=gray",
            "-pix_fmt",
            "gray",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        timeout=180,
        env=minimal_subprocess_env(),
    )
    if proc.returncode != 0:
        raise ClipUniquenessError("could not fingerprint clip for reuse gate")
    frames = [
        proc.stdout[offset : offset + _FRAME_BYTES]
        for offset in range(0, len(proc.stdout), _FRAME_BYTES)
        if len(proc.stdout[offset : offset + _FRAME_BYTES]) == _FRAME_BYTES
    ]
    if not frames:
        raise ClipUniquenessError("clip has no decodable frames for reuse gate")
    hashes: list[int] = []
    for frame in frames:
        bits = 0
        for row in range(_HEIGHT):
            start = row * _WIDTH
            for col in range(_WIDTH - 1):
                bits = (bits << 1) | (frame[start + col] > frame[start + col + 1])
        hashes.append(bits)
    return hashes


def fingerprint_clip(path: Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ClipUniquenessError(f"clip is missing: {source}")
    hashes = _frame_hashes(source)
    return {
        "sha256": sha256_file(source),
        "sample_fps": 1,
        "dhashes": [f"{item:x}" for item in hashes],
    }


def _near_same(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("sha256") == right.get("sha256"):
        return True
    a = left.get("dhashes") if isinstance(left.get("dhashes"), list) else []
    b = right.get("dhashes") if isinstance(right.get("dhashes"), list) else []
    if not a or len(a) != len(b):
        return False
    # Same visual segment survives a normal transcode with a very small dHash delta.
    return all((int(x, 16) ^ int(y, 16)).bit_count() <= 5 for x, y in zip(a, b, strict=True))


def assert_clip_is_unique(
    source: Path, *, manifest: dict[str, Any], shot_id: str
) -> dict[str, Any]:
    candidate = fingerprint_clip(source)
    matches: list[str] = []
    for other_id, record in (manifest.get("clips") or {}).items():
        if str(other_id) == str(shot_id) or not isinstance(record, dict):
            continue
        known = record.get("uniqueness") if isinstance(record.get("uniqueness"), dict) else None
        if known is None:
            digest = record.get("sha256")
            if digest and digest == candidate["sha256"]:
                matches.append(str(other_id))
            continue
        if _near_same(candidate, known):
            matches.append(str(other_id))
    if matches:
        raise ClipUniquenessError(
            "duplicate visual segment already active for shot(s): " + ", ".join(sorted(matches))
        )
    return candidate


def active_clip_reuse_report(
    manifest: dict[str, Any], *, required_shot_ids: list[str]
) -> dict[str, Any]:
    """Validate persisted active-take fingerprints without running FFmpeg again.

    A production gate must not trust that `register-clip` was the only writer
    of the manifest. Missing fingerprints fail closed for every required
    approved shot, so old media needs explicit re-registration and review.
    """
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    strict_perceptual = int(manifest.get("review_contract_version") or 1) >= 2
    missing: list[str] = []
    fingerprints: list[tuple[str, dict[str, Any]]] = []
    for shot_id in required_shot_ids:
        record = clips.get(shot_id)
        if not isinstance(record, dict) or record.get("status") != "approved":
            continue
        fingerprint = record.get("uniqueness")
        if not isinstance(fingerprint, dict) or not fingerprint.get("sha256"):
            missing.append(str(shot_id))
            continue
        if strict_perceptual and (
            not isinstance(fingerprint.get("dhashes"), list) or not fingerprint["dhashes"]
        ):
            missing.append(str(shot_id))
            continue
        fingerprints.append((str(shot_id), fingerprint))
    exact_pairs: list[list[str]] = []
    perceptual_pairs: list[list[str]] = []
    for (left_id, left), (right_id, right) in combinations(fingerprints, 2):
        pair = [left_id, right_id]
        if left["sha256"] == right["sha256"]:
            exact_pairs.append(pair)
        elif _near_same(left, right):
            # A normal transcode changes SHA-256 but must not become a new take.
            perceptual_pairs.append(pair)
    return {
        "ok": not missing and not exact_pairs and not perceptual_pairs,
        "required_shot_count": len(required_shot_ids),
        "missing_fingerprint_shots": sorted(missing),
        "duplicate_sha256_pairs": sorted(exact_pairs),
        # Kept for quality-closure consumers during the report schema migration.
        "duplicate_sha256_groups": sorted(exact_pairs),
        "perceptual_duplicate_pairs": sorted(perceptual_pairs),
        "reason": (
            "every approved active I2V clip has a unique persisted visual fingerprint"
            if not missing and not exact_pairs and not perceptual_pairs
            else "re-register and review the affected I2V clips; identical segments cannot be delivered"
        ),
    }
