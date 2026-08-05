#!/usr/bin/env python3
"""Multi-backend TTS for ai-film-grok.

Backends (human-likeness roughly ↑):
  minimax   — MiniMax Speech 2.6/2.8 HD (strong CN + emotion tags; needs MINIMAX_API_KEY)
  fish      — Fish Audio API (s2.1-pro / free tier)
  grok      — Grok TTS via OAuth (api.x.ai /v1/tts; speech tags; opt-in, SuperGrok)
  voicebox  — local open-source studio (https://github.com/jamiepine/voicebox) on :17493
  mimo      — Xiaomi MiMo V2.5 TTS (limited-time free; built-in Chinese voices) **film default**
  edge      — Microsoft Edge Neural (free explicit fallback; more synthetic)
  cosyvoice-local — explicit local CosyVoice adapter (never selected automatically)
  kokoro-local — explicit offline Kokoro Chinese adapter (never selected automatically)
  chatterbox-local — explicit offline multilingual Chatterbox adapter (never selected automatically)
  piper-local — explicit offline Piper Chinese adapter (never selected automatically)
  external  — arbitrary approved CLI via AIFILM_TTS_ARGV

Env / config.env:
  AIFILM_TTS_BACKEND=mimo|auto|minimax|fish|voicebox|edge|external|cosyvoice-local|kokoro-local|grok
  MIMO_API_KEY=...  MIMO_TTS_VOICE=冰糖  MIMO_TTS_MODEL=mimo-v2.5-tts
  AIFILM_GROK_TTS_VOICE=eve   # or ara, leo, carina, zagan, …
  AIFILM_GROK_TTS_LANGUAGE=zh
  FISH_API_KEY=...  FISH_VOICE_ID=...  FISH_MODEL=s2.1-pro-free
  MINIMAX_API_KEY=...  MINIMAX_VOICE_ID=Chinese (Mandarin)_Lyrical_Voice
  MINIMAX_MODEL=speech-2.6-hd
  VOICEBOX_BASE_URL=http://127.0.0.1:17493
  VOICEBOX_PROFILE=<profile name or id>
  VOICEBOX_LANGUAGE=zh
  AIFILM_TTS_ARGV='["python","/path/infer.py","--text-file","{text_file}","--out","{out}"]'

Fallback (opt-in only; never silent cross-provider):
  tts_allow_network_fallback / --allow-network-fallback in auto mode:
    primary fail → voicebox (if ready) → edge
  AIFILM_TTS_VOICEBOX_FALLBACK=1: even explicit edge/minimax/fish may try voicebox once.

Note: auto never picks grok (keeps MiMo/local defaults for reproducible 中文说书).
Use --tts-backend grok or AIFILM_TTS_BACKEND=grok explicitly.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from stat import S_ISREG
from typing import Any

from config_loader import get_config
from performance_cue import compile_edge, compile_instruction, cue_hash, normalize_performance_cue
from security_policy import (
    SecurityPolicyError,
    atomic_write_bytes,
    atomic_write_text,
    expand_argv,
    minimal_subprocess_env,
    parse_argv_json,
)


class TTSError(RuntimeError):
    pass


TTS_BACKENDS = frozenset(
    {
        "auto",
        "mimo",
        "minimax",
        "fish",
        "voicebox",
        "edge",
        "external",
        "cosyvoice-local",
        "kokoro-local",
        "chatterbox-local",
        "piper-local",
        "grok",
        "qwen3",
        "higgs",
        "audio_node",
    }
)
MIMO_TTS_MODELS = frozenset(
    {"mimo-v2.5-tts", "mimo-v2.5-tts-voicedesign", "mimo-v2.5-tts-voiceclone"}
)
DEFAULT_VOICEBOX_URL = "http://127.0.0.1:17493"
# Built-in Grok voices (subset; full list via aifilm grok-oauth voices)
GROK_BUILTIN_VOICES = frozenset(
    {
        "eve",
        "ara",
        "leo",
        "rex",
        "sal",
        "carina",
        "zagan",
        "helix",
        "orion",
        "luna",
        "altair",
    }
)


def _load_config_env() -> None:
    """Compatibility hook for older callers; config loading is centralized now."""
    get_config()


def fish_api_key() -> str | None:
    return get_config().fish_api_key or None


def fish_voice_id() -> str | None:
    return get_config().fish_voice_id or None


def fish_model() -> str:
    return get_config().fish_model or "s2.1-pro-free"


def minimax_api_key() -> str | None:
    return get_config().minimax_api_key or None


def minimax_voice_id() -> str:
    return get_config().minimax_voice_id or "Chinese (Mandarin)_Lyrical_Voice"


def minimax_model() -> str:
    return get_config().minimax_model or "speech-2.6-hd"


def minimax_group_id() -> str | None:
    return get_config().minimax_group_id or None


def mimo_api_key() -> str | None:
    return get_config().mimo_api_key or None


def mimo_api_base() -> str:
    return (get_config().mimo_api_base or "https://api.xiaomimimo.com/v1").rstrip("/")


def mimo_tts_model() -> str:
    return get_config().mimo_tts_model or "mimo-v2.5-tts"


def mimo_tts_voice() -> str:
    return get_config().mimo_tts_voice or "冰糖"


def mimo_tts_style() -> str:
    return get_config().mimo_tts_style or "自然、电影感的中文旁白；保持原文，不改写。"


def mimo_tts_reference_audio() -> Path | None:
    raw = get_config().mimo_tts_reference_audio.strip()
    return Path(raw).expanduser() if raw else None


def _mimo_model_error(model: str) -> str | None:
    if model not in MIMO_TTS_MODELS:
        return f"unsupported MIMO_TTS_MODEL={model!r}; choose one of {sorted(MIMO_TTS_MODELS)}"
    return None


def _validated_mimo_reference_audio(reference: Path) -> tuple[bytes, str]:
    if reference.is_symlink():
        raise TTSError("MIMO_TTS_REFERENCE_AUDIO must not be a symbolic link")
    if reference.suffix.lower() not in {".mp3", ".wav"}:
        raise TTSError("MIMO_TTS_REFERENCE_AUDIO must be an MP3 or WAV file")
    try:
        metadata = reference.stat()
        reference_bytes = reference.read_bytes()
    except OSError as exc:
        raise TTSError(f"cannot read MIMO_TTS_REFERENCE_AUDIO: {exc}") from exc
    if not S_ISREG(metadata.st_mode):
        raise TTSError("MIMO_TTS_REFERENCE_AUDIO must be a regular file")
    if not reference_bytes or len(reference_bytes) > 7_500_000:
        raise TTSError("MIMO_TTS_REFERENCE_AUDIO must be non-empty and at most 7.5 MB")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(reference),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        duration = float((probe.stdout or "").strip())
    except ValueError:
        duration = 0.0
    if probe.returncode != 0 or duration <= 0:
        raise TTSError("MIMO_TTS_REFERENCE_AUDIO is not decodable audio")
    mime_type = "audio/mpeg" if reference.suffix.lower() == ".mp3" else "audio/wav"
    return reference_bytes, mime_type


def external_argv() -> list[str] | None:
    raw = get_config().tts_argv
    if raw and raw.strip():
        try:
            return parse_argv_json(raw, variable="AIFILM_TTS_ARGV")
        except SecurityPolicyError as exc:
            raise TTSError(str(exc)) from exc
    if os.environ.get("AIFILM_TTS_CMD"):
        raise TTSError(
            "AIFILM_TTS_CMD is disabled because shell templates are unsafe; use AIFILM_TTS_ARGV JSON"
        )
    return None


def cosyvoice_local_argv_configured() -> bool:
    """Whether argv invokes this checkout's local-only CosyVoice adapter."""
    argv = external_argv()
    if not argv or len(argv) < 2:
        return False
    adapter = (Path(__file__).resolve().parent / "adapters" / "cosyvoice_local_tts.py").resolve()
    try:
        configured = Path(argv[1]).expanduser().resolve()
    except OSError:
        return False
    return configured == adapter


def cosyvoice_local_model_label() -> str:
    """Expose the configured local CosyVoice variant in render provenance."""
    return (
        "CosyVoice-300M-SFT"
        if os.environ.get("COSYVOICE_MODE", "").strip().lower() == "sft"
        else "Fun-CosyVoice3-local"
    )


def kokoro_local_argv_configured() -> bool:
    """Whether argv invokes this checkout's offline Kokoro adapter."""
    argv = external_argv()
    if not argv or len(argv) < 2:
        return False
    adapter = (Path(__file__).resolve().parent / "adapters" / "kokoro_tts.py").resolve()
    try:
        configured = Path(argv[1]).expanduser().resolve()
    except OSError:
        return False
    return configured == adapter


def chatterbox_local_argv_configured() -> bool:
    """Whether argv invokes this checkout's offline Chatterbox adapter."""
    argv = external_argv()
    if not argv or len(argv) < 6:
        return False
    interpreter = Path(argv[0]).expanduser()
    if not interpreter.is_absolute():
        return False
    adapter = (Path(__file__).resolve().parent / "adapters" / "chatterbox_local_tts.py").resolve()
    trusted_python = (
        Path(__file__).resolve().parents[3]
        / ".local-runtimes"
        / "chatterbox-mac"
        / "bin"
        / "python"
    ).resolve()
    try:
        resolved_interpreter = interpreter.resolve()
        configured = Path(argv[1]).expanduser().resolve()
    except OSError:
        return False
    if resolved_interpreter != trusted_python or configured != adapter:
        return False
    option_argv = argv[2:]
    if len(option_argv) % 2:
        return False
    options: dict[str, str] = {}
    for index in range(0, len(option_argv), 2):
        name, value = option_argv[index : index + 2]
        if name in options:
            return False
        options[name] = value
    required = {"--text-file": "{text_file}", "--out": "{out}"}
    allowed = {**required, "--voice": "{voice}"}
    return all(options.get(name) == value for name, value in required.items()) and all(
        name in allowed and value == allowed[name] for name, value in options.items()
    )


def piper_local_argv_configured() -> bool:
    """Whether argv invokes the fixed Piper isolated runtime and adapter."""
    argv = external_argv()
    if not argv or len(argv) < 6:
        return False
    interpreter_path = Path(argv[0]).expanduser()
    if not interpreter_path.is_absolute():
        return False
    root = Path(__file__).resolve().parents[3]
    adapter = (Path(__file__).resolve().parent / "adapters" / "piper_local_tts.py").resolve()
    trusted_python = (root / ".local-runtimes" / "piper-mac" / "bin" / "python").resolve()
    try:
        interpreter = interpreter_path.resolve()
        configured = Path(argv[1]).expanduser().resolve()
    except OSError:
        return False
    if interpreter != trusted_python or configured != adapter:
        return False
    option_argv = argv[2:]
    if len(option_argv) % 2:
        return False
    options: dict[str, str] = {}
    for index in range(0, len(option_argv), 2):
        name, value = option_argv[index : index + 2]
        if name in options:
            return False
        options[name] = value
    return options == {"--text-file": "{text_file}", "--out": "{out}", "--voice": "{voice}"}


def external_tts_subprocess_env() -> dict[str, str]:
    """Pass CosyVoice's non-secret local render settings only to its own adapter."""
    env = minimal_subprocess_env()
    if cosyvoice_local_argv_configured():
        for name in (
            "COSYVOICE_ROOT",
            "COSYVOICE_MODEL_DIR",
            "COSYVOICE_REF_WAV",
            "COSYVOICE_PROMPT_TEXT",
            "COSYVOICE_MODE",
            "COSYVOICE_SPEAKER",
            "COSYVOICE_TEXT_FRONTEND",
        ):
            value = os.environ.get(name)
            if value:
                env[name] = value
    if kokoro_local_argv_configured():
        for name in ("KOKORO_VOICE", "KOKORO_DEVICE", "HF_HOME"):
            value = os.environ.get(name)
            if value:
                env[name] = value
    if chatterbox_local_argv_configured():
        for name in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
            env.pop(name, None)
        env["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{os.defpath}"
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        for name in ("CHATTERBOX_DEVICE", "CHATTERBOX_LANGUAGE", "HF_HOME"):
            value = os.environ.get(name)
            if value:
                env[name] = value
    if piper_local_argv_configured():
        for name in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
            env.pop(name, None)
        env["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{os.defpath}"
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["HF_DATASETS_OFFLINE"] = "1"
        for name in ("PIPER_VOICE_DIR", "PIPER_MODEL", "PIPER_CONFIG", "PIPER_BINARY"):
            value = os.environ.get(name)
            if value:
                env[name] = value
    return env


def external_tts_timeout() -> int:
    """Allow one cold local model load without relaxing cloud adapter limits."""
    return (
        600
        if (
            cosyvoice_local_argv_configured()
            or kokoro_local_argv_configured()
            or chatterbox_local_argv_configured()
            or piper_local_argv_configured()
        )
        else 300
    )


def strict_voice_enabled() -> bool:
    return get_config().tts_strict_voice


def voicebox_fallback_enabled() -> bool:
    """Opt-in: on explicit backend failure, try local Voicebox once."""
    return get_config().tts_voicebox_fallback


def voicebox_base_url() -> str:
    return (get_config().voicebox_base_url or DEFAULT_VOICEBOX_URL).rstrip("/")


def voicebox_profile() -> str | None:
    raw = (get_config().voicebox_profile or "").strip()
    return raw or None


def voicebox_language() -> str:
    return (get_config().voicebox_language or "zh").strip() or "zh"


def voicebox_engine() -> str | None:
    eng = (get_config().voicebox_engine or "").strip()
    return eng or None


def _voicebox_http_json(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: float = 15,
) -> Any:
    url = f"{voicebox_base_url()}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:600]
        raise TTSError(f"Voicebox HTTP {exc.code} {path}: {err}") from exc
    except Exception as exc:
        raise TTSError(
            f"Voicebox unreachable at {voicebox_base_url()}: {exc}. "
            "Start the Voicebox app (API default http://127.0.0.1:17493)."
        ) from exc


def probe_voicebox() -> dict[str, Any]:
    """Lightweight readiness: /health + at least one profile; resolve default if set."""
    try:
        _voicebox_http_json("GET", "/health", timeout=3)
    except TTSError as exc:
        return {"ok": False, "error": str(exc), "profile_id": None, "profile_name": None}
    try:
        profiles = _voicebox_http_json("GET", "/profiles", timeout=8)
    except TTSError as exc:
        return {"ok": False, "error": str(exc), "profile_id": None, "profile_name": None}
    if not isinstance(profiles, list) or not profiles:
        return {
            "ok": False,
            "error": "Voicebox has no profiles — create/clone one in the app",
            "profile_id": None,
            "profile_name": None,
            "profile_count": 0,
        }
    wanted = voicebox_profile()
    resolved_id = None
    resolved_name = None
    if wanted:
        low = wanted.lower()
        for p in profiles:
            if str(p.get("id")) == wanted or str(p.get("name") or "").lower() == low:
                resolved_id = str(p["id"])
                resolved_name = str(p.get("name") or p["id"])
                break
        if not resolved_id:
            return {
                "ok": False,
                "error": f"VOICEBOX_PROFILE={wanted!r} not found among {len(profiles)} profiles",
                "profile_id": None,
                "profile_name": None,
                "profile_count": len(profiles),
            }
    else:
        for p in profiles:
            if str(p.get("voice_type") or "") != "import":
                resolved_id = str(p["id"])
                resolved_name = str(p.get("name") or p["id"])
                break
        if not resolved_id:
            p0 = profiles[0]
            resolved_id = str(p0["id"])
            resolved_name = str(p0.get("name") or p0["id"])
    return {
        "ok": True,
        "error": None,
        "profile_id": resolved_id,
        "profile_name": resolved_name,
        "profile_count": len(profiles),
        "base_url": voicebox_base_url(),
        "language": voicebox_language(),
        "engine": voicebox_engine(),
    }


def grok_tts_voice() -> str:
    return (get_config().grok_tts_voice or "eve").strip() or "eve"


def grok_tts_language() -> str:
    return (get_config().grok_tts_language or "zh").strip() or "zh"


def probe_grok_tts() -> dict[str, Any]:
    """Cheap readiness: OAuth auth present + models ok (does not call /tts every probe)."""
    try:
        from grok_oauth import auth_path
        from grok_oauth import probe as grok_probe

        if not auth_path().is_file() and not get_config().xai_api_key.strip():
            return {"ok": False, "error": "no grok auth.json and no XAI_API_KEY"}
        # Avoid deep TTS list on every film probe — models list is enough
        g = grok_probe(deep=False)
        if not g.get("ok"):
            return {"ok": False, "error": g.get("error") or "grok oauth not ok", "detail": g}
        return {
            "ok": True,
            "source": g.get("source"),
            "voice": grok_tts_voice(),
            "language": grok_tts_language(),
            "has_imagine_video": g.get("has_imagine_video"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def probe_qwen3_tts() -> dict[str, Any]:
    try:
        import qwen_tts  # type: ignore  # noqa: F401
        import soundfile  # type: ignore  # noqa: F401

        return {
            "ok": True,
            "model": get_config().qwen3_tts_model,
            "ref_audio": bool(get_config().qwen3_tts_ref_audio),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240], "model": get_config().qwen3_tts_model}


def probe_higgs_audio() -> dict[str, Any]:
    configured = bool(get_config().higgs_audio_argv.strip())
    return {
        "ok": configured,
        "argv_configured": configured,
        "model": get_config().higgs_audio_model,
        "error": None if configured else "HIGGS_AUDIO_ARGV not configured",
    }


def probe_audio_node() -> dict[str, Any]:
    base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
    token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
    if not base or not token:
        return {"ok": False, "error": "AIFILM_AUDIO_NODE_URL/TOKEN not configured"}
    try:
        from audio_node_client import health, public_health_report

        result = public_health_report(health(base, token), secret_values=(token,))
        variants = result.get("tts_variants", {})
        return {
            "ok": bool(
                result.get("ok")
                and result.get("models", {}).get("tts")
                and variants.get("voice_design") is True
            ),
            "detail": result,
            "error": None
            if variants.get("voice_design") is True
            else "audio node is missing required tts_variants.voice_design handshake",
        }
    except Exception:
        return {"ok": False, "error": "audio node health check failed"}


def probe() -> dict[str, Any]:
    external_error = None
    try:
        ext = external_argv()
    except TTSError as exc:
        ext = None
        external_error = str(exc)
    vb = probe_voicebox()
    grok = probe_grok_tts()
    qwen = probe_qwen3_tts()
    higgs = probe_higgs_audio()
    node = probe_audio_node()
    backends: dict[str, bool] = {
        "mimo": bool(mimo_api_key()) and _mimo_model_error(mimo_tts_model()) is None,
        "edge": True,
        "fish": bool(fish_api_key()),
        "minimax": bool(minimax_api_key()),
        "external": bool(ext),
        "voicebox": bool(vb.get("ok")),
        "grok": bool(grok.get("ok")),
        "qwen3": bool(qwen.get("ok")),
        "higgs": bool(higgs.get("ok")),
        "audio_node": bool(node.get("ok")),
        "cosyvoice-local": cosyvoice_local_argv_configured(),
        "kokoro-local": kokoro_local_argv_configured(),
        "chatterbox-local": chatterbox_local_argv_configured(),
        "piper-local": piper_local_argv_configured(),
    }
    try:
        import edge_tts  # noqa: F401

        backends["edge"] = True
    except ImportError:
        backends["edge"] = False

    preferred = (get_config().tts_backend or "auto").lower()
    strict_voice = strict_voice_enabled()
    fish_ready = bool(backends["fish"] and (fish_voice_id() or not strict_voice))
    if preferred == "auto":
        # Prefer local execution, then expressive APIs with stable voice identity.
        # Voicebox is local-first quality when the app is up + profile exists.
        # Never auto-pick grok (opt-in only for SuperGrok OAuth path).
        if backends["mimo"]:
            choice = "mimo"
        elif backends["external"]:
            choice = "external"
        elif backends["voicebox"]:
            choice = "voicebox"
        elif backends["minimax"]:
            choice = "minimax"
        elif fish_ready:
            choice = "fish"
        else:
            choice = "edge"
    else:
        choice = preferred

    ready = {**backends, "fish": fish_ready}
    return {
        "ok": bool(ready.get(choice, False)),
        "preferred": preferred,
        # Keep an explicit configured backend active even when unready so synthesis fails closed.
        "active": choice,
        "backends": backends,
        "ready": ready,
        "fish_key_set": backends["fish"],
        "mimo_key_set": backends["mimo"],
        "mimo_model": mimo_tts_model() if backends["mimo"] else None,
        "mimo_voice": mimo_tts_voice() if backends["mimo"] else None,
        "mimo_error": _mimo_model_error(mimo_tts_model()),
        "fish_voice_id": fish_voice_id(),
        "fish_model": fish_model(),
        "minimax_key_set": backends["minimax"],
        "minimax_voice_id": minimax_voice_id() if backends["minimax"] else None,
        "minimax_model": minimax_model() if backends["minimax"] else None,
        "grok_ok": backends["grok"],
        "grok_voice": grok_tts_voice() if backends["grok"] else None,
        "grok_language": grok_tts_language() if backends["grok"] else None,
        "grok_error": grok.get("error"),
        "qwen3": qwen,
        "higgs": higgs,
        "audio_node": node,
        "voicebox_ok": backends["voicebox"],
        "voicebox_base_url": voicebox_base_url(),
        "voicebox_profile": vb.get("profile_name") or voicebox_profile(),
        "voicebox_profile_id": vb.get("profile_id"),
        "voicebox_error": vb.get("error"),
        "voicebox_fallback": voicebox_fallback_enabled(),
        "external_argv_set": backends["external"],
        "external_config_error": external_error,
        "strict_voice_lock": strict_voice,
        "locked_speaker_policy": (
            "MiMo uses one fixed MIMO_TTS_VOICE per film; fish without FISH_VOICE_ID fails closed when strict; "
            "minimax uses fixed MINIMAX_VOICE_ID; voicebox locks VOICEBOX_PROFILE; "
            "grok uses AIFILM_GROK_TTS_VOICE (default eve); "
            "edge uses fixed vo_voice/cast_voices"
        ),
        "note": (
            "一角一声: set MIMO_TTS_VOICE / FISH_VOICE_ID / MINIMAX_VOICE_ID / VOICEBOX_PROFILE / AIFILM_GROK_TTS_VOICE; "
            "strict lock defaults ON. MiMo is the film default when MIMO_API_KEY is set. Local quality: voicebox (app :17493) or external. "
            "Grok TTS is opt-in (never auto). Fallback: auto+tts_allow_network_fallback → voicebox then edge; "
            "AIFILM_TTS_VOICEBOX_FALLBACK=1 also covers explicit edge/minimax/fish fails."
        ),
    }


# cn sediment: edge occasional empty stream → retry before hard fail (min payload bytes).
EDGE_MIN_AUDIO_BYTES = 500
EDGE_EMPTY_RETRIES = 3
EDGE_RETRY_BACKOFF_SEC = 0.35


def _local_adapter(
    name: str,
    text: str,
    out_mp3: Path,
    *,
    voice: str,
    performance: dict[str, Any],
) -> None:
    """Run an optional local adapter without exposing the parent secret env."""
    script = Path(__file__).resolve().parent / "adapters" / f"{name}.py"
    if not script.is_file():
        raise TTSError(f"missing {name} adapter: {script}")
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    text_fd, text_name = tempfile.mkstemp(prefix="aifilm-tts-", suffix=".txt", dir=out_mp3.parent)
    perf_fd, perf_name = tempfile.mkstemp(
        prefix="aifilm-performance-", suffix=".json", dir=out_mp3.parent
    )
    os.close(text_fd)
    os.close(perf_fd)
    text_file = Path(text_name)
    perf_file = Path(perf_name)
    try:
        atomic_write_text(text_file, text)
        atomic_write_text(perf_file, json.dumps(performance, ensure_ascii=False, sort_keys=True))
        env = minimal_subprocess_env()
        cfg = get_config()
        env.update(
            {
                "QWEN3_TTS_MODEL": cfg.qwen3_tts_model,
                "QWEN3_TTS_REF_AUDIO": cfg.qwen3_tts_ref_audio,
                "QWEN3_TTS_REF_TEXT": cfg.qwen3_tts_ref_text,
                "QWEN3_TTS_DEVICE": cfg.qwen3_tts_device,
                "HIGGS_AUDIO_MODEL": cfg.higgs_audio_model,
                "HIGGS_AUDIO_DEVICE": cfg.higgs_audio_device,
            }
        )
        if cfg.higgs_audio_argv:
            env["HIGGS_AUDIO_ARGV"] = cfg.higgs_audio_argv
        try:
            p = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--text-file",
                    str(text_file),
                    "--out",
                    str(out_mp3),
                    "--voice",
                    voice or "",
                    "--performance-file",
                    str(perf_file),
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise TTSError(f"{name} adapter timed out after 600s") from exc
        if p.returncode != 0:
            detail = (p.stderr or p.stdout or "adapter failed").strip()[-800:]
            raise TTSError(f"{name} adapter failed: {detail}")
        if not out_mp3.is_file() or out_mp3.stat().st_size < 500:
            raise TTSError(f"{name} adapter produced no usable audio")
    finally:
        text_file.unlink(missing_ok=True)
        perf_file.unlink(missing_ok=True)


def tts_grok(
    text: str,
    out_mp3: Path,
    *,
    voice_id: str | None = None,
    language: str | None = None,
    speed: float | None = None,
    with_timestamps: bool = False,
    usage_root: Path | str | None = None,
    shot_id: str = "",
    job_id: str = "",
) -> Path:
    """Grok OAuth TTS (POST /v1/tts). Opt-in only — never film default."""
    try:
        from grok_oauth import GrokOAuthError, tts_speak
    except ImportError as exc:
        raise TTSError(f"grok_oauth import failed: {exc}") from exc
    vid = (voice_id or "").strip()
    if not vid or _is_edge_voice_name(vid):
        vid = grok_tts_voice()
    lang = (language or grok_tts_language()).strip() or "zh"
    try:
        result = tts_speak(
            text,
            out=out_mp3,
            voice_id=vid,
            language=lang,
            speed=speed,
            with_timestamps=with_timestamps,
            usage_root=usage_root,
            shot_id=shot_id,
            job_id=job_id,
        )
    except GrokOAuthError as exc:
        raise TTSError(f"grok TTS failed: {exc}") from exc
    if not result.get("ok"):
        raise TTSError(f"grok TTS produced no audio: {result}")
    return Path(result["path"])


def tts_edge(
    text: str,
    out_mp3: Path,
    voice: str = "zh-CN-XiaoxiaoNeural",
    *,
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
    min_bytes: int = EDGE_MIN_AUDIO_BYTES,
    max_attempts: int = EDGE_EMPTY_RETRIES,
) -> Path:
    """Edge Neural TTS with empty/tiny stream retry (ai-film-cn empty-stream lesson)."""
    import asyncio
    import time

    import edge_tts

    async def _run() -> bytes:
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
        data = bytearray()
        async for event in communicate.stream():
            if event["type"] == "audio" and event.get("data") is not None:
                data.extend(event["data"])
        return bytes(data)

    attempts = max(1, int(max_attempts))
    floor = max(1, int(min_bytes))
    last_size = 0
    data = b""
    for attempt in range(1, attempts + 1):
        data = asyncio.run(_run())
        last_size = len(data) if data else 0
        if data and last_size >= floor:
            break
        if attempt < attempts:
            time.sleep(EDGE_RETRY_BACKOFF_SEC * attempt)
    if not data or last_size < floor:
        raise TTSError(
            f"edge-tts empty/tiny audio after {attempts} attempt(s) "
            f"({last_size}B < {floor}B): {text[:40]}"
        )
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(out_mp3, data)
    return out_mp3


def tts_mimo(
    text: str,
    out_mp3: Path,
    *,
    voice_id: str | None = None,
    style: str | None = None,
    model: str | None = None,
) -> Path:
    """MiMo OpenAI-compatible TTS with a fixed built-in voice per film."""
    if not text or not text.strip():
        raise TTSError("MiMo TTS requires non-empty text")
    key = mimo_api_key()
    if not key:
        raise TTSError("MIMO_API_KEY not set — create one at https://platform.xiaomimimo.com")
    selected_model = (model or mimo_tts_model()).strip()
    if error := _mimo_model_error(selected_model):
        raise TTSError(error)
    voice = (voice_id or mimo_tts_voice()).strip() or "冰糖"
    audio: dict[str, str] = {"format": "mp3"}
    if selected_model == "mimo-v2.5-tts":
        audio["voice"] = voice
    elif selected_model == "mimo-v2.5-tts-voiceclone":
        reference = mimo_tts_reference_audio()
        if reference is None:
            raise TTSError("MIMO_TTS_REFERENCE_AUDIO is required for MiMo voice cloning")
        reference_bytes, mime_type = _validated_mimo_reference_audio(reference)
        audio["voice"] = (
            f"data:{mime_type};base64,{base64.b64encode(reference_bytes).decode('ascii')}"
        )
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "user", "content": (style or mimo_tts_style()).strip()},
            {"role": "assistant", "content": text},
        ],
        "audio": audio,
    }
    req = urllib.request.Request(
        f"{mimo_api_base()}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:800]
        raise TTSError(f"MiMo TTS HTTP {exc.code}: {err}") from exc
    except Exception as exc:
        raise TTSError(f"MiMo TTS request failed: {exc}") from exc
    try:
        response = json.loads(raw.decode("utf-8"))
        audio_data = response["choices"][0]["message"]["audio"]["data"]
        audio_bytes = base64.b64decode(audio_data, validate=True)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TTSError("MiMo TTS response missing valid base64 audio") from exc
    if len(audio_bytes) < 200:
        raise TTSError(f"MiMo TTS returned empty/tiny audio ({len(audio_bytes)} bytes)")
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(out_mp3, audio_bytes)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(out_mp3),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        duration = float((probe.stdout or "").strip())
    except ValueError:
        duration = 0.0
    if probe.returncode != 0 or duration <= 0:
        out_mp3.unlink(missing_ok=True)
        raise TTSError("MiMo TTS response is not decodable audio")
    return out_mp3


def tts_fish(
    text: str,
    out_mp3: Path,
    *,
    voice_id: str | None = None,
    model: str | None = None,
    speed: float = 0.95,
) -> Path:
    """Fish Audio REST API — human-like Chinese/EN TTS.

    Docs: https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech
    Free tier model header: s2.1-pro-free
    """
    key = fish_api_key()
    if not key:
        raise TTSError("FISH_API_KEY not set — get one at https://fish.audio/app/api-keys")

    ref = voice_id or fish_voice_id()
    mdl = model or fish_model()
    # Without a fixed reference_id, Fish may pick different speakers per request
    # (one film = many voices). Prefer locking temperature low when unlocked.
    locked = bool(ref)
    payload: dict[str, Any] = {
        "text": text,
        "format": "mp3",
        "mp3_bitrate": 192,
        "sample_rate": 44100,
        "normalize": True,
        "latency": "normal",
        "prosody": {
            "speed": float(speed),
            "volume": 0,
            "normalize_loudness": True,
        },
        # Lower temperature when we need 一角一声 consistency
        "temperature": 0.45 if locked else 0.35,
        "top_p": 0.65 if locked else 0.5,
        "condition_on_previous_chunks": True,
        "repetition_penalty": 1.2,
    }
    if ref:
        payload["reference_id"] = ref

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.fish.audio/v1/tts",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "model": mdl,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:800]
        raise TTSError(f"Fish TTS HTTP {exc.code}: {err}") from exc
    except Exception as exc:
        raise TTSError(f"Fish TTS request failed: {exc}") from exc

    if not data or len(data) < 200:
        raise TTSError(f"Fish TTS returned empty/tiny audio ({len(data) if data else 0} bytes)")

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(out_mp3, data)
    return out_mp3


def tts_minimax(
    text: str,
    out_mp3: Path,
    *,
    voice_id: str | None = None,
    model: str | None = None,
    speed: float = 0.95,
    emotion: str | None = None,
) -> Path:
    """MiniMax T2A HTTP — Speech 2.6/2.8 HD.

    Docs: https://platform.minimax.io/docs/api-reference/speech-t2a-http
    Returns hex-encoded audio in JSON (non-streaming).
    """
    key = minimax_api_key()
    if not key:
        raise TTSError("MINIMAX_API_KEY not set — https://platform.minimax.io")

    vid = voice_id or minimax_voice_id()
    mdl = model or minimax_model()
    payload: dict[str, Any] = {
        "model": mdl,
        "text": text,
        "stream": False,
        "output_format": "hex",
        "language_boost": "Chinese",
        "voice_setting": {
            "voice_id": vid,
            "speed": float(speed),
            "vol": 1.0,
            "pitch": 0,
            "text_normalization": True,
        },
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    if emotion:
        payload["voice_setting"]["emotion"] = emotion

    url = "https://api.minimax.io/v1/t2a_v2"
    gid = minimax_group_id()
    if gid:
        url = f"{url}?GroupId={gid}"

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:800]
        raise TTSError(f"MiniMax TTS HTTP {exc.code}: {err}") from exc
    except Exception as exc:
        raise TTSError(f"MiniMax TTS request failed: {exc}") from exc

    try:
        obj = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TTSError(f"MiniMax TTS non-JSON response: {raw[:200]!r}") from exc

    base = obj.get("base_resp") or {}
    if int(base.get("status_code", -1)) != 0:
        raise TTSError(f"MiniMax TTS error: {base.get('status_msg') or obj}")

    data_obj = obj.get("data") or {}
    hex_audio = data_obj.get("audio")
    if not hex_audio or not isinstance(hex_audio, str):
        raise TTSError(f"MiniMax TTS missing audio hex: {str(obj)[:400]}")
    try:
        audio_bytes = bytes.fromhex(hex_audio)
    except ValueError as exc:
        raise TTSError("MiniMax TTS invalid hex audio") from exc
    if len(audio_bytes) < 200:
        raise TTSError(f"MiniMax TTS tiny audio ({len(audio_bytes)} bytes)")

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(out_mp3, audio_bytes)
    return out_mp3


def tts_external(text: str, out_mp3: Path, voice: str = "") -> Path:
    cmd_tpl = external_argv()
    if not cmd_tpl:
        raise TTSError("AIFILM_TTS_ARGV not set")
    is_chatterbox_local = chatterbox_local_argv_configured()
    is_piper_local = piper_local_argv_configured()
    temporary_text_file: Path | None = None
    if is_chatterbox_local or is_piper_local:
        file_fd, temporary_name = tempfile.mkstemp(prefix="aifilm-local-tts-text-", suffix=".txt")
        temporary_text_file = Path(temporary_name)
        with os.fdopen(file_fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        text_file = temporary_text_file
    else:
        out_mp3.parent.mkdir(parents=True, exist_ok=True)
        text_file = out_mp3.with_suffix(".txt")
        atomic_write_text(text_file, text)
    try:
        argv = expand_argv(
            cmd_tpl,
            {
                "text": text,
                "out": str(out_mp3),
                "voice": voice or "",
                "text_file": str(text_file),
            },
            variable="AIFILM_TTS_ARGV",
        )
    except SecurityPolicyError as exc:
        raise TTSError(str(exc)) from exc
    try:
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=external_tts_timeout(),
                env=external_tts_subprocess_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            if is_chatterbox_local:
                raise TTSError("CHATTERBOX_LOCAL_EXEC_FAILED") from exc
            if is_piper_local:
                raise TTSError("PIPER_LOCAL_EXEC_FAILED") from exc
            raise TTSError(f"external TTS could not run: {exc}") from exc
    finally:
        if temporary_text_file is not None:
            temporary_text_file.unlink(missing_ok=True)
    if proc.returncode != 0 or not out_mp3.is_file():
        if is_chatterbox_local:
            raise TTSError(f"CHATTERBOX_LOCAL_PROCESS_FAILED rc={proc.returncode}")
        if is_piper_local:
            raise TTSError(f"PIPER_LOCAL_PROCESS_FAILED rc={proc.returncode}")
        raise TTSError(
            f"external TTS failed rc={proc.returncode}: {(proc.stderr or proc.stdout)[:800]}"
        )
    return out_mp3


def tts_voicebox(
    text: str,
    out_mp3: Path,
    *,
    voice: str = "",
    language: str | None = None,
    engine: str | None = None,
    instruct: str | None = None,
    timeout: float = 600,
) -> Path:
    """Local Voicebox studio via loopback REST (stream preferred, poll fallback)."""
    # Prefer in-process HTTP (same as adapter) so minimal_subprocess_env is not required.
    adapters = Path(__file__).resolve().parent / "adapters"
    if str(adapters) not in sys.path:
        sys.path.insert(0, str(adapters))
    try:
        import voicebox_tts as vb  # type: ignore
    except ImportError as exc:
        raise TTSError(f"voicebox_tts adapter missing: {exc}") from exc

    # Adapter raises SystemExit on hard errors — map to TTSError.
    try:
        meta = vb.synthesize(
            text,
            out_mp3,
            voice=voice or (voicebox_profile() or ""),
            language=language or voicebox_language(),
            engine=engine if engine is not None else voicebox_engine(),
            instruct=instruct,
            prefer_stream=True,
            timeout=timeout,
        )
    except SystemExit as exc:
        raise TTSError(str(exc) or "voicebox synthesis failed") from exc
    except Exception as exc:
        raise TTSError(f"voicebox synthesis failed: {exc}") from exc
    if not out_mp3.is_file() and not out_mp3.with_suffix(".wav").is_file():
        raise TTSError(f"voicebox produced no file: {meta}")
    # render_final expects the path it passed (often .mp3); adapter writes that path.
    if not out_mp3.is_file():
        wav = out_mp3.with_suffix(".wav")
        if wav.is_file():
            # ensure target exists for callers that only check out_mp3
            if out_mp3.suffix.lower() == ".mp3":
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(wav),
                            "-ac",
                            "1",
                            "-ar",
                            "44100",
                            "-codec:a",
                            "libmp3lame",
                            "-q:a",
                            "2",
                            str(out_mp3),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        check=False,
                    )
            if not out_mp3.is_file():
                # last resort: copy wav bytes under the requested name (ffmpeg sniff works)
                out_mp3.write_bytes(wav.read_bytes())
    return out_mp3


def _edge_voice_or_default(voice: str) -> str:
    if voice and (voice.startswith("zh-") or "Neural" in voice):
        return voice
    return "zh-CN-XiaoxiaoNeural"


def _is_edge_voice_name(voice: str) -> bool:
    return bool(voice and (voice.startswith("zh-") or "Neural" in voice))


def is_edge_neural_voice_id(voice: str | None) -> bool:
    """Public: Edge Neural style ids (zh-CN-…Neural) must not go to ElevenLabs/external."""
    return _is_edge_voice_name(str(voice or "").strip())


def external_tts_argv_hints_provider(provider: str = "eleven") -> bool:
    """True if AIFILM_TTS_ARGV JSON/string mentions a cloud provider (default: elevenlabs)."""
    raw = get_config().tts_argv.strip()
    if not raw:
        return False
    return provider.lower() in raw.lower()


def assert_voice_backend_compatible(backend: str, voice: str | None) -> None:
    """Hard-fail when Edge Neural ids are sent to external/cloud TTS (e.g. ElevenLabs)."""
    choice = (backend or "edge").strip().lower()
    if not is_edge_neural_voice_id(voice):
        return
    # Neural id only safe on explicit edge (fish/minimax/voicebox/grok strip Neural themselves)
    if choice in {
        "edge",
        "mimo",
        "fish",
        "minimax",
        "voicebox",
        "grok",
        "qwen3",
        "higgs",
        "audio_node",
    }:
        return
    if choice in {
        "external",
        "cosyvoice-local",
        "kokoro-local",
    } or external_tts_argv_hints_provider("eleven"):
        raise TTSError(
            f"TTS voice {voice!r} looks like Microsoft Edge Neural — cannot use with "
            "external/ElevenLabs (AIFILM_TTS_ARGV). "
            "Fix: --tts-backend edge for Chinese storyteller, "
            "or set vo_voice to a real provider voice id (not zh-CN-…Neural)."
        )
    if choice == "auto" and get_config().tts_argv.strip():
        raise TTSError(
            f"tts_backend=auto with AIFILM_TTS_ARGV set would send Edge Neural voice "
            f"{voice!r} to external TTS. Use --tts-backend edge (recommended for 中文旁白) "
            "or a provider-native voice id."
        )


def synthesize(
    text: str,
    out_mp3: Path,
    *,
    backend: str | None = None,
    voice: str = "zh-CN-XiaoxiaoNeural",
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
    speed: float | None = None,
    allow_network_fallback: bool = False,
    usage_root: Path | str | None = None,
    shot_id: str = "",
    job_id: str = "",
    performance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Synthesize speech. Returns {backend, path, voice}."""
    cue_input = dict(performance or {})
    cue_input.setdefault("rate", rate)
    cue_input.setdefault("pitch", pitch)
    cue_input.setdefault("volume", volume)
    cue = normalize_performance_cue(cue_input)
    edge_plan = compile_edge(cue, text)
    info = probe()
    # Hard gate: Edge Neural ids never go to external/ElevenLabs
    req = "auto" if backend is None else str(backend).lower()
    assert_voice_backend_compatible(req, voice)
    choice = req
    if choice == "auto":
        choice = str(info.get("active") or "edge").lower()
    if choice not in TTS_BACKENDS - {"auto"}:
        raise TTSError(f"Unknown TTS backend {choice!r}; choose one of {sorted(TTS_BACKENDS)}")
    assert_voice_backend_compatible(choice, voice)

    def _tracked(
        provider: str,
        model: str,
        *,
        local_zero: bool,
        call,
    ) -> None:
        if usage_root is None:
            call()
            return
        from generation_usage import finish_generation, start_generation

        generation_id = start_generation(
            usage_root,
            operation="tts",
            provider=provider,
            model=model,
            shot_id=shot_id,
            job_id=job_id,
        )
        try:
            call()
        except Exception:
            finish_generation(
                usage_root,
                generation_id,
                status="failed",
                measurement="local_zero" if local_zero else "unknown",
            )
            raise
        finish_generation(
            usage_root,
            generation_id,
            status="succeeded",
            measurement="local_zero" if local_zero else "unknown",
            output=out_mp3,
        )

    def _speed_from_rate() -> float:
        if speed is not None:
            return float(speed)
        sp = 0.95
        if rate and rate.endswith("%"):
            try:
                pct = float(rate.replace("%", "").replace("+", ""))
                sp = max(0.5, min(2.0, 1.0 + pct / 100.0))
            except ValueError:
                sp = 0.95
        return sp

    used = choice
    voice_used = voice
    model_used = None
    primary_error: TTSError | None = None
    try:
        if choice == "mimo":
            # Edge Neural identifiers are not MiMo voices — use the locked MiMo built-in voice.
            m_voice = "" if _is_edge_voice_name(voice) else (voice or "")
            _tracked(
                "mimo",
                mimo_tts_model(),
                local_zero=False,
                call=lambda: tts_mimo(text, out_mp3, voice_id=m_voice or None),
            )
            voice_used = m_voice or mimo_tts_voice()
            model_used = mimo_tts_model()
        elif choice == "minimax":
            sp = _speed_from_rate()
            # If --voice looks like MiniMax id (not edge zh-CN-*), use it
            vid = voice if voice and not voice.startswith("zh-") else None
            _tracked(
                "minimax",
                minimax_model(),
                local_zero=False,
                call=lambda: tts_minimax(text, out_mp3, voice_id=vid, speed=sp),
            )
            voice_used = vid or minimax_voice_id()
            model_used = minimax_model()
        elif choice == "fish":
            sp = _speed_from_rate()
            # Fish reference_id if voice is not an edge Neural name
            vid = voice if voice and not voice.startswith("zh-") and "Neural" not in voice else None
            # 一角一声：无固定 voice_id 时 Fish 会每镜漂移，因此严格模式默认拒绝。
            strict = strict_voice_enabled()
            if strict and not (vid or fish_voice_id()):
                raise TTSError(
                    "Fish backend requires a fixed FISH_VOICE_ID in strict voice mode; "
                    "explicit backends never cross providers"
                )
            _tracked(
                "fish",
                fish_model(),
                local_zero=False,
                call=lambda: tts_fish(text, out_mp3, voice_id=vid, speed=sp),
            )
            voice_used = vid or fish_voice_id() or "fish-default"
            model_used = fish_model()
        elif choice == "voicebox":
            # Edge Neural names are not Voicebox profiles — strip them.
            vb_voice = "" if _is_edge_voice_name(voice) else (voice or "")
            if strict_voice_enabled() and not (
                vb_voice or voicebox_profile() or info.get("voicebox_profile_id")
            ):
                raise TTSError(
                    "Voicebox backend requires VOICEBOX_PROFILE (or vo_voice = profile name) "
                    "in strict voice mode"
                )
            _tracked(
                "voicebox",
                voicebox_engine() or "voicebox",
                local_zero=True,
                call=lambda: tts_voicebox(text, out_mp3, voice=vb_voice),
            )
            voice_used = (
                vb_voice or info.get("voicebox_profile") or voicebox_profile() or "voicebox-default"
            )
            model_used = voicebox_engine() or "voicebox"
        elif choice == "grok":
            # Edge Neural names are not Grok voice_ids — fall back to AIFILM_GROK_TTS_VOICE.
            g_voice = "" if _is_edge_voice_name(voice) else (voice or "")
            sp = _speed_from_rate()
            # Map edge-like rate % into Grok speed range 0.7–1.5
            sp = max(0.7, min(1.5, sp))
            tts_grok(
                text,
                out_mp3,
                voice_id=g_voice or None,
                speed=sp,
                usage_root=usage_root,
                shot_id=shot_id,
                job_id=job_id,
            )
            voice_used = g_voice or grok_tts_voice()
            model_used = "grok-tts"
        elif choice == "qwen3":
            _tracked(
                "qwen3",
                get_config().qwen3_tts_model,
                local_zero=True,
                call=lambda: _local_adapter(
                    "qwen3_tts", text, out_mp3, voice=voice, performance=cue
                ),
            )
            voice_used = voice or ("clone" if get_config().qwen3_tts_ref_audio else "designed")
            model_used = get_config().qwen3_tts_model
        elif choice == "higgs":
            _tracked(
                "higgs",
                get_config().higgs_audio_model,
                local_zero=True,
                call=lambda: _local_adapter(
                    "higgs_audio", text, out_mp3, voice=voice, performance=cue
                ),
            )
            voice_used = voice or "higgs-reference"
            model_used = get_config().higgs_audio_model
        elif choice == "audio_node":
            from audio_node_client import AudioNodeError, health, render
            from voice_armory import render_ready_tts_profile

            base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
            token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
            rendered: dict[str, Any] = {}
            profile_id = "" if _is_edge_voice_name(voice) else voice
            try:
                node_health = health(base, token)
                profile = render_ready_tts_profile(profile_id, node_health.get("tts_variants", {}))
            except (AudioNodeError, ValueError) as exc:
                raise TTSError(f"private audio node voice is unavailable: {exc}") from exc
            node_variant = str(profile["variant"])
            node_voice = str(profile.get("speaker", ""))
            node_language = str(profile["language"])
            prefix = str(profile.get("instruction_prefix", "")).strip()
            instruction = compile_instruction(cue)
            if prefix:
                instruction = f"{prefix} {instruction}"

            def _node_call() -> None:
                nonlocal rendered
                temp_wav = out_mp3.with_suffix(".node.wav")
                try:
                    rendered = render(
                        base,
                        token,
                        "tts",
                        {
                            "text": text,
                            "model_variant": node_variant,
                            "voice_profile_id": node_voice,
                            "language": node_language,
                            "performance": {"instruction": instruction},
                        },
                        temp_wav,
                    )
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(temp_wav),
                            "-ar",
                            "44100",
                            "-ac",
                            "2",
                            str(out_mp3),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=180,
                    )
                except (AudioNodeError, OSError, subprocess.SubprocessError) as exc:
                    raise TTSError(f"private audio node failed: {exc}") from exc
                finally:
                    temp_wav.unlink(missing_ok=True)

            _tracked("audio_node", "qwen3-tts-5090", local_zero=True, call=_node_call)
            voice_used = profile_id or "qwen_zh_female_design"
            model_used = f"qwen3-tts-5090/{node_variant}"
        elif choice == "cosyvoice-local":
            if not cosyvoice_local_argv_configured():
                raise TTSError(
                    "cosyvoice-local requires AIFILM_TTS_ARGV to invoke "
                    "adapters/cosyvoice_local_tts.py"
                )
            _tracked(
                "cosyvoice-local",
                cosyvoice_local_model_label(),
                local_zero=True,
                call=lambda: tts_external(text, out_mp3, voice=voice),
            )
            voice_used = voice or "cosyvoice-local"
            model_used = cosyvoice_local_model_label()
        elif choice == "kokoro-local":
            if not kokoro_local_argv_configured():
                raise TTSError(
                    "kokoro-local requires AIFILM_TTS_ARGV to invoke adapters/kokoro_tts.py"
                )
            _tracked(
                "kokoro-local",
                "Kokoro-82M-v1.1-zh",
                local_zero=True,
                call=lambda: tts_external(text, out_mp3, voice=voice),
            )
            voice_used = voice or "zf_001"
            model_used = "Kokoro-82M-v1.1-zh"
        elif choice == "chatterbox-local":
            if not chatterbox_local_argv_configured():
                raise TTSError(
                    "chatterbox-local requires AIFILM_TTS_ARGV to invoke "
                    "adapters/chatterbox_local_tts.py"
                )
            _tracked(
                "chatterbox-local",
                "ResembleAI/chatterbox",
                local_zero=True,
                call=lambda: tts_external(text, out_mp3, voice=voice),
            )
            voice_used = voice or "chatterbox-builtin"
            model_used = "ResembleAI/chatterbox"
        elif choice == "piper-local":
            if not piper_local_argv_configured():
                raise TTSError("piper-local requires the fixed adapters/piper_local_tts.py argv")
            _tracked(
                "piper-local",
                "Piper/zh_CN-chaowen-medium",
                local_zero=True,
                call=lambda: tts_external(text, out_mp3, voice=voice),
            )
            voice_used = voice or "zh_CN-chaowen-medium"
            model_used = "Piper/zh_CN-chaowen-medium"
        elif choice == "external":
            _tracked(
                "external",
                "external-tts",
                local_zero=False,
                call=lambda: tts_external(text, out_mp3, voice=voice),
            )
        else:
            used = "edge"
            _tracked(
                "edge",
                "edge-neural",
                local_zero=True,
                call=lambda: tts_edge(
                    edge_plan["text"],
                    out_mp3,
                    voice,
                    rate=edge_plan["rate"],
                    volume=edge_plan["volume"],
                    pitch=edge_plan["pitch"],
                ),
            )
            voice_used = voice
    except TTSError as exc:
        primary_error = exc
        requested_auto = backend is None or str(backend).lower() == "auto"
        recovered = False

        # 1) Opt-in auto fallback chain: primary → voicebox → edge
        if allow_network_fallback and requested_auto and choice not in {"edge"}:
            if choice != "voicebox" and info["backends"].get("voicebox"):
                try:
                    vb_voice = "" if _is_edge_voice_name(voice) else (voice or "")
                    _tracked(
                        "voicebox",
                        voicebox_engine() or "voicebox",
                        local_zero=True,
                        call=lambda: tts_voicebox(text, out_mp3, voice=vb_voice),
                    )
                    used = f"{choice}->voicebox_opt_in_fallback"
                    voice_used = vb_voice or info.get("voicebox_profile") or "voicebox-fallback"
                    model_used = voicebox_engine() or "voicebox"
                    recovered = True
                except TTSError:
                    recovered = False
            if not recovered and info["backends"].get("edge"):
                edge_v = _edge_voice_or_default(voice)
                _tracked(
                    "edge",
                    "edge-neural",
                    local_zero=True,
                    call=lambda: tts_edge(
                        edge_plan["text"],
                        out_mp3,
                        edge_v,
                        rate=edge_plan["rate"],
                        volume=edge_plan["volume"],
                        pitch=edge_plan["pitch"],
                    ),
                )
                used = f"{choice}->edge_opt_in_fallback"
                voice_used = edge_v
                recovered = True

        # 2) Explicit backend + AIFILM_TTS_VOICEBOX_FALLBACK=1 → try local Voicebox once
        if (
            not recovered
            and voicebox_fallback_enabled()
            and choice in {"edge", "minimax", "fish", "external"}
            and info["backends"].get("voicebox")
        ):
            try:
                vb_voice = "" if _is_edge_voice_name(voice) else (voice or "")
                _tracked(
                    "voicebox",
                    voicebox_engine() or "voicebox",
                    local_zero=True,
                    call=lambda: tts_voicebox(text, out_mp3, voice=vb_voice),
                )
                used = f"{choice}->voicebox_opt_in_fallback"
                voice_used = vb_voice or info.get("voicebox_profile") or "voicebox-fallback"
                model_used = voicebox_engine() or "voicebox"
                recovered = True
            except TTSError:
                recovered = False

        if not recovered:
            raise primary_error from None

    result: dict[str, Any] = {
        "backend": used,
        "path": str(out_mp3),
        "voice": voice_used,
        "model": model_used,
        "fish_model": fish_model() if "fish" in used else None,
        "minimax_model": minimax_model() if "minimax" in used else None,
        "voicebox_profile": info.get("voicebox_profile") if "voicebox" in used else None,
        "performance": cue,
        "performance_hash": cue_hash(cue),
        "performance_compile": {"edge": edge_plan, "instruction": compile_instruction(cue)},
    }
    # AF4 · PARTIAL-honest when opt-in fallback recovered primary failure
    if "fallback" in str(used).lower():
        from util import utc_now as _utc_now
        from util import write_json as _write_json

        result["partial"] = True
        result["honest_limits"] = [
            f"TTS recovered via fallback chain: {used}",
            "voice quality may be more synthetic than primary backend",
            "do not claim primary TTS succeeded without reading receipts/tts-partial.json",
        ]
        if usage_root:
            try:
                root = Path(usage_root).expanduser().resolve()
                path = root / "receipts" / "tts-partial.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                _write_json(
                    path,
                    {
                        "kind": "tts-partial",
                        "schema_version": 1,
                        "at": _utc_now(),
                        "ok": True,
                        "partial": True,
                        "used": used,
                        "voice": voice_used,
                        "model": model_used,
                        "shot_id": str(shot_id or "") or None,
                        "job_id": str(job_id or "") or None,
                        "primary_error": (
                            str(primary_error)[:300] if primary_error is not None else None
                        ),
                        "honest_limits": result["honest_limits"],
                        "path": str(out_mp3),
                    },
                )
                result["partial_receipt"] = str(path)
            except Exception:
                pass  # never block audio write on receipt I/O
    return result


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="ai-film-grok TTS backend")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="Probe backends")
    syn = sub.add_parser("synth", help="Synthesize one line")
    syn.add_argument("--text", required=True)
    syn.add_argument("--out", required=True)
    syn.add_argument("--backend", default=None)
    syn.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    syn.add_argument("--rate", default="-5%")
    syn.add_argument("--allow-network-fallback", action="store_true")
    args = p.parse_args()
    if args.cmd == "doctor":
        print(json.dumps(probe(), ensure_ascii=False, indent=2))
        return 0
    r = synthesize(
        args.text,
        Path(args.out),
        backend=args.backend,
        voice=args.voice,
        rate=args.rate,
        allow_network_fallback=args.allow_network_fallback,
    )
    print(json.dumps({"ok": True, **r}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
