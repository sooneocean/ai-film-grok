#!/usr/bin/env python3
"""Render offline multilingual Chatterbox speech through an explicit local route.

The isolated runtime must have already downloaded ``ResembleAI/chatterbox``.
Renders stay offline and use its built-in conditioning; this adapter never
accepts a reference recording or silently changes provider.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import stat
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
        raise ChatterboxError("CHATTERBOX_VOICE_PROVIDER_MISMATCH: provider-native voice required")
    if voice and voice != "chatterbox-builtin":
        raise ChatterboxError("Chatterbox local uses only the model's built-in voice")
    return "chatterbox-builtin"


def _open_output_parent(out: Path) -> tuple[Path, int]:
    """Open/create every output directory component without following symlinks."""
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise ChatterboxError("CHATTERBOX_SAFE_OUTPUT_UNSUPPORTED")
    target = Path(os.path.abspath(out.expanduser()))
    if not target.name:
        raise ChatterboxError("CHATTERBOX_OUTPUT_INVALID")
    directory_fd = os.open(target.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in target.parent.parts[1:]:
            try:
                next_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except FileNotFoundError:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(component, mode=0o700, dir_fd=directory_fd)
                next_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            os.close(directory_fd)
            directory_fd = next_fd
        try:
            metadata = os.stat(target.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            metadata = None
        if metadata is not None and stat.S_ISLNK(metadata.st_mode):
            raise ChatterboxError("output path must not contain a symbolic link")
        return target, directory_fd
    except OSError as exc:
        os.close(directory_fd)
        raise ChatterboxError("output path must not contain a symbolic link") from exc
    except Exception:
        os.close(directory_fd)
        raise


def _install_output(source: Path, out: Path) -> Path:
    """Atomically install an internal render through a pinned output directory."""
    target, directory_fd = _open_output_parent(out)
    installed = False
    try:
        os.replace(source, target.name, dst_dir_fd=directory_fd)
        installed = True
        file_fd = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            metadata = os.fstat(file_fd)
        finally:
            os.close(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 500:
            raise ChatterboxError("CHATTERBOX_OUTPUT_INVALID")
    except OSError as exc:
        raise ChatterboxError("CHATTERBOX_OUTPUT_INSTALL_FAILED") from exc
    except ChatterboxError:
        if installed:
            with contextlib.suppress(OSError):
                os.unlink(target.name, dir_fd=directory_fd)
        raise
    finally:
        os.close(directory_fd)
    return target


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
        raise ChatterboxError("CHATTERBOX_RENDER_FAILED") from exc
    if audio is None or audio.shape[-1] < 100:
        raise ChatterboxError("Chatterbox returned empty audio")
    with tempfile.TemporaryDirectory(prefix="aifilm-chatterbox-") as tmp_dir:
        wav = Path(tmp_dir) / "render.wav"
        try:
            torchaudio.save(str(wav), audio.detach().cpu(), model.sr)
        except Exception as exc:
            raise ChatterboxError("CHATTERBOX_AUDIO_SAVE_FAILED") from exc
        rendered = wav
        if out.suffix.lower() != ".wav":
            rendered = Path(tmp_dir) / "render.mp3"
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav), "-ar", "44100", "-ac", "1", str(rendered)],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if result.returncode != 0:
                raise ChatterboxError("CHATTERBOX_FFMPEG_EXPORT_FAILED")
        return _install_output(rendered, out)


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
