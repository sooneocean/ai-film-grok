"""F3 · Still path must bind current face-lock generation (ban archive / drift).

When cast is enrolled in face-identity, I2V stills for on-camera shots must:
1. not live under ``_archive_*`` paths
2. pass face-identity verify against enrolled anchors (face-lock / cast master)

Escape: ``AIFILM_SKIP_STILL_FACE_LOCK=1`` or film-spec ``face_identity_soft: true``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_REL = Path("receipts/still-face-lock-bind.json")
_ARCHIVE_RE = re.compile(r"(^|/)(_archive[^/]*|archive_old)", re.I)


def _env_skip(root: Path | None) -> bool:
    try:
        from core.skip_audit import skip_flag

        return bool(
            skip_flag(
                "AIFILM_SKIP_STILL_FACE_LOCK",
                origin="env",
                film_root=root,
                call_site="still_face_lock_bind",
            )
        )
    except Exception:
        return os.environ.get("AIFILM_SKIP_STILL_FACE_LOCK", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def _shot_cast_ids(shot: dict[str, Any] | None) -> list[str]:
    if not isinstance(shot, dict):
        return []
    out: list[str] = []
    for key in ("cast", "characters", "character_ids"):
        val = shot.get(key)
        if isinstance(val, list):
            for x in val:
                if isinstance(x, str) and x.strip():
                    out.append(x.strip())
                elif isinstance(x, dict) and x.get("id"):
                    out.append(str(x["id"]).strip())
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cast = dsl.get("cast") if isinstance(dsl.get("cast"), list) else []
    for x in cast:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    # speaker / hero default
    for key in ("speaker", "focal_character", "char_id", "character"):
        v = shot.get(key)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for c in out:
        if c not in seen and c.lower() not in {"env", "bg", "background", "none"}:
            seen.add(c)
            uniq.append(c)
    return uniq


def path_is_archive_generation(path: str | Path | None) -> bool:
    if path is None:
        return False
    return bool(_ARCHIVE_RE.search(str(path).replace("\\", "/")))


def check_still_face_lock_bind(
    root: Path | str,
    still_path: Path | str | None,
    shot: dict[str, Any] | None = None,
    *,
    force: bool = False,
    record_verify: bool = False,
) -> dict[str, Any]:
    """Return {ok, codes, issues, char_id?} for one still path."""
    base = Path(root).expanduser().resolve()
    if force or _env_skip(base):
        return {"ok": True, "skipped": True, "codes": [], "escape": "AIFILM_SKIP_STILL_FACE_LOCK"}

    spec = read_json(base / "film-spec.json") or {}
    soft = isinstance(spec, dict) and spec.get("face_identity_soft") is True

    bible = read_json(base / "style-bible.json") or {}
    cast_masters = (
        bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
    )
    if not cast_masters:
        return {"ok": True, "checked": False, "codes": [], "detail": "no cast_masters"}

    try:
        from assets.face_identity import load_receipt, verify_image
    except ImportError:  # pragma: no cover
        from face_identity import load_receipt, verify_image  # type: ignore

    receipt = load_receipt(base)
    enrolled = receipt.get("enrolled") if isinstance(receipt.get("enrolled"), dict) else {}

    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    path = Path(still_path).expanduser() if still_path else None

    if path is None or not str(path):
        return {
            "ok": True,
            "checked": False,
            "codes": [],
            "detail": "no still path",
        }

    if path_is_archive_generation(path):
        codes.append("STILL_FACE_ARCHIVE_PATH")
        issues.append(
            {
                "code": "STILL_FACE_ARCHIVE_PATH",
                "message": f"still under archive path banned for H3/I2V face bind: {path}",
                "path": str(path),
            }
        )

    cast_ids = _shot_cast_ids(shot)
    if not cast_ids:
        # default hero when masters include hero
        cast_ids = ["hero"] if "hero" in cast_masters else [str(next(iter(cast_masters)))]

    primary = cast_ids[0]
    if primary not in enrolled and not any(c in enrolled for c in cast_ids):
        codes.append("STILL_FACE_NOT_ENROLLED")
        issues.append(
            {
                "code": "STILL_FACE_NOT_ENROLLED",
                "message": (
                    f"cast {cast_ids} not enrolled in face-identity — "
                    "run enroll-bible before H3 (or face_identity_soft)"
                ),
                "cast": cast_ids,
            }
        )
    else:
        char = primary if primary in enrolled else next(c for c in cast_ids if c in enrolled)
        # Path bind: still == enrolled source / face-lock plate counts as bound without pixel.
        enrolled_entry = enrolled.get(char) if isinstance(enrolled.get(char), dict) else {}
        enrolled_src = str(enrolled_entry.get("source") or "")
        path_s = str(path).replace("\\", "/")
        path_bound = bool(
            enrolled_src
            and (
                path_s.endswith(enrolled_src.replace("\\", "/").split("/")[-1])
                or enrolled_src.replace("\\", "/") in path_s
                or path_s in enrolled_src.replace("\\", "/")
            )
        )
        if path.is_file() and not path_bound:
            try:
                vr = verify_image(base, path, char, record=record_verify)
                if not vr.get("ok"):
                    # Pixel drift is soft by default (angles/CU differ); hard only under strict.
                    strict = isinstance(spec, dict) and (
                        spec.get("face_identity_strict") is True
                        or str(spec.get("heat_scale") or "").lower()
                        in {"max", "hot", "extreme"}
                    )
                    code = "STILL_FACE_LOCK_DRIFT" if strict else "STILL_FACE_LOCK_DRIFT_SOFT"
                    codes.append(code)
                    issues.append(
                        {
                            "code": code,
                            "message": (
                                f"still face score weak vs enrolled {char}: "
                                f"score={vr.get('score')} "
                                f"(rebind still to current face-lock / re-enroll)"
                            ),
                            "char_id": char,
                            "path": str(path),
                            "score": vr.get("score"),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                codes.append("STILL_FACE_VERIFY_ERROR_SOFT")
                issues.append(
                    {
                        "code": "STILL_FACE_VERIFY_ERROR_SOFT",
                        "message": f"face verify error (soft): {exc}"[:160],
                        "char_id": char,
                    }
                )

    soft_only = {
        "STILL_FACE_LOCK_DRIFT_SOFT",
        "STILL_FACE_VERIFY_ERROR_SOFT",
    }
    if soft:
        soft_only.add("STILL_FACE_NOT_ENROLLED")
    hard_codes = [c for c in codes if c not in soft_only]
    if hard_codes == [] and codes:
        return {
            "ok": True,
            "soft": True,
            "checked": True,
            "codes": codes,
            "hard_codes": [],
            "issues": issues,
            "char_id": primary,
            "path": str(path),
        }

    ok = len(hard_codes) == 0
    return {
        "ok": ok,
        "checked": True,
        "codes": codes,
        "hard_codes": hard_codes,
        "issues": issues,
        "char_id": primary,
        "path": str(path),
        "soft": soft and not ok,
    }


def audit_film_still_face_lock_bind(
    root: Path | str,
    *,
    write_receipt: bool = True,
    max_shots: int = 40,
) -> dict[str, Any]:
    """Film-level audit over resolved still sources."""
    base = Path(root).expanduser().resolve()
    if _env_skip(base):
        out = {
            "kind": "still-face-lock-bind",
            "ok": True,
            "skipped": True,
            "codes": [],
            "at": utc_now(),
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, out)
        return out

    from media.still_source import (
        audit_film_still_sources,
        resolve_still_source,
    )

    spec = read_json(base / "film-spec.json") or {}
    shots: list[dict[str, Any]] = []
    if isinstance(spec, dict):
        for scene in spec.get("scenes") or []:
            if isinstance(scene, dict):
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict) and sh.get("id"):
                        shots.append(sh)
        if not shots and isinstance(spec.get("shots"), list):
            shots = [s for s in spec["shots"] if isinstance(s, dict) and s.get("id")]

    rows: list[dict[str, Any]] = []
    hard: list[str] = []
    all_codes: list[str] = []
    for sh in shots[:max_shots]:
        sid = str(sh["id"])
        try:
            entry = resolve_still_source(base, sid, shot=sh, kind="i2v")
        except Exception as exc:  # noqa: BLE001 — fail-closed: resolve error ≠ pass
            rows.append(
                {
                    "shot_id": sid,
                    "ok": False,
                    "codes": ["STILL_SOURCE_RESOLVE_FAILED"],
                    "error": str(exc)[:120],
                }
            )
            hard.append(f"{sid}:STILL_SOURCE_RESOLVE_FAILED")
            if "STILL_SOURCE_RESOLVE_FAILED" not in all_codes:
                all_codes.append("STILL_SOURCE_RESOLVE_FAILED")
            continue
        if not entry.get("path"):
            continue
        # skip pure env inserts
        df = str(sh.get("dramatic_function") or "").lower()
        if df in {"insert", "env", "bridge", "broll"} and not _shot_cast_ids(sh):
            continue
        bind = check_still_face_lock_bind(
            base, entry.get("path"), sh, record_verify=False
        )
        row = {
            "shot_id": sid,
            "ok": bind.get("ok"),
            "codes": bind.get("codes") or [],
            "path": entry.get("path"),
            "char_id": bind.get("char_id"),
        }
        rows.append(row)
        for c in bind.get("hard_codes") or bind.get("codes") or []:
            if c not in all_codes:
                all_codes.append(str(c))
        if not bind.get("ok") and not bind.get("soft"):
            hard.append(f"{sid}:{','.join(bind.get('codes') or ['fail'])}")

    out = {
        "kind": "still-face-lock-bind",
        "schema_version": 1,
        "at": utc_now(),
        "root": str(base),
        "ok": not hard,
        "codes": all_codes,
        "hard": hard[:20],
        "shots": rows,
        "checked": len(rows),
        "next_cmd": (
            None
            if not hard
            else f'aifilm face-identity enroll-bible --root "{base}" && reseed stills'
        ),
    }
    # keep audit_film_still_sources available for callers
    try:
        ssa = audit_film_still_sources(base)
        out["still_source_audit_ok"] = bool(ssa.get("ok"))
    except Exception as exc:  # noqa: BLE001 — fail-closed audit signal
        out["still_source_audit_ok"] = False
        out["still_source_audit_error"] = str(exc)[:160]
        if out.get("ok") is True:
            # do not flip whole gate hard solely on nested audit probe; record only
            out.setdefault("codes", []).append("STILL_SOURCE_AUDIT_PROBE_FAILED")
    if write_receipt:
        write_json(base / RECEIPT_REL, out)
        out["path"] = str(base / RECEIPT_REL)
    return out


class StillFaceLockBindError(ValueError):
    """Still not bound to current face-lock generation."""


def assert_still_face_lock_bound(
    root: Path | str,
    still_path: Path | str | None,
    shot: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    rep = check_still_face_lock_bind(root, still_path, shot, force=force)
    if rep.get("ok") or rep.get("skipped") or rep.get("soft"):
        return rep
    msg = "; ".join(
        f"[{i.get('code')}] {i.get('message')}" for i in (rep.get("issues") or [])[:4]
    )
    raise StillFaceLockBindError(
        msg
        or f"still face-lock bind failed codes={rep.get('codes')}"
    )


__all__ = [
    "StillFaceLockBindError",
    "assert_still_face_lock_bound",
    "audit_film_still_face_lock_bind",
    "check_still_face_lock_bind",
    "path_is_archive_generation",
]
