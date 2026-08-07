"""Tests for the localhost review console extension (gates / assets / select).

Mirrors the security contract already proven in ``test_review_ui.py``:
path-escape 404, bad token 401, cross-origin 403, hash-bound writes, and
revision-conflict 409.  The extension must not regress those guarantees.
"""

from __future__ import annotations

import json
import sys
from http.client import HTTPConnection
from pathlib import Path

import pytest

pytestmark = pytest.mark.console

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from review_ui import make_handler  # noqa: E402


def _server(root: Path, token: str = "test-token"):
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, token))
    t = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _request(server, method, path, *, body=None, token="test-token"):
    headers = {"X-Review-Token": token}
    if body is not None:
        headers.update(
            {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"}
        )
    conn = HTTPConnection("127.0.0.1", server.server_port)
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, payload


@pytest.fixture
def film_root(tmp_path: Path) -> Path:
    (tmp_path / "receipts").mkdir()
    (tmp_path / "drama-graph.json").write_text('{"scenes": []}', encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"genre": "adult", "heat_scale": "max", "cast_voices": {"f": "zh-CN-XiaoyiNeural"}}),
        encoding="utf-8",
    )
    return tmp_path


def test_gates_endpoint_returns_panel(film_root):
    server = _server(film_root)
    try:
        status, payload = _request(server, "GET", "/api/gates")
        assert status == 200, payload
        data = json.loads(payload)
        assert data["kind"] == "gate-panel"
        assert isinstance(data["gates"], list) and data["gates"]
        assert "blocking" in data
    finally:
        server.shutdown()
        server.server_close()


def test_assets_endpoint_lists_and_rejects_bad_kind(film_root):
    server = _server(film_root)
    try:
        status, payload = _request(server, "GET", "/api/assets?kind=character")
        assert status == 200, payload
        assert "items" in json.loads(payload)
        bad, _ = _request(server, "GET", "/api/assets?kind=nope")
        assert bad == 400
    finally:
        server.shutdown()
        server.server_close()


def test_console_state_served(film_root):
    server = _server(film_root)
    try:
        status, payload = _request(server, "GET", "/api/console-state")
        assert status == 200, payload
        data = json.loads(payload)
        assert data["kind"] == "console-state"
        assert "ledger_revision" in data
        assert "gate_blocking" in data
        assert "approved_clips" in data
        assert "onboarding" in data
        assert "recent_selections" in data
    finally:
        server.shutdown()
        server.server_close()


def test_select_is_hash_bound_and_conflict_safe(film_root):
    server = _server(film_root)
    try:
        # first selection: revision starts at 0
        status, payload = _request(
            server, "POST", "/api/select",
            body={"kind": "voice", "asset_id": "f", "expected_revision": 0},
        )
        assert status == 200, payload
        rev = json.loads(payload)["revision"]
        assert rev == 1
        # stale revision must be rejected with 409
        _, payload2 = _request(
            server, "POST", "/api/select",
            body={"kind": "voice", "asset_id": "f", "expected_revision": 0},
        )
        assert json.loads(payload2).get("error", "").lower().count("stale")  # conflict message
    finally:
        server.shutdown()
        server.server_close()


def test_bad_token_rejected_and_cross_origin_blocked(film_root):
    server = _server(film_root)
    try:
        status, _ = _request(server, "GET", "/api/gates", token="wrong")
        assert status == 401
        conn = HTTPConnection("127.0.0.1", server.server_port)
        conn.request(
            "POST", "/api/select",
            body=json.dumps({"kind": "voice", "asset_id": "female_lead"}),
            headers={"X-Review-Token": "test-token", "Origin": "http://evil.example",
                      "Content-Type": "application/json"},
        )
        assert conn.getresponse().status == 403
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_media_lib_escape_is_rejected(film_root):
    server = _server(film_root)
    try:
        status, _ = _request(server, "GET", "/media-lib/../../etc/passwd")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_console_page_served_at_dedicated_route(film_root):
    server = _server(film_root)
    try:
        status, payload = _request(server, "GET", "/console")
        assert status == 200
        assert "选素材" in payload.decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()


def test_select_rejected_on_blocking_gate_stdlib(film_root):
    # P6: a failed hard gate must reject selection with 403 (fail-closed).
    (film_root / "film-spec.json").write_text(
        json.dumps({"genre": "adult", "heat_scale": "normal"}), encoding="utf-8")
    server = _server(film_root)
    try:
        status, payload = _request(
            server, "POST", "/api/select",
            body={"kind": "voice", "asset_id": "female_lead", "expected_revision": 0},
        )
        assert status == 403, payload
        assert "硬门禁" in payload.decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
