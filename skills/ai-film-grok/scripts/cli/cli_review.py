"""Read-only continuity review packet presentation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json


def review_packet_status(root: Path | str, shot_id: str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    packet = read_json(base / "receipts" / "reviews" / f"{shot_id}.json") or {}
    continuity = (
        packet.get("continuity_packet") if isinstance(packet.get("continuity_packet"), dict) else {}
    )
    return {
        "kind": "review-packet-status",
        "shot_id": shot_id,
        "reviewed": packet.get("approved") is True,
        "continuity_packet_current": continuity.get("ok") is True,
        "neighbours": continuity.get("neighbours") or {},
        "receipt": packet,
    }
