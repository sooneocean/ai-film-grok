"""Hash-bound dual-master delivery package contract for premium vertical films."""

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


REQUIRED = {
    "mezzanine": ("film_final_prores.mov", "film_final_prores.mp4"),
    "publish": ("film_final.mp4", "film_final_h264.mp4", "film_final_h265.mp4"),
    "subtitle": ("final.srt",),
    "clean": ("film_final_clean.mp4",),
    "edl": ("edit.edl",),
}


def build_delivery_package(root: Path | str, *, allow_missing: bool = False) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    out = base / "out"
    assets: dict[str, Any] = {}
    blockers: list[dict[str, str]] = []
    for role, candidates in REQUIRED.items():
        selected = next((out / name for name in candidates if (out / name).is_file()), None)
        if selected is None:
            assets[role] = {"path": None, "sha256": None}
            if not allow_missing:
                blockers.append(
                    {"code": "DELIVERY_ASSET_MISSING", "message": f"missing {role} delivery asset"}
                )
        else:
            assets[role] = {"path": str(selected), "sha256": _sha(selected)}
    stems_dir = base / "audio" / "stems"
    stems = (
        sorted(str(path) for path in stems_dir.glob("*") if path.is_file())
        if stems_dir.is_dir()
        else []
    )
    if not stems and not allow_missing:
        blockers.append(
            {
                "code": "STEMS_MISSING",
                "message": "audio/stems must contain dialogue, ambience, foley, SFX and music deliverables",
            }
        )
    report = {
        "schema_version": 1,
        "kind": "premium-delivery-package",
        "ok": not blockers,
        "assets": assets,
        "stems": [{"path": item, "sha256": _sha(Path(item))} for item in stems],
        "provenance": read_json(base / "provenance.json") or {},
        "blockers": blockers,
        "human_review_required": True,
    }
    write_json(base / "receipts" / "premium-delivery-package.json", report)
    return report
