from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _service():
    pytest.importorskip("fastapi")
    return importlib.import_module("lipsync_node_service")


def test_backend_ready_requires_measured_clean_checkout_and_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    monkeypatch.setenv(
        "AIFILM_LIPSYNC_NODE_LATENTSYNC_ARGV",
        '["trusted-adapter","--video","{video_wsl}","--audio","{audio_wsl}","--out","{out_wsl}"]',
    )
    monkeypatch.delenv("AIFILM_LIPSYNC_NODE_LATENTSYNC_CHECKPOINT_SHA256", raising=False)
    assert not service._backend_info("latentsync")["ready"]
    monkeypatch.setenv("AIFILM_LIPSYNC_NODE_LATENTSYNC_CHECKPOINT_SHA256", "a" * 64)
    monkeypatch.setenv("AIFILM_LIPSYNC_NODE_LATENTSYNC_REPO_COMMIT", "b" * 40)
    monkeypatch.setenv("AIFILM_LIPSYNC_NODE_LATENTSYNC_PROBE_ARGV", '["trusted-probe"]')
    monkeypatch.setattr(
        service,
        "_measure_backend",
        lambda _argv, force=False: {
            "checkpoint_sha256": "a" * 64,
            "repo_commit": "b" * 40,
            "repo_dirty": False,
            "gpu": "RTX 5090",
            "pytorch": "2.7.1",
            "cuda": "12.8",
        },
    )
    measured = service._backend_info("latentsync")
    assert measured["technical_ready"]
    assert not measured["ready"]
    monkeypatch.setenv("AIFILM_LIPSYNC_NODE_LATENTSYNC_APPROVED", "1")
    assert service._backend_info("latentsync")["ready"]


def test_only_technical_failures_may_fallback() -> None:
    service = _service()
    assert service._may_fallback("technical")
    assert not service._may_fallback("quality_rejected")
    assert not service._may_fallback("unknown")


def test_execute_records_fallback_and_hash_bound_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = _service()
    jobs_root = tmp_path / "jobs"
    job_id = "job"
    job_dir = jobs_root / job_id
    job_dir.mkdir(parents=True)
    video = job_dir / "input.mp4"
    audio = job_dir / "input.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    monkeypatch.setattr(service, "JOBS_ROOT", jobs_root)
    monkeypatch.setattr(
        service,
        "jobs",
        {
            job_id: {
                "job_id": job_id,
                "status": "queued",
                "requested_backend": "latentsync",
                "fallback_backend": "musetalk",
                "video_path": str(video),
                "audio_path": str(audio),
                "input_video_sha256": hashlib.sha256(b"video").hexdigest(),
                "input_audio_sha256": hashlib.sha256(b"audio").hexdigest(),
                "parameters": {"inference_steps": 20, "guidance_scale": 1.5, "deepcache": True},
            }
        },
    )

    def fake_run(backend: str, *_args, **_kwargs):
        if backend == "latentsync":
            raise service.BackendExecutionError("technical", "CUDA launch failed")
        output = job_dir / "candidate.mp4"
        output.write_bytes(b"\x00\x00\x00\x18ftypmp42fallback")
        return output, {"wall_time_sec": 1.2, "peak_vram_mib": 1234}

    monkeypatch.setattr(service, "_run_backend", fake_run)
    monkeypatch.setattr(
        service,
        "_probe_mp4",
        lambda _path: {"duration": 4.0, "fps": 25.0, "video_codec": "h264"},
    )
    monkeypatch.setattr(
        service,
        "_backend_info",
        lambda backend: {
            "ready": True,
            "technical_ready": True,
            "backend": backend,
            "model": f"{backend}-model",
            "checkpoint_sha256": ("a" if backend == "latentsync" else "b") * 64,
            "repo_commit": "c" * 40,
        },
    )

    asyncio.run(service._execute(job_id))
    state = service.jobs[job_id]

    assert state["status"] == "completed"
    assert state["chosen_backend"] == "musetalk"
    assert state["fallback_reason"]["failure_class"] == "technical"
    assert len(state["output_sha256"]) == 64
    assert "video_path" not in service._public_job(state)
    assert "audio_path" not in json.dumps(service._public_job(state))


def test_private_service_exposes_no_schema_routes() -> None:
    service = _service()
    assert service.app.openapi_url is None
    assert service.app.docs_url is None
    assert service.app.redoc_url is None


def test_completed_job_is_restored_from_disk_after_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = _service()
    job_id = "a" * 32
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    artifact = job_dir / "artifact.mp4"
    artifact.write_bytes(b"\x00\x00\x00\x18ftypmp42restored")
    receipt = {
        "job_id": job_id,
        "status": "completed",
        "output_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }
    (job_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(service, "JOBS_ROOT", tmp_path)
    monkeypatch.setattr(service, "jobs", {})

    restored = service._load_job(job_id)

    assert restored is not None
    assert restored["status"] == "completed"
    assert restored["artifact_path"] == str(artifact)


def test_interrupted_job_is_failed_closed_after_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = _service()
    job_id = "b" * 32
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    (job_dir / "receipt.json").write_text(
        json.dumps({"job_id": job_id, "status": "running"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "JOBS_ROOT", tmp_path)
    monkeypatch.setattr(service, "jobs", {})

    restored = service._load_job(job_id)

    assert restored is not None
    assert restored["status"] == "failed"
    assert restored["failure"]["failure_class"] == "technical"


def test_auth_rejects_before_multipart_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    service = _service()
    monkeypatch.setenv("AIFILM_LIPSYNC_NODE_TOKEN", "x" * 32)
    response = TestClient(service.app).post(
        "/v1/lipsync/jobs",
        content=b"not multipart",
        headers={"Content-Length": "13"},
    )
    assert response.status_code == 401
