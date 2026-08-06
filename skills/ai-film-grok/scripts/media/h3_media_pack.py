#!/usr/bin/env python3
"""Resolve per-shot media pack for MiniMax H3 (first / last / refs).

Phase 1: first + last path resolution (CLI / file convention / shot fields).
Phase 2: cast identity / state masters / still-challenge end auto-resolve.
Phase 3: multi-ref list for R2V (<Picture n> roles).
Phase 4: missing-last hints for end-still production.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, sha256_file

MAX_AUTO_REFS = 3


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _file_entry(
    path: Path | None,
    *,
    source: str | None,
    role: str | None = None,
) -> dict[str, Any] | None:
    if path is None:
        return None
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return None
    entry: dict[str, Any] = {
        "path": str(p),
        "source": source,
        "sha256": sha256_file(p),
    }
    if role:
        entry["role"] = role
    return entry


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


def _rel_file(root: Path, raw: Any) -> Path | None:
    if not raw:
        return None
    p = Path(str(raw)).expanduser()
    if not p.is_absolute():
        p = root / p
    return p.resolve() if p.is_file() else None


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

    # Still-challenge end promote (takes/<id>/still_frw_*_end* or manifest end)
    takes = base / "takes" / shot_id
    if takes.is_dir():
        ends = sorted(takes.glob("still_frw_*_end*.png")) + sorted(
            takes.glob("still_frw_*_end*.jpg")
        )
        if ends and ends[-1].is_file():
            return ends[-1].resolve(), "still_challenge_end_candidate"

    manifest = read_json(base / "manifest.json") or {}
    stills = manifest.get("stills") if isinstance(manifest, dict) else {}
    if isinstance(stills, dict):
        entry = stills.get(f"{shot_id}_end") or stills.get(f"{shot_id}:end")
        if isinstance(entry, dict):
            p = _rel_file(base, entry.get("path") or entry.get("file"))
            if p is not None:
                return p, "manifest_end"

    # State-index end-state still (wardrobe end ladder)
    state_end = _resolve_state_end_still(base, sh)
    if state_end is not None:
        return state_end, "state_master_end"

    return None, None


def _char_ids(shot: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("cast_ids", "character_ids", "chars"):
        raw = shot.get(key)
        if isinstance(raw, list):
            ids.extend(str(x) for x in raw if x)
        elif isinstance(raw, str) and raw.strip():
            ids.append(raw.strip())
    for key in ("cast_id", "character_id", "char_id", "speaker_id"):
        raw = shot.get(key)
        if raw:
            ids.append(str(raw))
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _resolve_state_end_still(root: Path, shot: dict[str, Any]) -> Path | None:
    """Best-effort end wardrobe/pose still from style-bible cast_state_masters."""
    bible = read_json(root / "style-bible.json") or {}
    if not isinstance(bible, dict):
        return None
    csm = (
        bible.get("cast_state_masters") if isinstance(bible.get("cast_state_masters"), dict) else {}
    )
    wardrobe = str(shot.get("wardrobe_state") or shot.get("end_wardrobe_state") or "").strip()
    end_state = str(
        shot.get("end_state") or shot.get("end_wardrobe_state") or wardrobe or ""
    ).strip()
    if not end_state:
        return None
    for cid in _char_ids(shot) or list(csm.keys())[:1]:
        bag = csm.get(cid) if isinstance(csm.get(cid), dict) else None
        if not bag:
            continue
        # Prefer explicit end keys then current wardrobe state path
        for key in (
            f"{end_state}_end",
            f"end_{end_state}",
            end_state,
            "bare",
            "undressed",
            "act",
        ):
            raw = bag.get(key)
            if isinstance(raw, dict):
                raw = raw.get("path") or raw.get("file")
            p = _rel_file(root, raw)
            if p is not None:
                return p
    return None


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


def resolve_identity_refs(
    root: Path | str,
    shot: dict[str, Any] | None = None,
    *,
    max_refs: int = MAX_AUTO_REFS,
    include_legacy: bool = True,
) -> list[dict[str, Any]]:
    """Delegate to identity_refs (M5 canonical-first)."""
    from identity_refs import resolve_identity_refs as _resolve
    return _resolve(root, shot, max_refs=max_refs, include_legacy=include_legacy)


def resolve_identity_refs_report(
    root: Path | str,
    shot: dict[str, Any] | None = None,
    *,
    max_refs: int = MAX_AUTO_REFS,
) -> dict[str, Any]:
    from identity_refs import resolve_identity_refs_report as _report
    return _report(root, shot, max_refs=max_refs)


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
    max_refs: int = MAX_AUTO_REFS,
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

    first = _file_entry(first_path, source=first_source, role="first")
    last = _file_entry(last_path, source=last_source, role="last")

    refs: list[dict[str, Any]] = []
    identity_warnings: list[str] = []
    if refs_override:
        for idx, raw in enumerate(refs_override):
            entry = _file_entry(Path(raw), source=f"explicit_ref_{idx}", role="reference")
            if entry:
                refs.append(entry)
    else:
        id_rep = resolve_identity_refs_report(base, sh, max_refs=max_refs)
        refs = list(id_rep.get("refs") or [])
        identity_warnings = list(id_rep.get("warnings") or [])

    # Drop refs that duplicate first/last bytes path
    drop = {
        str(first_path.resolve()) if first_path else "",
        str(last_path.resolve()) if last_path else "",
    }
    refs = [r for r in refs if r.get("path") not in drop][:max_refs]

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

    missing_last_hint = None
    if first and not last:
        missing_last_hint = {
            "message": (
                "no end still — FLF unavailable (default quality path needs last); "
                "produce stills/<id>_end.png or promote --as end"
            ),
            "mode_without_last": "i2v",
            "mode_with_last": "flf",
            "suggested_paths": [
                str(base / "stills" / f"{shot_id}_end.png"),
                str(base / "keyframes" / f"{shot_id}_end.png"),
            ],
            "commands": [
                f'aifilm still-challenge promote --root "{base}" --shot-id {shot_id} --as end '
                f"--identity-approved --anatomy-safe --review-note end-still",
                f"# or copy an end pose board to stills/{shot_id}_end.png",
            ],
        }
    flf_ready = first is not None and last is not None
    mode_hint = "flf" if flf_ready else ("i2v" if first is not None else "t2v")
    return {
        "schema_version": 2,
        "kind": "ai-film-h3-media-pack",
        "shot_id": shot_id,
        "first": first,
        "last": last,
        "refs": refs,
        "has_first": first is not None,
        "has_last": last is not None,
        "has_refs": bool(refs),
        "flf_ready": flf_ready,
        "mode_hint": mode_hint,
        "identity_warnings": list(identity_warnings),
        "reasons": reasons,
        "missing_last_hint": missing_last_hint,
    }


def flf_prompt_clause() -> str:
    return (
        "First-last-frame control: interpolate motion from the first keyframe to the "
        "last keyframe; land on the last pose, wardrobe, and composition; preserve "
        "identity; do not ignore the end frame."
    )


def r2v_ref_prompt_clause(refs: list[dict[str, Any]]) -> str:
    """Build <Picture n> duty lines for MiniMax H3 R2V multi-ref.

    Convention for first/last quality: primary still is ref_image_0 (first frame);
    additional refs should list pose/end land before identity when both exist.
    """
    if not refs:
        return ""
    parts: list[str] = []
    for i, ref in enumerate(refs, start=1):
        role = str(ref.get("role") or "reference")
        duty = {
            "identity": "identity lock (same face, hair, body)",
            "style": "style and medium lock",
            "pose": "end pose / composition land target (last frame)",
            "wardrobe_state": "wardrobe and body state",
            "contact": "contact / detail insert",
            "last": "end pose land target (last frame)",
            "first": "start frame identity (first frame)",
            "reference": "subject reference",
        }.get(role, "subject reference")
        parts.append(f"<Picture {i}> = {duty}")
    return "Reference duties: " + "; ".join(parts) + "."


def end_still_dest(root: Path | str, shot_id: str) -> Path:
    """Canonical end-still path for Phase 4 production."""
    return _root(root) / "stills" / f"{shot_id}_end.png"


def enrich_h3_last_frames(root: Path | str) -> dict[str, Any]:
    """Scan continue handoffs and auto-derive candidate end stills for FLF chains."""
    import shutil
    from util import read_json, utc_now

    base = _root(root)
    spec_path = base / "film-spec.json"
    if not spec_path.is_file():
        return {"ok": False, "error": "film-spec.json missing"}

    spec = read_json(spec_path) or {}
    from continue_handoff import iter_shot_ids, previous_shot_id

    shot_ids = iter_shot_ids(spec)
    stills_dir = base / "stills"
    stills_dir.mkdir(parents=True, exist_ok=True)
    handoff_dir = base / "receipts" / "continue-handoff"

    derived: list[dict[str, Any]] = []
    for sid in shot_ids:
        prev_id = previous_shot_id(spec, sid)
        if not prev_id:
            continue

        # Check if previous shot produced a continue handoff endframe
        end_png = handoff_dir / f"{prev_id}_end.png"
        last_png = base / "keyframes" / f"_last_{prev_id}.png"
        source_frame = end_png if end_png.is_file() else (last_png if last_png.is_file() else None)

        if not source_frame:
            continue

        target_end_still = stills_dir / f"{prev_id}_end.png"
        if not target_end_still.is_file():
            shutil.copy2(source_frame, target_end_still)
            derived.append(
                {
                    "prev_shot_id": prev_id,
                    "target_shot_id": sid,
                    "source_frame": str(source_frame),
                    "derived_end_still": str(target_end_still),
                    "mode_enabled": "flf",
                }
            )

    return {
        "ok": True,
        "kind": "h3-enrich-last-frames",
        "derived_count": len(derived),
        "derived": derived,
        "created_at": utc_now(),
    }
