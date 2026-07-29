#!/usr/bin/env python3
"""Private Windows/LAN audio-node service.

Start with: uvicorn audio_node_service:app --host <LAN-IP> --port 8788
Only Qwen TTS is built in. Music, SFX, and performance tracks use explicit
trusted argv adapters so the control plane never guesses model-specific CLIs.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(os.environ.get("AIFILM_AUDIO_NODE_ROOT", r"C:\\aifilm-audio-node")).resolve()
JOBS = ROOT / "jobs"
REFERENCES = ROOT / "music-references"
SFX_SOURCES = ROOT / "sfx-sources"
TOKEN = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "")
MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_QWEN_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
MODEL_PATH = os.environ.get("AIFILM_AUDIO_NODE_QWEN_MODEL_PATH", MODEL_ID)
CUSTOM_1_7B_MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_QWEN_CUSTOM_1_7B_MODEL", "")
CUSTOM_1_7B_MODEL_PATH = os.environ.get("AIFILM_AUDIO_NODE_QWEN_CUSTOM_1_7B_MODEL_PATH", "")
CUSTOM_0_6B_MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_QWEN_CUSTOM_0_6B_MODEL", "")
CUSTOM_0_6B_MODEL_PATH = os.environ.get("AIFILM_AUDIO_NODE_QWEN_CUSTOM_0_6B_MODEL_PATH", "")
MUSIC_MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_MUSIC_MODEL", "ACE-Step-1.5")
MUSIC_CHECKPOINT_FINGERPRINT = os.environ.get(
    "AIFILM_AUDIO_NODE_MUSIC_CHECKPOINT_FINGERPRINT", "unknown"
)
PERFORMANCE_MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_PERFORMANCE_MODEL", "")
SFX_MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_SFX_MODEL", "")
SFX_CHECKPOINT_FINGERPRINT = os.environ.get("AIFILM_AUDIO_NODE_SFX_CHECKPOINT_FINGERPRINT", "")
SFX_LICENSE = os.environ.get("AIFILM_AUDIO_NODE_SFX_LICENSE", "")
AMBIENT_MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_AMBIENT_MODEL", "")
AMBIENT_LICENSE = os.environ.get("AIFILM_AUDIO_NODE_AMBIENT_LICENSE", "")
AMBIENT_CHECKPOINT_SHA256 = os.environ.get("AIFILM_AUDIO_NODE_AMBIENT_CHECKPOINT_SHA256", "")
AMBIENT_ADAPTER_SHA256 = os.environ.get("AIFILM_AUDIO_NODE_AMBIENT_ADAPTER_SHA256", "")
MMAUDIO_CHECKPOINT_SHA256 = os.environ.get("AIFILM_MMAUDIO_CHECKPOINT_SHA256", "")
MMAUDIO_REPO_COMMIT = os.environ.get("AIFILM_MMAUDIO_REPO_COMMIT", "")
FFMPEG = os.environ.get("AIFILM_AUDIO_NODE_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get(
    "AIFILM_AUDIO_NODE_FFPROBE",
    str(Path(FFMPEG).with_name("ffprobe.exe")) if Path(FFMPEG).suffix else "ffprobe",
)
jobs: dict[str, dict[str, Any]] = {}
# ``ambient`` is deliberately separate from ``sfx``.  MMAudio SFX is
# video-bound and CC-BY-NC; Stable Audio is text-only ambience/transition
# material and must never inherit MMAudio's provenance claim.
AUDIO_KINDS = ("tts", "music", "sfx", "performance", "ambient")
STABLE_AUDIO_MODEL = "stabilityai/stable-audio-open-1.0"
STABLE_AUDIO_LICENSE = "Stability AI Community License"
# All configured renderers use the same 5090.  Serializing execution prevents
# independently valid jobs from evicting each other's model weights or OOMing.
GPU_GENERATION_LOCK = asyncio.Lock()
_PROBE_LOCK = threading.Lock()
_PROBE_CACHE: dict[str, tuple[float, tuple[str, ...], dict[str, Any] | None]] = {}
_PROBE_CACHE_TTL_SEC = 300
_MAX_JSON_BYTES = 129 * 1024 * 1024
app = FastAPI(title="ai-film private audio node", docs_url=None, redoc_url=None, openapi_url=None)
_SAFE_SUBPROCESS_ENV_NAMES = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "CUDA_PATH",
        "HF_HOME",
        "HF_HUB_CACHE",
        "LOCALAPPDATA",
        "NUMBER_OF_PROCESSORS",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERNAME",
        "USERPROFILE",
        "WINDIR",
    }
)
_SAFE_MMAUDIO_ENV_NAMES = frozenset(
    {
        "AIFILM_MMAUDIO_CHECKPOINT_SHA256",
        "AIFILM_MMAUDIO_PYTHON",
        "AIFILM_MMAUDIO_REPO_COMMIT",
        "AIFILM_MMAUDIO_RUNNER",
        "AIFILM_MMAUDIO_SYNCHFORMER_SHA256",
        "AIFILM_MMAUDIO_VAE_SHA256",
    }
)
_SHELL_EXECUTABLES = frozenset(
    {"bash", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "sh", "zsh"}
)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _adapter_environment() -> dict[str, str]:
    """Keep node credentials out of model adapters and their dependencies."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in _SAFE_SUBPROCESS_ENV_NAMES
        or key.upper() in _SAFE_MMAUDIO_ENV_NAMES
        or key.upper().startswith(("CUDA_", "NVIDIA_"))
    }
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    if not environment.get("USERNAME") and environment.get("USERPROFILE"):
        environment["USERNAME"] = (
            environment["USERPROFILE"].replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        )
    return environment


def _adapter_failure_code(output: str | bytes | None, returncode: int) -> str:
    """Extract only a fixed adapter error code; never expose prompts or command lines."""
    text = (
        output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output or "")
    )
    for line in reversed(text.splitlines()):
        try:
            report = json.loads(line)
        except json.JSONDecodeError:
            continue
        error = report.get("error") if isinstance(report, dict) else None
        if isinstance(error, str):
            match = re.fullmatch(r"[a-z_]+ failed: ([a-z0-9_]+)", error)
            if match:
                return match.group(1)
    return f"adapter_exit_{returncode}"


def _auth(value: str | None) -> None:
    if (
        len(TOKEN) < 24
        or not value
        or not value.startswith("Bearer ")
        or not hmac.compare_digest(value[7:], TOKEN)
    ):
        raise HTTPException(401, "unauthorized")


@app.middleware("http")
async def authenticate_before_body_parsing(request: Request, call_next):
    try:
        _auth(request.headers.get("authorization"))
    except HTTPException:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    if request.method in {"POST", "PUT", "PATCH"}:
        if request.headers.get("transfer-encoding"):
            return JSONResponse({"detail": "content-length required"}, status_code=411)
        raw_length = request.headers.get("content-length")
        try:
            content_length = int(raw_length or "")
        except ValueError:
            return JSONResponse({"detail": "valid content-length required"}, status_code=411)
        if content_length <= 0:
            return JSONResponse({"detail": "non-empty body required"}, status_code=411)
        if content_length > _MAX_JSON_BYTES:
            return JSONResponse({"detail": "request body too large"}, status_code=413)
    return await call_next(request)


def _available(kind: str) -> bool:
    if kind == "tts":
        try:
            import qwen_tts  # noqa: F401
            import soundfile  # noqa: F401
            import torch  # noqa: F401

            return True
        except Exception:
            return False
    if kind == "sfx":
        try:
            command = _command_template(kind)
        except RuntimeError:
            return False
        if shutil.which(command[0]) is None:
            return False
        return _sfx_renderer_bound(command) and _sfx_probe_ok()
    if kind == "ambient":
        try:
            command = _command_template(kind)
        except RuntimeError:
            return False
        return bool(
            shutil.which(command[0])
            and AMBIENT_MODEL_ID == STABLE_AUDIO_MODEL
            and AMBIENT_LICENSE == STABLE_AUDIO_LICENSE
            and _ambient_renderer_bound(command)
            and _ambient_probe_ok()
        )
    try:
        _command_template(kind)
        return True
    except RuntimeError:
        return False


def _tts_variant_available(variant: str) -> bool:
    if not _available("tts"):
        return False
    if variant == "voice_design":
        return bool(MODEL_ID and MODEL_PATH)
    if variant == "custom_1_7b":
        return bool(CUSTOM_1_7B_MODEL_ID and CUSTOM_1_7B_MODEL_PATH)
    if variant == "custom_0_6b":
        return bool(CUSTOM_0_6B_MODEL_ID and CUSTOM_0_6B_MODEL_PATH)
    return False


def _cached_probe(
    name: str, command: list[str], fingerprint: tuple[str, ...], *, timeout: int
) -> dict[str, Any] | None:
    now = time.monotonic()
    with _PROBE_LOCK:
        cached = _PROBE_CACHE.get(name)
        if cached and cached[1] == fingerprint and now - cached[0] < _PROBE_CACHE_TTL_SEC:
            return cached[2]
        try:
            proc = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_adapter_environment(),
            )
            report = json.loads(proc.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            report = None
        valid_report = report if isinstance(report, dict) else None
        _PROBE_CACHE[name] = (time.monotonic(), fingerprint, valid_report)
        return valid_report


def _probe_command(env_name: str) -> list[str] | None:
    raw = os.environ.get(env_name, "")
    try:
        command = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
        or shutil.which(command[0]) is None
    ):
        return None
    return command


def _trusted_argv(command: list[str], *, required_placeholders: set[str]) -> bool:
    executable = command[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if executable in _SHELL_EXECUTABLES:
        return False
    placeholders = {
        item
        for item in command
        if item.startswith("{") and item.endswith("}") and item.count("{") == 1
    }
    return required_placeholders.issubset(placeholders)


def _sfx_renderer_bound(renderer: list[str]) -> bool:
    probe = _probe_command("AIFILM_AUDIO_NODE_SFX_PROBE_ARGV")
    if probe is None or len(probe) != 5 or len(renderer) != 14:
        return False
    expected_renderer = [
        probe[0],
        probe[1],
        "--repo",
        probe[3],
        "--prompt",
        "{prompt}",
        "--duration",
        "{duration}",
        "--seed",
        "{seed}",
        "--out",
        "{out}",
        "--video",
        "{video}",
    ]
    return bool(
        probe[2:] == ["--repo", probe[3], "--probe"]
        and renderer == expected_renderer
        and probe[1].replace("\\", "/").rsplit("/", 1)[-1] == "mmaudio_adapter.py"
        and _trusted_argv(
            renderer,
            required_placeholders={"{prompt}", "{duration}", "{seed}", "{out}", "{video}"},
        )
    )


def _ambient_renderer_bound(renderer: list[str]) -> bool:
    probe = _probe_command("AIFILM_AUDIO_NODE_AMBIENT_PROBE_ARGV")
    if probe is None or len(renderer) != 18 or len(probe) != 12:
        return False
    model_root, checkpoint, adapter = probe[3], probe[5], probe[7]
    expected_renderer = [
        probe[0],
        adapter,
        "--model-root",
        model_root,
        "--checkpoint",
        checkpoint,
        "--expected-checkpoint-sha256",
        AMBIENT_CHECKPOINT_SHA256.lower(),
        "--expected-adapter-sha256",
        AMBIENT_ADAPTER_SHA256.lower(),
        "--prompt",
        "{prompt}",
        "--duration",
        "{duration}",
        "--seed",
        "{seed}",
        "--out",
        "{out}",
    ]
    expected_probe = [
        probe[0],
        probe[1],
        "--model-root",
        model_root,
        "--checkpoint",
        checkpoint,
        "--adapter",
        adapter,
        "--model",
        STABLE_AUDIO_MODEL,
        "--license",
        STABLE_AUDIO_LICENSE,
    ]
    return bool(
        renderer == expected_renderer
        and probe == expected_probe
        and adapter.replace("\\", "/").rsplit("/", 1)[-1] == "stable_audio_adapter.py"
        and probe[1].replace("\\", "/").rsplit("/", 1)[-1] == "stable_audio_probe.py"
    )


def _sfx_probe_ok() -> bool:
    command = _probe_command("AIFILM_AUDIO_NODE_SFX_PROBE_ARGV")
    if (
        command is None
        or SFX_MODEL_ID != "hkchengrex/MMAudio-large-44k-v2"
        or SFX_LICENSE != "CC-BY-NC-4.0"
        or not _is_sha256(SFX_CHECKPOINT_FINGERPRINT)
        or SFX_CHECKPOINT_FINGERPRINT.lower() != MMAUDIO_CHECKPOINT_SHA256.lower()
        or len(MMAUDIO_REPO_COMMIT) != 40
    ):
        return False
    fingerprint = (
        *command,
        SFX_MODEL_ID,
        SFX_LICENSE,
        SFX_CHECKPOINT_FINGERPRINT.lower(),
        MMAUDIO_REPO_COMMIT.lower(),
    )
    report = _cached_probe("sfx", command, fingerprint, timeout=60)
    valid = bool(
        isinstance(report, dict)
        and report.get("ok") is True
        and report.get("model") == SFX_MODEL_ID
        and report.get("license") == SFX_LICENSE
        and report.get("checkpoint_sha256") == SFX_CHECKPOINT_FINGERPRINT.lower()
        and report.get("repo_commit") == MMAUDIO_REPO_COMMIT.lower()
    )
    return valid


def _ambient_probe_ok() -> bool:
    command = _probe_command("AIFILM_AUDIO_NODE_AMBIENT_PROBE_ARGV")
    if (
        command is None
        or AMBIENT_MODEL_ID != STABLE_AUDIO_MODEL
        or AMBIENT_LICENSE != STABLE_AUDIO_LICENSE
        or not _is_sha256(AMBIENT_CHECKPOINT_SHA256)
        or not _is_sha256(AMBIENT_ADAPTER_SHA256)
    ):
        return False
    fingerprint = (
        *command,
        AMBIENT_MODEL_ID,
        AMBIENT_LICENSE,
        AMBIENT_CHECKPOINT_SHA256.lower(),
        AMBIENT_ADAPTER_SHA256.lower(),
    )
    report = _cached_probe("ambient", command, fingerprint, timeout=60)
    valid = bool(
        isinstance(report, dict)
        and report.get("ok") is True
        and report.get("model") == AMBIENT_MODEL_ID
        and report.get("license") == AMBIENT_LICENSE
        and report.get("checkpoint_sha256") == AMBIENT_CHECKPOINT_SHA256.lower()
        and report.get("adapter_sha256") == AMBIENT_ADAPTER_SHA256.lower()
    )
    return valid


def _command_template(kind: str) -> list[str]:
    raw = os.environ.get(f"AIFILM_AUDIO_NODE_{kind.upper()}_ARGV", "")
    if not raw:
        raise RuntimeError(f"{kind} model is not configured")
    try:
        template = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{kind} argv is invalid") from exc
    if (
        not isinstance(template, list)
        or not template
        or not all(isinstance(item, str) for item in template)
    ):
        raise RuntimeError(f"{kind} argv is invalid")
    return template


def _music_batch_template() -> list[str]:
    raw = os.environ.get("AIFILM_AUDIO_NODE_MUSIC_BATCH_ARGV", "")
    if not raw:
        raise RuntimeError("music batch model is not configured")
    try:
        template = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("music batch argv is invalid") from exc
    if (
        not isinstance(template, list)
        or not template
        or not all(isinstance(item, str) for item in template)
    ):
        raise RuntimeError("music batch argv is invalid")
    return template


def _gpu_health() -> dict[str, Any]:
    """Report capacity only; never expose inputs, tokens, or filesystem paths."""
    try:
        import torch

        if not torch.cuda.is_available():
            return {"available": False}
        free, total = torch.cuda.mem_get_info(0)
        report = {
            "available": True,
            "name": torch.cuda.get_device_name(0),
            "cuda": torch.version.cuda,
            "free_vram_mib": int(free // 1024**2),
            "total_vram_mib": int(total // 1024**2),
        }
        try:
            driver = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            if re.fullmatch(r"[0-9][0-9.]{0,30}", driver):
                report["driver"] = driver
        except (OSError, subprocess.SubprocessError):
            pass
        return report
    except Exception:
        return {"available": False}


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    report = {
        "ok": True,
        "node": "private-lan",
        "models": {kind: _available(kind) for kind in AUDIO_KINDS},
        "tts_variants": {
            variant: _tts_variant_available(variant)
            for variant in ("voice_design", "custom_1_7b", "custom_0_6b")
        },
        "music_batch": bool(os.environ.get("AIFILM_AUDIO_NODE_MUSIC_BATCH_ARGV", "").strip()),
        "music_reference_upload": True,
        "model": MODEL_ID,
        "music_model": MUSIC_MODEL_ID,
        "music_checkpoint_fingerprint": MUSIC_CHECKPOINT_FINGERPRINT,
        "sfx_model": SFX_MODEL_ID,
        "sfx_checkpoint_fingerprint": SFX_CHECKPOINT_FINGERPRINT,
        "sfx_license": SFX_LICENSE,
        "ambient_model": AMBIENT_MODEL_ID,
        "ambient_license": AMBIENT_LICENSE,
        "ambient_checkpoint_sha256": AMBIENT_CHECKPOINT_SHA256,
        "ambient_adapter_sha256": AMBIENT_ADAPTER_SHA256,
        "gpu": _gpu_health(),
    }
    if PERFORMANCE_MODEL_ID:
        report["performance_model"] = PERFORMANCE_MODEL_ID
    return report


def _normalize(source: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-i",
            str(source),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )


def _store_music_reference(raw: bytes) -> dict[str, str]:
    if len(raw) < 512 or len(raw) > 64 * 1024 * 1024 or raw[:4] != b"RIFF":
        raise HTTPException(422, "invalid music reference WAV")
    source_hash = hashlib.sha256(raw).hexdigest()
    REFERENCES.mkdir(parents=True, exist_ok=True)
    source = REFERENCES / f".{uuid.uuid4().hex}.wav"
    target = REFERENCES / f"{source_hash}.wav"
    try:
        source.write_bytes(raw)
        with wave.open(str(source), "rb") as handle:
            if (
                handle.getnchannels() != 2
                or handle.getsampwidth() != 2
                or handle.getframerate() != 44100
                or handle.getnframes() <= 0
            ):
                raise HTTPException(422, "music reference must be 44.1kHz stereo PCM s16le")
        if target.exists():
            if (
                target.is_symlink()
                or not target.is_file()
                or hashlib.sha256(target.read_bytes()).hexdigest() != source_hash
            ):
                raise HTTPException(409, "stored music reference hash mismatch")
        else:
            source.replace(target)
    except Exception:
        source.unlink(missing_ok=True)
        raise
    source.unlink(missing_ok=True)
    return {"reference_id": source_hash, "source_sha256": source_hash}


@app.post("/v1/music-reference")
async def upload_music_reference(
    request: Request, authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _auth(authorization)
    return _store_music_reference(await request.body())


def _store_sfx_source(raw: bytes) -> dict[str, str]:
    if len(raw) < 1024 or len(raw) > 128 * 1024 * 1024:
        raise HTTPException(422, "invalid SFX source video")
    source_hash = hashlib.sha256(raw).hexdigest()
    SFX_SOURCES.mkdir(parents=True, exist_ok=True)
    temporary = SFX_SOURCES / f".{uuid.uuid4().hex}.mp4"
    target = SFX_SOURCES / f"{source_hash}.mp4"
    try:
        temporary.write_bytes(raw)
        probe = subprocess.run(
            [
                FFPROBE,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type:format=duration",
                "-of",
                "json",
                str(temporary),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        report = json.loads(probe.stdout)
        streams = report.get("streams") if isinstance(report, dict) else None
        duration = float((report.get("format") or {}).get("duration") or 0)
        if (
            not isinstance(streams, list)
            or not streams
            or streams[0].get("codec_type") != "video"
            or not 0 < duration <= 30
        ):
            raise HTTPException(422, "SFX source must be a 0-30 second video")
        if target.exists():
            if (
                target.is_symlink()
                or not target.is_file()
                or hashlib.sha256(target.read_bytes()).hexdigest() != source_hash
            ):
                raise HTTPException(409, "stored SFX source hash mismatch")
        else:
            temporary.replace(target)
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(422, "invalid SFX source video") from exc
    temporary.unlink(missing_ok=True)
    return {"source_id": source_hash, "source_sha256": source_hash}


@app.post("/v1/sfx-source")
async def upload_sfx_source(
    request: Request, authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _auth(authorization)
    try:
        content_length = int(request.headers.get("content-length") or 0)
    except ValueError as exc:
        raise HTTPException(413, "invalid SFX source content length") from exc
    if not 1024 <= content_length <= 128 * 1024 * 1024:
        raise HTTPException(413, "SFX source content length is required and bounded")
    return _store_sfx_source(await request.body())


def _run_tts(payload: dict[str, Any], out: Path) -> None:
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    text = str(payload.get("text") or "").strip()
    if not text or len(text) > 10000:
        raise ValueError("text must contain 1-10000 characters")
    variant = str(payload.get("model_variant") or "voice_design")
    if variant == "voice_design":
        model_id, model_path = MODEL_ID, MODEL_PATH
    elif variant == "custom_1_7b" and CUSTOM_1_7B_MODEL_ID and CUSTOM_1_7B_MODEL_PATH:
        model_id, model_path = CUSTOM_1_7B_MODEL_ID, CUSTOM_1_7B_MODEL_PATH
    elif variant == "custom_0_6b" and CUSTOM_0_6B_MODEL_ID and CUSTOM_0_6B_MODEL_PATH:
        model_id, model_path = CUSTOM_0_6B_MODEL_ID, CUSTOM_0_6B_MODEL_PATH
    else:
        raise ValueError("requested Qwen model variant is unavailable")
    voice = str(payload.get("voice_profile_id") or "Vivian")
    language = str(payload.get("language") or "Chinese")
    instruction = str((payload.get("performance") or {}).get("instruction") or "")[:1000]
    model = Qwen3TTSModel.from_pretrained(model_path, device_map="cuda:0", dtype=torch.bfloat16)
    wavs, sr = (
        model.generate_voice_design(text=text, language=language, instruct=instruction)
        if "VoiceDesign" in model_id
        else model.generate_custom_voice(
            text=text, language=language, speaker=voice, instruct=instruction
        )
    )
    raw = out.with_suffix(".raw.wav")
    sf.write(raw, wavs[0], sr)
    _normalize(raw, out)
    raw.unlink(missing_ok=True)


def _run_command(kind: str, payload: dict[str, Any], out: Path) -> None:
    template = _command_template(kind)
    source = out.with_suffix(".source.wav")
    values = {
        "out": str(source),
        "prompt": str(payload.get("prompt") or ""),
        "duration": str(payload.get("duration") or 5),
        "seed": str(payload.get("seed") or 0),
        "video": str(payload.get("source_video") or ""),
    }
    command = [item.format(**values) for item in template]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=900,
            env=_adapter_environment(),
        )
    except subprocess.CalledProcessError as exc:
        code = _adapter_failure_code(exc.stderr, exc.returncode)
        print(f"{kind} adapter failed: {code}", file=sys.stderr)
        raise
    _normalize(source, out)
    source.unlink(missing_ok=True)


def _run_music_batch(payload: dict[str, Any], out_dir: Path) -> list[Path]:
    """Run one trusted ACE adapter with an ephemeral JSON request."""
    template = _music_batch_template()
    out_dir.mkdir(parents=True, exist_ok=True)
    request_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=out_dir.parent,
            prefix=".music-batch-",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False)
            request_path = Path(handle.name)
        values = {"request_json": str(request_path), "out_dir": str(out_dir)}
        command = [item.format(**values) for item in template]
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=1800,
            env=_adapter_environment(),
        )
    finally:
        if request_path is not None:
            request_path.unlink(missing_ok=True)

    batch_size = int(payload["batch_size"])
    generated = [out_dir / f"{index:02d}.wav" for index in range(batch_size)]
    if not all(path.is_file() for path in generated):
        raise RuntimeError("music batch adapter returned incomplete outputs")
    normalized: list[Path] = []
    for index, source in enumerate(generated):
        target = out_dir / f"{index:02d}.normalized.wav"
        _normalize(source, target)
        source.unlink(missing_ok=True)
        target.replace(source)
        normalized.append(source)
    return normalized


async def _execute(job_id: str, kind: str, payload: dict[str, Any]) -> None:
    job = jobs[job_id]
    target = JOBS / f"{job_id}.wav"
    try:
        JOBS.mkdir(parents=True, exist_ok=True)
        async with GPU_GENERATION_LOCK:
            job["status"] = "running"
            if kind == "tts":
                await asyncio.to_thread(_run_tts, payload, target)
            else:
                await asyncio.to_thread(_run_command, kind, payload, target)
        job.update(
            {
                "status": "completed",
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "path": str(target),
            }
        )
    except Exception as exc:
        target.unlink(missing_ok=True)
        target.with_suffix(".raw.wav").unlink(missing_ok=True)
        target.with_suffix(".source.wav").unlink(missing_ok=True)
        job.update({"status": "failed", "error": type(exc).__name__})


async def _execute_music_batch(job_id: str, payload: dict[str, Any]) -> None:
    job = jobs[job_id]
    target_dir = JOBS / job_id
    try:
        JOBS.mkdir(parents=True, exist_ok=True)
        async with GPU_GENERATION_LOCK:
            job["status"] = "running"
            paths = await asyncio.to_thread(_run_music_batch, payload, target_dir)
        seeds = [int(seed) for seed in payload["seeds"]]
        artifacts = [
            {
                "index": index,
                "seed": seeds[index],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for index, path in enumerate(paths)
        ]
        job.update(
            {
                "status": "completed",
                "model": MUSIC_MODEL_ID,
                "checkpoint_fingerprint": MUSIC_CHECKPOINT_FINGERPRINT,
                "artifacts": artifacts,
            }
        )
    except Exception as exc:
        if target_dir.is_dir():
            for path in target_dir.glob("*"):
                if path.is_file():
                    path.unlink(missing_ok=True)
            target_dir.rmdir()
        job.update({"status": "failed", "error": type(exc).__name__})


def _create(kind: str, payload: dict[str, Any]) -> dict[str, str]:
    if not _available(kind):
        raise HTTPException(503, f"{kind} model is unavailable")
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "queued", "kind": kind, "node": "private-lan"}
    if kind == "ambient":
        jobs[job_id].update(
            {
                "production_eligible": False,
                "usage_scope": "stable_audio_community_license_candidate",
                "model": AMBIENT_MODEL_ID,
                "license": AMBIENT_LICENSE,
                "checkpoint_sha256": AMBIENT_CHECKPOINT_SHA256.lower(),
                "adapter_sha256": AMBIENT_ADAPTER_SHA256.lower(),
            }
        )
    if kind == "sfx":
        jobs[job_id].update(
            {
                "production_eligible": False,
                "usage_scope": "noncommercial_internal_research",
                "model": SFX_MODEL_ID,
                "license": SFX_LICENSE,
                "checkpoint_fingerprint": SFX_CHECKPOINT_FINGERPRINT.lower(),
            }
        )
    asyncio.create_task(_execute(job_id, kind, payload))
    return {"job_id": job_id, "status": "queued"}


@app.post("/v1/{kind}")
async def create(
    kind: str, payload: dict[str, Any], authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _auth(authorization)
    if kind == "music-batch":
        return await create_music_batch(payload, authorization)
    if kind not in AUDIO_KINDS:
        raise HTTPException(404, "unknown audio kind")
    if kind == "sfx":
        try:
            prompt = str(payload.get("prompt") or "").strip()
            duration = float(payload.get("duration"))
            seed = payload.get("seed")
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "invalid SFX request") from exc
        if not 1 <= len(prompt) <= 512:
            raise HTTPException(422, "SFX prompt must contain 1-512 characters")
        if not 1 <= duration <= 30:
            raise HTTPException(422, "SFX duration must be between 1 and 30 seconds")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise HTTPException(422, "SFX seed must be an integer")
        if payload.get("noncommercial_research_ok") is not True:
            raise HTTPException(422, "MMAudio requires explicit non-commercial research approval")
        if (
            SFX_MODEL_ID != "hkchengrex/MMAudio-large-44k-v2"
            or SFX_LICENSE != "CC-BY-NC-4.0"
            or not _is_sha256(SFX_CHECKPOINT_FINGERPRINT)
            or SFX_CHECKPOINT_FINGERPRINT.lower() != MMAUDIO_CHECKPOINT_SHA256.lower()
            or not _sfx_probe_ok()
        ):
            raise HTTPException(503, "MMAudio provenance is not configured")
        source_id = str(payload.pop("source_video_id", "") or "")
        if source_id:
            source = SFX_SOURCES / f"{source_id}.mp4"
            if (
                not _is_sha256(source_id)
                or source.is_symlink()
                or not source.is_file()
                or hashlib.sha256(source.read_bytes()).hexdigest() != source_id
            ):
                raise HTTPException(422, "SFX source video is unavailable")
            payload = dict(payload)
            payload["source_video"] = str(source)
    if kind == "ambient":
        try:
            prompt = str(payload.get("prompt") or "").strip()
            duration = float(payload.get("duration"))
            seed = payload.get("seed")
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "invalid ambient request") from exc
        if not 1 <= len(prompt) <= 512:
            raise HTTPException(422, "ambient prompt must contain 1-512 characters")
        if not 1 <= duration <= 47:
            raise HTTPException(422, "ambient duration must be between 1 and 47 seconds")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise HTTPException(422, "ambient seed must be an integer")
        # The caller must explicitly acknowledge the model-card use boundary.
        # Acceptance of a gated download is not evidence of commercial rights.
        if payload.get("stable_audio_candidate_only") is not True:
            raise HTTPException(
                422, "Stable Audio output is candidate-only pending human/license review"
            )
        if AMBIENT_MODEL_ID != STABLE_AUDIO_MODEL or AMBIENT_LICENSE != STABLE_AUDIO_LICENSE:
            raise HTTPException(503, "Stable Audio provenance is not configured")
    return _create(kind, payload)


@app.post("/v1/music-batch")
async def create_music_batch(
    payload: dict[str, Any], authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _auth(authorization)
    try:
        prompt = str(payload.get("prompt") or "").strip()
        batch_size = int(payload.get("batch_size") or 0)
        seeds = [int(seed) for seed in payload.get("seeds") or []]
        duration = float(payload.get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "invalid music batch request") from exc
    if not 1 <= len(prompt) <= 512:
        raise HTTPException(422, "prompt must contain 1-512 characters")
    if not 1 <= batch_size <= 8:
        raise HTTPException(422, "batch_size must be between 1 and 8")
    if len(seeds) != batch_size or len(set(seeds)) != batch_size:
        raise HTTPException(422, "seeds must contain one unique seed per batch item")
    if not 10 <= duration <= 600:
        raise HTTPException(422, "duration must be between 10 and 600 seconds")
    task_type = str(payload.get("task_type") or "text2music")
    if task_type not in {"text2music", "cover", "repaint"}:
        raise HTTPException(422, "invalid ACE-Step task type")
    payload = dict(payload)
    if task_type == "repaint":
        try:
            repainting_start = float(payload.get("repainting_start"))
            repainting_end = float(payload.get("repainting_end"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "repaint requires numeric start and end") from exc
        if repainting_start < 0 or repainting_end <= repainting_start or repainting_end > duration:
            raise HTTPException(422, "repaint window must be within requested duration")
        payload["repainting_start"] = repainting_start
        payload["repainting_end"] = repainting_end
    else:
        payload.pop("repainting_start", None)
        payload.pop("repainting_end", None)
    if task_type in {"cover", "repaint"}:
        reference_id = str(payload.pop("reference_audio_id", "") or "")
        reference_path = REFERENCES / f"{reference_id}.wav"
        if (
            len(reference_id) != 64
            or any(character not in "0123456789abcdef" for character in reference_id)
            or not reference_path.is_file()
        ):
            raise HTTPException(422, "cover/repaint requires an uploaded reference")
        payload["reference_audio"] = str(reference_path)
    else:
        payload.pop("reference_audio_id", None)
    try:
        _music_batch_template()
    except RuntimeError as exc:
        raise HTTPException(503, "music batch model is unavailable") from exc
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "queued", "kind": "music-batch", "node": "private-lan"}
    asyncio.create_task(_execute_music_batch(job_id, payload))
    return {"job_id": job_id, "status": "queued"}


@app.get("/v1/jobs/{job_id}")
def job(job_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    if job_id not in jobs:
        raise HTTPException(404, "job not found")
    return {key: value for key, value in jobs[job_id].items() if key not in {"path"}}


@app.get("/v1/jobs/{job_id}/audio")
def audio(job_id: str, authorization: str | None = Header(default=None)) -> FileResponse:
    _auth(authorization)
    job = jobs.get(job_id) or {}
    path = Path(str(job.get("path") or ""))
    if job.get("status") != "completed" or not path.is_file():
        raise HTTPException(409, "audio is not ready")
    return FileResponse(path, media_type="audio/wav", filename=f"{job_id}.wav")


@app.get("/v1/jobs/{job_id}/audio/{index}")
def batch_audio(
    job_id: str, index: int, authorization: str | None = Header(default=None)
) -> FileResponse:
    _auth(authorization)
    job = jobs.get(job_id) or {}
    artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
    if (
        job.get("status") != "completed"
        or index < 0
        or index >= len(artifacts)
        or int(artifacts[index].get("index", -1)) != index
    ):
        raise HTTPException(409, "batch audio is not ready")
    path = JOBS / job_id / f"{index:02d}.wav"
    if not path.is_file():
        raise HTTPException(409, "batch audio is not ready")
    return FileResponse(path, media_type="audio/wav", filename=f"{job_id}-{index:02d}.wav")
