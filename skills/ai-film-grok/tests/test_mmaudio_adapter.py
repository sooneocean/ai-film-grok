from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from mmaudio_adapter import MMAudioAdapterError, _require_checkout, run


def _checkout(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "MMAudio"
    (repo / "weights").mkdir(parents=True)
    (repo / "ext_weights").mkdir()
    checkpoint = repo / "weights" / "mmaudio_large_44k_v2.pth"
    checkpoint.write_bytes(b"checkpoint")
    (repo / "ext_weights" / "v1-44.pth").write_bytes(b"vae")
    (repo / "ext_weights" / "synchformer_state_dict.pth").write_bytes(b"sync")
    (repo / "demo.py").write_text("pass\n")
    return repo, hashlib.sha256(b"checkpoint").hexdigest()


def _pin_all_weights(monkeypatch: pytest.MonkeyPatch, checkpoint: str) -> None:
    monkeypatch.setenv("AIFILM_MMAUDIO_CHECKPOINT_SHA256", checkpoint)
    monkeypatch.setenv("AIFILM_MMAUDIO_VAE_SHA256", hashlib.sha256(b"vae").hexdigest())
    monkeypatch.setenv(
        "AIFILM_MMAUDIO_SYNCHFORMER_SHA256", hashlib.sha256(b"sync").hexdigest()
    )


def test_requires_pinned_clean_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo, checkpoint = _checkout(tmp_path)
    monkeypatch.setenv("AIFILM_MMAUDIO_REPO_COMMIT", "a" * 40)
    _pin_all_weights(monkeypatch, checkpoint)
    replies = [
        subprocess.CompletedProcess([], 0, stdout="a" * 40 + "\n", stderr=""),
        subprocess.CompletedProcess([], 0, stdout="dirty.py\n", stderr=""),
    ]
    with patch("mmaudio_adapter.subprocess.run", side_effect=replies):
        with pytest.raises(MMAudioAdapterError, match="clean commit"):
            _require_checkout(repo)


def test_rejects_checkpoint_hash_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo, _ = _checkout(tmp_path)
    monkeypatch.setenv("AIFILM_MMAUDIO_REPO_COMMIT", "a" * 40)
    _pin_all_weights(monkeypatch, "b" * 64)
    replies = [
        subprocess.CompletedProcess([], 0, stdout="a" * 40 + "\n", stderr=""),
        subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    ]
    with patch("mmaudio_adapter.subprocess.run", side_effect=replies):
        with pytest.raises(MMAudioAdapterError, match="SHA-256"):
            _require_checkout(repo)


def test_run_forces_offline_inference_and_exactly_one_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo, checkpoint = _checkout(tmp_path)
    monkeypatch.setenv("AIFILM_MMAUDIO_REPO_COMMIT", "a" * 40)
    _pin_all_weights(monkeypatch, checkpoint)
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("env") or {}))
        if "rev-parse" in command:
            return subprocess.CompletedProcess(command, 0, stdout="a" * 40 + "\n", stderr="")
        if "status" in command:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if str(repo / "demo.py") in command:
            output_dir = Path(command[command.index("--output") + 1])
            (output_dir / "result.flac").write_bytes(b"flac")
        elif command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"R" * 1024)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    out = tmp_path / "out.wav"
    with patch("mmaudio_adapter.subprocess.run", side_effect=fake_run):
        run(
            repo=repo,
            prompt="door closes",
            duration=8,
            seed=7,
            out=out,
            video=None,
        )

    demo_call = next(item for item in calls if str(repo / "demo.py") in item[0])
    assert demo_call[1]["HF_HUB_OFFLINE"] == "1"
    assert demo_call[1]["TRANSFORMERS_OFFLINE"] == "1"
    assert out.is_file()


def test_run_rejects_symlink_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo, checkpoint = _checkout(tmp_path)
    linked = tmp_path / "linked"
    linked.symlink_to(repo, target_is_directory=True)
    monkeypatch.setenv("AIFILM_MMAUDIO_REPO_COMMIT", "a" * 40)
    _pin_all_weights(monkeypatch, checkpoint)

    with pytest.raises(MMAudioAdapterError, match="symlinked"):
        run(
            repo=linked,
            prompt="door closes",
            duration=8,
            seed=7,
            out=tmp_path / "out.wav",
            video=None,
        )
