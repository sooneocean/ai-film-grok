from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import stable_audio_adapter


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_adapter_accepts_only_hash_bound_local_checkpoint(tmp_path: Path) -> None:
    model_root = tmp_path / "model"
    model_root.mkdir()
    checkpoint = model_root / "model.safetensors"
    checkpoint.write_bytes(b"pinned-checkpoint")
    adapter = Path(stable_audio_adapter.__file__).resolve()
    args = argparse.Namespace(
        model_root=str(model_root),
        checkpoint=str(checkpoint),
        expected_checkpoint_sha256=_sha256(checkpoint),
        expected_adapter_sha256=_sha256(adapter),
    )

    assert stable_audio_adapter._pinned_local_model(args) == model_root.resolve()


def test_probe_reports_checkpoint_and_adapter_hashes(tmp_path: Path) -> None:
    model_root = tmp_path / "model"
    model_root.mkdir()
    checkpoint = model_root / "model.safetensors"
    checkpoint.write_bytes(b"pinned-checkpoint")
    adapter = Path(stable_audio_adapter.__file__).resolve()
    probe = Path(__file__).resolve().parent.parent / "scripts" / "node" / "stable_audio_probe.py"

    result = subprocess.run(
        [
            sys.executable,
            str(probe),
            "--model-root",
            str(model_root),
            "--checkpoint",
            str(checkpoint),
            "--adapter",
            str(adapter),
            "--model",
            "stabilityai/stable-audio-open-1.0",
            "--license",
            "Stability AI Community License",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)

    assert report["ok"] is True
    assert report["checkpoint_sha256"] == _sha256(checkpoint)
    assert report["adapter_sha256"] == _sha256(adapter)


def test_adapter_rejects_abbreviated_override_arguments() -> None:
    adapter = Path(stable_audio_adapter.__file__).resolve()
    result = subprocess.run(
        [
            sys.executable,
            str(adapter),
            "--model-root",
            "good",
            "--checkpoint",
            "good/model.safetensors",
            "--expected-checkpoint-sha256",
            "c" * 64,
            "--expected-adapter-sha256",
            "d" * 64,
            "--prompt",
            "rain",
            "--duration",
            "8",
            "--seed",
            "1",
            "--out",
            "candidate.wav",
            "--checkp",
            "evil/model.safetensors",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --checkp" in result.stderr
