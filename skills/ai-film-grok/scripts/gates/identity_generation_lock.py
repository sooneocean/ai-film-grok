"""E1 · Identity generation lock — one cast generation per film root timeline.

Machine gate for hard-defaults row「身份代际锁」:
- Active approved stills/clips must not resolve under ``_archive_*`` paths.
- When cast_masters exist, ``face-identity.verified≠true`` → IDENTITY_PARTIAL
  (honest plate only; never claim face-stable master).

Escape: ``AIFILM_SKIP_IDENTITY_GEN=1`` (+ skip_audit when film root known).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from util import utc_now

RECEIPT_REL = Path("receipts/cast-generation.json")
_ARCHIVE_RE = re.compile(r"(^|/)(_archive[^/]*|archive_pre_|_archive_pre_)", re.I)


def _env_skip(root: Path | None = None) -> bool:
    try:
        from core.skip_audit import skip_flag

        return bool(
            skip_flag(
                "AIFILM_SKIP_IDENTITY_GEN",
                film_root=root,
                origin="identity_generation_lock",
                call_site="env_skip",
            )
        )
    except Exception:
        return os.environ.get("AIFILM_SKIP_IDENTITY_GEN", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def _path_looks_archive(path: str | Path | None) -> bool:
    if path is None:
        return False
    s = str(path).replace("\\", "/")
    if not s.strip():
        return False
    if _ARCHIVE_RE.search(s):
        return True
    # takes/_archive_* / stills/_archive_*
    parts = s.split("/")
    return any(p.startswith("_archive") or p.startswith("archive_pre_") for p in parts)


def _iter_manifest_media_paths(manifest: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return list of (kind, shot_id, path_str)."""
    out: list[tuple[str, str, str]] = []
    for kind, key in (("still", "stills"), ("clip", "clips")):
        bucket = manifest.get(key) or {}
        if not isinstance(bucket, dict):
            continue
        for sid, rec in bucket.items():
            if not isinstance(rec, dict):
                continue
            status = str(rec.get("status") or "").lower()
            if status and status not in {"approved", "active", "selected", "promoted"}:
                # still scan non-approved lightly for archive restore silence
                if status in {"rejected", "archived", "poison"}:
                    continue
            path = (
                rec.get("path")
                or rec.get("file")
                or rec.get("relpath")
                or rec.get("clip_path")
                or rec.get("still_path")
            )
            if path:
                out.append((kind, str(sid), str(path)))
    return out


def _load_json(path: Path) -> dict[str, Any]:
    try:
        from util import read_json

        data = read_json(path)
        return data if isinstance(data, dict) else {}
    except Exception:
        try:
            import json

            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}


def audit_identity_generation(
    root: Path | str,
    *,
    write_receipt: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Audit one-generation / no-archive-mix / verified honesty.

    Returns dict with ``ok``, ``identity_partial``, ``codes``, ``issues``, …
    ``ok=False`` only on hard archive-mix (or skip disabled + hard codes).
    Unverified face-identity → ``identity_partial=True`` but ``ok=True`` so plate
    can ship as PARTIAL; master claims must read the flag.
    """
    base = Path(root).expanduser().resolve()
    if force or _env_skip(base):
        rep = {
            "kind": "cast-generation",
            "schema_version": 1,
            "ok": True,
            "skipped": True,
            "identity_partial": False,
            "codes": [],
            "issues": [],
            "escape": "AIFILM_SKIP_IDENTITY_GEN=1",
            "at": utc_now(),
            "root": str(base),
        }
        if write_receipt:
            _write_receipt(base, rep)
        return rep

    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    archive_hits: list[dict[str, str]] = []

    manifest_path = base / "film-manifest.json"
    if not manifest_path.is_file():
        # also try common names
        for alt in ("manifest.json", "receipts/film-manifest.json"):
            p = base / alt
            if p.is_file():
                manifest_path = p
                break
    manifest = _load_json(manifest_path) if manifest_path.is_file() else {}

    for kind, sid, path in _iter_manifest_media_paths(manifest):
        if _path_looks_archive(path):
            archive_hits.append({"kind": kind, "shot_id": sid, "path": path})
            issues.append(
                {
                    "code": "ARCHIVE_MIX_IN_TIMELINE",
                    "shot_id": sid,
                    "kind": kind,
                    "message": (
                        f"active {kind} {sid} resolves under archive path — "
                        "one generation per film; re-I2V, do not silent-restore archive"
                    ),
                    "path": path,
                }
            )
            codes.append("ARCHIVE_MIX_IN_TIMELINE")

    # Walk approved keyframe/clip dirs for archive-named files registered via relative path
    for sub in ("takes", "stills", "keyframes", "clips"):
        d = base / sub
        if not d.is_dir():
            continue
        # Only flag if something outside archive dirs points into archive — handled above.
        # Extra: if film-spec timeline lists archive paths
        pass

    # face-identity verified honesty
    bible = _load_json(base / "style-bible.json")
    cast_masters = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
    fi = _load_json(base / "receipts" / "face-identity.json")
    verified = bool(fi.get("verified")) if fi else False
    enrolled = fi.get("enrolled") if isinstance(fi.get("enrolled"), dict) else {}
    identity_partial = False

    if cast_masters:
        if not fi:
            identity_partial = True
            codes.append("FACE_IDENTITY_MISSING")
            issues.append(
                {
                    "code": "FACE_IDENTITY_MISSING",
                    "message": (
                        "cast_masters present but no receipts/face-identity.json — "
                        "enroll+audit or ship as IDENTITY_PARTIAL only"
                    ),
                }
            )
        elif not verified:
            identity_partial = True
            codes.append("IDENTITY_UNVERIFIED")
            issues.append(
                {
                    "code": "IDENTITY_UNVERIFIED",
                    "message": (
                        "face-identity.verified≠true — ban face-stable master claim; "
                        "technical plate must be IDENTITY_PARTIAL"
                    ),
                }
            )
        # generation id bookkeeping (optional field)
    gen_id = None
    if isinstance(bible.get("cast_generation_id"), str) and bible["cast_generation_id"].strip():
        gen_id = bible["cast_generation_id"].strip()
    elif isinstance(fi.get("cast_generation_id"), str):
        gen_id = str(fi.get("cast_generation_id")).strip() or None

    hard_codes = {"ARCHIVE_MIX_IN_TIMELINE"}
    hard = [c for c in codes if c in hard_codes]
    ok = len(hard) == 0

    rep: dict[str, Any] = {
        "kind": "cast-generation",
        "schema_version": 1,
        "ok": ok,
        "identity_partial": identity_partial or (not ok),
        "classification": (
            "FAIL_ARCHIVE_MIX"
            if not ok
            else ("IDENTITY_PARTIAL" if identity_partial else "IDENTITY_OK")
        ),
        "codes": sorted(set(codes)),
        "issues": issues,
        "archive_hits": archive_hits[:40],
        "cast_generation_id": gen_id,
        "face_identity_verified": verified,
        "enrolled_chars": sorted(enrolled.keys()) if enrolled else [],
        "cast_master_chars": sorted(str(k) for k in cast_masters) if cast_masters else [],
        "escape": "AIFILM_SKIP_IDENTITY_GEN=1",
        "at": utc_now(),
        "root": str(base),
        "next_cmd": (
            None
            if ok and not identity_partial
            else (
                'aifilm face-identity enroll-bible && aifilm face-identity audit  # or re-I2V; '
                "never mix _archive_* into final"
            )
        ),
    }
    if write_receipt:
        _write_receipt(base, rep)
    return rep


def _write_receipt(root: Path, rep: dict[str, Any]) -> Path:
    out = root / RECEIPT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from util import write_json

        write_json(out, rep)
    except Exception:
        import json

        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def assert_identity_generation_ok(
    root: Path | str,
    *,
    force: bool = False,
    allow_partial: bool = True,
) -> dict[str, Any]:
    """Fail-closed on archive mix. IDENTITY_PARTIAL raises only if allow_partial=False."""
    rep = audit_identity_generation(root, write_receipt=True, force=force)
    if not rep.get("ok"):
        raise IdentityGenerationError(
            "ARCHIVE_MIX_IN_TIMELINE: " + "; ".join(
                i.get("message", "") for i in (rep.get("issues") or [])[:3]
            )
        )
    if not allow_partial and rep.get("identity_partial"):
        raise IdentityGenerationError(
            "IDENTITY_PARTIAL: face-identity not verified — ban master claim"
        )
    return rep


class IdentityGenerationError(RuntimeError):
    """Hard identity generation lock violation."""


__all__ = [
    "IdentityGenerationError",
    "assert_identity_generation_ok",
    "audit_identity_generation",
]
