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
