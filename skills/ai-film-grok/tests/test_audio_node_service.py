from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect

import pytest


def test_create_endpoint_runs_in_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)
    monkeypatch.setattr(
        service, "_create", lambda kind, payload: {"job_id": "job", "status": "queued"}
    )

    assert inspect.iscoroutinefunction(service.create)
    result = asyncio.run(service.create("tts", {"text": "test"}, f"Bearer {'t' * 32}"))

    assert result == {"job_id": "job", "status": "queued"}


def test_health_reports_capacity_without_private_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)
    monkeypatch.setattr(
        service,
        "_gpu_health",
        lambda: {"available": True, "free_vram_mib": 1024, "total_vram_mib": 2048},
    )

    report = service.health(f"Bearer {'t' * 32}")

    assert report["gpu"] == {"available": True, "free_vram_mib": 1024, "total_vram_mib": 2048}
    assert "token" not in report


def test_performance_adapter_is_reported_only_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.delenv("AIFILM_AUDIO_NODE_PERFORMANCE_ARGV", raising=False)
    assert not service._available("performance")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_PERFORMANCE_ARGV", '["trusted-adapter"]')
    assert service._available("performance")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_PERFORMANCE_ARGV", "not-json")
    assert not service._available("performance")


def test_private_service_exposes_no_schema_or_documentation_routes() -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")

    assert service.app.openapi_url is None
    assert service.app.docs_url is None
    assert service.app.redoc_url is None


def test_execute_creates_jobs_directory_before_tts_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    jobs_dir = tmp_path / "jobs-missing"
    monkeypatch.setattr(service, "JOBS", jobs_dir)
    monkeypatch.setattr(service, "jobs", {"job": {"status": "queued"}})

    def fake_tts(_payload, output):
        output.write_bytes(b"candidate")

    monkeypatch.setattr(service, "_run_tts", fake_tts)
    asyncio.run(service._execute("job", "tts", {"text": "test"}))

    state = service.jobs["job"]
    assert state["status"] == "completed"
    assert state["sha256"] == hashlib.sha256(b"candidate").hexdigest()


def test_execute_discards_partial_audio_when_generation_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "JOBS", tmp_path / "jobs")
    monkeypatch.setattr(service, "jobs", {"job": {"status": "queued"}})

    def fake_tts(_payload, output):
        output.write_bytes(b"partial")
        raise RuntimeError("generation failed")

    monkeypatch.setattr(service, "_run_tts", fake_tts)
    asyncio.run(service._execute("job", "tts", {"text": "test"}))

    assert service.jobs["job"]["status"] == "failed"
    assert not (tmp_path / "jobs" / "job.wav").exists()
