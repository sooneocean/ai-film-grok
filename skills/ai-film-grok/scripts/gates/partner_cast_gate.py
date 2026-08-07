"""E2 · Partner / on-camera cast master + face_lock gate.

hard-defaults: every on-camera character needs cast_master + face_lock image paths;
style.locked must not green on heroine-only masters.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from util import utc_now

RECEIPT_REL = Path("receipts/partner-cast-gate.json")
_CHAR_LINE = re.compile(r"Character\s+([A-Za-z0-9_\-]+)\s*:", re.I)


def _env_skip(root: Path | None = None) -> bool:
    try:
        from core.skip_audit import skip_flag

        return bool(
            skip_flag(
                "AIFILM_SKIP_PARTNER_CAST",
                film_root=root,
                origin="partner_cast_gate",
                call_site="env_skip",
            )
        )
    except Exception:
        return os.environ.get("AIFILM_SKIP_PARTNER_CAST", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        from util import read_json

        data = read_json(path)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_media_path(root: Path, raw: object) -> Path | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = (
            raw.get("path")
            or raw.get("file")
            or raw.get("image")
            or raw.get("master")
            or raw.get("face_lock")
        )
    s = str(raw or "").strip()
    if not s:
        return None
    p = Path(s)
    if p.is_file():
        return p
    cand = (root / s).resolve()
    if cand.is_file():
        return cand
    # common cast/ layout
    for prefix in ("cast", "assets/cast", "style", "lookbook"):
        c2 = (root / prefix / s).resolve()
        if c2.is_file():
            return c2
    return None


def _entry_paths(entry: object) -> tuple[object, object]:
    if not isinstance(entry, dict):
        return entry, None
    master = (
        entry.get("cast_master")
        or entry.get("master")
        or entry.get("path")
        or entry.get("image")
        or entry.get("file")
    )
    face = (
        entry.get("face_lock")
        or entry.get("face")
        or entry.get("face_ref")
        or entry.get("face_path")
        or entry.get("lock")
    )
    return master, face


def audit_partner_cast(
    root: Path | str,
    *,
    write_receipt: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Check cast_masters completeness for style.locked honesty."""
    base = Path(root).expanduser().resolve()
    if force or _env_skip(base):
        rep = {
            "kind": "partner-cast-gate",
            "ok": True,
            "skipped": True,
            "codes": [],
            "escape": "AIFILM_SKIP_PARTNER_CAST=1",
            "at": utc_now(),
        }
        if write_receipt:
            _write(base, rep)
        return rep

    bible = _load_json(base / "style-bible.json")
    cast = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
    style_locked_flag = bool(bible.get("locked") or (bible.get("style") or {}).get("locked"))
    # also style-bible style.locked
    if isinstance(bible.get("style"), dict) and "locked" in bible["style"]:
        style_locked_flag = bool(bible["style"].get("locked"))

    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    per_char: dict[str, Any] = {}

    if not cast:
        rep = {
            "kind": "partner-cast-gate",
            "ok": True,
            "checked": False,
            "codes": [],
            "issues": [],
            "style_locked_claim": style_locked_flag,
            "note": "no cast_masters — gate not applicable",
            "at": utc_now(),
            "root": str(base),
        }
        if write_receipt:
            _write(base, rep)
        return rep

    missing_master: list[str] = []
    missing_face: list[str] = []
    for cid, entry in cast.items():
        cid_s = str(cid)
        master_raw, face_raw = _entry_paths(entry)
        master_p = _resolve_media_path(base, master_raw)
        face_p = _resolve_media_path(base, face_raw)
        # single-path cast master can serve as face_lock if only one image
        if master_p and not face_p and isinstance(entry, (str, Path)):
            face_p = master_p
        if master_p and not face_p and isinstance(entry, dict) and not face_raw:
            # allow face_lock == master when only one path field
            face_p = master_p
        per_char[cid_s] = {
            "master_ok": bool(master_p),
            "face_lock_ok": bool(face_p),
            "master": str(master_p) if master_p else None,
            "face_lock": str(face_p) if face_p else None,
        }
        if not master_p:
            missing_master.append(cid_s)
        if not face_p:
            missing_face.append(cid_s)

    if missing_master:
        codes.append("CAST_MASTER_MISSING")
        issues.append(
            {
                "code": "CAST_MASTER_MISSING",
                "chars": missing_master,
                "message": f"cast_master path missing/unreadable: {', '.join(missing_master)}",
            }
        )
    if missing_face:
        codes.append("FACE_LOCK_MISSING")
        issues.append(
            {
                "code": "FACE_LOCK_MISSING",
                "chars": missing_face,
                "message": f"face_lock path missing/unreadable: {', '.join(missing_face)}",
            }
        )

    style_locked_false_green = False
    if style_locked_flag and (missing_master or missing_face):
        style_locked_false_green = True
        codes.append("STYLE_LOCKED_FALSE_GREEN")
        issues.append(
            {
                "code": "STYLE_LOCKED_FALSE_GREEN",
                "message": (
                    "style.locked=true but not all cast_masters have master+face_lock — "
                    "heroine-only lock is fake green"
                ),
            }
        )

    # Dual-character prompt lint: advisory from film-spec dialogue shots
    dual_prompt_issues: list[dict[str, Any]] = []
    spec = _load_json(base / "film-spec.json")
    shots = spec.get("shots") if isinstance(spec.get("shots"), list) else []
    multi_ids = [str(k) for k in cast if str(k).lower() not in {"hero", "env", "bg"}]
    if len(cast) >= 2:
        for sh in shots[:80]:
            if not isinstance(sh, dict):
                continue
            prompt = " ".join(
                str(sh.get(k) or "")
                for k in ("prompt", "i2v_prompt", "still_prompt", "visual_prompt")
            )
            chars_field = sh.get("characters") or sh.get("cast") or []
            n_chars = 0
            if isinstance(chars_field, list):
                n_chars = len([c for c in chars_field if c])
            elif isinstance(chars_field, str) and "," in chars_field:
                n_chars = 2
            # heuristic: shot mentions 2+ character ids
            mentioned = [cid for cid in multi_ids if cid.lower() in prompt.lower()]
            if n_chars >= 2 or len(mentioned) >= 2:
                if not _CHAR_LINE.search(prompt):
                    dual_prompt_issues.append(
                        {
                            "shot_id": sh.get("id"),
                            "code": "DUAL_CHAR_PROMPT_MISSING",
                            "message": "multi-character shot prompt lacks `Character <id>:` labels",
                        }
                    )
    if dual_prompt_issues:
        codes.append("DUAL_CHAR_PROMPT_MISSING")
        issues.extend(dual_prompt_issues[:12])

    # hard when style claims locked or adult-looking multi cast incomplete
    hard = bool(missing_master or missing_face) and (
        style_locked_flag or len(cast) >= 2
    )
    # dual prompt is advisory (soft codes only for ok)
    soft_only = set(codes) <= {"DUAL_CHAR_PROMPT_MISSING"}
    ok = (not hard) if not soft_only else True
    if soft_only and dual_prompt_issues and not (missing_master or missing_face):
        ok = True  # advisory

    rep = {
        "kind": "partner-cast-gate",
        "schema_version": 1,
        "ok": ok,
        "checked": True,
        "codes": sorted(set(codes)),
        "issues": issues,
        "per_char": per_char,
        "style_locked_claim": style_locked_flag,
        "style_locked_false_green": style_locked_false_green,
        "escape": "AIFILM_SKIP_PARTNER_CAST=1",
        "at": utc_now(),
        "root": str(base),
        "next_cmd": (
            None
            if ok
            else "add cast_master+face_lock images for every on-camera character; fix style.locked"
        ),
    }
    if write_receipt:
        _write(base, rep)
    return rep


def _write(root: Path, rep: dict[str, Any]) -> Path:
    out = root / RECEIPT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from util import write_json

        write_json(out, rep)
    except Exception:
        import json

        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


__all__ = ["audit_partner_cast"]
