#!/usr/bin/env python3
"""Render offline Chinese speech with the Apache-licensed Kokoro v1.1 model.

This adapter is deliberately invoked through ``AIFILM_TTS_ARGV`` using its
isolated runtime. It loads only a preinstalled, fixed model from the local
Hugging Face cache and never falls back to another provider or network.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


class KokoroError(RuntimeError):
    """A local Kokoro prerequisite or render failed."""


SAMPLE_RATE = 24_000
DEFAULT_REPO_ID = "hexgrad/Kokoro-82M-v1.1-zh"
DEFAULT_VOICE = "zf_001"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _voice(value: str) -> str:
    selected = value.strip()
    if selected.endswith("Neural"):
        raise KokoroError(f"Kokoro requires a provider-native voice id, not {selected!r}")
    return selected or _env("KOKORO_VOICE", DEFAULT_VOICE)


def _offline_repo_id() -> str:
    configured = _env("KOKORO_REPO_ID", DEFAULT_REPO_ID)
    if configured != DEFAULT_REPO_ID:
        raise KokoroError("KOKORO_REPO_ID must use the approved Kokoro Chinese model")
    # The isolated runtime must never turn a render into an implicit download.
    os.environ["HF_HUB_OFFLINE"] = "1"
    return DEFAULT_REPO_ID


def synthesize(text: str, out: Path, voice: str = "") -> Path:
    body = text.strip()
    if not body:
        raise KokoroError("text must not be empty")
    repo_id = _offline_repo_id()
    try:
        import soundfile as sf
        import torch
        from kokoro import KModel, KPipeline
    except ImportError as exc:  # pragma: no cover - isolated runtime prerequisite
        raise KokoroError("Kokoro runtime is not ready") from exc

    requested_device = _env("KOKORO_DEVICE", "auto").lower()
    if requested_device not in {"auto", "cpu", "mps", "cuda"}:
        raise KokoroError("KOKORO_DEVICE must be auto, cpu, mps, or cuda")
    if requested_device == "auto":
        device = (
            "mps"
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
            else "cpu"
        )
    elif requested_device == "mps" and not (
        getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
    ):
        raise KokoroError("KOKORO_DEVICE=mps but MPS is unavailable")
    elif requested_device == "cuda" and not torch.cuda.is_available():
        raise KokoroError("KOKORO_DEVICE=cuda but CUDA is unavailable")
    else:
        device = requested_device

    try:
        model = KModel(repo_id=repo_id).to(device).eval()
        pipeline = KPipeline(lang_code="z", repo_id=repo_id, model=model)
        result = next(pipeline(body, voice=_voice(voice)))
        audio = result.audio
    except Exception as exc:  # upstream model errors are not safe to recover from here
        raise KokoroError(f"Kokoro render failed: {exc}") from exc
    if audio is None or len(audio) < 100:
        raise KokoroError("Kokoro returned empty audio")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".wav":
        sf.write(str(out), audio, SAMPLE_RATE)
    else:
        with tempfile.TemporaryDirectory(prefix="aifilm-kokoro-") as tmp_dir:
            wav = Path(tmp_dir) / "render.wav"
            sf.write(str(wav), audio, SAMPLE_RATE)
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav), "-ar", "44100", "-ac", "1", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                raise KokoroError(f"ffmpeg audio export failed: {(result.stderr or '')[-400:]}")
    if not out.is_file() or out.stat().st_size < 500:
        raise KokoroError("Kokoro wrote no usable WAV")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Kokoro Chinese TTS adapter")
    parser.add_argument("--text", default="")
    parser.add_argument("--text-file", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--voice", default="")
    args = parser.parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
    try:
        target = synthesize(text, Path(args.out), args.voice)
    except KokoroError as exc:
        raise SystemExit(f"kokoro-local: {exc}") from exc
    print(f"kokoro-local ok: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
