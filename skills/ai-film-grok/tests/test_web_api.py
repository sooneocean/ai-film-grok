"""Tests for the FastAPI review-console gateway (``web_api``).

The framework is an optional dependency: skip the whole module if FastAPI /
uvicorn are not importable so ``make check-all`` never breaks on environments
that only run the stdlib server.
"""
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.console

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from fastapi.testclient import TestClient  # noqa: E402
from web_api import create_app  # noqa: E402

TOKEN = "unit-test-gateway-token"
PORT = 56158


@pytest.fixture
def client(tmp_path):
    (tmp_path / "receipts").mkdir(exist_ok=True)
    app = create_app(tmp_path, TOKEN, PORT)
    return TestClient(app)


def test_gates_endpoint_requires_auth(client):
    assert client.get("/api/gates").status_code == 401
    r = client.get("/api/gates", headers={"X-Review-Token": TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "gate-panel"
    assert "gates" in body and "blocking" in body


def test_assets_endpoint_lists_and_rejects_bad_kind(client):
    r = client.get("/api/assets?kind=bgm", headers={"X-Review-Token": TOKEN})
    assert r.status_code == 200
    assert r.json()["kind"] == "bgm"
    bad = client.get("/api/assets?kind=bogus", headers={"X-Review-Token": TOKEN})
    assert bad.status_code == 400


def test_console_state_served_gateway(client):
    r = client.get("/api/console-state", headers={"X-Review-Token": TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "console-state"
    assert "ledger_revision" in body
    assert "gate_blocking" in body
    assert "approved_clips" in body
    assert "onboarding" in body
    assert "recent_selections" in body


def test_select_is_hash_bound_and_conflict_safe(client):
    url = "/api/select"
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    # voice kind falls back to the documented Chinese pool in an empty root.
    r1 = client.post(
        url, headers=headers,
        json={"kind": "voice", "asset_id": "female_lead", "expected_revision": 0},
    )
    assert r1.status_code == 200, r1.text
    rev = r1.json()["revision"]
    # a stale tab holding the old revision must be rejected with 409.
    stale = client.post(
        url, headers=headers,
        json={"kind": "voice", "asset_id": "male_lead", "expected_revision": 0},
    )
    assert stale.status_code == 409, stale.text
    # a fresh tab holding the current revision proceeds.
    fresh = client.post(
        url, headers=headers,
        json={"kind": "voice", "asset_id": "male_lead", "expected_revision": rev},
    )
    assert fresh.status_code == 200, fresh.text


def test_shot_select_binds_manifest_via_gateway(client, tmp_path):
    url = "/api/select"
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    r = client.post(
        url, headers=headers,
        json={"kind": "shot", "asset_id": "s1", "expected_revision": 0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # P5: shot approval is the only kind that writes the production manifest
    assert body["manifest_binding"]["bound"] is True
    assert body["manifest_binding"]["shot_id"] == "s1"
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["clips"]["s1"]["status"] == "approved"


def test_cross_origin_post_rejected(client):
    headers = {"X-Review-Token": TOKEN, "Origin": "http://evil.example.com"}
    r = client.post(
        "/api/select", headers=headers,
        json={"kind": "voice", "asset_id": "female_lead"},
    )
    assert r.status_code == 403


def test_media_path_escape_rejected(client):
    r = client.get("/media-lib/..%2f..%2fetc%2fpasswd", headers={"X-Review-Token": TOKEN})
    assert r.status_code == 404


def test_console_page_served_with_token(client):
    r = client.get("/?token=" + TOKEN)
    assert r.status_code == 200
    assert "选素材" in r.text


# ---- onboarding wizard (references -> story -> characters -> go) ----
def test_onboarding_state_requires_auth(client):
    assert client.get("/api/onboarding").status_code == 401
    assert client.get(f"/api/onboarding?token={TOKEN}").status_code == 200


def test_onboarding_step_cross_origin_rejected(client):
    headers = {"X-Review-Token": TOKEN, "Origin": "http://evil.example.com"}
    r = client.post(
        "/api/onboarding/step", headers=headers,
        json={"step": "references", "payload": {"items": [{"url": "x"}]}},
    )
    assert r.status_code == 403


def test_onboarding_step_bad_kind(client):
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    r = client.post(
        "/api/onboarding/step", headers=headers,
        json={"step": "bogus", "payload": {}},
    )
    assert r.status_code == 400


def test_onboarding_step_and_go(client, monkeypatch):
    monkeypatch.setattr("onboarding._try_advance", lambda base: (True, "advanced: ok"))
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}

    assert client.post(
        "/api/onboarding/step", headers=headers,
        json={"step": "references", "payload": {"items": [{"url": "http://x/a.png", "note": "mood"}]}},
    ).status_code == 200
    assert client.post(
        "/api/onboarding/step", headers=headers,
        json={"step": "story", "payload": {"text": "故事文本"}},
    ).status_code == 200
    assert client.post(
        "/api/onboarding/step", headers=headers,
        json={"step": "characters", "payload": {"items": [{"id": "hero", "name": "阿强"}]}},
    ).status_code == 200

    r = client.post("/api/onboarding/go", headers=headers, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["advanced"] is True

    # canonical files written into the app's root (the fixture tmp_path)
    from pathlib import Path as _P

    root = client.app.state.root
    assert (_P(root) / "references.json").is_file()
    assert (_P(root) / "intake-manifest.json").is_file()


def test_onboarding_go_incomplete(client, monkeypatch):
    monkeypatch.setattr("onboarding._try_advance", lambda base: (False, "skip"))
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    r = client.post("/api/onboarding/go", headers=headers, json={})
    assert r.status_code == 400


def test_select_rejected_on_blocking_gate_gateway(client, tmp_path):
    # P6: a hard (required) gate failure must reject selection with 403 at the
    # gateway layer and must NOT write the ledger or the production manifest.
    root = Path(client.app.state.root)
    (root / "film-spec.json").write_text(
        json.dumps({"genre": "adult", "heat_scale": "normal"}), encoding="utf-8"
    )
    url = "/api/select"
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    r = client.post(
        url, headers=headers,
        json={"kind": "shot", "asset_id": "s1", "expected_revision": 0},
    )
    assert r.status_code == 403, r.text
    assert "硬门禁" in r.text
    # neither the ledger nor the production manifest may be created.
    assert not (root / "selection-ledger.json").is_file()
    assert not (root / "manifest.json").is_file()

