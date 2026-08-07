"""Director command center + takes API (Phase A–C)."""

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

from console_projection import (  # noqa: E402
    attach_console_url_to_dispatch,
    project_director_live,
    project_events_tail,
    session_meta,
)
from web.director_center import DirectorCenterError, _find_stage_item, wait_for_approval  # noqa: E402
from web.takes_api import get_takes, list_take_shots, review_take  # noqa: E402


def test_live_empty_film(tmp_path):
    (tmp_path / "receipts").mkdir()
    live = project_director_live(tmp_path)
    assert live["kind"] == "director-center-live"
    assert live["human_inbox"] == []
    assert live["session"]["active"] is False


def test_live_inbox_stage(tmp_path, monkeypatch):
    (tmp_path / "receipts").mkdir()

    def fake_queue(_root):
        return {
            "items": [
                {
                    "id": "pilot",
                    "title": "Pilot",
                    "state": "pending_review",
                    "media": [],
                    "cloud_candidates": [],
                }
            ]
        }

    monkeypatch.setattr("review_control.review_queue", fake_queue)
    live = project_director_live(tmp_path)
    assert live["inbox_count"] >= 1
    assert any(i["id"] == "pilot" for i in live["human_inbox"])


def test_events_tail(tmp_path):
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "pipeline-events.jsonl").write_text(
        json.dumps(
            {
                "event_id": "e1",
                "stage": "h3",
                "phase": "registered",
                "shot_id": "s01",
                "occurred_at": "2026-08-07T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    tail = project_events_tail(tmp_path)
    assert tail["available"] is True
    assert len(tail["events"]) == 1


def test_session_and_console_url(tmp_path):
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "review-ui-session.json").write_text(
        json.dumps(
            {
                "pid": None,
                "port": 5555,
                "token": "tok",
                "root": str(tmp_path.resolve()),
            }
        ),
        encoding="utf-8",
    )
    assert session_meta(tmp_path)["active"] is True
    packet = attach_console_url_to_dispatch(tmp_path, {"ok": True})
    assert "5555" in (packet.get("console_url") or "")


def test_wait_ok_and_timeout(tmp_path, monkeypatch):
    (tmp_path / "receipts").mkdir()

    def ok(_r):
        return {"items": [{"id": "pilot", "state": "approved", "approval_id": "a"}]}

    monkeypatch.setattr("review_control.review_queue", ok)
    assert wait_for_approval(tmp_path, stage="pilot", timeout_sec=1, poll_sec=0.2)["ok"]

    def pending(_r):
        return {"items": [{"id": "pilot", "state": "pending_review"}]}

    monkeypatch.setattr("review_control.review_queue", pending)
    assert wait_for_approval(tmp_path, stage="pilot", timeout_sec=0.4, poll_sec=0.2)["ok"] is False


def test_find_stage_item():
    items = [{"id": "pilot"}, {"id": "director:pilot_approval"}]
    assert _find_stage_item(items, "pilot")["id"] == "pilot"


def test_wait_empty_stage(tmp_path):
    with pytest.raises(DirectorCenterError):
        wait_for_approval(tmp_path, stage="")


def _write_manifest_two_takes(root: Path) -> None:
    (root / "clips").mkdir(exist_ok=True)
    p1 = root / "clips" / "a.mp4"
    p2 = root / "clips" / "b.mp4"
    p1.write_bytes(b"fakea")
    p2.write_bytes(b"fakeb")
    manifest = {
        "schema_version": 2,
        "clips": {
            "s01": {
                "shot_id": "s01",
                "take_id": "s01--aaaaaaaaaaaa",
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "path": str(p1),
                "active": True,
                "state": "active",
            }
        },
        "take_history": {
            "s01": [
                {
                    "shot_id": "s01",
                    "take_id": "s01--bbbbbbbbbbbb",
                    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "path": str(p2),
                    "active": False,
                    "state": "superseded",
                }
            ]
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_takes_list_and_select(tmp_path):
    (tmp_path / "receipts").mkdir()
    _write_manifest_two_takes(tmp_path)
    idx = list_take_shots(tmp_path)
    assert idx["shot_count"] == 1
    assert idx["multi_take_count"] == 1
    cmp = get_takes(tmp_path, "s01")
    assert cmp["candidate_count"] == 2
    report = review_take(
        tmp_path,
        shot_id="s01",
        take_id="s01--bbbbbbbbbbbb",
        director_status="selected",
        note="pick b",
    )
    assert report["ok"] is True
    assert report["result"]["director_status"] == "selected"
    cmp2 = get_takes(tmp_path, "s01")
    active = [c for c in cmp2["candidates"] if c.get("active")]
    assert active and active[0]["take_id"] == "s01--bbbbbbbbbbbb"


def test_console_state_director_live(tmp_path):
    from asset_picker import console_state

    (tmp_path / "receipts").mkdir()
    state = console_state(tmp_path)
    assert state["director_live"]["kind"] == "director-center-live"


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_api_live_and_takes(tmp_path):
    from fastapi.testclient import TestClient
    from web_api import create_app

    (tmp_path / "receipts").mkdir()
    _write_manifest_two_takes(tmp_path)
    app = create_app(tmp_path, token="t", port=8765)
    client = TestClient(app)
    h = {"X-Review-Token": "t"}
    assert client.get("/api/live", headers=h).json()["kind"] == "director-center-live"
    assert client.get("/api/events", headers=h).json()["kind"] == "pipeline-events-tail"
    assert client.get("/api/takes", headers=h).json()["kind"] == "takes-index"
    assert client.get("/api/takes?shot=s01", headers=h).json()["candidate_count"] == 2
    r = client.post(
        "/api/takes/review",
        headers={**h, "Origin": "http://127.0.0.1:8765"},
        json={"shot_id": "s01", "take_id": "s01--bbbbbbbbbbbb", "director_status": "selected"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_review_mode_default_async(tmp_path):
    from review_mode_policy import get_review_mode

    (tmp_path / "receipts").mkdir()
    assert get_review_mode(tmp_path) == "async_dailies"


def test_review_mode_gate_each_blocks_take_pick(tmp_path):
    from review_mode_policy import (
        ReviewModeError,
        assert_review_advance_allowed,
        collect_pending_review_blockers,
        set_review_mode,
    )

    (tmp_path / "receipts").mkdir()
    _write_manifest_two_takes(tmp_path)
    set_review_mode(tmp_path, "gate_each")
    blockers = collect_pending_review_blockers(
        tmp_path, include_take_picks=True, include_stages=True, include_shot_stages=True
    )
    assert any(b.get("kind") == "take_pick" for b in blockers)
    with pytest.raises(ReviewModeError, match="pending human review"):
        assert_review_advance_allowed(tmp_path)
    set_review_mode(tmp_path, "async_dailies")
    # async bulk: take_pick alone does not appear when stages-only collection
    async_picks = collect_pending_review_blockers(
        tmp_path, include_take_picks=True, include_stages=False
    )
    assert any(b.get("kind") == "take_pick" for b in async_picks)
    # hard boundary still blocked by take_pick
    with pytest.raises(ReviewModeError, match="pending human review"):
        assert_review_advance_allowed(tmp_path, boundary="picture_lock")
    with pytest.raises(ReviewModeError, match="pending human review"):
        assert_review_advance_allowed(tmp_path, next_id="final")


def test_hard_boundary_clear_after_select(tmp_path):
    from review_mode_policy import (
        assert_review_advance_allowed,
        collect_pending_review_blockers,
        set_review_mode,
    )
    from web.takes_api import review_take

    (tmp_path / "receipts").mkdir()
    _write_manifest_two_takes(tmp_path)
    set_review_mode(tmp_path, "async_dailies")
    review_take(
        tmp_path,
        shot_id="s01",
        take_id="s01--bbbbbbbbbbbb",
        director_status="selected",
    )
    picks = collect_pending_review_blockers(
        tmp_path, include_take_picks=True, include_stages=False
    )
    assert not any(b.get("kind") == "take_pick" for b in picks)
    report = assert_review_advance_allowed(tmp_path, boundary="final")
    assert report["ok"] is True


def test_sse_frames_hello_and_live(tmp_path):
    from web.sse_stream import format_sse, iter_director_sse

    (tmp_path / "receipts").mkdir()
    frames = list(iter_director_sse(tmp_path, interval_sec=0.3, max_events=1))
    text = b"".join(frames).decode("utf-8")
    assert "event: hello" in text
    assert "event: live" in text
    assert "director-center-live" in text or "director-center-sse" in text
    assert format_sse("ping", {"ok": True}).startswith(b"event: ping")


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_api_stream_endpoint(tmp_path):
    from fastapi.testclient import TestClient
    from web_api import create_app

    (tmp_path / "receipts").mkdir()
    app = create_app(tmp_path, token="t-stream", port=8765)
    client = TestClient(app)
    with client.stream(
        "GET",
        "/api/stream?max=1&interval=0.3",
        headers={"X-Review-Token": "t-stream"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = b"".join(resp.iter_bytes()).decode("utf-8", errors="replace")
    assert "event: hello" in body
    assert "event: live" in body


def test_shot_card_api_from_film_spec(tmp_path):
    from util import write_json
    from web.shot_card_api import get_shot_card, list_shot_cards

    write_json(
        tmp_path / "film-spec.json",
        {
            "schema_version": 1,
            "kind": "film-spec",
            "shots": [
                {
                    "id": "s01",
                    "title": "Door",
                    "dramatic_function": "setup",
                    "action": "opens door",
                    "shot_size": "MCU",
                    "duration_sec": 5,
                }
            ],
        },
    )
    one = get_shot_card(tmp_path, "s01")
    assert one["found"] is True
    assert one["summary"]["id"] == "s01"
    assert one["card"]["kind"] == "ai-film-shot-card"
    missing = get_shot_card(tmp_path, "s99")
    assert missing["found"] is False
    idx = list_shot_cards(tmp_path)
    assert idx["count"] >= 1
    assert idx["items"][0]["id"] == "s01"


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_api_shot_card_endpoint(tmp_path):
    from fastapi.testclient import TestClient
    from util import write_json
    from web_api import create_app

    write_json(
        tmp_path / "film-spec.json",
        {
            "schema_version": 1,
            "kind": "film-spec",
            "shots": [{"id": "s01", "title": "Hi", "dramatic_function": "setup"}],
        },
    )
    app = create_app(tmp_path, token="t-card", port=8766)
    client = TestClient(app)
    r = client.get("/api/shot-card?shot=s01", headers={"X-Review-Token": "t-card"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["summary"]["id"] == "s01"
    r2 = client.get("/api/shot-card", headers={"X-Review-Token": "t-card"})
    assert r2.status_code == 200
    assert r2.json()["kind"] == "shot-card-index"
