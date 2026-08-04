#!/usr/bin/env python3
"""Resolve per-shot media pack for MiniMax H3 (first / last / refs).

Phase 1: first + last path resolution (CLI / file convention / shot fields).
Phase 2+: cast identity refs, state masters, still-challenge end promote.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, sha256_file


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _file_entry(path: Path | None, *, source: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return None
    return {
        "path": str(p),
        "source": source,
        "sha256": sha256_file(p),
    }


def _path_from_shot_field(root: Path, shot: dict[str, Any], *keys: str) -> Path | None:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    media = shot.get("media") if isinstance(shot.get("media"), dict) else {}
    for key in keys:
        for bag in (shot, dsl, media):
            if not isinstance(bag, dict):
                continue
            raw = bag.get(key)
            if not raw:
                continue
            p = Path(str(raw)).expanduser()
            if not p.is_absolute():
                p = root / p
            if p.is_file():
                return p.resolve()
    return None


def resolve_last_frame_path(
    root: Path | str,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
    last_override: Path | str | None = None,
) -> tuple[Path | None, str | None]:
    """Locate an end/last keyframe for FLF. Never invents by copying first."""
    base = _root(root)
    sh = shot if isinstance(shot, dict) else {}

    if last_override is not None:
        ov = Path(last_override).expanduser().resolve()
        if ov.is_file():
            return ov, "explicit_override"

    explicit = _path_from_shot_field(
        base,
        sh,
        "end_still",
        "last_frame",
        "end_keyframe",
        "last_keyframe",
        "end_image",
    )
    if explicit is not None:
        return explicit, "shot_field"

    for candidate, source in (
        (base / "stills" / f"{shot_id}_end.png", "stills_end"),
        (base / "stills" / f"{shot_id}_last.png", "stills_last"),
        (base / "keyframes" / f"{shot_id}_end.png", "keyframes_end"),
        (base / "keyframes" / f"{shot_id}_last.png", "keyframes_last"),
        (base / "stills" / f"{shot_id}_end.jpg", "stills_end"),
        (base / "keyframes" / f"{shot_id}_end.jpg", "keyframes_end"),
    ):
        if candidate.is_file():
            return candidate.resolve(), source

    manifest = read_json(base / "manifest.json") or {}
    stills = manifest.get("stills") if isinstance(manifest, dict) else {}
    if isinstance(stills, dict):
        entry = stills.get(f"{shot_id}_end") or stills.get(f"{shot_id}:end")
        if isinstance(entry, dict):
            raw = entry.get("path") or entry.get("file")
            if raw:
                p = Path(str(raw))
                if not p.is_absolute():
                    p = base / p
                if p.is_file():
                    return p.resolve(), "manifest_end"

    return None, None


def resolve_first_frame_path(
    root: Path | str,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
    still_override: Path | str | None = None,
    approved_still: Path | None = None,
    continue_end_frame: Path | str | None = None,
    wants_continue: bool = False,
) -> tuple[Path | None, str | None]:
    """Locate first/start keyframe (still) for I2V/FLF/R2V."""
    base = _root(root)
    sh = shot if isinstance(shot, dict) else {}

    if still_override is not None:
        ov = Path(still_override).expanduser().resolve()
        if ov.is_file():
            return ov, "explicit_override"

    cont_path: Path | None = None
    if continue_end_frame:
        cp = Path(continue_end_frame).expanduser().resolve()
        if cp.is_file():
            cont_path = cp

    if wants_continue and cont_path is not None:
        return cont_path, "continue_handoff"
    if approved_still is not None and Path(approved_still).is_file():
        return Path(approved_still).resolve(), "approved"
    if cont_path is not None and approved_still is None:
        return cont_path, "continue_handoff_fallback"

    explicit = _path_from_shot_field(base, sh, "still", "keyframe", "first_frame", "start_image")
    if explicit is not None:
        return explicit, "shot_field"

    for candidate, source in (
        (base / "stills" / f"{shot_id}.png", "stills"),
        (base / "keyframes" / f"{shot_id}.png", "keyframes"),
        (base / "stills" / f"{shot_id}.jpg", "stills"),
        (base / "keyframes" / f"{shot_id}.jpg", "keyframes"),
    ):
        if candidate.is_file():
            return candidate.resolve(), source

    return None, None


def resolve_media_pack(
    root: Path | str,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
    still_override: Path | str | None = None,
    last_override: Path | str | None = None,
    approved_still: Path | None = None,
    continue_end_frame: Path | str | None = None,
    wants_continue: bool = False,
    refs_override: list[Path | str] | None = None,
) -> dict[str, Any]:
    """Build machine-readable first/last/refs pack for h3 plan/run."""
    base = _root(root)
    sh = shot if isinstance(shot, dict) else {}

    first_path, first_source = resolve_first_frame_path(
        base,
        shot_id,
        shot=sh,
        still_override=still_override,
        approved_still=approved_still,
        continue_end_frame=continue_end_frame,
        wants_continue=wants_continue,
    )
    last_path, last_source = resolve_last_frame_path(
        base,
        shot_id,
        shot=sh,
        last_override=last_override,
    )

    if (
        first_path is not None
        and last_path is not None
        and first_path.resolve() == last_path.resolve()
    ):
        last_path, last_source = None, None

    first = _file_entry(first_path, source=first_source)
    last = _file_entry(last_path, source=last_source)

    refs: list[dict[str, Any]] = []
    if refs_override:
        for idx, raw in enumerate(refs_override):
            entry = _file_entry(Path(raw), source=f"explicit_ref_{idx}")
            if entry:
                entry["role"] = "reference"
                refs.append(entry)

    reasons: list[str] = []
    if first:
        reasons.append(f"first:{first_source}")
    else:
        reasons.append("first:missing")
    if last:
        reasons.append(f"last:{last_source}")
    else:
        reasons.append("last:absent")
    if refs:
        reasons.append(f"refs:{len(refs)}")

    return {
        "schema_version": 1,
        "kind": "ai-film-h3-media-pack",
        "shot_id": shot_id,
        "first": first,
        "last": last,
        "refs": refs,
        "has_first": first is not None,
        "has_last": last is not None,
        "has_refs": bool(refs),
        "reasons": reasons,
    }


def flf_prompt_clause() -> str:
    return (
        "First-last-frame control: interpolate motion from the first keyframe to the "
        "last keyframe; land on the last pose, wardrobe, and composition; preserve "
        "identity; do not ignore the end frame."
    )
