"""Signed, project-bound attachment receipts for restricted audio candidates."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from performance_candidates import receipt_is_signed, sign_receipt
from util import read_json, write_json

_CANDIDATE_KIND_BY_EVENT_TYPE = {"action_sfx": "sfx", "ambience": "ambience"}
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _confined_without_symlinks(root: Path, path: Path, *, require_file: bool) -> bool:
    """Accept only a literal in-root path whose components are never symlinks."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return False
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return False
    return current.is_file() if require_file else current.is_dir()


def bind(
    root: Path, *, candidate_kind: str, asset_id: str, shot_id: str, cue: dict[str, Any]
) -> str:
    root = root.resolve()
    if candidate_kind not in set(_CANDIDATE_KIND_BY_EVENT_TYPE.values()):
        raise ValueError("candidate_kind is invalid")
    if not all(_IDENTIFIER_RE.fullmatch(value) for value in (asset_id, shot_id)):
        raise ValueError("asset_id and shot_id must be safe identifiers")
    approval_raw = str(cue["approval_receipt"])
    if approval_raw.startswith("library:"):
        from sfx_library import SFXLibraryError, resolve_uri

        try:
            approval = resolve_uri(approval_raw)
        except SFXLibraryError as exc:
            raise ValueError("candidate approval receipt is missing") from exc
        approval_identity = approval_raw
    else:
        approval = root / approval_raw.removeprefix("local:")
        if not _confined_without_symlinks(root, approval, require_file=True):
            raise ValueError("candidate approval receipt is missing")
        approval_identity = str(approval.relative_to(root))
    attachment_dir = root / "audio" / "attachments" / candidate_kind
    attachment_dir.mkdir(parents=True, exist_ok=True)
    if not _confined_without_symlinks(root, attachment_dir, require_file=False):
        raise ValueError("candidate attachment directory is unsafe")
    identity = hashlib.sha256(
        f"{root}|{asset_id}|{shot_id}|{cue['start_offset_sec']}|{cue['duration_sec']}|{cue['source_sha256']}".encode()
    ).hexdigest()[:20]
    receipt = attachment_dir / f"{asset_id}-{shot_id}-{identity}.json"
    record = {
        "schema": "aifilm-restricted-audio-attachment-v1",
        "candidate_kind": candidate_kind,
        "asset_id": asset_id,
        "project_root_sha256": hashlib.sha256(str(root).encode()).hexdigest(),
        "shot_id": shot_id,
        "delivery_scope": "noncommercial_internal",
        "approval_receipt": approval_identity,
        "approval_receipt_sha256": _digest(approval),
        "cue": {
            key: cue.get(key)
            for key in (
                "kind",
                "start_offset_sec",
                "duration_sec",
                "source",
                "source_sha256",
                "gain",
                "pan",
                "fade_in_sec",
                "fade_out_sec",
            )
        },
    }
    sign_receipt(record)
    write_json(receipt, record)
    return f"local:{receipt.relative_to(root)}"


def valid(root: Path, event: dict[str, Any]) -> bool:
    root = root.resolve()
    raw = str(event.get("attachment_receipt") or "")
    expected_kind = _CANDIDATE_KIND_BY_EVENT_TYPE.get(str(event.get("type") or ""))
    if expected_kind is None or not raw.startswith("local:"):
        return False
    path = root / raw.removeprefix("local:")
    try:
        relative = path.relative_to(root)
        if relative.parts[:3] != (
            "audio",
            "attachments",
            expected_kind,
        ) or not _confined_without_symlinks(root, path, require_file=True):
            return False
        record = read_json(path)
        approval_raw = str(event.get("approval_receipt") or "")
        if approval_raw.startswith("library:"):
            from sfx_library import SFXLibraryError, resolve_uri

            try:
                approval = resolve_uri(approval_raw)
            except SFXLibraryError:
                return False
            approval_identity = approval_raw
        else:
            approval = root / approval_raw.removeprefix("local:")
            approval_identity = str(approval.relative_to(root))
        cue = {
            key: event.get(key)
            for key in (
                "duration_sec",
                "source",
                "source_sha256",
                "gain",
                "pan",
                "fade_in_sec",
                "fade_out_sec",
            )
        }
        cue["kind"] = event.get("track")
        cue["start_offset_sec"] = event.get("start_offset_sec", event.get("start_sec"))
        return bool(
            isinstance(record, dict)
            and receipt_is_signed(record)
            and record.get("schema") == "aifilm-restricted-audio-attachment-v1"
            and record.get("candidate_kind") == expected_kind
            and record.get("project_root_sha256") == hashlib.sha256(str(root).encode()).hexdigest()
            and record.get("shot_id") == event.get("shot_id")
            and record.get("delivery_scope") == "noncommercial_internal"
            and (
                approval_raw.startswith("library:")
                or _confined_without_symlinks(root, approval, require_file=True)
            )
            and record.get("approval_receipt") == approval_identity
            and record.get("approval_receipt_sha256") == _digest(approval)
            and record.get("cue") == cue
        )
    except (OSError, ValueError):
        return False
