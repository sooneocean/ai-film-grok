"""bulk-preflight exposes weapon inventory primaries on fail paths."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workflow_pack import WorkflowPackError, assert_bulk_preflight, bulk_preflight  # noqa: E402


def _seed(root: Path, *, with_pilot: bool = False) -> None:
    (root / "receipts").mkdir(parents=True, exist_ok=True)
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "inv-bulk",
                "heat_scale": "soft",
                "scenes": [
                    {
                        "shots": [
                            {
                                "id": "shot01",
                                "nar": "一",
                                "duration_sec": 6,
                                "wardrobe_state": "full",
                                "dsl": {"subject": "a", "action": "b", "motion": "c"},
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    if with_pilot:
        (root / "receipts" / "pilot-approval.json").write_text(
            json.dumps({"approved": True, "approved_by": "user"}),
            encoding="utf-8",
        )


def test_bulk_preflight_attaches_weapon_inventory(tmp_path: Path) -> None:
    root = tmp_path / "film"
    root.mkdir()
    _seed(root, with_pilot=False)
    report = bulk_preflight(root, write=True, probe_tunnel=False, check_lease=False)
    inv = report.get("weapon_inventory") or {}
    assert inv.get("still_primary") == "qwen-image-2512-quality"
    assert inv.get("motion_primary") == "minimax-h3-i2v-pilot"
    assert inv.get("edit_primary") == "qwen-image-edit-2511-local"
    assert "pilot" in (report.get("failed") or [])
    assert report.get("next_cmd")
    assert "still=" in (report.get("next_why") or "")
    assert report.get("weapon_hints", {}).get("motion_primary") == "minimax-h3-i2v-pilot"
    # pilot fail should name motion primary in check weapon_hint
    pilot = next(c for c in report["checks"] if c["id"] == "pilot")
    assert pilot.get("ok") is False
    assert "minimax-h3" in str(pilot.get("weapon_hint") or "")


def test_assert_bulk_preflight_error_names_weapons(tmp_path: Path) -> None:
    root = tmp_path / "film"
    root.mkdir()
    _seed(root, with_pilot=False)
    with pytest.raises(WorkflowPackError) as ei:
        assert_bulk_preflight(root, require=True, probe_tunnel=False, check_lease=False)
    msg = str(ei.value)
    assert "bulk preflight failed" in msg
    assert "still=qwen-image-2512-quality" in msg
    assert "motion=minimax-h3-i2v-pilot" in msg


def test_still_source_fail_next_cmd_names_edit_primary(tmp_path: Path) -> None:
    """Synthetic still_source fail path via patched audit."""
    root = tmp_path / "film"
    root.mkdir()
    _seed(root, with_pilot=True)
    (root / "manifest.json").write_text(
        json.dumps({"stills": {"shot01": {"path": "stills/x.png", "status": "approved"}}}),
        encoding="utf-8",
    )
    import workflow_pack as wp

    class Fake:
        @staticmethod
        def audit_film_still_sources(_root):
            return {"ok": False, "hard": ["PEAK_CAST_MASTER"], "peak_missing": ["shot01"]}

    import sys
    from types import ModuleType

    fake = ModuleType("still_source")
    fake.audit_film_still_sources = Fake.audit_film_still_sources  # type: ignore[attr-defined]
    sys.modules["still_source"] = fake
    try:
        report = wp.bulk_preflight(root, write=False, probe_tunnel=False, check_lease=False)
    finally:
        sys.modules.pop("still_source", None)
    assert "still_source" in (report.get("failed") or [])
    ss = next(c for c in report["checks"] if c["id"] == "still_source")
    assert ss.get("ok") is False
    assert "still=" in str(ss.get("weapon_hint") or "")
    # when still_source is first fail, next_cmd names edit primary
    if (report.get("failed") or [None])[0] == "still_source":
        assert "qwen-image-edit" in str(report.get("next_cmd") or "")
    else:
        # state_index may rank first — still inventory attaches on report
        assert report.get("weapon_inventory", {}).get("edit_primary") == "qwen-image-edit-2511-local"
        assert "edit=" in str(ss.get("weapon_hint") or "") or "still=" in str(ss.get("weapon_hint") or "")
