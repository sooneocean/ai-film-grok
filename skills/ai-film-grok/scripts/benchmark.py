"""No-spend benchmark contract for the premium vertical quality profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from production_book import read_production_book
from util import write_json

SUITES = {
    "premium-vertical": (
        {"id": "dialogue-subtext", "duration_sec": 45, "focus": "dialogue/performance"},
        {"id": "motion-continuity", "duration_sec": 45, "focus": "action/continuity"},
        {"id": "atmosphere-sound", "duration_sec": 45, "focus": "visual-motif/sound"},
        {"id": "longform-stress", "duration_sec": 90, "focus": "segmentation/rhythm"},
    )
}


def run_benchmark(root: Path | str | None, *, suite: str, mode: str) -> dict[str, Any]:
    if suite not in SUITES:
        raise ValueError(f"unknown benchmark suite: {suite}")
    base = Path(root).expanduser().resolve() if root else None
    if mode == "contract":
        blockers: list[dict[str, str]] = []
        target = "standard"
        if base is not None and (base / "production-book.json").is_file():
            target = str(read_production_book(base).get("quality_target", "standard"))
            if target != "premium_vertical":
                blockers.append(
                    {
                        "code": "QUALITY_TARGET_NOT_PREMIUM",
                        "message": "benchmark requires quality_target=premium_vertical",
                    }
                )
        report = {
            "ok": not blockers,
            "kind": "premium-vertical-benchmark-contract",
            "suite": suite,
            "mode": mode,
            "quality_target": target,
            "cases": list(SUITES[suite]),
            "blockers": blockers,
            "live_media_required": True,
            "human_review_required": True,
        }
    elif mode == "live":
        report = {
            "ok": False,
            "kind": "premium-vertical-benchmark-live",
            "suite": suite,
            "mode": mode,
            "blockers": [
                {
                    "code": "LIVE_CANARY_APPROVAL_REQUIRED",
                    "message": "live benchmark may spend provider credits; obtain explicit approval and run the provider canary first",
                }
            ],
            "human_review_required": True,
        }
    else:
        raise ValueError("benchmark mode must be contract|live")
    if base is not None:
        path = base / "receipts" / "premium-benchmark.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
