"""Shared helpers used across the spine dispatch/advance/workflow modules.

These functions are intentionally simple and have no cross-imports back
into the spine packages, so they can be safely imported by all spine files.
"""

from __future__ import annotations

import re
from pathlib import Path

from util import soft_json


def present(path: Path, *, min_bytes: int = 2) -> bool:
    """Return True when *path* exists and exceeds *min_bytes*."""
    return path.is_file() and path.stat().st_size > min_bytes


def pilot_user_ok(root: Path) -> bool:
    """Check whether the pilot was approved by the user.

    Tries the authoritative ``production_gates`` path first; falls back
    to a direct receipt check when the import fails.
    """
    pilot_approval = soft_json(root / "receipts" / "pilot-approval.json")
    try:
        from production_gates import pilot_is_user_approved

        return pilot_is_user_approved(pilot_approval)
    except Exception:
        return bool(
            str(pilot_approval.get("approved_by") or "").lower() == "user"
            and str(pilot_approval.get("user_phrase") or "").strip()
        )


def post_audit_current(root: Path) -> bool:
    """Return True when the post-audit receipt exists and is fresh."""
    receipt = soft_json(root / "receipts" / "post-audit.json")
    if not isinstance(receipt, dict) or receipt.get("delivery_ready") is not True:
        return False
    try:
        from post_audit import audit_freshness

        return audit_freshness(root, receipt).get("stale") is False
    except (ImportError, OSError, ValueError):
        return False


def export_desktop_name(root: Path) -> str:
    """Stable Desktop folder name without placeholders (advance-safe argv)."""
    for rel in ("film-spec.json", "brief.json", "manifest.json"):
        data = soft_json(root / rel)
        if not isinstance(data, dict):
            continue
        raw = str(data.get("title") or data.get("name") or "").strip()
        if raw:
            cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", raw, flags=re.UNICODE)
            cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-.")
            if cleaned:
                return cleaned
    return "film"
