#!/usr/bin/env python3
"""P2-1 extend: Perceptual image hash for face identity verification.

Uses PIL (already a dependency) to compute average hash (aHash) of images.
Compares cast master against generated stills/last-frames to detect identity drift.

This is a **lightweight** approach — it does NOT do face detection or face embedding.
It computes a whole-image perceptual hash and measures Hamming distance.
If images are similar (same face, same framing), hash distance is small.
If face/identity drifts, hash distance is large.

Capability boundary (honest): perceptual hash catches gross identity drift
(wrong character, drastically different face) but NOT subtle drift
(slightly different expression, minor lighting change). For production-grade
face identity, use face embedding (face_recognition / InsightFace) — but
that requires CV dependencies this plugin deliberately does not bundle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from util import utc_now


def _ahash(image_path: Path, hash_size: int = 8) -> str | None:
    """Compute average hash (aHash) of an image using PIL.

    Returns hex string or None if image cannot be loaded.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        img = Image.open(image_path).convert("L").resize((hash_size, hash_size))
    except Exception:
        return None

    pixels = (
        list(img.get_flattened_data())
        if hasattr(img, "get_flattened_data")
        else list(img.getdata())
    )
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p > avg else "0" for p in pixels)
    # Convert to hex
    return f"{int(bits, 16):0{hash_size * hash_size // 4}x}"


def _hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two hex hash strings."""
    if len(hash1) != len(hash2):
        return max(len(hash1), len(hash2)) * 8  # max possible
    val1 = int(hash1, 16)
    val2 = int(hash2, 16)
    return bin(val1 ^ val2).count("1")


def compute_identity_hash(image_path: Path | str) -> str | None:
    """Public API: compute perceptual hash of an image file."""
    return _ahash(Path(image_path))


def verify_face_identity(
    cast_master_path: Path | str,
    comparison_image_path: Path | str,
    *,
    max_distance: int = 12,
) -> dict[str, Any]:
    """Verify face identity by comparing perceptual hashes.

    Args:
        cast_master_path: Path to canonical cast master image.
        comparison_image_path: Path to still/last-frame to verify.
        max_distance: Maximum acceptable Hamming distance (default 12 out of 64 bits).

    Returns:
        {verified, distance, max_distance, method, cast_hash, comparison_hash}
    """
    cast_path = Path(cast_master_path)
    comp_path = Path(comparison_image_path)

    if not cast_path.is_file():
        return {
            "verified": False,
            "distance": None,
            "max_distance": max_distance,
            "method": "perceptual_hash_ahash",
            "error": f"cast master not found: {cast_path}",
        }
    if not comp_path.is_file():
        return {
            "verified": False,
            "distance": None,
            "max_distance": max_distance,
            "method": "perceptual_hash_ahash",
            "error": f"comparison image not found: {comp_path}",
        }

    cast_hash = _ahash(cast_path)
    comp_hash = _ahash(comp_path)

    if cast_hash is None or comp_hash is None:
        return {
            "verified": False,
            "distance": None,
            "max_distance": max_distance,
            "method": "perceptual_hash_ahash",
            "error": "failed to compute hash — PIL may be missing or image unreadable",
        }

    distance = _hamming_distance(cast_hash, comp_hash)
    verified = distance <= max_distance

    return {
        "verified": verified,
        "distance": distance,
        "max_distance": max_distance,
        "method": "perceptual_hash_ahash",
        "cast_hash": cast_hash,
        "comparison_hash": comp_hash,
        "cast_path": str(cast_path),
        "comparison_path": str(comp_path),
        "note": (
            "Perceptual hash (aHash, 64-bit). Catches gross identity drift only — "
            "NOT face detection. For production face identity, use face embedding."
        ),
    }


def write_identity_receipt(
    root: Path | str,
    cast_master_path: Path | str,
    comparison_paths: list[Path | str],
    *,
    max_distance: int = 12,
) -> dict[str, Any]:
    """Run face identity verification for all comparison images and write receipt.

    Writes receipts/face-identity.json with verified=true only if ALL images pass.
    """
    root = Path(root)
    results: list[dict[str, Any]] = []
    all_verified = True

    for comp_path in comparison_paths:
        result = verify_face_identity(cast_master_path, comp_path, max_distance=max_distance)
        results.append(result)
        if not result.get("verified"):
            all_verified = False

    receipt = {
        "verified": all_verified,
        "method": "perceptual_hash_ahash",
        "max_distance": max_distance,
        "cast_master": str(cast_master_path),
        "comparisons": results,
        "at": utc_now(),
    }

    receipt_dir = root / "receipts"
    receipt_dir.mkdir(exist_ok=True)
    (receipt_dir / "face-identity.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return receipt
