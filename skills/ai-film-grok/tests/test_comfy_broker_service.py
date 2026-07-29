from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _service():
    pytest.importorskip("fastapi")
    return importlib.import_module("comfy_broker_service")


@pytest.fixture(autouse=True)
def _broker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("AIFILM_COMFY_BROKER_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AIFILM_COMFY_BROKER_TOKEN", "t" * 32)
    monkeypatch.setenv("AIFILM_COMFY_BROKER_WEAPON_IDS", "fantasy-talking-6step-pilot")


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer " + "t" * 32}


def test_broker_requires_auth_before_exposing_health() -> None:
    from fastapi.testclient import TestClient

    service = _service()
    assert TestClient(service.app).get("/health").status_code == 401


def test_broker_denies_global_interrupt_and_free() -> None:
    from fastapi.testclient import TestClient

    service = _service()
    client = TestClient(service.app)
    assert client.post("/interrupt", headers=_headers()).status_code == 403
    assert client.post("/free", headers=_headers()).status_code == 403
    assert client.post("/queue", headers=_headers(), json={"delete": ["x"]}).status_code == 403


def test_broker_requires_registered_weapon_and_matching_workflow_hash() -> None:
    from fastapi.testclient import TestClient

    service = _service()
    graph = {"1": {"class_type": "LoadImage", "inputs": {"image": "x.png"}}}
    payload = {"client_id": "aifilm-test", "prompt": graph}
    checksum = hashlib.sha256(
        json.dumps(graph, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with patch.object(service, "_proxy", return_value=service.Response(content=b"{}")) as proxy:
        client = TestClient(service.app)
        denied = client.post("/prompt", headers=_headers(), json=payload)
        assert denied.status_code == 403
        mismatch = client.post(
            "/prompt",
            headers={
                **_headers(),
                "X-AIFilm-Weapon-ID": "fantasy-talking-6step-pilot",
                "X-AIFilm-Workflow-SHA256": "0" * 64,
            },
            json=payload,
        )
        assert mismatch.status_code == 400
        accepted = client.post(
            "/prompt",
            headers={
                **_headers(),
                "X-AIFilm-Weapon-ID": "fantasy-talking-6step-pilot",
                "X-AIFilm-Workflow-SHA256": checksum,
            },
            json=payload,
        )
    assert accepted.status_code == 200
    assert proxy.call_args.args[:2] == ("POST", "/prompt")


def test_broker_allows_only_explicit_read_paths() -> None:
    from fastapi.testclient import TestClient

    service = _service()
    with patch.object(service, "_proxy", return_value=service.Response(content=b"{}")) as proxy:
        client = TestClient(service.app)
        assert client.get("/system_stats", headers=_headers()).status_code == 200
        assert client.get("/workflow", headers=_headers()).status_code == 403
    assert proxy.call_args.args[:2] == ("GET", "/system_stats")
