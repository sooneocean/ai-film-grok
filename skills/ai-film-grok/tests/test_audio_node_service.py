from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import io
import json
import subprocess
import wave
from pathlib import Path

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
        lambda: {
            "available": True,
            "driver": "580.12",
            "free_vram_mib": 1024,
            "total_vram_mib": 2048,
        },
    )

    report = service.health(f"Bearer {'t' * 32}")

    assert report["gpu"] == {
        "available": True,
        "driver": "580.12",
        "free_vram_mib": 1024,
        "total_vram_mib": 2048,
    }
    assert "token" not in report
    assert isinstance(report["tts_variants"]["voice_design"], bool)
    assert report["tts_variants"]["custom_1_7b"] is False


def test_health_identifies_the_configured_performance_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)
    monkeypatch.setattr(service, "PERFORMANCE_MODEL_ID", "bosonai/higgs-audio-v2-generation")

    report = service.health(f"Bearer {'t' * 32}")

    assert report["performance_model"] == "bosonai/higgs-audio-v2-generation"


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


def test_music_batch_validates_size_and_fixed_seeds(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)
    monkeypatch.setenv("AIFILM_AUDIO_NODE_MUSIC_BATCH_ARGV", '["trusted-batch-adapter"]')

    with pytest.raises(Exception, match="batch_size"):
        asyncio.run(
            service.create_music_batch(
                {"prompt": "instrumental", "batch_size": 9, "seeds": list(range(9))},
                f"Bearer {'t' * 32}",
            )
        )
    with pytest.raises(Exception, match="seeds"):
        asyncio.run(
            service.create_music_batch(
                {"prompt": "instrumental", "batch_size": 2, "seeds": [1]},
                f"Bearer {'t' * 32}",
            )
        )


def test_execute_music_batch_records_only_sanitized_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "JOBS", tmp_path / "jobs")
    monkeypatch.setattr(
        service,
        "jobs",
        {"batch": {"status": "queued", "kind": "music-batch", "node": "private-lan"}},
    )

    def fake_batch(_payload, output):
        output.mkdir(parents=True)
        paths = []
        for index in range(2):
            path = output / f"{index}.wav"
            path.write_bytes(f"candidate-{index}".encode())
            paths.append(path)
        return paths

    monkeypatch.setattr(service, "_run_music_batch", fake_batch)
    asyncio.run(
        service._execute_music_batch(
            "batch", {"prompt": "private prompt", "batch_size": 2, "seeds": [11, 12]}
        )
    )

    state = service.jobs["batch"]
    assert state["status"] == "completed"
    assert [item["seed"] for item in state["artifacts"]] == [11, 12]
    assert "prompt" not in state
    assert "path" not in state["artifacts"][0]


def test_reference_upload_is_hash_named_and_batch_resolves_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    references = tmp_path / "refs"
    monkeypatch.setattr(service, "REFERENCES", references)
    monkeypatch.setattr(service, "TOKEN", "t" * 32)
    monkeypatch.setenv("AIFILM_AUDIO_NODE_MUSIC_BATCH_ARGV", '["trusted-batch-adapter"]')
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\0\0\0\0" * 4410)
    raw = buffer.getvalue()

    receipt = service._store_music_reference(raw)
    reference_id = receipt["reference_id"]
    assert (references / f"{reference_id}.wav").is_file()

    monkeypatch.setattr(asyncio, "create_task", lambda coroutine: coroutine.close())
    result = asyncio.run(
        service.create_music_batch(
            {
                "prompt": "abstract reusable recipe",
                "duration": 30,
                "batch_size": 1,
                "seeds": [9],
                "task_type": "cover",
                "reference_audio_id": reference_id,
            },
            f"Bearer {'t' * 32}",
        )
    )
    assert result["status"] == "queued"
    assert service.jobs[result["job_id"]]["status"] == "queued"


def test_sfx_health_rejects_missing_probe_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "SFX_MODEL_ID", "hkchengrex/MMAudio-large-44k-v2")
    monkeypatch.setattr(service, "SFX_LICENSE", "CC-BY-NC-4.0")
    monkeypatch.setattr(service, "SFX_CHECKPOINT_FINGERPRINT", "a" * 64)
    monkeypatch.setattr(service, "MMAUDIO_CHECKPOINT_SHA256", "a" * 64)
    monkeypatch.setattr(service, "MMAUDIO_REPO_COMMIT", "b" * 40)
    monkeypatch.setenv("AIFILM_AUDIO_NODE_SFX_ARGV", '["trusted-render-adapter"]')
    monkeypatch.setenv("AIFILM_AUDIO_NODE_SFX_PROBE_ARGV", '["missing-mmaudio-probe"]')
    assert service._available("sfx") is False


def test_sfx_health_requires_render_adapter_even_after_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.delenv("AIFILM_AUDIO_NODE_SFX_ARGV", raising=False)
    monkeypatch.setattr(service, "_sfx_probe_ok", lambda: True)
    assert service._available("sfx") is False


def test_sfx_health_rejects_missing_render_executable_even_after_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_SFX_ARGV", '["missing-render-adapter"]')
    monkeypatch.setattr(service, "_sfx_probe_ok", lambda: True)
    monkeypatch.setattr(service.shutil, "which", lambda _executable: None)

    assert service._available("sfx") is False


def test_reference_upload_rejects_wrong_delivery_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "REFERENCES", tmp_path / "refs")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\0\0" * 4410)
    with pytest.raises(Exception, match="44.1kHz"):
        service._store_music_reference(buffer.getvalue())


def test_sfx_source_upload_is_hash_named_and_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "SFX_SOURCES", tmp_path / "sfx-sources")
    raw = b"video" * 512
    probe = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout='{"streams":[{"codec_type":"video"}],"format":{"duration":"8.0"}}',
        stderr="",
    )
    monkeypatch.setattr(service.subprocess, "run", lambda *args, **kwargs: probe)

    receipt = service._store_sfx_source(raw)

    source_hash = hashlib.sha256(raw).hexdigest()
    assert receipt == {"source_id": source_hash, "source_sha256": source_hash}
    assert (tmp_path / "sfx-sources" / f"{source_hash}.mp4").is_file()


def test_sfx_source_upload_rejects_poisoned_existing_hash_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    sources = tmp_path / "sfx-sources"
    sources.mkdir()
    monkeypatch.setattr(service, "SFX_SOURCES", sources)
    raw = b"video" * 512
    source_hash = hashlib.sha256(raw).hexdigest()
    (sources / f"{source_hash}.mp4").write_bytes(b"tampered")
    probe = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout='{"streams":[{"codec_type":"video"}],"format":{"duration":"8.0"}}',
        stderr="",
    )
    monkeypatch.setattr(service.subprocess, "run", lambda *args, **kwargs: probe)

    with pytest.raises(Exception, match="hash mismatch"):
        service._store_sfx_source(raw)


def test_sfx_upload_rejects_unbounded_body_before_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)

    class Request:
        headers = {}
        body_called = False

        async def body(self):
            self.body_called = True
            return b"video"

    request = Request()
    with pytest.raises(Exception, match="content length"):
        asyncio.run(service.upload_sfx_source(request, f"Bearer {'t' * 32}"))
    assert request.body_called is False


def test_sfx_submission_requires_license_provenance_and_ack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)
    monkeypatch.setenv("AIFILM_AUDIO_NODE_SFX_ARGV", '["trusted-adapter"]')
    monkeypatch.setattr(service, "SFX_MODEL_ID", "hkchengrex/MMAudio-large-44k-v2")
    monkeypatch.setattr(service, "SFX_LICENSE", "CC-BY-NC-4.0")
    monkeypatch.setattr(service, "SFX_CHECKPOINT_FINGERPRINT", "a" * 64)
    monkeypatch.setattr(service, "MMAUDIO_CHECKPOINT_SHA256", "a" * 64)
    monkeypatch.setattr(service, "_sfx_probe_ok", lambda: True)
    monkeypatch.setattr(service.shutil, "which", lambda executable: executable)
    monkeypatch.setattr(asyncio, "create_task", lambda coroutine: coroutine.close())

    with pytest.raises(Exception, match="non-commercial"):
        asyncio.run(
            service.create(
                "sfx",
                {"prompt": "door closes", "duration": 8, "seed": 1},
                f"Bearer {'t' * 32}",
            )
        )

    result = asyncio.run(
        service.create(
            "sfx",
            {
                "prompt": "door closes",
                "duration": 8,
                "seed": 1,
                "noncommercial_research_ok": True,
            },
            f"Bearer {'t' * 32}",
        )
    )
    assert result["status"] == "queued"


def test_ambient_submission_requires_candidate_ack_and_model_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)
    monkeypatch.setattr(service, "AMBIENT_MODEL_ID", "stabilityai/stable-audio-open-1.0")
    monkeypatch.setattr(service, "AMBIENT_LICENSE", "Stability AI Community License")
    monkeypatch.setattr(service, "AMBIENT_CHECKPOINT_SHA256", "c" * 64)
    monkeypatch.setattr(service, "AMBIENT_ADAPTER_SHA256", "d" * 64)
    renderer = [
        "python",
        "stable_audio_adapter.py",
        "--model-root",
        "model-root",
        "--checkpoint",
        "model-root/model.safetensors",
        "--expected-checkpoint-sha256",
        "c" * 64,
        "--expected-adapter-sha256",
        "d" * 64,
        "--prompt",
        "{prompt}",
        "--duration",
        "{duration}",
        "--seed",
        "{seed}",
        "--out",
        "{out}",
    ]
    probe = [
        "python",
        "stable_audio_probe.py",
        "--model-root",
        "model-root",
        "--checkpoint",
        "model-root/model.safetensors",
        "--adapter",
        "stable_audio_adapter.py",
        "--model",
        "stabilityai/stable-audio-open-1.0",
        "--license",
        "Stability AI Community License",
    ]
    monkeypatch.setenv("AIFILM_AUDIO_NODE_AMBIENT_ARGV", json.dumps(renderer))
    monkeypatch.setenv("AIFILM_AUDIO_NODE_AMBIENT_PROBE_ARGV", json.dumps(probe))
    monkeypatch.setattr(service.shutil, "which", lambda executable: executable)
    monkeypatch.setattr(service, "_ambient_probe_ok", lambda: True)
    monkeypatch.setattr(asyncio, "create_task", lambda coroutine: coroutine.close())
    with pytest.raises(Exception, match="candidate-only"):
        asyncio.run(
            service.create(
                "ambient", {"prompt": "rain", "duration": 8, "seed": 1}, f"Bearer {'t' * 32}"
            )
        )
    result = asyncio.run(
        service.create(
            "ambient",
            {"prompt": "rain", "duration": 8, "seed": 1, "stable_audio_candidate_only": True},
            f"Bearer {'t' * 32}",
        )
    )
    assert result["status"] == "queued"
    job = service.jobs[result["job_id"]]
    assert job["production_eligible"] is False
    assert job["usage_scope"] == "stable_audio_community_license_candidate"
    assert job["checkpoint_sha256"] == "c" * 64
    assert job["adapter_sha256"] == "d" * 64


def test_ambient_health_rejects_wrong_license_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "AMBIENT_MODEL_ID", "stabilityai/stable-audio-open-1.0")
    monkeypatch.setattr(service, "AMBIENT_LICENSE", "MIT")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_AMBIENT_ARGV", '["trusted-ambient-adapter"]')
    monkeypatch.setattr(service.shutil, "which", lambda executable: executable)

    assert service._available("ambient") is False


def test_ambient_health_rejects_renderer_without_provenance_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "AMBIENT_MODEL_ID", "stabilityai/stable-audio-open-1.0")
    monkeypatch.setattr(service, "AMBIENT_LICENSE", "Stability AI Community License")
    monkeypatch.setattr(service, "AMBIENT_CHECKPOINT_SHA256", "c" * 64)
    monkeypatch.setattr(service, "AMBIENT_ADAPTER_SHA256", "d" * 64)
    monkeypatch.setenv("AIFILM_AUDIO_NODE_AMBIENT_ARGV", '["/usr/bin/true"]')
    monkeypatch.delenv("AIFILM_AUDIO_NODE_AMBIENT_PROBE_ARGV", raising=False)

    assert service._available("ambient") is False


def test_ambient_health_rejects_renderer_not_bound_to_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "AMBIENT_MODEL_ID", "stabilityai/stable-audio-open-1.0")
    monkeypatch.setattr(service, "AMBIENT_LICENSE", "Stability AI Community License")
    monkeypatch.setattr(service, "AMBIENT_CHECKPOINT_SHA256", "c" * 64)
    monkeypatch.setattr(service, "AMBIENT_ADAPTER_SHA256", "d" * 64)
    monkeypatch.setenv("AIFILM_AUDIO_NODE_AMBIENT_ARGV", '["/usr/bin/true"]')
    monkeypatch.setenv(
        "AIFILM_AUDIO_NODE_AMBIENT_PROBE_ARGV",
        json.dumps(
            [
                "/usr/bin/true",
                "stable_audio_probe.py",
                "--model-root",
                "model-root",
                "--checkpoint",
                "model-root/model.safetensors",
                "--adapter",
                "stable_audio_adapter.py",
                "--model",
                "stabilityai/stable-audio-open-1.0",
                "--license",
                "Stability AI Community License",
            ]
        ),
    )
    monkeypatch.setattr(service, "_ambient_probe_ok", lambda: True)

    assert service._available("ambient") is False


def test_ambient_binding_rejects_abbreviated_override_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "AMBIENT_CHECKPOINT_SHA256", "c" * 64)
    monkeypatch.setattr(service, "AMBIENT_ADAPTER_SHA256", "d" * 64)
    probe = [
        "python",
        "stable_audio_probe.py",
        "--model-root",
        "good",
        "--checkpoint",
        "good/model.safetensors",
        "--adapter",
        "stable_audio_adapter.py",
        "--model",
        "stabilityai/stable-audio-open-1.0",
        "--license",
        "Stability AI Community License",
    ]
    renderer = [
        "python",
        "stable_audio_adapter.py",
        "--model-root",
        "good",
        "--checkpoint",
        "good/model.safetensors",
        "--expected-checkpoint-sha256",
        "c" * 64,
        "--expected-adapter-sha256",
        "d" * 64,
        "--prompt",
        "{prompt}",
        "--duration",
        "{duration}",
        "--seed",
        "{seed}",
        "--out",
        "{out}",
        "--checkp",
        "evil/model.safetensors",
    ]
    monkeypatch.setenv("AIFILM_AUDIO_NODE_AMBIENT_PROBE_ARGV", json.dumps(probe))

    assert service._ambient_renderer_bound(renderer) is False


def test_http_auth_rejects_before_json_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)

    response = TestClient(service.app).post(
        "/v1/ambient",
        content=b"{",
        headers={"Authorization": f"Bearer {'x' * 32}", "Content-Type": "application/json"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}


def test_music_batch_validates_repaint_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("fastapi")
    service = importlib.import_module("audio_node_service")
    monkeypatch.setattr(service, "TOKEN", "t" * 32)
    references = tmp_path / "refs"
    references.mkdir()
    reference_id = "a" * 64
    (references / f"{reference_id}.wav").write_bytes(b"RIFF" + b"\0" * 1024)
    monkeypatch.setattr(service, "REFERENCES", references)
    monkeypatch.setattr(service, "_music_batch_template", lambda: ["music"])
    monkeypatch.setattr(asyncio, "create_task", lambda coroutine: coroutine.close())
    base = {
        "prompt": "repair the musical ending",
        "duration": 20,
        "batch_size": 1,
        "seeds": [7],
        "task_type": "repaint",
        "reference_audio_id": reference_id,
    }

    accepted = asyncio.run(
        service.create_music_batch(
            {**base, "repainting_start": 12, "repainting_end": 20},
            f"Bearer {'t' * 32}",
        )
    )
    assert accepted["status"] == "queued"

    with pytest.raises(Exception, match="repaint"):
        asyncio.run(
            service.create_music_batch(
                {**base, "repainting_start": 20, "repainting_end": 12},
                f"Bearer {'t' * 32}",
            )
        )
