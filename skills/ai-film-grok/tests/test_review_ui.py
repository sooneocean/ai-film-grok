from __future__ import annotations

import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from review_ui import (
    _PAGE,  # noqa: E402
    make_handler,  # noqa: E402
)


def _server(root: Path):
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, "test-token"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _request(
    server, method: str, path: str, *, body: dict | None = None, token: str = "test-token"
):
    headers = {"X-Review-Token": token}
    if body is not None:
        headers.update(
            {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"}
        )
    connection = HTTPConnection("127.0.0.1", server.server_port)
    connection.request(
        method, path, body=json.dumps(body) if body is not None else None, headers=headers
    )
    response = connection.getresponse()
    payload = response.read()
    connection.close()
    return response.status, payload


def test_status_rejects_bad_token_and_action_rejects_cross_origin(tmp_path: Path) -> None:
    (tmp_path / "receipts").mkdir()
    (tmp_path / "drama-graph.json").write_text('{"scenes": []}', encoding="utf-8")
    (tmp_path / "film-spec.json").write_text('{"scenes": []}', encoding="utf-8")
    server = _server(tmp_path)
    try:
        status, _ = _request(server, "GET", "/api/status", token="wrong")
        assert status == 401
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "POST",
            "/api/advance",
            body="{}",
            headers={
                "X-Review-Token": "test-token",
                "Origin": "http://evil.example",
                "Content-Type": "application/json",
            },
        )
        assert connection.getresponse().status == 403
        connection.close()
    finally:
        server.shutdown()
        server.server_close()


def test_media_range_and_workspace_escape_are_handled(tmp_path: Path) -> None:
    (tmp_path / "receipts").mkdir()
    (tmp_path / "sample.mp4").write_bytes(b"abcdef")
    server = _server(tmp_path)
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "GET",
            "/media/sample.mp4",
            headers={"X-Review-Token": "test-token", "Range": "bytes=1-3"},
        )
        response = connection.getresponse()
        assert response.status == 206 and response.read() == b"bcd"
        assert response.getheader("Cache-Control") == "no-store"
        assert response.getheader("X-Content-Type-Options") == "nosniff"
        connection.close()
        status, _ = _request(server, "GET", "/media/../../etc/passwd")
        assert status == 404
        (tmp_path / "config.env").write_text("FRW_API_KEY=not-for-ui", encoding="utf-8")
        status, _ = _request(server, "GET", "/media/config.env")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_page_exposes_media_preview_and_budget_controls() -> None:
    assert "<video" in _PAGE
    assert "saveSettings" in _PAGE
    assert "budget_envelopes" in _PAGE
    assert "onclick=" not in _PAGE
    assert "data-review-action" in _PAGE
    assert "renderedStages.has(stage)" in _PAGE
    assert "reviewActions.has(action)" in _PAGE
    assert "recent_actions" in _PAGE
    assert "function history(actions)" in _PAGE
    assert "role=status" in _PAGE
    assert "alert(" not in _PAGE
    assert "final-review-form" in _PAGE
    assert "/api/final-review-input" in _PAGE


def test_review_ui_writes_hash_bound_final_review_input(tmp_path: Path) -> None:
    final_sha256 = "a" * 64
    (tmp_path / "receipts").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "review_contract_version": 3,
                "outputs": {"final_film": {"sha256": final_sha256}},
            }
        ),
        encoding="utf-8",
    )
    body = {
        "schema_version": 1,
        "kind": "final-review-input",
        "approve": True,
        "reviewer": "dex",
        "notes": "完整观看并核对。",
        "watched_full": True,
        "final_output_sha256": final_sha256,
        "human_minutes": 2,
        "scorecard": {
            dimension: "pass"
            for dimension in (
                "identity",
                "style",
                "motion",
                "escalation",
                "audio",
                "subs",
                "dead_air",
                "rhythm",
                "emotion",
                "theme",
                "performance",
            )
        },
        "grades": {
            dimension: 4
            for dimension in (
                "identity",
                "style",
                "motion",
                "escalation",
                "audio",
                "subs",
                "dead_air",
                "rhythm",
                "emotion",
                "theme",
                "performance",
            )
        },
        "screening_evidence": {
            dimension: {"timestamp_sec": index + 0.1, "note": "checked"}
            for index, dimension in enumerate(
                (
                    "identity",
                    "style",
                    "motion",
                    "escalation",
                    "audio",
                    "subs",
                    "dead_air",
                    "rhythm",
                    "emotion",
                    "theme",
                    "performance",
                )
            )
        },
        "fail_reasons": {},
        "reshoot_shots": [],
    }
    server = _server(tmp_path)
    try:
        status, payload = _request(server, "POST", "/api/final-review-input", body=body)
    finally:
        server.shutdown()
        server.server_close()

    assert status == 200, payload
    report = json.loads(payload)
    assert report["ok"] is True
    assert Path(report["path"]).is_file()
