#!/usr/bin/env python3
"""Append-only dailies ledger and current selects projection."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from production_book import stable_content_hash
from util import read_json, write_json

DAILIES_PATH = Path("receipts/dailies-selects.json")
TAKE_STATES = {"raw", "select", "alternate", "reject"}
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class DailiesError(ValueError):
    """A take or director decision is incomplete or invalid."""


def _path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / DAILIES_PATH


def read_dailies(root: Path | str) -> dict[str, Any]:
    ledger = read_json(_path(root)) or {}
    ledger.setdefault("schema_version", 1)
    ledger.setdefault("kind", "dailies-selects")
    ledger.setdefault("revision", 0)
    ledger.setdefault("takes", {})
    ledger.setdefault("events", [])
    return ledger


def _required_text(value: str, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise DailiesError(f"{field} is required")
    return text


def _write(root: Path | str, ledger: dict[str, Any]) -> dict[str, Any]:
    ledger["revision"] = int(ledger.get("revision") or 0) + 1
    ledger["content_sha256"] = stable_content_hash(ledger)
    write_json(_path(root), ledger)
    return ledger


def record_take(
    root: Path | str,
    *,
    take_id: str,
    shot_id: str,
    asset_ref: str,
    asset_hash: str,
    director_notes: str,
) -> dict[str, Any]:
    take = _required_text(take_id, "take_id")
    shot = _required_text(shot_id, "shot_id")
    ref = _required_text(asset_ref, "asset_ref")
    notes = _required_text(director_notes, "director_notes")
    if not _SHA256_RE.fullmatch(str(asset_hash)):
        raise DailiesError("asset_hash must be a lowercase SHA-256")
    ledger = read_dailies(root)
    if take in ledger["takes"]:
        raise DailiesError(f"take_id already exists: {take}")
    current = {
        "take_id": take,
        "shot_id": shot,
        "state": "raw",
        "asset_ref": ref,
        "asset_hash": asset_hash,
        "director_notes": notes,
        "rejection_notes": None,
    }
    event = {"action": "record", **current}
    event["event_sha256"] = stable_content_hash(event)
    ledger["takes"][take] = current
    ledger["events"].append(event)
    _write(root, ledger)
    return current


def set_take_state(
    root: Path | str,
    *,
    take_id: str,
    state: str,
    director_notes: str,
    rejection_notes: str | None = None,
) -> dict[str, Any]:
    take = _required_text(take_id, "take_id")
    if state not in TAKE_STATES:
        raise DailiesError("state must be raw|select|alternate|reject")
    notes = _required_text(director_notes, "director_notes")
    rejection = str(rejection_notes or "").strip() or None
    if state == "reject" and rejection is None:
        raise DailiesError("reject state requires rejection_notes")
    ledger = read_dailies(root)
    if take not in ledger["takes"]:
        raise DailiesError(f"unknown take_id: {take}")
    current = ledger["takes"][take]
    current["state"] = state
    current["director_notes"] = notes
    current["rejection_notes"] = rejection
    event = {
        "action": "decision",
        "take_id": take,
        "shot_id": current["shot_id"],
        "state": state,
        "asset_ref": current["asset_ref"],
        "asset_hash": current["asset_hash"],
        "director_notes": notes,
        "rejection_notes": rejection,
    }
    event["event_sha256"] = stable_content_hash(event)
    ledger["events"].append(event)
    _write(root, ledger)
    return dict(current)


def selects_for_shot(root: Path | str, shot_id: str) -> list[dict[str, Any]]:
    shot = _required_text(shot_id, "shot_id")
    return [
        dict(take)
        for take in read_dailies(root)["takes"].values()
        if take.get("shot_id") == shot and take.get("state") in {"select", "alternate"}
    ]
