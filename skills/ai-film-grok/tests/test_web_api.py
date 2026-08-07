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


# ---- onboarding v2: brief -> upload -> decompose -> plan -> go ----
_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def test_onboarding_brief_saved(client):
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    r = client.post(
        "/api/onboarding/brief", headers=headers,
        json={"story_text": "林晚说：你好。", "hints": ["甜宠"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["brief"]["story_text"] == "林晚说：你好。"


def test_onboarding_upload_and_file_serve(client):
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    r = client.post(
        "/api/upload", headers=headers,
        json={"filename": "lead.png", "data_url": "data:image/png;base64," + _PNG_B64},
    )
    assert r.status_code == 200, r.text
    path = r.json()["path"]
    assert path.startswith("intake/characters/")
    g = client.get("/api/file?path=" + path, headers={"X-Review-Token": TOKEN})
    assert g.status_code == 200
    assert g.headers["content-type"].startswith("image/")


def test_onboarding_file_path_escape_rejected(client):
    r = client.get("/api/file?path=" + "../" * 6 + "etc/passwd", headers={"X-Review-Token": TOKEN})
    assert r.status_code == 404


def test_onboarding_brief_decompose_heuristic(client):
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    r = client.post(
        "/api/onboarding/decompose", headers=headers,
        json={"brief": {"story_text": "林晚说：今晚的雨真大。顾沉道：进来避避吧。", "image_paths": [], "hints": []}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan_source"] == "heuristic"
    names = [c["name"] for c in body["plan"]["characters"]]
    assert "林晚" in names and "顾沉" in names
    assert body["plan"]["genre"] and body["plan"]["heat_scale"]


def test_onboarding_decompose_then_plan_then_go_writes_canonical(client, monkeypatch, tmp_path):
    monkeypatch.setattr("onboarding._try_advance", lambda base: (True, "advanced: ok"))
    monkeypatch.delenv("AIFILM_LOCAL_LLM_BASE_URL", raising=False)
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    story = "林晚说：今晚的雨真大。顾沉道：进来避避吧。"

    d = client.post(
        "/api/onboarding/decompose", headers=headers,
        json={"brief": {"story_text": story, "image_paths": [], "hints": []}},
    )
    assert d.status_code == 200, d.text
    rev = d.json()["revision"]

    # edit the plan (rename the lead) and persist it
    plan = d.json()["plan"]
    plan["title"] = "雨夜书店"
    p = client.post("/api/onboarding/plan", headers=headers, json={"plan": plan, "expected_revision": rev})
    assert p.status_code == 200, p.text
    rev = p.json()["revision"]

    g = client.post("/api/onboarding/go", headers=headers, json={"expected_revision": rev})
    assert g.status_code == 200, g.text
    root = client.app.state.root
    assert (Path(root) / "film-spec.json").is_file()
    spec = json.loads((Path(root) / "film-spec.json").read_text(encoding="utf-8"))
    assert spec["title"] == "雨夜书店"
    assert (Path(root) / "style-bible.json").is_file()
    assert (Path(root) / "intake-manifest.json").is_file()


def test_onboarding_decompose_stale_conflict(client):
    headers = {"X-Review-Token": TOKEN, "Origin": f"http://127.0.0.1:{PORT}"}
    story = "林晚说：你好。"
    first = client.post(
        "/api/onboarding/decompose", headers=headers,
        json={"brief": {"story_text": story, "image_paths": [], "hints": []}},
    )
    assert first.status_code == 200
    stale = client.post(
        "/api/onboarding/decompose", headers=headers,
        json={"brief": {"story_text": story, "image_paths": [], "hints": []}, "expected_revision": 0},
    )
    assert stale.status_code == 409, stale.text


def test_onboarding_new_endpoints_require_auth(client):
    headers = {"Origin": f"http://127.0.0.1:{PORT}"}
    assert client.post("/api/upload", headers=headers, json={"filename": "x.png", "data_url": "data:image/png;base64,xx"}).status_code == 401
    assert client.post("/api/onboarding/brief", headers=headers, json={"story_text": "x"}).status_code == 401
    assert client.post("/api/onboarding/decompose", headers=headers, json={}).status_code == 401
    assert client.post("/api/onboarding/plan", headers=headers, json={"plan": {}}).status_code == 401


def test_onboarding_new_endpoints_cross_origin_rejected(client):
    headers = {"X-Review-Token": TOKEN, "Origin": "http://evil.example.com"}
    assert client.post("/api/upload", headers=headers, json={"filename": "x.png", "data_url": "data:image/png;base64,xx"}).status_code == 403
    assert client.post("/api/onboarding/decompose", headers=headers, json={"brief": {"story_text": "x"}}).status_code == 403
    assert client.post("/api/onboarding/plan", headers=headers, json={"plan": {}}).status_code == 403


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

