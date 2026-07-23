from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from take_registry import (  # noqa: E402
    compare_takes,
    mark_shots_stale,
    register_active_take,
    take_id,
)


def test_take_id_is_stable() -> None:
    assert take_id("shot01", "abcdef1234567890") == "shot01--abcdef123456"


def test_register_active_take_preserves_previous_and_writes_receipt(tmp_path: Path) -> None:
    root = tmp_path / "film"
    root.mkdir()
    manifest = {"clips": {}}
    first = register_active_take(
        root, manifest, {"shot_id": "shot01", "sha256": "a" * 64, "path": "old.mp4"}
    )
    previous = dict(first)
    previous["archived_path"] = "clips/takes/shot01--aaaaaaaaaaaa.mp4"
    second = register_active_take(
        root,
        manifest,
        {"shot_id": "shot01", "sha256": "b" * 64, "path": "new.mp4"},
        previous=previous,
    )
    assert second["state"] == "active"
    assert manifest["active_takes"]["shot01"] == "shot01--bbbbbbbbbbbb"
    assert manifest["take_history"]["shot01"][0]["state"] == "active"
    receipt = json.loads((root / "receipts" / "takes" / "shot01.json").read_text())
    assert receipt["previous_take_id"] == "shot01--aaaaaaaaaaaa"


def test_mark_shots_stale_is_scoped(tmp_path: Path) -> None:
    manifest = {
        "clips": {
            "shot01": {"state": "active", "active": True},
            "shot02": {"state": "active", "active": True},
        }
    }
    report = mark_shots_stale(tmp_path, manifest, ["shot01"], reason="beat changed")
    assert report["changed_shots"] == ["shot01"]
    assert manifest["clips"]["shot01"]["state"] == "stale"
    assert manifest["clips"]["shot02"]["state"] == "active"


def test_compare_takes_keeps_active_first_and_scores_candidates() -> None:
    manifest = {
        "clips": {
            "shot01": {
                "take_id": "shot01--new",
                "sha256": "b" * 64,
                "state": "active",
                "active": True,
                "quality_gate": {
                    "ok": True,
                    "review": {"approved": True, "scorecard": {"dimensions": {"motion": 5}}},
                },
            }
        },
        "take_history": {
            "shot01": [{"take_id": "shot01--old", "state": "superseded", "sha256": "a" * 64}]
        },
    }
    report = compare_takes(manifest, "shot01")
    assert report["candidates"][0]["take_id"] == "shot01--new"
    assert report["candidates"][0]["score_total"] == 5
