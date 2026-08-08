"""Tests for the director 总控台 (studio registry + multi-film serve mode).

Covers both the pure registry module (``studio.py``) and the review-ui studio
API (active-film switching, path-traversal guards) introduced for the director
command center. Mirrors ``test_web_console.py``'s security contract.
"""

from __future__ import annotations

import json
import sys
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.console

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import studio  # noqa: E402
from review_ui import make_handler  # noqa: E402


def _make_film(root: Path, title, theme, clips, gates):
    (root / "receipts").mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "title": title,
        "theme": theme,
        "aspect_ratio": "16:9",
        "clips": clips,
        "gates": gates,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def studio_dir(tmp_path: Path) -> Path:
    base = tmp_path / "studio"
    base.mkdir()
    _make_film(
        base / "film-a",
        "雨夜书店",
        "甜宠",
        {"s1": {"status": "approved"}, "s2": {"status": "generating"}},
        {"brief": True, "safety": True, "identity": False},
    )
    _make_film(base / "film-b", "孤岛余生", "悬疑", {}, {"brief": True})
    return base


# ---- pure registry module ----


def test_discover_films_finds_roots(studio_dir):
    films = studio.discover_films(studio_dir)
    assert {f.name for f in films} == {"film-a", "film-b"}


def test_summarize_film_progress_and_status(studio_dir):
    s = studio.summarize_film(studio_dir / "film-a")
    assert s["title"] == "雨夜书店"
    assert s["status"] == "producing"
    assert s["clips_approved"] == 1 and s["clips_total"] == 2
    assert 0 <= s["progress"] <= 100
    assert s["genre"] == "甜宠"


def test_build_studio_merges_categories_and_counts(studio_dir):
    d = studio.build_studio(studio_dir)
    assert d["film_count"] == 2
    assert d["categories"] == {"甜宠": 1, "悬疑": 1}
    assert d["status_counts"]["producing"] == 1
    assert d["status_counts"]["draft"] == 1
    assert d["active_film_id"] == d["films"][0]["id"]


def test_load_released_empty_when_no_catalog(tmp_path):
    # missing catalog -> [] (best-effort, never raises)
    assert studio.load_released(tmp_path / "nope.json") == []


def test_single_film_view_shape(studio_dir):
    sv = studio.single_film_view(studio_dir / "film-a")
    assert sv["studio_mode"] is False
    assert sv["film_count"] == 1
    assert sv["films"][0]["id"] == "film-a"


# ---- in-process studio API (active-film switching + guards) ----


def _server_studio(studio_dir: Path, token: str = "t"):
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(studio_dir, token))
    server.studio_dir = studio_dir.resolve()
    server.active_film = studio.discover_films(studio_dir)[0]
    t = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _request(server, method, path, *, body=None, token="t"):
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


def test_studio_api_lists_films(studio_dir):
    server = _server_studio(studio_dir)
    try:
        st, p = _request(server, "GET", "/api/studio")
        assert st == 200, p
        d = json.loads(p)
        assert d["studio_mode"] is True
        assert d["film_count"] == 2
        assert d["active_film_id"] == "film-a"
    finally:
        server.shutdown()
        server.server_close()


def test_studio_detail_and_select(studio_dir):
    server = _server_studio(studio_dir)
    try:
        st, p = _request(server, "GET", "/api/studio/film-a")
        assert st == 200 and json.loads(p)["title"] == "雨夜书店"
        st, p = _request(server, "POST", "/api/studio/select", body={"id": "film-b"})
        assert st == 200, p
        assert json.loads(p)["active_film_id"] == "film-b"
        # console-state now reflects the active film + studio mode
        st, p = _request(server, "GET", "/api/console-state")
        cs = json.loads(p)
        assert cs["active_film_id"] == "film-b"
        assert cs["studio_mode"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_studio_select_traversal_and_missing_guards(studio_dir):
    server = _server_studio(studio_dir)
    try:
        # path traversal must be rejected (400), not escape the studio dir
        st, _ = _request(server, "POST", "/api/studio/select", body={"id": "../etc"})
        assert st == 400
        # unknown film -> 404
        st, _ = _request(server, "GET", "/api/studio/nope")
        assert st == 404
    finally:
        server.shutdown()
        server.server_close()


def test_studio_single_mode_shape_and_rejects_select(tmp_path):
    # single-root serve: /api/studio returns a single-film view, /select is 400
    _make_film(tmp_path, "独片", "剧情", {"s1": {"status": "approved"}}, {"brief": True})
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, "t"))
    server.studio_dir = None
    server.active_film = tmp_path
    t = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        st, p = _request(server, "GET", "/api/studio")
        assert st == 200 and json.loads(p)["studio_mode"] is False
        st, _ = _request(server, "POST", "/api/studio/select", body={"id": "x"})
        assert st == 400
    finally:
        server.shutdown()
        server.server_close()


# ---- W0: live aggregation endpoint (reuses project_director_live) ----

ROLLUP_KEYS = {"blocked", "failed", "reviewable", "running", "multi_take", "inbox"}


def test_build_studio_live_shape(studio_dir):
    d = studio.build_studio_live(studio_dir, active_id="film-a")
    assert d["active_film_id"] == "film-a"
    assert len(d["films"]) == 2
    assert {f["id"] for f in d["films"]} == {"film-a", "film-b"}
    for f in d["films"]:
        assert {"id", "title", "live", "attention"} <= set(f)
        assert isinstance(f["attention"], bool)
    assert ROLLUP_KEYS <= set(d["rollup"])
    assert "generated_at" in d


def test_studio_live_endpoint_aggregates(studio_dir):
    server = _server_studio(studio_dir)
    try:
        st, p = _request(server, "GET", "/api/studio/live")
        assert st == 200, p
        d = json.loads(p)
        assert d["studio_mode"] is True
        assert d["active_film_id"] == "film-a"
        assert "generated_at" in d
        assert len(d["films"]) == 2
        for f in d["films"]:
            assert {"id", "title", "live", "attention"} <= set(f)
            assert isinstance(f["attention"], bool)
        assert ROLLUP_KEYS <= set(d["rollup"])
    finally:
        server.shutdown()
        server.server_close()


def test_studio_live_single_mode_returns_empty(tmp_path):
    _make_film(tmp_path, "独片", "剧情", {"s1": {"status": "approved"}}, {"brief": True})
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, "t"))
    server.studio_dir = None
    server.active_film = tmp_path
    t = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        st, p = _request(server, "GET", "/api/studio/live")
        assert st == 200, p
        d = json.loads(p)
        assert d["studio_mode"] is False
        assert d["films"] == []
        assert d["rollup"] == {}
    finally:
        server.shutdown()
        server.server_close()
