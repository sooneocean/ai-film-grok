"""Candidate-only controls for a private Hugging Face Speech-to-Speech sidecar.

The sidecar is deliberately not a TTS backend.  A separately managed launcher
owns the remote 5090 process; this module verifies its immutable configuration,
refuses unsafe launches, and turns measured dialogue samples into reviewable
candidate receipts.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from media_probe import MediaProbeError, verify_full_decode
from media_qa import MediaQAError, analyze_media
from security_policy import (
    SecurityPolicyError,
    minimal_subprocess_env,
    parse_argv_json,
    safe_existing_file,
)
from util import sha256_file, write_json

URL_ENV = "AIFILM_SPEECH_PREVIEW_URL"
LAUNCH_ENV = "AIFILM_SPEECH_PREVIEW_START_ARGV"
GUARD_ENV = "AIFILM_SPEECH_PREVIEW_GUARD_ARGV"
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
LLM_ID = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
STT_ID = "large-v3"
PACKAGE_VERSION = "0.2.11"
MIN_VRAM_MIB = 24 * 1024
MIN_RAM_MIB = 12 * 1024


class SpeechPreviewError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _loopback_url(value: str | None = None) -> str:
    raw = str(value or os.environ.get(URL_ENV) or "http://127.0.0.1:8765").strip()
    parsed = urlsplit(raw)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise SpeechPreviewError("speech preview endpoint must use loopback HTTP only")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise SpeechPreviewError("speech preview endpoint must be a plain loopback base URL")
    return f"http://{parsed.hostname}:{parsed.port or 8765}"


def _argv(variable: str) -> list[str]:
    raw = os.environ.get(variable, "").strip()
    if not raw:
        raise SpeechPreviewError(f"{variable} is not configured")
    try:
        return parse_argv_json(raw, variable=variable)
    except SecurityPolicyError as exc:
        raise SpeechPreviewError(str(exc)) from exc


def _launcher() -> list[str]:
    argv = _argv(LAUNCH_ENV)
    joined = "\x00".join(argv)
    if "--enable_llm_proxy" in argv:
        raise SpeechPreviewError("speech preview launcher must not enable the LLM proxy")
    if "--ws_host" not in argv or "127.0.0.1" not in argv:
        raise SpeechPreviewError("speech preview launcher must explicitly bind --ws_host 127.0.0.1")
    if "speech-to-speech" not in joined:
        raise SpeechPreviewError(
            "speech preview launcher must invoke the pinned speech-to-speech service"
        )
    for required in ("--stt", "--tts", "--llm_backend"):
        if required not in argv:
            raise SpeechPreviewError(f"speech preview launcher is missing {required}")
    return argv


def _guard() -> dict[str, Any]:
    command = _argv(GUARD_ENV)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=minimal_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpeechPreviewError("speech preview live capacity check failed") from exc
    if result.returncode:
        raise SpeechPreviewError("speech preview live capacity check failed")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SpeechPreviewError("speech preview capacity check returned invalid JSON") from exc
    if not isinstance(report, dict):
        raise SpeechPreviewError("speech preview capacity check returned invalid JSON")
    if report.get("queue_idle") is not True:
        raise SpeechPreviewError("speech preview blocked: 5090 queue is not idle")
    for field, minimum in (("free_vram_mib", MIN_VRAM_MIB), ("free_ram_mib", MIN_RAM_MIB)):
        value = report.get(field)
        if not isinstance(value, int) or value < minimum:
            raise SpeechPreviewError(f"speech preview blocked: {field} is below required capacity")
    if report.get("python_version") != "3.11" or not isinstance(report.get("cuda"), str):
        raise SpeechPreviewError("speech preview requires the verified Python 3.11 CUDA runtime")
    return {
        "queue_idle": True,
        "free_vram_mib": report["free_vram_mib"],
        "free_ram_mib": report["free_ram_mib"],
        "python_version": "3.11",
        "cuda": report["cuda"],
    }


def probe() -> dict[str, Any]:
    """Validate configuration only; never contacts or starts the sidecar."""
    issues: list[str] = []
    try:
        endpoint = _loopback_url()
    except SpeechPreviewError as exc:
        endpoint = None
        issues.append(str(exc))
    try:
        _launcher()
    except SpeechPreviewError as exc:
        issues.append(str(exc))
    try:
        _argv(GUARD_ENV)
    except SpeechPreviewError as exc:
        issues.append(str(exc))
    return {
        "schema_version": 1,
        "kind": "speech-preview-probe",
        "at": _now(),
        "ok": not issues,
        "status": "configured" if not issues else "not_configured",
        "inference_started": False,
        "endpoint": endpoint,
        "profile": {
            "speech_to_speech_version": PACKAGE_VERSION,
            "stt": {"backend": "whisper", "model": STT_ID},
            "llm": {"backend": "llama.cpp", "model_file": LLM_ID},
            "tts": {"backend": "qwen3", "model": MODEL_ID, "ja_female_voice": "Ono_Anna"},
        },
        "candidate_only": True,
        "may_change_tts_default": False,
        "issues": issues,
    }


def start(*, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise SpeechPreviewError(
            "speech preview start requires --confirm after a live capacity check"
        )
    endpoint = _loopback_url()
    capacity = _guard()
    command = _launcher()
    try:
        subprocess.Popen(
            command,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=minimal_subprocess_env(),
        )
    except OSError as exc:
        raise SpeechPreviewError("speech preview launcher could not be started") from exc
    return {
        "schema_version": 1,
        "kind": "speech-preview-start",
        "at": _now(),
        "status": "launch_requested",
        "endpoint": endpoint,
        "capacity": capacity,
        "candidate_only": True,
        "next_step": "Use speech-preview session with a measured client receipt; human review is still required.",
    }


def _root_file(root: Path, value: Path | str, *, label: str) -> Path:
    try:
        return safe_existing_file(root, value, field=label)
    except SecurityPolicyError as exc:
        raise SpeechPreviewError(
            f"{label} must be a regular file inside the film workspace"
        ) from exc


def _session_payload(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpeechPreviewError("session JSON must be readable") from exc
    if not isinstance(data, dict):
        raise SpeechPreviewError("session JSON must be an object")
    for field in (
        "recognized_text",
        "reply_text",
        "language",
        "first_audio_latency_ms",
        "response_latency_ms",
    ):
        value = data.get(field)
        if field.endswith("_ms"):
            if not isinstance(value, int) or value < 0:
                raise SpeechPreviewError(f"session JSON has invalid {field}")
        elif not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise SpeechPreviewError(f"session JSON has invalid {field}")
    if data["language"] not in {"zh", "ja"}:
        raise SpeechPreviewError("session language must be zh or ja")
    return data


def record_session(
    root: Path | str, *, audio: Path | str, session_json: Path | str
) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise SpeechPreviewError("film root must exist")
    source = _root_file(base, audio, label="audio")
    payload_path = _root_file(base, session_json, label="session JSON")
    payload = _session_payload(payload_path)
    try:
        media = analyze_media(source, require_audio=True, require_motion=False)
        verify_full_decode(source)
    except (MediaQAError, MediaProbeError) as exc:
        raise SpeechPreviewError("session audio must pass complete local decode") from exc
    if media.get("has_audio") is not True:
        raise SpeechPreviewError("session audio must contain an audio stream")
    receipt = {
        "schema_version": 1,
        "kind": "speech-preview-session",
        "at": _now(),
        "status": "candidate_only",
        "profile": {
            "speech_to_speech_version": PACKAGE_VERSION,
            "stt_model": STT_ID,
            "tts_model": MODEL_ID,
            "llm_model": LLM_ID,
        },
        "audio": {
            "path": str(source.relative_to(base)),
            "sha256": sha256_file(source),
            "technical_qa": media,
        },
        "session": payload,
        "may_approve_production": False,
        "may_change_tts_default": False,
    }
    output = base / "receipts" / "speech-preview-session.json"
    if output.is_symlink():
        raise SpeechPreviewError("speech preview receipt output must not be a symlink")
    write_json(output, receipt)
    receipt["path"] = str(output)
    return receipt


def export_candidate(root: Path | str, *, session_receipt: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    receipt_path = _root_file(base, session_receipt, label="session receipt")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpeechPreviewError("session receipt must be readable JSON") from exc
    if (
        not isinstance(receipt, dict)
        or receipt.get("kind") != "speech-preview-session"
        or receipt.get("status") != "candidate_only"
    ):
        raise SpeechPreviewError("session receipt must be a candidate-only speech preview receipt")
    audio = receipt.get("audio") if isinstance(receipt.get("audio"), dict) else {}
    path = audio.get("path")
    source = _root_file(base, str(path), label="session audio")
    if audio.get("sha256") != sha256_file(source):
        raise SpeechPreviewError("session audio checksum no longer matches its receipt")
    candidate = {
        "schema_version": 1,
        "kind": "speech-preview-export-candidate",
        "at": _now(),
        "status": "awaiting_human_listening",
        "source_receipt_sha256": sha256_file(receipt_path),
        "audio_sha256": audio["sha256"],
        "language": receipt["session"]["language"],
        "restrictions": ["not_final_audio", "not_tts_backend", "no_auto_approval"],
        "required_next": "full_human_listening_and_explicit_review",
    }
    output = base / "receipts" / "speech-preview-export-candidate.json"
    if output.is_symlink():
        raise SpeechPreviewError("speech preview candidate output must not be a symlink")
    write_json(output, candidate)
    candidate["path"] = str(output)
    return candidate
