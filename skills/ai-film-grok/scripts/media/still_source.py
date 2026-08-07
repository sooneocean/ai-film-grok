#!/usr/bin/env python3
"""StillSource — single resolver for which pixel still feeds generation.

Priority (motion / I2V first frame):
  1. explicit override
  2. continue handoff endframe (when chain wants continue)
  3. approved still (manifest / stills|keyframes convention)
  4. shot field still/keyframe/first_frame
  5. state photo for wardrobe (undressed/bare/partial)
  6. never silent full cast master for peak undress (blocked)

Does not invent pixels. Delegates path layout to h3_media_pack conventions
and wardrobe lookup to visual_bible / wardrobe_ladder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, sha256_file

WARDROBE_RANK: dict[str, int] = {
    "full": 0,
    "armored": 1,
    "partial": 2,
    "undressed": 3,
    "bare": 4,
    "default": 0,
}

PEAK_WARDROBE = frozenset({"undressed", "bare", "partial"})
CAST_MASTER_MARKERS = (
    "/cast/",
    "/canonical/cast/",
    "cast_master",
    "_master.",
    "cast-masters",
)


class StillSourceError(ValueError):
    """Still source resolution failed closed (wrong wardrobe tier or missing)."""


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def wardrobe_of(shot: dict[str, Any] | None) -> str:
    sh = shot if isinstance(shot, dict) else {}
    dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
    raw = sh.get("wardrobe_state") or dsl.get("wardrobe_state") or "full"
    return str(raw).strip().lower() or "full"


def wardrobe_rank(state: str) -> int:
    return int(WARDROBE_RANK.get(str(state or "").strip().lower(), 0))


def heat_phase_of(shot: dict[str, Any] | None) -> str:
    sh = shot if isinstance(shot, dict) else {}
    return str(sh.get("heat_phase") or sh.get("heatPhase") or "").strip().lower()


def _char_ids(shot: dict[str, Any] | None) -> list[str]:
    sh = shot if isinstance(shot, dict) else {}
    ids: list[str] = []
    for key in ("cast_ids", "character_ids", "chars", "heroine_ids"):
        raw = sh.get(key)
        if isinstance(raw, list):
            ids.extend(str(x) for x in raw if x)
        elif isinstance(raw, str) and raw.strip():
            ids.append(raw.strip())
    for key in ("cast_id", "character_id", "char_id", "speaker_id"):
        raw = sh.get(key)
        if raw:
            ids.append(str(raw))
    dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
    cast = dsl.get("cast") if isinstance(dsl.get("cast"), list) else []
    ids.extend(str(c) for c in cast if c)
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out or ["hero"]


def _rel_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path.resolve())


def looks_like_cast_master(path: Path | str | None) -> bool:
    if path is None:
        return False
    s = str(path).replace("\\", "/").lower()
    return any(m in s for m in CAST_MASTER_MARKERS)


def _file_ok(path: Path | None) -> Path | None:
    if path is None:
        return None
    p = Path(path).expanduser().resolve()
    return p if p.is_file() else None


def _entry(
    path: Path | None,
    *,
    source: str,
    role: str,
    wardrobe_rank_val: int,
    parents: list[dict[str, str]] | None = None,
    blocked: bool = False,
    block_reason: str | None = None,
) -> dict[str, Any]:
    p = _file_ok(path)
    out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "still-source",
        "ok": p is not None and not blocked,
        "path": str(p) if p else None,
        "source": source,
        "role": role,
        "wardrobe_rank": wardrobe_rank_val,
        "sha256": sha256_file(p) if p else None,
        "parents": parents or [],
        "blocked": blocked,
        "block_reason": block_reason,
    }
    return out


def resolve_state_photo_path(
    root: Path | str,
    shot: dict[str, Any] | None = None,
) -> tuple[Path | None, str | None]:
    """Best state photo for the shot wardrobe (not a per-shot narrative keyframe)."""
    base = _root(root)
    sh = shot if isinstance(shot, dict) else {}
    wardrobe = wardrobe_of(sh)
    bible = read_json(base / "style-bible.json") or {}
    if not isinstance(bible, dict):
        return None, None
    dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
    state_id = sh.get("wardrobe_state_id") or dsl.get("wardrobe_state_id")
    state_id = str(state_id).strip() if state_id else None
    try:
        from visual_bible import resolve_state_photo
    except ImportError:
        return None, None
    for cid in _char_ids(sh):
        raw = resolve_state_photo(
            bible,
            cid,
            wardrobe,
            root=base,
            wardrobe_state_id=state_id,
        )
        if not raw:
            continue
        p = Path(str(raw))
        if not p.is_absolute():
            p = base / p
        if p.is_file():
            return p.resolve(), f"state_photo:{cid}:{wardrobe}"
    return None, None


def is_peak_forbidden_cast_master(
    path: Path | str | None,
    shot: dict[str, Any] | None,
) -> bool:
    """True when undress/bare shot would animate from full cast master only."""
    if not looks_like_cast_master(path):
        return False
    wardrobe = wardrobe_of(shot)
    heat = heat_phase_of(shot)
    if wardrobe in PEAK_WARDROBE:
        return True
    if heat in {"act", "climax", "peak"} and wardrobe_rank(wardrobe) >= 2:
        return True
    return False


def resolve_still_source(
    root: Path | str,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
    still_override: Path | str | None = None,
    approved_still: Path | str | None = None,
    continue_end_frame: Path | str | None = None,
    wants_continue: bool | None = None,
    kind: str = "i2v",
    allow_cast_master_fallback: bool = False,
) -> dict[str, Any]:
    """Resolve primary still for generation.

    ``kind``: still | i2v | flf | r2v (still prefers state photo when no keyframe).
    """
    base = _root(root)
    sh = shot if isinstance(shot, dict) else {}
    if not sh:
        spec = read_json(base / "film-spec.json") or {}
        if isinstance(spec, dict):
            try:
                from continue_handoff import find_shot

                sh = find_shot(spec, shot_id) or {}
            except Exception:
                sh = {}
    wardrobe = wardrobe_of(sh)
    w_rank = wardrobe_rank(wardrobe)
    parents: list[dict[str, str]] = []

    # 1) explicit override
    if still_override is not None:
        ov = _file_ok(Path(still_override))
        if ov is not None:
            if not allow_cast_master_fallback and is_peak_forbidden_cast_master(ov, sh):
                return _entry(
                    ov,
                    source="explicit_override",
                    role="first",
                    wardrobe_rank_val=w_rank,
                    blocked=True,
                    block_reason="PEAK_CAST_MASTER_FORBIDDEN",
                )
            return _entry(
                ov,
                source="explicit_override",
                role="first",
                wardrobe_rank_val=w_rank,
                parents=parents,
            )

    # 2) continue handoff
    cont_path: Path | None = None
    if continue_end_frame:
        cont_path = _file_ok(Path(continue_end_frame))
    wants = wants_continue
    if wants is None:
        try:
            from continue_handoff import shot_wants_continue

            wants = shot_wants_continue(sh)
        except Exception:
            wants = False
    if wants and cont_path is not None:
        return _entry(
            cont_path,
            source="continue_handoff",
            role="first",
            wardrobe_rank_val=w_rank,
            parents=[{"role": "prev_end", "path": str(cont_path)}],
        )

    # 3) approved still (manifest preferred, then stills/keyframes convention)
    approved = _file_ok(Path(approved_still)) if approved_still else None
    if approved is None:
        man = read_json(base / "manifest.json") or {}
        stills = man.get("stills") if isinstance(man, dict) else {}
        entry = stills.get(shot_id) if isinstance(stills, dict) else None
        if isinstance(entry, dict):
            raw = entry.get("path") or entry.get("file")
            if raw:
                p = Path(str(raw))
                if not p.is_absolute():
                    p = base / p
                approved = _file_ok(p)
        if approved is None:
            for cand in (
                base / "stills" / f"{shot_id}.png",
                base / "keyframes" / f"{shot_id}.png",
                base / "stills" / f"{shot_id}.jpg",
                base / "keyframes" / f"{shot_id}.jpg",
            ):
                if cand.is_file():
                    approved = cand.resolve()
                    break
    if approved is not None:
        if not allow_cast_master_fallback and is_peak_forbidden_cast_master(approved, sh):
            # fall through to state photo rather than animate full cast
            parents.append({"role": "rejected_cast_master", "path": str(approved)})
        else:
            return _entry(
                approved,
                source="approved",
                role="first",
                wardrobe_rank_val=w_rank,
                parents=parents,
            )

    # continue fallback without approved
    if cont_path is not None:
        return _entry(
            cont_path,
            source="continue_handoff_fallback",
            role="first",
            wardrobe_rank_val=w_rank,
        )

    # 4) delegate path conventions (shot fields + stills/keyframes)
    try:
        from h3_media_pack import resolve_first_frame_path

        path, source = resolve_first_frame_path(
            base,
            shot_id,
            shot=sh,
            approved_still=None,
            continue_end_frame=None,
            wants_continue=False,
        )
        if path is not None and source not in {
            None,
            "continue_handoff",
            "continue_handoff_fallback",
        }:
            if not allow_cast_master_fallback and is_peak_forbidden_cast_master(path, sh):
                parents.append({"role": "rejected_cast_master", "path": str(path)})
            else:
                return _entry(
                    path,
                    source=str(source or "convention"),
                    role="first",
                    wardrobe_rank_val=w_rank,
                    parents=parents,
                )
    except Exception:
        pass

    # 5) state photo (still gen or missing keyframe)
    state_path, state_src = resolve_state_photo_path(base, sh)
    if state_path is not None:
        role = "state_photo" if str(kind) == "still" else "first"
        return _entry(
            state_path,
            source=state_src or "state_photo",
            role=role,
            wardrobe_rank_val=w_rank,
            parents=parents,
        )

    # 6) peak: block silent cast master
    if wardrobe in PEAK_WARDROBE or heat_phase_of(sh) in {"act", "climax", "peak"}:
        return _entry(
            None,
            source="missing",
            role="first",
            wardrobe_rank_val=w_rank,
            parents=parents,
            blocked=True,
            block_reason="PEAK_STILL_MISSING_NO_CAST_FALLBACK",
        )

    if allow_cast_master_fallback:
        bible = read_json(base / "style-bible.json") or {}
        masters = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
        for cid in _char_ids(sh):
            raw = masters.get(cid)
            if isinstance(raw, dict):
                raw = raw.get("path") or raw.get("file")
            if raw:
                p = Path(str(raw))
                if not p.is_absolute():
                    p = base / p
                if p.is_file():
                    return _entry(
                        p,
                        source=f"cast_master:{cid}",
                        role="identity",
                        wardrobe_rank_val=w_rank,
                        parents=parents,
                    )

    return _entry(
        None,
        source="missing",
        role="first",
        wardrobe_rank_val=w_rank,
        parents=parents,
    )


def assert_still_source_safe(
    entry: dict[str, Any],
    *,
    shot_id: str = "",
    root: Path | str | None = None,
    shot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed when peak wardrobe would use cast master or is blocked.

    Also enforces I2V composition-fill on resolved pixel path (P0 2026-08-07 EP02):
    cast fullbody masters and postage-stamp subjects cannot feed motion.

    F3 · when ``root`` given, still must bind current face-lock enroll (no archive path).
    """
    if entry.get("blocked"):
        raise StillSourceError(
            f"still source blocked for {shot_id or '?'}: {entry.get('block_reason')}"
        )
    if not entry.get("ok") or not entry.get("path"):
        raise StillSourceError(f"still source missing for {shot_id or '?'}")
    # Composition fill: refuse tiny fullbody / cast-sheet paths as I2V first frame
    try:
        from composition_fill_gate import assert_i2v_firstframe_fill, path_looks_like_cast_fullbody

        p = Path(str(entry["path"]))
        if p.is_file():
            # Cast master under cast/ is never a playable first frame
            if path_looks_like_cast_fullbody(p) and "keyframes/" not in str(p).replace(
                "\\", "/"
            ) and "stills/" not in str(p).replace("\\", "/"):
                raise StillSourceError(
                    f"still source for {shot_id or '?'} is cast/fullbody sheet path "
                    f"({p.name}); cover-crop to keyframes/ as MS/CU first "
                    "(EP02 composition-fill iron)"
                )
            fill = assert_i2v_firstframe_fill(p, mode="open")
            entry["composition_fill"] = {
                "ok": fill.get("ok"),
                "codes": fill.get("codes"),
                "metrics": fill.get("metrics"),
            }
            if not fill.get("ok") and not fill.get("skipped"):
                codes = ",".join(fill.get("codes") or ["TINY"])
                raise StillSourceError(
                    f"still source for {shot_id or '?'} failed composition-fill "
                    f"({codes}): subject must fill frame; see composition_fill_gate"
                )
    except StillSourceError:
        raise
    except Exception:
        pass  # soft if gate import/deps missing

    # F3 · face-lock generation bind (enroll + no archive still as H3 source)
    if root is not None:
        try:
            from gates.still_face_lock_bind import (
                StillFaceLockBindError,
                assert_still_face_lock_bound,
            )

            bind = assert_still_face_lock_bound(
                root, entry.get("path"), shot, force=False
            )
            entry["face_lock_bind"] = {
                "ok": bind.get("ok"),
                "codes": bind.get("codes"),
                "char_id": bind.get("char_id"),
                "soft": bind.get("soft"),
            }
        except StillFaceLockBindError as exc:
            raise StillSourceError(
                f"still face-lock bind failed for {shot_id or '?'}: {exc}"
            ) from exc
        except Exception:
            pass  # soft if face stack unavailable
    return entry


def audit_film_still_sources(root: Path | str) -> dict[str, Any]:
    """Per-shot still source summary for bulk-preflight / dispatch."""
    base = _root(root)
    spec = read_json(base / "film-spec.json") or {}
    shots: list[dict[str, Any]] = []
    if isinstance(spec, dict):
        for scene in spec.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for sh in scene.get("shots") or []:
                if isinstance(sh, dict) and sh.get("id"):
                    shots.append(sh)
        if not shots and isinstance(spec.get("shots"), list):
            shots = [s for s in spec["shots"] if isinstance(s, dict) and s.get("id")]
    rows: list[dict[str, Any]] = []
    hard: list[str] = []
    for sh in shots:
        sid = str(sh["id"])
        entry = resolve_still_source(base, sid, shot=sh, kind="i2v")
        row = {
            "shot_id": sid,
            "ok": bool(entry.get("ok")),
            "source": entry.get("source"),
            "path": entry.get("path"),
            "sha256": entry.get("sha256"),
            "wardrobe": wardrobe_of(sh),
            "blocked": bool(entry.get("blocked")),
            "block_reason": entry.get("block_reason"),
        }
        rows.append(row)
        if entry.get("blocked") or (wardrobe_of(sh) in PEAK_WARDROBE and not entry.get("ok")):
            hard.append(f"{sid}:{entry.get('block_reason') or 'missing'}")
    return {
        "schema_version": 1,
        "kind": "still-source-audit",
        "ok": not hard,
        "hard": hard,
        "shots": rows,
        "peak_missing": [r["shot_id"] for r in rows if r.get("blocked")],
    }
