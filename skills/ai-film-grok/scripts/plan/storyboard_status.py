"""Storyboard planning artifact status (not final image quality).

Film Production OS W3: draft → review → approved before keyframe bulk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

STORYBOARD_STATES = frozenset({"draft", "review", "approved", "rejected"})

CODE_STORYBOARD_MISSING = "STORYBOARD_MISSING"
CODE_STORYBOARD_NOT_APPROVED = "STORYBOARD_NOT_APPROVED"
CODE_STORYBOARD_STALE = "STORYBOARD_STALE"


def _sha_spec(root: Path) -> str:
    from util import sha256_file

    p = root / "film-spec.json"
    if not p.is_file():
        return ""
    return sha256_file(p)


def load_storyboard_receipt(root: Path | str) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    data = read_json(root_p / "receipts" / "storyboard.json") or {}
    return data if isinstance(data, dict) else {}


def set_storyboard_status(
    root: Path | str,
    *,
    status: str,
    user_phrase: str = "",
    notes: str = "",
    shot_ids: list[str] | None = None,
) -> dict[str, Any]:
    status_n = str(status or "").strip().lower()
    if status_n not in STORYBOARD_STATES:
        return {
            "ok": False,
            "error": f"status must be one of {sorted(STORYBOARD_STATES)}",
        }
    root_p = Path(root).expanduser().resolve()
    if status_n == "approved" and not str(user_phrase or "").strip():
        return {"ok": False, "error": "approve requires --user-phrase"}

    payload = {
        "schema_version": 1,
        "kind": "storyboard-status",
        "status": status_n,
        "user_phrase": str(user_phrase or "").strip() or None,
        "notes": str(notes or "").strip() or None,
        "shot_ids": list(shot_ids or []),
        "spec_sha256": _sha_spec(root_p),
        "at": utc_now(),
        "ok": True,
    }
    path = root_p / "receipts" / "storyboard.json"
    write_json(path, payload)
    payload["receipt"] = str(path)
    payload["root"] = str(root_p)
    return payload


def check_storyboard_gate(
    root: Path | str,
    *,
    strict: bool = False,
    require_approved: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    receipt = load_storyboard_receipt(root_p)
    issues: list[dict[str, Any]] = []
    if not receipt:
        issues.append(
            {
                "code": CODE_STORYBOARD_MISSING,
                "severity": "error" if strict else "warning",
                "message": "no storyboard receipt — run aifilm plan storyboard set --status review",
            }
        )
    else:
        st = str(receipt.get("status") or "")
        if require_approved and st != "approved":
            issues.append(
                {
                    "code": CODE_STORYBOARD_NOT_APPROVED,
                    "severity": "error" if strict else "warning",
                    "message": f"storyboard status={st!r}; need approved before keyframe bulk",
                }
            )
        current = _sha_spec(root_p)
        if receipt.get("spec_sha256") and current and receipt.get("spec_sha256") != current:
            issues.append(
                {
                    "code": CODE_STORYBOARD_STALE,
                    "severity": "error" if strict else "warning",
                    "message": "storyboard stale after film-spec change — re-review",
                }
            )
    errors = [i for i in issues if i.get("severity") == "error"]
    return {
        "ok": not errors,
        "kind": "storyboard-gate",
        "strict": strict,
        "status": receipt.get("status") if receipt else None,
        "issues": issues,
        "codes": sorted({str(i["code"]) for i in issues}),
        "blocking": sorted({str(i["code"]) for i in errors}),
        "keyframe_bulk_allowed": not errors,
        "receipt": receipt or None,
        "root": str(root_p),
        "at": utc_now(),
    }
