#!/usr/bin/env python3
"""Run a locally installed CosyVoice model as an explicit ai-film-grok TTS adapter.

This program must be launched by the CosyVoice environment, not by the plugin
runtime.  It never downloads a model or substitutes another provider.

Required local configuration::

  COSYVOICE_ROOT=/Users/dex/Developer/CosyVoice
  COSYVOICE_MODEL_DIR=/Users/dex/Developer/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-hf
  COSYVOICE_MODE=zero_shot
  COSYVOICE_REF_WAV=/absolute/path/to/licensed-reference.wav
  COSYVOICE_PROMPT_TEXT='reference transcript'

For the model's built-in SFT speaker (no cloning and no reference audio)::

  COSYVOICE_MODE=sft
  COSYVOICE_SPEAKER=中文女

The film must use a provider-native voice label (for example
``cosyvoice-narrator``), never an Edge ``...Neural`` name.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


class CosyVoiceLocalError(RuntimeError):
    """A local CosyVoice prerequisite or render failed."""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _regular_file(path: Path, *, name: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise CosyVoiceLocalError(f"{name} must be a regular file: {path}")
    return path


def _mode() -> str:
    mode = (_env("COSYVOICE_MODE") or "zero_shot").lower()
    if mode not in {"zero_shot", "sft"}:
        raise CosyVoiceLocalError("COSYVOICE_MODE must be zero_shot or sft")
    return mode


def _text_frontend_enabled() -> bool:
    """Allow an offline canary to bypass optional WeText downloads explicitly."""
    return _env("COSYVOICE_TEXT_FRONTEND", "1").lower() not in {"0", "false", "no", "off"}


def _configuration() -> tuple[Path, Path, Path | None, str]:
    root_raw = _env("COSYVOICE_ROOT")
    model_raw = _env("COSYVOICE_MODEL_DIR")
    ref_raw = _env("COSYVOICE_REF_WAV")
    prompt = _env("COSYVOICE_PROMPT_TEXT")
    mode = _mode()
    if not all((root_raw, model_raw)):
        raise CosyVoiceLocalError("COSYVOICE_ROOT and COSYVOICE_MODEL_DIR are required")
    if mode == "zero_shot" and not all((ref_raw, prompt)):
        raise CosyVoiceLocalError(
            "COSYVOICE_REF_WAV and COSYVOICE_PROMPT_TEXT are required for zero_shot"
        )
    root = Path(root_raw).expanduser().resolve()
    model = Path(model_raw).expanduser().resolve()
    reference = (
        _regular_file(Path(ref_raw).expanduser(), name="COSYVOICE_REF_WAV").resolve()
        if mode == "zero_shot" and ref_raw
        else None
    )
    if not (root / "cosyvoice").is_dir() or not (root / "third_party" / "Matcha-TTS").is_dir():
        raise CosyVoiceLocalError(f"COSYVOICE_ROOT is not a CosyVoice checkout: {root}")
    if not any((model / name).is_file() for name in ("cosyvoice.yaml", "cosyvoice3.yaml")):
        raise CosyVoiceLocalError(f"COSYVOICE_MODEL_DIR is incomplete: {model}")
    return root, model, reference, prompt


def _provider_voice(value: str) -> str:
    voice = value.strip()
    if voice.startswith(("zh-", "ja-")) and "Neural" in voice:
        raise CosyVoiceLocalError(
            f"CosyVoice requires a provider-native voice label, not {voice!r}"
        )
    return voice or _env("COSYVOICE_SPEAKER") or "cosyvoice-local"


def _write_output(samples: object, sample_rate: int, out: Path) -> None:
    try:
        import torchaudio
    except ImportError as exc:  # pragma: no cover - environment prerequisite
        raise CosyVoiceLocalError("CosyVoice environment is missing torchaudio") from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aifilm-cosyvoice-") as tmp_dir:
        wav = Path(tmp_dir) / "render.wav"
        torchaudio.save(str(wav), samples, sample_rate)
        # Keep the FFmpeg destination distinct even when callers request WAV.
        # An in-place ``render.wav → render.wav`` conversion is rejected.
        rendered = Path(tmp_dir) / f"render.output{out.suffix or '.mp3'}"
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(wav),
            "-ar",
            "44100",
            "-ac",
            "1",
            str(rendered),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if result.returncode != 0 or not rendered.is_file() or rendered.stat().st_size < 500:
            raise CosyVoiceLocalError(f"ffmpeg audio export failed: {(result.stderr or '')[-400:]}")
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(rendered),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        try:
            duration = float((probe.stdout or "0").strip() or 0)
        except ValueError as exc:
            raise CosyVoiceLocalError("CosyVoice output duration could not be read") from exc
        if probe.returncode != 0 or duration <= 0:
            raise CosyVoiceLocalError("CosyVoice output is not decodable audio")
        os.replace(rendered, out)


def synthesize(text: str, out: Path, voice: str) -> Path:
    body = text.strip()
    if not body:
        raise CosyVoiceLocalError("text must not be empty")
    mode = _mode()
    text_frontend = _text_frontend_enabled()
    if not text_frontend:
        # AutoModel otherwise attempts to fetch optional WeText assets during
        # construction.  The provider accepts pre-normalized text below.
        os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
    root, model_dir, reference, prompt = _configuration()
    provider_voice = _provider_voice(voice)
    if mode == "sft" and provider_voice == "cosyvoice-local":
        provider_voice = "中文女"
    for location in (str(root), str(root / "third_party" / "Matcha-TTS")):
        if location not in sys.path:
            sys.path.insert(0, location)
    try:
        from cosyvoice.cli.cosyvoice import AutoModel
    except ImportError as exc:  # pragma: no cover - environment prerequisite
        raise CosyVoiceLocalError("CosyVoice Python environment is not ready") from exc
    model = AutoModel(model_dir=str(model_dir))
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - environment prerequisite
        raise CosyVoiceLocalError("CosyVoice environment is missing torch") from exc
    if mode == "sft":
        chunks = [
            result["tts_speech"]
            for result in model.inference_sft(
                body, provider_voice, stream=False, text_frontend=text_frontend
            )
        ]
    else:
        if reference is None:  # guarded by _configuration; keeps type narrowing explicit
            raise CosyVoiceLocalError("zero_shot requires COSYVOICE_REF_WAV")
        chunks = [
            result["tts_speech"]
            for result in model.inference_zero_shot(
                body,
                prompt,
                str(reference),
                stream=False,
                text_frontend=text_frontend,
            )
        ]
    if not chunks:
        raise CosyVoiceLocalError("CosyVoice returned no audio")
    _write_output(torch.cat(chunks, dim=1), int(model.sample_rate), out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Local CosyVoice TTS adapter for ai-film-grok")
    parser.add_argument("--text", default="")
    parser.add_argument("--text-file", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--voice", default="")
    args = parser.parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
    try:
        target = synthesize(text, Path(args.out), args.voice)
    except CosyVoiceLocalError as exc:
        raise SystemExit(f"cosyvoice-local: {exc}") from exc
    print(f"cosyvoice-local ok: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
