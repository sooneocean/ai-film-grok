"""Lightweight asset version parent chain (Film Production OS W7).

CHAR_v01 → CHAR_v02 APPROVED; downstream records used_version.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

ASSET_KINDS = frozenset({"character", "location", "wardrobe", "prop", "reference", "look"})


def _text(value: object) -> str:
    return str(value or "").strip()


def normalize_version_record(raw: object) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    return {
        "id": _text(src.get("id")),
        "kind": _text(src.get("kind") or "character") or "character",
        "version": _text(src.get("version") or src.get("rev") or "v01") or "v01",
        "parent_version": _text(src.get("parent_version") or src.get("parent")) or None,
        "status": _text(src.get("status") or "draft").lower() or "draft",
        "path": _text(src.get("path")) or None,
        "approved_at": src.get("approved_at"),
        "notes": _text(src.get("notes")) or None,
    }


def load_version_ledger(root: Path | str) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    data = read_json(root_p / "receipts" / "asset-versions.json") or {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("kind", "asset-version-ledger")
    data.setdefault("assets", {})
    return data


def register_asset_version(
    root: Path | str,
    *,
    asset_id: str,
    kind: str = "character",
    version: str = "v01",
    parent_version: str | None = None,
    status: str = "draft",
    path: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    ledger = load_version_ledger(root_p)
    assets = ledger.setdefault("assets", {})
    if not isinstance(assets, dict):
        assets = {}
        ledger["assets"] = assets
    aid = _text(asset_id)
    chain = assets.setdefault(aid, [])
    if not isinstance(chain, list):
        chain = []
        assets[aid] = chain
    rec = normalize_version_record(
        {
            "id": aid,
            "kind": kind if kind in ASSET_KINDS else "character",
            "version": version,
            "parent_version": parent_version,
            "status": status,
            "path": path,
            "notes": notes,
            "approved_at": utc_now() if str(status).lower() == "approved" else None,
        }
    )
    # replace same version id if re-register
    chain[:] = [c for c in chain if not (isinstance(c, dict) and c.get("version") == rec["version"])]
    chain.append(rec)
    ledger["at"] = utc_now()
    path_out = root_p / "receipts" / "asset-versions.json"
    write_json(path_out, ledger)
    return {"ok": True, "asset_id": aid, "record": rec, "receipt": str(path_out), "chain": chain}


def resolve_approved_version(root: Path | str, asset_id: str) -> dict[str, Any]:
    ledger = load_version_ledger(root)
    chain = (ledger.get("assets") or {}).get(_text(asset_id)) or []
    if not isinstance(chain, list):
        return {"ok": False, "error": "no chain"}
    approved = [c for c in chain if isinstance(c, dict) and str(c.get("status")).lower() == "approved"]
    if not approved:
        latest = chain[-1] if chain else None
        return {
            "ok": False,
            "asset_id": asset_id,
            "approved": None,
            "latest": latest,
            "message": "no APPROVED version — do not claim identity lock from draft",
        }
    return {"ok": True, "asset_id": asset_id, "approved": approved[-1], "chain_len": len(chain)}
