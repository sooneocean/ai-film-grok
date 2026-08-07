#!/usr/bin/env python3
"""Render the preinstalled Piper Chinese ONNX voice without network access."""

from __future__ import annotations

import argparse
import contextlib
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from util.paths import build_subprocess_path, plugin_root


class PiperError(RuntimeError):
    pass


DEFAULT_ROOT = plugin_root() / "piper-voices"
DEFAULT_VOICE = "zh_CN-chaowen-medium"
DEFAULT_BINARY = (
    Path(__file__).resolve().parents[4] / ".local-runtimes" / "piper-mac" / "bin" / "piper"
)


def _contains_symlink(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.is_symlink():
            return True
    return False


def _trusted_path(name: str, expected: Path, *, executable: bool = False) -> Path:
    configured = Path(os.environ.get(name, str(expected))).expanduser()
    try:
        resolved = configured.resolve(strict=True)
        trusted = expected.expanduser().resolve(strict=True)
    except OSError as exc:
        raise PiperError("PIPER_PATH_UNTRUSTED") from exc
    if (
        resolved != trusted
        or _contains_symlink(configured)
        or not resolved.is_file()
        or (executable and not os.access(resolved, os.X_OK))
    ):
        raise PiperError("PIPER_PATH_UNTRUSTED")
    return resolved


def _configuration() -> tuple[Path, Path, Path]:
    configured_root = Path(os.environ.get("PIPER_VOICE_DIR", str(DEFAULT_ROOT))).expanduser()
    try:
        root = configured_root.resolve(strict=True)
        trusted_root = DEFAULT_ROOT.expanduser().resolve(strict=True)
    except OSError as exc:
        raise PiperError("PIPER_PATH_UNTRUSTED") from exc
    if root != trusted_root or _contains_symlink(configured_root) or not root.is_dir():
        raise PiperError("PIPER_PATH_UNTRUSTED")
    model = _trusted_path("PIPER_MODEL", root / f"{DEFAULT_VOICE}.onnx")
    config = _trusted_path("PIPER_CONFIG", root / f"{DEFAULT_VOICE}.onnx.json")
    binary = _trusted_path("PIPER_BINARY", DEFAULT_BINARY, executable=True)
    return binary, model, config


def _subprocess_env() -> dict[str, str]:
    env = {
        name: value
        for name in ("HOME", "LANG", "LC_ALL", "TMPDIR")
        if (value := os.environ.get(name))
    }
    env["PATH"] = build_subprocess_path()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["HF_DATASETS_OFFLINE"] = "1"
    return env


def _ffmpeg_path() -> Path:
    from util.paths import resolve_tool

    found = resolve_tool("ffmpeg")
    if found is None:
        raise PiperError("PIPER_FFMPEG_UNAVAILABLE")
    return found


def _open_output_parent(out: Path) -> tuple[Path, int]:
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise PiperError("PIPER_SAFE_OUTPUT_UNSUPPORTED")
    target = Path(os.path.abspath(out.expanduser()))
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
            raise PiperError("output path must not contain a symbolic link")
        return target, directory_fd
    except OSError as exc:
        os.close(directory_fd)
        raise PiperError("output path must not contain a symbolic link") from exc
    except Exception:
        os.close(directory_fd)
        raise


def _install_output(source: Path, out: Path) -> Path:
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
            raise PiperError("PIPER_OUTPUT_INVALID")
    except OSError as exc:
        raise PiperError("PIPER_OUTPUT_INSTALL_FAILED") from exc
    except PiperError:
        if installed:
            with contextlib.suppress(OSError):
                os.unlink(target.name, dir_fd=directory_fd)
        raise
    finally:
        os.close(directory_fd)
    return target


def _voice(value: str) -> str:
    selected = value.strip() or DEFAULT_VOICE
    if selected != DEFAULT_VOICE or selected.endswith("Neural"):
        raise PiperError("Piper requires the approved provider-native voice id")
    return selected


def synthesize(text: str, out: Path, voice: str = "") -> Path:
    body = text.strip()
    if not body:
        raise PiperError("text must not be empty")
    _voice(voice)
    binary, model, config = _configuration()
    with tempfile.TemporaryDirectory(prefix="aifilm-piper-") as tmp:
        wav = Path(tmp) / "render.wav"
        try:
            result = subprocess.run(
                [
                    str(binary),
                    "--model",
                    str(model),
                    "--config",
                    str(config),
                    "--output-file",
                    str(wav),
                ],
                input=body,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
                env=_subprocess_env(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PiperError("PIPER_RENDER_EXEC_FAILED") from exc
        if result.returncode != 0 or not wav.is_file() or wav.stat().st_size < 500:
            raise PiperError("PIPER_RENDER_FAILED")
        if out.suffix.lower() == ".wav":
            rendered = wav
        else:
            rendered = Path(tmp) / "render.mp3"
            try:
                result = subprocess.run(
                    [
                        str(_ffmpeg_path()),
                        "-y",
                        "-i",
                        str(wav),
                        "-ar",
                        "44100",
                        "-ac",
                        "1",
                        str(rendered),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                    env=_subprocess_env(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise PiperError("PIPER_EXPORT_EXEC_FAILED") from exc
            if result.returncode != 0:
                raise PiperError("PIPER_EXPORT_FAILED")
        return _install_output(rendered, out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="")
    parser.add_argument("--text-file", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--voice", default="")
    args = parser.parse_args()
    try:
        text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
        synthesize(text, Path(args.out), args.voice)
    except (OSError, UnicodeError) as exc:
        raise SystemExit("piper-local: PIPER_TEXT_INPUT_FAILED") from exc
    except PiperError as exc:
        raise SystemExit(f"piper-local: {exc}") from exc
    print("piper-local ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
