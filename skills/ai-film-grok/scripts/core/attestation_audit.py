"""Human attestation provenance (honesty-rail R2 · 2026-08-07).

Records *who/when/what* for anatomy_safe and related human gates so closeout can
prove attestation is not a bare boolean. Does **not** auto-approve pilot/PK.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

LEDGER_REL = "receipts/attestation-ledger.json"
_PROV_KEYS = ("agent_session", "reviewer", "timestamp", "still_path")


def _utc() -> str | None:
    try:
        from util import utc_now

        return utc_now()
    except Exception:  # noqa: BLE001
        return None


def load_attestation_ledger(root: Path | str | None) -> dict[str, Any]:
    if root is None:
        return {"schema_version": 1, "kind": "attestation-ledger", "entries": []}
    base = Path(root).expanduser().resolve()
    try:
        from util import read_json

        data = read_json(base / LEDGER_REL) or {}
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []
    return {
        "schema_version": 1,
        "kind": "attestation-ledger",
        "root": str(base),
        "entries": [e for e in entries if isinstance(e, dict)],
    }


def write_attestation(
    root: Path | str | None,
    *,
    kind: str,
    shot_id: str,
    still_path: str | Path | None = None,
    reviewer: str | None = None,
    agent_session: str | None = None,
    anatomy_safe: bool | None = None,
    note: str | None = None,
    source: str = "register",
) -> dict[str, Any]:
    """Append provenance for a human attestation event.

    Missing reviewer/agent_session → entry marked ``pending_human_review``
    (never invents a fake source).
    """
    if root is None:
        return load_attestation_ledger(None)
    base = Path(root).expanduser().resolve()
    ledger = load_attestation_ledger(base)
    entries: list[dict[str, Any]] = list(ledger.get("entries") or [])
    sid = str(shot_id or "").strip()
    kind_s = str(kind or "anatomy").strip() or "anatomy"
    ts = _utc()
    rev = (str(reviewer).strip() if reviewer else "") or (
        str(os.environ.get("AIFILM_REVIEWER") or "").strip()
    )
    sess = (str(agent_session).strip() if agent_session else "") or (
        str(os.environ.get("AIFILM_AGENT_SESSION") or os.environ.get("GROK_SESSION_ID") or "").strip()
    )
    path_s = str(still_path) if still_path else ""
    pending = not (rev and sess and ts and path_s)
    row = {
        "kind": kind_s,
        "shot_id": sid,
        "still_path": path_s or None,
        "reviewer": rev or None,
        "agent_session": sess or None,
        "timestamp": ts,
        "anatomy_safe": anatomy_safe,
        "note": (str(note)[:240] if note else None),
        "source": str(source or "register"),
        "pending_human_review": pending,
        "provenance_complete": not pending,
    }
    # idempotent replace same kind+shot_id
    out: list[dict[str, Any]] = []
    replaced = False
    for e in entries:
        if e.get("kind") == kind_s and str(e.get("shot_id") or "") == sid:
            out.append(row)
            replaced = True
        else:
            out.append(e)
    if not replaced:
        out.append(row)
    payload = {
        "schema_version": 1,
        "kind": "attestation-ledger",
        "root": str(base),
        "entries": out,
        "count": len(out),
        "pending_count": sum(1 for e in out if e.get("pending_human_review")),
    }
    try:
        from util import write_json

        write_json(base / LEDGER_REL, payload)
    except (OSError, ValueError, TypeError):
        pass
    return payload


def provenance_fields(entry: dict[str, Any] | None) -> dict[str, Any]:
    e = entry if isinstance(entry, dict) else {}
    return {k: e.get(k) for k in _PROV_KEYS}


def find_attestation(
    root: Path | str | None,
    *,
    kind: str,
    shot_id: str,
) -> dict[str, Any] | None:
    kind_s = str(kind or "").strip()
    sid = str(shot_id or "").strip()
    for e in load_attestation_ledger(root).get("entries") or []:
        if isinstance(e, dict) and e.get("kind") == kind_s and str(e.get("shot_id") or "") == sid:
            return e
    return None


def verify_attestation_ledger(root: Path | str | None) -> dict[str, Any]:
    """Closeout summary: complete vs pending provenance (advisory, not hard-block)."""
    ledger = load_attestation_ledger(root)
    entries = list(ledger.get("entries") or [])
    pending = [e for e in entries if e.get("pending_human_review")]
    complete = [e for e in entries if e.get("provenance_complete")]
    return {
        "ok": True,  # never hard-fail delivery; human review is advisory
        "kind": "attestation-verify",
        "advisory": True,
        "count": len(entries),
        "complete_count": len(complete),
        "pending_count": len(pending),
        "pending_human_review": [
            {"kind": e.get("kind"), "shot_id": e.get("shot_id")} for e in pending
        ],
        "note": (
            "all attestations have full provenance"
            if entries and not pending
            else (
                "no attestation events recorded"
                if not entries
                else "some attestations lack reviewer/session/path — pending_human_review"
            )
        ),
    }
