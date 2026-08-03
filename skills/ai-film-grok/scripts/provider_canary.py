"""Truthful provider canary receipts; no API call or spend is implicit."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from util import read_json, write_json


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_canary(
    root: Path | str,
    *,
    provider: str,
    output: str,
    reviewer: str,
    identity_ok: bool,
    motion_ok: bool,
    provider_model: str = "",
    notes: str = "",
) -> dict[str, Any]:
    if provider not in {"grok", "seedance", "frw-api-i2v", "frw-ltx23"}:
        raise ValueError("provider must be grok|seedance|frw-api-i2v|frw-ltx23")
    if provider == "grok" and not provider_model.strip():
        provider_model = "grok-imagine-video-1.5"
    elif provider == "frw-ltx23" and not provider_model.strip():
        provider_model = "ltx-2.3"
    elif provider == "frw-api-i2v" and not provider_model.strip():
        provider_model = "img2video"
    base = Path(root).expanduser().resolve()
    media = Path(output).expanduser()
    if not media.is_absolute():
        media = base / media
    sha = _sha(media)
    if not sha:
        raise ValueError("canary output must be a real local media file")
    report = {
        "schema_version": 1,
        "kind": "provider-canary",
        "provider": provider,
        "provider_model": provider_model.strip() or None,
        "output": str(media),
        "output_sha256": sha,
        "reviewer": reviewer.strip(),
        "identity_ok": bool(identity_ok),
        "motion_ok": bool(motion_ok),
        "notes": notes.strip(),
        "ok": bool(identity_ok and motion_ok),
        "human_review_required": True,
    }
    write_json(base / "receipts" / "provider-canary.json", report)
    if provider == "grok":
        write_json(base / "receipts" / "grok-i2v-canary.json", report)
    elif provider == "seedance":
        write_json(base / "receipts" / "seedance-canary.json", report)
    elif provider == "frw-ltx23":
        write_json(base / "receipts" / "frw-ltx23-canary.json", report)
    elif provider == "frw-api-i2v":
        write_json(base / "receipts" / "frw-api-i2v-canary.json", report)
    return report


def canary_status(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    report = read_json(base / "receipts" / "provider-canary.json") or {}
    output = Path(str(report.get("output") or ""))
    if not output.is_absolute():
        output = base / output
    current = _sha(output)
    ok = bool(report.get("ok") and report.get("output_sha256") == current)
    return {**report, "current_output_sha256": current, "ok": ok, "stale": bool(report) and not ok}
