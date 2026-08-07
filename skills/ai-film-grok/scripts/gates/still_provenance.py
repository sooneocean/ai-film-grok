"""E4 · Still provenance / no midframe composite as I2V source.

Rejects stills tagged composite/midframe_paste/half-frame restyle, and paths
under ``_archive_poison_*``. Does **not** claim CV seam detection.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from util import utc_now

_BAD_PROVENANCE = frozenset(
    {
        "composite",
        "midframe_composite",
        "midframe_paste",
        "half_frame_restyle",
        "half_frame",
        "feather_paste",
        "seam_paste",
        "poison_composite",
    }
)
_POISON_DIR_RE = re.compile(r"(^|/)(_archive_poison[^/]*|archive_poison)", re.I)


def _env_skip(root: Path | None = None) -> bool:
    try:
        from core.skip_audit import skip_flag

        return bool(
            skip_flag(
                "AIFILM_SKIP_STILL_PROVENANCE",
                film_root=root,
                origin="still_provenance",
                call_site="env_skip",
            )
        )
    except Exception:
        return os.environ.get("AIFILM_SKIP_STILL_PROVENANCE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def path_is_poison_archive(path: str | Path | None) -> bool:
    if path is None:
        return False
    s = str(path).replace("\\", "/")
    return bool(_POISON_DIR_RE.search(s))


def provenance_is_bad(value: object) -> bool:
    if value is None:
        return False
    s = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not s:
        return False
    if s in _BAD_PROVENANCE:
        return True
    return any(b in s for b in ("composite", "midframe_paste", "half_frame", "feather_paste"))


def assert_still_record_safe_for_i2v(
    record: dict[str, Any] | None,
    *,
    path: str | Path | None = None,
    root: Path | str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Return {ok, codes, issues}. Raises StillProvenanceError when hard-bad."""
    root_p = Path(root).expanduser().resolve() if root else None
    if force or _env_skip(root_p):
        return {"ok": True, "skipped": True, "codes": [], "escape": "AIFILM_SKIP_STILL_PROVENANCE=1"}

    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    rec = record if isinstance(record, dict) else {}
    p = path or rec.get("path") or rec.get("file") or rec.get("still_path")
    prov = (
        rec.get("still_provenance")
        or rec.get("provenance")
        or rec.get("source_kind")
        or rec.get("compose_method")
    )

    if path_is_poison_archive(p):
        codes.append("POISON_ARCHIVE_STILL")
        issues.append(
            {
                "code": "POISON_ARCHIVE_STILL",
                "message": f"still under poison archive path banned as I2V source: {p}",
                "path": str(p),
            }
        )
    if provenance_is_bad(prov):
        codes.append("STILL_PROVENANCE_COMPOSITE")
        issues.append(
            {
                "code": "STILL_PROVENANCE_COMPOSITE",
                "message": (
                    f"still_provenance={prov!r} banned for I2V — use whole_frame only; "
                    "no half-frame restyle paste"
                ),
                "provenance": prov,
            }
        )

    ok = len(codes) == 0
    out = {
        "ok": ok,
        "codes": codes,
        "issues": issues,
        "still_provenance": prov,
        "path": str(p) if p else None,
        "escape": "AIFILM_SKIP_STILL_PROVENANCE=1",
        "at": utc_now(),
    }
    if not ok:
        raise StillProvenanceError("; ".join(i["message"] for i in issues))
    return out


class StillProvenanceError(RuntimeError):
    """Still is not safe as I2V/FLF source (composite / poison archive)."""


def audit_film_still_provenance(root: Path | str) -> dict[str, Any]:
    """Scan manifest stills for bad provenance / poison paths (no raise)."""
    base = Path(root).expanduser().resolve()
    if _env_skip(base):
        return {"ok": True, "skipped": True, "codes": [], "checked": 0}
    try:
        from util import read_json

        manifest = read_json(base / "film-manifest.json") or {}
    except Exception as exc:  # noqa: BLE001 — fail-closed, not silent empty
        return {
            "kind": "still-provenance-audit",
            "ok": False,
            "checked": 0,
            "codes": ["STILL_PROVENANCE_MANIFEST_READ_FAILED"],
            "issues": [{"message": str(exc)[:200]}],
            "escape": "AIFILM_SKIP_STILL_PROVENANCE=1",
            "at": utc_now(),
            "root": str(base),
            "error": str(exc)[:200],
        }
    stills = manifest.get("stills") if isinstance(manifest.get("stills"), dict) else {}
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    checked = 0
    for sid, rec in stills.items():
        if not isinstance(rec, dict):
            continue
        status = str(rec.get("status") or "").lower()
        if status in {"rejected", "archived", "poison"}:
            continue
        checked += 1
        try:
            assert_still_record_safe_for_i2v(rec, root=base)
        except StillProvenanceError as exc:
            codes.extend(["STILL_PROVENANCE_BAD"])
            issues.append({"shot_id": sid, "message": str(exc)[:200]})
    return {
        "kind": "still-provenance-audit",
        "ok": len(issues) == 0,
        "checked": checked,
        "codes": sorted(set(codes)),
        "issues": issues[:40],
        "escape": "AIFILM_SKIP_STILL_PROVENANCE=1",
        "at": utc_now(),
        "root": str(base),
    }


__all__ = [
    "StillProvenanceError",
    "assert_still_record_safe_for_i2v",
    "audit_film_still_provenance",
    "path_is_poison_archive",
    "provenance_is_bad",
]
