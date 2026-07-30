#!/usr/bin/env python3
"""Render offline multilingual Chatterbox speech through an explicit local route.

The isolated runtime must have already downloaded ``ResembleAI/chatterbox``.
Renders stay offline and use its built-in conditioning; this adapter never
accepts a reference recording or silently changes provider.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


class ChatterboxError(RuntimeError):
    """A Chatterbox local prerequisite or render failed."""


SUPPORTED_LANGUAGES = frozenset({"zh", "ja"})


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _device(torch: object) -> str:
    requested = _env("CHATTERBOX_DEVICE", "auto").lower()
    if requested not in {"auto", "cpu", "mps", "cuda"}:
        raise ChatterboxError("CHATTERBOX_DEVICE must be auto, cpu, mps, or cuda")
    if requested == "auto":
        return "mps" if torch.backends.mps.is_available() else "cpu"  # type: ignore[attr-defined]
    if requested == "mps" and not torch.backends.mps.is_available():  # type: ignore[attr-defined]
        raise ChatterboxError("CHATTERBOX_DEVICE=mps but MPS is unavailable")
    if requested == "cuda" and not torch.cuda.is_available():  # type: ignore[attr-defined]
        raise ChatterboxError("CHATTERBOX_DEVICE=cuda but CUDA is unavailable")
    return requested


def _language() -> str:
    language = _env("CHATTERBOX_LANGUAGE", "zh").lower()
    if language not in SUPPORTED_LANGUAGES:
        raise ChatterboxError("CHATTERBOX_LANGUAGE must be zh or ja")
    return language


def _voice(value: str) -> str:
    voice = value.strip()
    if voice.endswith("Neural"):
        raise ChatterboxError(f"Chatterbox requires a provider-native voice label, not {voice!r}")
    if voice and voice != "chatterbox-builtin":
        raise ChatterboxError("Chatterbox local uses only the model's built-in voice")
    return "chatterbox-builtin"


def synthesize(text: str, out: Path, voice: str = "") -> Path:
    body = text.strip()
    if not body:
        raise ChatterboxError("text must not be empty")
    _voice(voice)
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        import torch
        import torchaudio
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    except ImportError as exc:  # pragma: no cover - isolated runtime prerequisite
        raise ChatterboxError("Chatterbox runtime is not ready") from exc
    try:
        model = ChatterboxMultilingualTTS.from_pretrained(device=_device(torch))
        audio = model.generate(body, language_id=_language())
    except Exception as exc:  # upstream errors must not select another provider
        raise ChatterboxError(f"Chatterbox render failed: {exc}") from exc
    if audio is None or audio.shape[-1] < 100:
        raise ChatterboxError("Chatterbox returned empty audio")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aifilm-chatterbox-") as tmp_dir:
        wav = Path(tmp_dir) / "render.wav"
        torchaudio.save(str(wav), audio.detach().cpu(), model.sr)
        target = out if out.suffix.lower() == ".wav" else Path(tmp_dir) / "render.mp3"
        if target != wav:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav), "-ar", "44100", "-ac", "1", str(target)],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if result.returncode != 0:
                raise ChatterboxError(f"ffmpeg audio export failed: {(result.stderr or '')[-400:]}")
            os.replace(target, out)
        else:
            os.replace(wav, out)
    if not out.is_file() or out.stat().st_size < 500:
        raise ChatterboxError("Chatterbox wrote no usable audio")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Chatterbox TTS adapter")
    parser.add_argument("--text", default="")
    parser.add_argument("--text-file", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--voice", default="")
    args = parser.parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
    try:
        target = synthesize(text, Path(args.out), args.voice)
    except ChatterboxError as exc:
        raise SystemExit(f"chatterbox-local: {exc}") from exc
    print(f"chatterbox-local ok: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
