"""Fail closed when two different shots approve the same still bytes.

Lesson 2026-07-29 (btc-vessel-ep02): agent copied one climax still onto 3 shot
ids → I2V files differed slightly but the cut felt like the same frame looping.
Clip uniqueness only fingerprints motion video; same-still I2V can pass it.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from util import sha256_file


class StillUniquenessError(ValueError):
    pass


def _still_sha(record: dict[str, Any], *, keyframes_dir: Path | None = None) -> str | None:
    path = record.get("path")
    if path:
        p = Path(str(path)).expanduser()
        if not p.is_file() and keyframes_dir is not None:
            candidate = keyframes_dir / Path(str(path)).name
            if candidate.is_file():
                p = candidate
        if p.is_file():
            try:
                return sha256_file(p)
            except OSError:
                pass
    sha = record.get("sha256")
    return sha.strip() if isinstance(sha, str) and sha.strip() else None


def active_still_reuse_report(
    manifest: dict[str, Any],
    *,
    required_shot_ids: list[str] | None = None,
    keyframes_dir: Path | None = None,
) -> dict[str, Any]:
    """Report exact still-byte reuse across approved stills of different shots."""
    stills = manifest.get("stills") if isinstance(manifest.get("stills"), dict) else {}
    by_sha: dict[str, list[str]] = defaultdict(list)
    missing: list[str] = []
    required = [str(x) for x in (required_shot_ids or list(stills.keys()))]

    for sid in required:
        rec = stills.get(sid)
        if not isinstance(rec, dict) or rec.get("status") != "approved":
            continue
        sha = _still_sha(rec, keyframes_dir=keyframes_dir)
        if not sha:
            missing.append(sid)
            continue
        by_sha[sha].append(sid)

    groups = sorted(
        [[sid for sid in ids] for ids in by_sha.values() if len(ids) > 1],
        key=lambda g: (len(g), g[0]),
        reverse=True,
    )
    pairs: list[list[str]] = []
    for group in groups:
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                pairs.append(sorted([a, b]))
    pairs = sorted(pairs)

    ok = not groups and not missing
    if groups:
        reason = (
            f"{len(groups)} still-byte reuse group(s) across approved shots; "
            "each shot needs its own keyframe (pose/phase/framing). "
            "See references/lessons-2026-07-29-still-unique-no-reuse.md"
        )
    elif missing:
        reason = f"approved stills missing readable sha/path: {missing}"
    else:
        reason = "every approved still has a unique content sha256"

    return {
        "ok": ok,
        "required_shot_count": len(required),
        "duplicate_sha256_groups": groups,
        "duplicate_sha256_pairs": pairs,
        "missing_fingerprint_shots": missing,
        "reason": reason,
    }


def assert_still_is_unique(
    *,
    root: Path,
    shot_id: str,
    source: Path,
    status: str,
    manifest: dict[str, Any] | None = None,
) -> None:
    """Raise if approving a still that byte-matches another approved shot."""
    if status != "approved":
        return
    root = Path(root).expanduser().resolve()
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise StillUniquenessError(f"still source missing: {source}")
    new_sha = sha256_file(source)
    man = manifest if isinstance(manifest, dict) else {}
    stills = man.get("stills") if isinstance(man.get("stills"), dict) else {}
    collisions: list[str] = []
    for other_id, rec in stills.items():
        if str(other_id) == str(shot_id):
            continue
        if not isinstance(rec, dict) or rec.get("status") != "approved":
            continue
        other_sha = _still_sha(rec, keyframes_dir=root / "keyframes")
        if other_sha and other_sha == new_sha:
            collisions.append(str(other_id))
    if collisions:
        raise StillUniquenessError(
            f"still for {shot_id} is byte-identical to approved still(s) {sorted(collisions)}; "
            "generate a distinct keyframe (different pose/phase/framing/lens) — "
            "do not copy/link the same PNG across shots. "
            "See references/lessons-2026-07-29-still-unique-no-reuse.md"
        )


# Path / note markers that mean "ffmpeg crop from cast master" fallback (savani EP02).
_CROP_MASTER_MARKERS = (
    "crop-master",
    "crop_master",
    "cropfrommaster",
    "from-master-crop",
    "from_master_crop",
    "master_crop",
    "cropmaster",
    "ffmpeg-crop-master",
    "whole-episode-crop",
)


def _record_looks_like_crop_master(rec: dict[str, Any]) -> tuple[bool, str]:
    """Return (is_crop_master_suspect, reason_tag)."""
    path = str(rec.get("path") or "").lower()
    note = str(rec.get("note") or rec.get("notes") or rec.get("review_note") or "").lower()
    source = str(
        rec.get("source")
        or rec.get("still_source")
        or rec.get("derived_from")
        or rec.get("parent")
        or ""
    ).lower()
    kind = str(rec.get("source_kind") or rec.get("kind") or "").lower()
    blob = " ".join([path, note, source, kind])
    for m in _CROP_MASTER_MARKERS:
        if m in blob.replace(" ", ""):
            return True, f"marker:{m}"
    # Explicit flags
    if rec.get("crop_from_master") is True or rec.get("from_cast_master_crop") is True:
        return True, "flag:crop_from_master"
    if kind in {"crop_master", "master_crop", "ffmpeg_crop_master"}:
        return True, f"kind:{kind}"
    # parent_sha shared later; single-record parent_id pointing at cast master
    parent = str(rec.get("parent_shot_id") or rec.get("parent_still") or "").lower()
    if parent in {"cast_master", "master", "style_master", "character_master"}:
        return True, f"parent:{parent}"
    return False, ""


def crop_master_still_report(
    manifest: dict[str, Any],
    *,
    required_shot_ids: list[str] | None = None,
    soft_ratio: float = 0.35,
    hard_ratio: float = 0.55,
    min_shots: int = 4,
) -> dict[str, Any]:
    """Flag seasons that mostly re-use cast-master crops as stills (savani lesson).

    Soft when ≥soft_ratio of approved stills look like crop-master; hard when
    ≥hard_ratio (or all tagged share one parent_sha). Does not replace exact
    sha uniqueness — that is still hard via active_still_reuse_report.
    """
    stills = manifest.get("stills") if isinstance(manifest.get("stills"), dict) else {}
    required = [str(x) for x in (required_shot_ids or list(stills.keys()))]
    tagged: list[dict[str, str]] = []
    approved_ids: list[str] = []
    parent_sha_groups: dict[str, list[str]] = defaultdict(list)

    for sid in required:
        rec = stills.get(sid)
        if not isinstance(rec, dict) or rec.get("status") != "approved":
            continue
        approved_ids.append(sid)
        hit, why = _record_looks_like_crop_master(rec)
        if hit:
            tagged.append({"shot_id": sid, "reason": why})
        psha = rec.get("parent_sha256") or rec.get("parent_sha") or rec.get("crop_source_sha256")
        if isinstance(psha, str) and psha.strip():
            parent_sha_groups[psha.strip()].append(sid)

    n = len(approved_ids)
    t = len(tagged)
    ratio = (t / n) if n else 0.0
    large_parent = [
        {"parent_sha256": sha, "shots": ids}
        for sha, ids in parent_sha_groups.items()
        if len(ids) >= max(min_shots, 3)
    ]
    # Parent-sha mass crop: count those shots as tagged for ratio if not already
    parent_mass_ids = {s for g in large_parent for s in g["shots"]}
    effective_tagged = {x["shot_id"] for x in tagged} | parent_mass_ids
    eff_n = len(effective_tagged)
    eff_ratio = (eff_n / n) if n else 0.0

    codes: list[str] = []
    severity = "ok"
    if n >= min_shots and eff_ratio >= hard_ratio:
        codes.append("STILL_CROP_MASTER_DOMINANT")
        severity = "hard"
    elif n >= min_shots and (ratio >= soft_ratio or eff_ratio >= soft_ratio or large_parent):
        codes.append("STILL_CROP_MASTER_WARN")
        severity = "soft"
    if large_parent and "STILL_CROP_MASTER_PARENT_SHA" not in codes:
        codes.append("STILL_CROP_MASTER_PARENT_SHA")

    ok = severity != "hard"
    if severity == "ok":
        reason = "no crop-master still dominance"
    elif severity == "soft":
        reason = (
            f"{eff_n}/{n} approved stills look like cast-master crop variants "
            f"({eff_ratio:.0%}) — ban whole-episode crop-master silent fallback; "
            "regenerate narrative stills. See memory 2026-08-06-h3-native-ship-review-lessons."
        )
    else:
        reason = (
            f"{eff_n}/{n} approved stills are crop-master-like ({eff_ratio:.0%}) — "
            "hard block bulk until distinct keyframes exist per shot"
        )

    return {
        "ok": ok,
        "severity": severity,
        "codes": codes,
        "approved_count": n,
        "tagged_count": t,
        "effective_tagged_count": eff_n,
        "ratio": round(ratio, 4),
        "effective_ratio": round(eff_ratio, 4),
        "tagged": tagged[:40],
        "parent_sha_groups": large_parent[:10],
        "reason": reason,
        "next": (
            [
                "regenerate stills from undress-anchor / state photos — not ffmpeg crop of cast master",
                "do not silent-ID-rename EP stills across episodes",
            ]
            if severity != "ok"
            else []
        ),
    }
