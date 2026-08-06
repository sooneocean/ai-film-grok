"""1:1 test for audio.stable_audio_adapter (P3-1 migration + contract lock).

Migrated from scripts/stable_audio_adapter.py into the audio package. The heavy
torch/stable_audio imports are lazy (inside main), so the pure helpers are
testable without GPU.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

from audio import stable_audio_adapter


def test_sha256_matches_hashlib():
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(b"hello stable audio")
        path = Path(handle.name)
    try:
        assert (
            stable_audio_adapter._sha256(path)
            == hashlib.sha256(b"hello stable audio").hexdigest()
        )
    finally:
        path.unlink()


def test_pinned_local_model_rejects_symlink():
    d = tempfile.mkdtemp()
    target = Path(d) / "real.txt"
    target.write_text("x")
    link = Path(d) / "link.txt"
    os.symlink(str(target), str(link))
    checkpoint = Path(d) / "ckpt.bin"
    checkpoint.write_text("c")

    args = _args(model_root=str(link), checkpoint=str(checkpoint))
    with pytest.raises(SystemExit):
        stable_audio_adapter._pinned_local_model(args)


def test_pinned_local_model_rejects_checkpoint_sha_mismatch(monkeypatch):
    d = tempfile.mkdtemp()
    root = Path(d) / "root"
    root.mkdir()
    checkpoint = root / "ckpt.bin"
    checkpoint.write_text("c")

    monkeypatch.setattr(stable_audio_adapter, "_sha256", lambda p: "deadbeef")
    args = _args(model_root=str(root), checkpoint=str(checkpoint), expected_ckpt="other")
    with pytest.raises(SystemExit):
        stable_audio_adapter._pinned_local_model(args)


def _args(*, model_root: str, checkpoint: str, expected_ckpt: str = "x") -> object:
    ns = type("Ns", (), {})()
    ns.model_root = model_root
    ns.checkpoint = checkpoint
    ns.expected_checkpoint_sha256 = expected_ckpt
    ns.expected_adapter_sha256 = "whatever"
    return ns
