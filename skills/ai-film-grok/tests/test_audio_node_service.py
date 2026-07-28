from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import io
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
