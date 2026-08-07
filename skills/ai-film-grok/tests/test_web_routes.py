"""Contract tests for workbench route table (web_routes) + gateway parity."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.console

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from web_routes import (  # noqa: E402
    ROUTES,
    api_route_keys,
    error_body,
    route_keys,
    routes_table,
)


def test_error_body_has_both_keys():
    body = error_body("stale selection")
    assert body["error"] == "stale selection"
    assert body["detail"] == "stale selection"


def test_routes_table_nonempty_and_unique_handler_ids():
    rows = routes_table()
    assert len(rows) >= 15
    ids = [r["handler_id"] for r in rows]
    assert len(ids) == len(set(ids)), "handler_id must be unique"


def test_stdlib_covers_all_shared_api_routes():
    """Every FastAPI API route must also exist on stdlib (stop is stdlib-only)."""
    fa = api_route_keys("fastapi")
    st = api_route_keys("stdlib")
    missing_on_stdlib = fa - st
    assert not missing_on_stdlib, f"API on FastAPI but missing stdlib: {missing_on_stdlib}"


def test_fastapi_covers_review_parity_apis():
    fa = api_route_keys("fastapi")
    required = {
        ("GET", "/api/status"),
        ("GET", "/api/final-review-template"),
        ("POST", "/api/action"),
        ("POST", "/api/settings"),
        ("POST", "/api/advance"),
        ("POST", "/api/final-review-input"),
        ("GET", "/api/gates"),
        ("GET", "/api/assets"),
        ("GET", "/api/console-state"),
        ("GET", "/api/live"),
        ("GET", "/api/events"),
        ("GET", "/api/stream"),
        ("GET", "/api/takes"),
        ("POST", "/api/takes/review"),
        ("POST", "/api/select"),
        ("GET", "/api/onboarding"),
    }
    missing = required - fa
    assert not missing, f"FastAPI missing review/selection APIs: {missing}"


def test_stop_is_stdlib_only():
    st = route_keys("stdlib")
    fa = route_keys("fastapi")
    assert ("POST", "/api/stop") in st
    assert ("POST", "/api/stop") not in fa


def test_loopback_flag_on_state_changing_posts():
    for r in ROUTES:
        if r.method.upper() == "POST" and r.path.startswith("/api/") and r.path != "/api/stop":
            # all workbench POSTs that mutate must require loopback on both gateways
            if r.fastapi or r.stdlib:
                assert r.loopback, f"{r.path} should require loopback Origin"


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_fastapi_app_registers_contract_api_paths(tmp_path):
    from web_api import create_app

    app = create_app(tmp_path, "contract-token", 56159)
    # Collect openapi paths+methods
    openapi = app.openapi()
    registered: set[tuple[str, str]] = set()
    for path, methods in openapi.get("paths", {}).items():
        for method in methods:
            if method.upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                # Normalize path params: FastAPI uses {rest_of_path}, contract uses {path}
                norm = path.replace("{rest_of_path}", "{path}")
                registered.add((method.upper(), norm))

    expected = api_route_keys("fastapi")
    # openapi may not list all if create_app failed mid-way; compare carefully
    missing = expected - registered
    # /api/file is GET with query — should be present
    assert not missing, f"FastAPI app missing contract routes: {missing}"


def test_asset_picker_kinds_include_scene_prop():
    import asset_picker

    assert "scene" in asset_picker.VALID_KINDS
    assert "prop" in asset_picker.VALID_KINDS
    assert "bgm" in asset_picker.VALID_KINDS


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_fastapi_assets_accepts_scene_kind(tmp_path):
    from fastapi.testclient import TestClient
    from web_api import create_app

    client = TestClient(create_app(tmp_path, "tok", 56160))
    r = client.get("/api/assets?kind=scene", headers={"X-Review-Token": "tok"})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "scene"


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_fastapi_error_body_has_error_and_detail(tmp_path):
    from fastapi.testclient import TestClient
    from web_api import create_app

    client = TestClient(create_app(tmp_path, "tok", 56161))
    r = client.get("/api/gates")  # no token
    assert r.status_code == 401
    body = r.json()
    assert body.get("error") == "invalid session token"
    assert body.get("detail") == "invalid session token"


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_fastapi_review_status_endpoint(tmp_path):
    from fastapi.testclient import TestClient
    from web_api import create_app

    (tmp_path / "receipts").mkdir(exist_ok=True)
    client = TestClient(create_app(tmp_path, "tok", 56162))
    r = client.get("/api/status", headers={"X-Review-Token": "tok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "queue" in body and "settings" in body
