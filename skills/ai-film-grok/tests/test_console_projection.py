"""Read-only dispatch / queue projections for console-state (Wave B2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.console

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from asset_picker import console_state  # noqa: E402
from console_projection import (  # noqa: E402
    enrich_console_state,
    project_dispatch_for_console,
    project_queue_snapshot,
)


def test_dispatch_projection_missing_receipt(tmp_path):
    proj = project_dispatch_for_console(tmp_path)
    assert proj["available"] is False
    assert "dispatch" in (proj.get("hint") or "").lower() or "aifilm" in (proj.get("copy_cmd") or "")
    assert "aifilm dispatch" in proj["copy_cmd"]


def test_dispatch_projection_from_receipt(tmp_path):
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "dispatch.json").write_text(
        json.dumps(
            {
                "at": "2026-08-07T00:00:00+00:00",
                "stage_public": "visual",
                "craft_stage": "media",
                "next_id": "h3-run-next",
                "next_cmd": "aifilm h3 run-next --root /film --max 5",
                "next_why": "clips incomplete; H3 primary",
                "route_catalog_id": "h3-run-next",
                "weapon_route": {"layer": "weapon", "inventory_line": "wp=minimax-h3-i2v"},
                "next_action": {
                    "id": "h3-run-next",
                    "cmd": "aifilm h3 run-next --root /film --max 5",
                    "blocked_by": [{"id": "pilot", "reason": "awaiting approval"}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    proj = project_dispatch_for_console(tmp_path)
    assert proj["available"] is True
    assert proj["stage_public"] == "visual"
    assert proj["next_id"] == "h3-run-next"
    assert "h3 run-next" in (proj["next_cmd"] or "")
    assert proj["copy_cmd"] == proj["next_cmd"]
    assert proj["weapon_line"] == "wp=minimax-h3-i2v"
    assert proj["blocked_by"]


def test_queue_snapshot_from_media_queue(tmp_path):
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "media-queue.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {"id": "a", "status": "running"},
                    {"id": "b", "status": "pending"},
                    {"id": "c", "status": "unknown"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "takes").mkdir()
    (tmp_path / "takes" / "t1.mp4").write_bytes(b"x")
    snap = project_queue_snapshot(tmp_path)
    assert snap["available"] is True
    assert snap["running"] >= 1
    assert snap["unknown"] == 1
    assert snap["takes_count"] == 1


def test_console_state_includes_projections(tmp_path):
    (tmp_path / "receipts").mkdir()
    state = console_state(tmp_path)
    assert state["kind"] == "console-state"
    assert "dispatch_projection" in state
    assert "queue_snapshot" in state
    assert state["dispatch_projection"]["available"] is False


def test_enrich_console_state_preserves_base_keys(tmp_path):
    base = {"kind": "console-state", "ledger_revision": 3}
    out = enrich_console_state(tmp_path, base)
    assert out["ledger_revision"] == 3
    assert out["dispatch_projection"]["available"] is False


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_console_state_endpoint_exposes_dispatch(tmp_path):
    from fastapi.testclient import TestClient
    from web_api import create_app

    (tmp_path / "receipts").mkdir()
    (tmp_path / "receipts" / "dispatch.json").write_text(
        json.dumps(
            {
                "stage_public": "voice",
                "next_id": "tts-render",
                "next_cmd": "aifilm tts render --root x",
                "next_why": "missing stems",
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path, "tok", 56170))
    r = client.get("/api/console-state", headers={"X-Review-Token": "tok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dispatch_projection"]["available"] is True
    assert body["dispatch_projection"]["next_id"] == "tts-render"
    assert "tts render" in body["dispatch_projection"]["copy_cmd"]
