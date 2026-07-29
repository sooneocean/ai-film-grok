#!/usr/bin/env python3
"""Stage one verified audio file to the private VibeVoice-ASR node.

This adapter matches the local ``{audio}``/``{out}`` contract.  It never
approves a delivery or submits a ComfyUI workflow; the caller owns that gate.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import uuid
from pathlib import Path, PureWindowsPath


class RemoteASRError(ValueError):
    pass


_SSH_TARGET_RE = re.compile(r"(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
_HOSTKEY_ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,252}$")
_REMOTE_ROOT = PureWindowsPath(r"C:\\aifilm-vibevoice")
_REMOTE_MODEL_ROOT = PureWindowsPath(r"C:\\AI_Models\\VibeVoice-ASR")


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RemoteASRError(f"{name} is required")
    return value


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ssh_target() -> str:
    target = _env("AIFILM_VIBEVOICE_ASR_SSH_TARGET")
    if not _SSH_TARGET_RE.fullmatch(target):
        raise RemoteASRError("AIFILM_VIBEVOICE_ASR_SSH_TARGET is not a safe SSH destination")
    return target


def _windows_path(value: str, *, allowed_root: PureWindowsPath, name: str) -> str:
    path = PureWindowsPath(value)
    if (
        not path.is_absolute()
        or path.drive.casefold() != allowed_root.drive.casefold()
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise RemoteASRError(f"{name} must be an absolute path below {allowed_root}")
    try:
        path.relative_to(allowed_root)
    except ValueError as exc:
        raise RemoteASRError(f"{name} must be below {allowed_root}") from exc
    return str(path)


def _ssh_options() -> list[str]:
    key = _env("AIFILM_VIBEVOICE_ASR_SSH_KEY")
    alias = _env("AIFILM_VIBEVOICE_ASR_SSH_HOSTKEY_ALIAS")
    if not Path(key).expanduser().is_file():
        raise RemoteASRError("AIFILM_VIBEVOICE_ASR_SSH_KEY must name an existing key")
    if not _HOSTKEY_ALIAS_RE.fullmatch(alias):
        raise RemoteASRError("AIFILM_VIBEVOICE_ASR_SSH_HOSTKEY_ALIAS is not a safe alias")
    return [
        "-i",
        str(Path(key).expanduser()),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"HostKeyAlias={alias}",
    ]


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, timeout=1_100, check=False)
    if completed.returncode:
        raise RemoteASRError("VibeVoice-ASR remote transfer or inference failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    audio, out = Path(args.audio).resolve(), Path(args.out).resolve()
    if audio.is_symlink() or not audio.is_file():
        raise RemoteASRError("audio must be a regular file")
    if out.is_symlink() or out.suffix.lower() != ".json":
        raise RemoteASRError("out must be a non-symlink JSON path")

    target = _ssh_target()
    remote_root = _windows_path(
        _env("AIFILM_VIBEVOICE_ASR_REMOTE_ROOT"),
        allowed_root=_REMOTE_ROOT,
        name="AIFILM_VIBEVOICE_ASR_REMOTE_ROOT",
    )
    if PureWindowsPath(remote_root) != _REMOTE_ROOT:
        raise RemoteASRError(f"AIFILM_VIBEVOICE_ASR_REMOTE_ROOT must be {_REMOTE_ROOT}")
    remote_model = _windows_path(
        _env("AIFILM_VIBEVOICE_ASR_REMOTE_MODEL_PATH"),
        allowed_root=_REMOTE_MODEL_ROOT,
        name="AIFILM_VIBEVOICE_ASR_REMOTE_MODEL_PATH",
    )
    token = uuid.uuid4().hex
    remote_audio = f"{remote_root}\\jobs\\{token}{audio.suffix.lower()}"
    remote_out = f"{remote_root}\\jobs\\{token}.json"
    remote_jobs = remote_root + "\\jobs"
    remote_python = remote_root + "\\venv\\Scripts\\python.exe"
    remote_adapter = remote_root + "\\vibevoice_asr.py"
    scp_audio = remote_audio.replace("\\", "/")
    scp_out = remote_out.replace("\\", "/")
    options = _ssh_options()
    mkdir_script = (
        "$ErrorActionPreference = 'Stop'\n"
        f"New-Item -ItemType Directory -Force -Path {_ps_quote(remote_jobs)} | Out-Null"
    )
    mkdir_encoded = base64.b64encode(mkdir_script.encode("utf-16le")).decode("ascii")
    _run(
        [
            "ssh",
            *options,
            "--",
            target,
            "powershell",
            "-NoProfile",
            "-EncodedCommand",
            mkdir_encoded,
        ]
    )
    _run(["scp", *options, "--", str(audio), f"{target}:{scp_audio}"])
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"& {_ps_quote(remote_python)} {_ps_quote(remote_adapter)} --audio {_ps_quote(remote_audio)} --out {_ps_quote(remote_out)} --model-path {_ps_quote(remote_model)} --device cuda",
        ]
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    _run(["ssh", *options, "--", target, "powershell", "-NoProfile", "-EncodedCommand", encoded])
    _run(["scp", *options, "--", f"{target}:{scp_out}", str(out)])
    try:
        payload = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RemoteASRError("VibeVoice-ASR remote transcript is invalid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("segments"), list):
        raise RemoteASRError("VibeVoice-ASR remote transcript has no segments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
