from __future__ import annotations

import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from review_ui import make_handler  # noqa: E402


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
        connection.close()
        status, _ = _request(server, "GET", "/media/../../etc/passwd")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
