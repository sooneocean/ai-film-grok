from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_CONFIG: ConfigSchema | None = None
_CONFIG_ENV_FINGERPRINT: tuple[tuple[str, str], ...] | None = None

_SKILL_ROOT_CANDIDATES: list[Path] = [
    Path(__file__).resolve().parent.parent / "config.env",
    Path.home() / ".grok/skills/ai-film-grok/config.env",
]


def _find_config_env() -> Path | None:
    for p in _SKILL_ROOT_CANDIDATES:
        if p.is_file():
            return p
    return None


def _load_env_file() -> None:
    cfg = _find_config_env()
    if cfg is None:
        return
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(key: str, *aliases: str) -> str:
    for k in (key, *aliases):
        v = os.environ.get(k)
        if v is not None:
            return v.strip()
    return ""


def _env_bool(key: str, *aliases: str) -> bool | None:
    raw = _env(key, *aliases)
    if not raw:
        return None
    return raw.lower() not in {"0", "false", "no", "off"}


def _env_int(key: str, *aliases: str) -> int | None:
    raw = _env(key, *aliases)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _resolve(
    default: str,
    env_name: str,
    *env_aliases: str,
) -> str:
    return _env(env_name, *env_aliases) or default


def _resolve_bool(env_name: str, *env_aliases: str, default: bool = False) -> bool:
    val = _env_bool(env_name, *env_aliases)
    return default if val is None else val


def _resolve_int(env_name: str, *env_aliases: str, default: int = 0) -> int:
    val = _env_int(env_name, *env_aliases)
    return default if val is None else val


def _config_env_fingerprint() -> tuple[tuple[str, str], ...]:
    """Return the environment slice that can affect ``ConfigSchema``.

    The CLI can execute several subcommands in one Python process and tests
    commonly patch environment variables between calls.  Caching the parsed
    config without noticing those changes makes routing and safety gates use
    stale values.  Keep the fingerprint in memory only; secrets never leave
    the process.
    """
    prefixes = (
        "AIFILM_",
        "XAI_",
        "FISH_",
        "MINIMAX_",
        "VOICEBOX_",
        "COSYVOICE_",
        "ELEVENLABS_",
        "MUSIC_",
        "ACESTEP_",
        "FRW_",
    )
    return tuple(
        sorted(
            (key, value)
            for key, value in os.environ.items()
            if key == "GROK_AUTH_JSON" or key.startswith(prefixes)
        )
    )


@dataclass
class ConfigSchema:
    # ── Grok OAuth ──────────────────────────────────────────────────────
    grok_auth: str = "auto"
    xai_api_key: str = ""
    grok_auth_path: str = ""
    grok_api_base: str = "https://api.x.ai/v1"
    grok_chat_model: str = "grok-4.5"
    grok_image_model: str = "grok-imagine-image"
    grok_video_model: str = "grok-imagine-video"
    grok_tts_voice: str = "eve"
    grok_tts_language: str = "zh"
    grok_probe_tts: bool = False

    # ── TTS ─────────────────────────────────────────────────────────────
    tts_backend: str = "edge"
    tts_strict_voice: bool = True
    tts_voicebox_fallback: bool = False
    tts_argv: str = ""

    # ── Fish Audio ──────────────────────────────────────────────────────
    fish_api_key: str = ""
    fish_voice_id: str = ""
    fish_model: str = "s2.1-pro-free"

    # ── MiniMax ─────────────────────────────────────────────────────────
    minimax_api_key: str = ""
    minimax_voice_id: str = "Chinese (Mandarin)_Lyrical_Voice"
    minimax_model: str = "speech-2.6-hd"
    minimax_group_id: str = ""

    # ── Voicebox ────────────────────────────────────────────────────────
    voicebox_base_url: str = "http://127.0.0.1:17493"
    voicebox_profile: str = ""
    voicebox_language: str = "zh"
    voicebox_engine: str = "qwen"

    # ── CosyVoice ───────────────────────────────────────────────────────
    cosyvoice_base_url: str = "http://127.0.0.1:9880"
    cosyvoice_endpoint: str = "/tts"
    cosyvoice_payload_style: str = "shengwang"
    cosyvoice_ref_wav: str = ""
    cosyvoice_speaker: str = "default"
    cosyvoice_language: str = "zh"
    cosyvoice_prompt_text: str = ""
    cosyvoice_ref_as_b64: bool = False

    # ── ElevenLabs ──────────────────────────────────────────────────────
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "cgSgspJ2msm6clMCkdW9"
    elevenlabs_model: str = "eleven_multilingual_v2"

    # ── Music / BGM ─────────────────────────────────────────────────────
    music_gen_base_url: str = "http://127.0.0.1:7860"
    music_gen_endpoint: str = "/generate"
    music_gen_extra_json: str = ""
    music_argv: str = ""
    music_prompt: str = ""
    music_timeout: int = 600
    music_require: bool = False
    music_license: str = ""

    # ── FRW / Seedance ──────────────────────────────────────────────────
    frw_api_key: str = ""
    frwclaw_root: str = ""

    # ── I2V ─────────────────────────────────────────────────────────────
    i2v_profile: str = "grok_primary"
    seedance_available: bool = False

    # ── Lipsync ─────────────────────────────────────────────────────────
    lipsync_backend: str = "off"
    lipsync_argv: str = ""
    musetalk_root: str = ""
    wav2lip_root: str = ""

    # ── Pipeline gates ──────────────────────────────────────────────────
    skip_pilot_gate: bool = False
    skip_loop_risk_gate: bool = False
    strict_tts_rehearsal: bool = False
    hud_stage: bool = True


def get_config() -> ConfigSchema:
    global _CONFIG, _CONFIG_ENV_FINGERPRINT
    _load_env_file()
    fingerprint = _config_env_fingerprint()
    if _CONFIG is not None and fingerprint == _CONFIG_ENV_FINGERPRINT:
        return _CONFIG
    _CONFIG = ConfigSchema(
        # Grok OAuth
        grok_auth=_resolve("auto", "AIFILM_GROK_AUTH"),
        xai_api_key=_env("XAI_API_KEY"),
        grok_auth_path=_env("AIFILM_GROK_AUTH_PATH", "GROK_AUTH_JSON"),
        grok_api_base=_resolve("https://api.x.ai/v1", "AIFILM_GROK_API_BASE", "XAI_BASE_URL"),
        grok_chat_model=_resolve("grok-4.5", "AIFILM_GROK_CHAT_MODEL"),
        grok_image_model=_resolve("grok-imagine-image", "AIFILM_GROK_IMAGE_MODEL"),
        grok_video_model=_resolve("grok-imagine-video", "AIFILM_GROK_VIDEO_MODEL"),
        grok_tts_voice=_resolve("eve", "AIFILM_GROK_TTS_VOICE"),
        grok_tts_language=_resolve("zh", "AIFILM_GROK_TTS_LANGUAGE"),
        grok_probe_tts=_resolve_bool("AIFILM_GROK_PROBE_TTS", default=False),
        # TTS
        tts_backend=_resolve("edge", "AIFILM_TTS_BACKEND"),
        tts_strict_voice=_resolve_bool("AIFILM_TTS_STRICT_VOICE", default=True),
        tts_voicebox_fallback=_resolve_bool("AIFILM_TTS_VOICEBOX_FALLBACK", default=False),
        tts_argv=_env("AIFILM_TTS_ARGV"),
        # Fish
        fish_api_key=_env("FISH_API_KEY", "FISH_AUDIO_API_KEY", "AIFILM_FISH_API_KEY"),
        fish_voice_id=_env("FISH_VOICE_ID", "AIFILM_FISH_VOICE_ID", "FISH_REFERENCE_ID"),
        fish_model=_resolve("s2.1-pro-free", "FISH_MODEL", "AIFILM_FISH_MODEL"),
        # MiniMax
        minimax_api_key=_env("MINIMAX_API_KEY", "AIFILM_MINIMAX_API_KEY"),
        minimax_voice_id=_resolve(
            "Chinese (Mandarin)_Lyrical_Voice", "MINIMAX_VOICE_ID", "AIFILM_MINIMAX_VOICE_ID"
        ),
        minimax_model=_resolve("speech-2.6-hd", "MINIMAX_MODEL", "AIFILM_MINIMAX_MODEL"),
        minimax_group_id=_env("MINIMAX_GROUP_ID"),
        # Voicebox
        voicebox_base_url=_resolve(
            "http://127.0.0.1:17493", "VOICEBOX_BASE_URL", "AIFILM_VOICEBOX_URL"
        ),
        voicebox_profile=_env("VOICEBOX_PROFILE", "VOICEBOX_PROFILE_ID", "AIFILM_VOICEBOX_PROFILE"),
        voicebox_language=_resolve("zh", "VOICEBOX_LANGUAGE", "AIFILM_VOICEBOX_LANGUAGE"),
        voicebox_engine=_resolve("qwen", "VOICEBOX_ENGINE", "AIFILM_VOICEBOX_ENGINE"),
        # CosyVoice
        cosyvoice_base_url=_resolve(
            "http://127.0.0.1:9880", "COSYVOICE_BASE_URL", "AIFILM_COSYVOICE_URL"
        ),
        cosyvoice_endpoint=_resolve("/tts", "COSYVOICE_ENDPOINT"),
        cosyvoice_payload_style=_resolve("shengwang", "COSYVOICE_PAYLOAD_STYLE"),
        cosyvoice_ref_wav=_env("COSYVOICE_REF_WAV", "AIFILM_COSYVOICE_REF"),
        cosyvoice_speaker=_resolve("default", "COSYVOICE_SPEAKER"),
        cosyvoice_language=_resolve("zh", "COSYVOICE_LANGUAGE"),
        cosyvoice_prompt_text=_env("COSYVOICE_PROMPT_TEXT"),
        cosyvoice_ref_as_b64=_resolve_bool("COSYVOICE_REF_AS_B64", default=False),
        # ElevenLabs
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_resolve("cgSgspJ2msm6clMCkdW9", "ELEVENLABS_VOICE_ID"),
        elevenlabs_model=_resolve("eleven_multilingual_v2", "ELEVENLABS_MODEL"),
        # Music
        music_gen_base_url=_resolve(
            "http://127.0.0.1:7860", "MUSIC_GEN_BASE_URL", "ACESTEP_BASE_URL"
        ),
        music_gen_endpoint=_resolve("/generate", "MUSIC_GEN_ENDPOINT"),
        music_gen_extra_json=_env("MUSIC_GEN_EXTRA_JSON"),
        music_argv=_env("AIFILM_MUSIC_ARGV"),
        music_prompt=_env("AIFILM_MUSIC_PROMPT"),
        music_timeout=_resolve_int("AIFILM_MUSIC_TIMEOUT", default=600),
        music_require=_resolve_bool("AIFILM_MUSIC_REQUIRE", default=False),
        music_license=_env("AIFILM_MUSIC_LICENSE"),
        # FRW
        frw_api_key=_env("FRW_API_KEY"),
        frwclaw_root=_env("FRWCLAW_ROOT"),
        # I2V
        i2v_profile=_resolve("grok_primary", "AIFILM_I2V_PROFILE"),
        seedance_available=_resolve_bool("AIFILM_SEEDANCE_AVAILABLE", default=False),
        # Lipsync
        lipsync_backend=_resolve("off", "AIFILM_LIPSYNC_BACKEND"),
        lipsync_argv=_env("AIFILM_LIPSYNC_ARGV"),
        musetalk_root=_env("AIFILM_MUSETALK_ROOT"),
        wav2lip_root=_env("AIFILM_WAV2LIP_ROOT"),
        # Pipeline gates
        skip_pilot_gate=_resolve_bool("AIFILM_SKIP_PILOT_GATE", default=False),
        skip_loop_risk_gate=_resolve_bool("AIFILM_SKIP_LOOP_RISK_GATE", default=False),
        strict_tts_rehearsal=_resolve_bool("AIFILM_STRICT_TTS_REHEARSAL", default=False),
        hud_stage=_resolve_bool("AIFILM_HUD_STAGE", default=True),
    )
    _CONFIG_ENV_FINGERPRINT = fingerprint
    return _CONFIG


_ENV_HELP: dict[str, str] = {
    "AIFILM_GROK_AUTH": "OAuth mode: auto | oauth | api_key",
    "XAI_API_KEY": "CI fallback API key (not for production OAuth flow)",
    "AIFILM_GROK_AUTH_PATH": "Custom auth.json path (aliases: GROK_AUTH_JSON)",
    "AIFILM_GROK_API_BASE": "xAI API base URL (alias: XAI_BASE_URL)",
    "AIFILM_GROK_CHAT_MODEL": "OAuth chat model id",
    "AIFILM_GROK_IMAGE_MODEL": "OAuth image generation model id",
    "AIFILM_GROK_VIDEO_MODEL": "OAuth I2V video model id",
    "AIFILM_GROK_TTS_VOICE": "Grok TTS voice (eve | ara | leo | carina | zagan | …)",
    "AIFILM_GROK_TTS_LANGUAGE": "Grok TTS language (zh | en | …)",
    "AIFILM_GROK_PROBE_TTS": "Set to 1 to enable deep TTS voice list in doctor probe",
    "AIFILM_TTS_BACKEND": "Active TTS backend: auto | edge | fish | minimax | voicebox | grok | external",
    "AIFILM_TTS_STRICT_VOICE": "1 = fail on missing voice_id (default 1)",
    "AIFILM_TTS_VOICEBOX_FALLBACK": "0|1 — opt-in: try Voicebox when explicit backend fails",
    "AIFILM_TTS_ARGV": "External TTS command as JSON argv array",
    "FISH_API_KEY": "Fish Audio API key (aliases: FISH_AUDIO_API_KEY, AIFILM_FISH_API_KEY)",
    "FISH_VOICE_ID": "Fish Audio reference/voice id (aliases: AIFILM_FISH_VOICE_ID, FISH_REFERENCE_ID)",
    "FISH_MODEL": "Fish Audio model (aliases: AIFILM_FISH_MODEL); default s2.1-pro-free",
    "MINIMAX_API_KEY": "MiniMax API key (alias: AIFILM_MINIMAX_API_KEY)",
    "MINIMAX_VOICE_ID": "MiniMax voice id (alias: AIFILM_MINIMAX_VOICE_ID)",
    "MINIMAX_MODEL": "MiniMax model (alias: AIFILM_MINIMAX_MODEL); default speech-2.6-hd",
    "MINIMAX_GROUP_ID": "MiniMax GroupId for resource isolation",
    "VOICEBOX_BASE_URL": "Voicebox local API URL (alias: AIFILM_VOICEBOX_URL)",
    "VOICEBOX_PROFILE": "Voicebox profile name or id (aliases: VOICEBOX_PROFILE_ID, AIFILM_VOICEBOX_PROFILE)",
    "VOICEBOX_LANGUAGE": "Voicebox TTS language (alias: AIFILM_VOICEBOX_LANGUAGE); default zh",
    "VOICEBOX_ENGINE": "Voicebox engine (alias: AIFILM_VOICEBOX_ENGINE); qwen | kokoro | chatterbox | …",
    "COSYVOICE_BASE_URL": "CosyVoice HTTP server URL (alias: AIFILM_COSYVOICE_URL)",
    "COSYVOICE_ENDPOINT": "CosyVoice API endpoint path; default /tts",
    "COSYVOICE_PAYLOAD_STYLE": "CosyVoice payload shape: shengwang | funaudio | openaiish",
    "COSYVOICE_REF_WAV": "CosyVoice reference WAV path (alias: AIFILM_COSYVOICE_REF)",
    "COSYVOICE_SPEAKER": "CosyVoice default speaker id",
    "COSYVOICE_LANGUAGE": "CosyVoice language; default zh",
    "COSYVOICE_PROMPT_TEXT": "CosyVoice prompt text for funaudio style zero-shot",
    "COSYVOICE_REF_AS_B64": "1 = inline reference audio as base64 in JSON body",
    "ELEVENLABS_API_KEY": "ElevenLabs API key",
    "ELEVENLABS_VOICE_ID": "ElevenLabs voice id",
    "ELEVENLABS_MODEL": "ElevenLabs model; default eleven_multilingual_v2",
    "MUSIC_GEN_BASE_URL": "External music generator base URL (alias: ACESTEP_BASE_URL)",
    "MUSIC_GEN_ENDPOINT": "Music gen API endpoint; default /generate",
    "MUSIC_GEN_EXTRA_JSON": "Extra JSON merged into music gen payload",
    "AIFILM_MUSIC_ARGV": "External music command as JSON argv array",
    "AIFILM_MUSIC_PROMPT": "Default music generation prompt text",
    "AIFILM_MUSIC_TIMEOUT": "Music generation timeout in seconds; default 600",
    "AIFILM_MUSIC_REQUIRE": "1 = fail final if music generation fails (no procedural fallback)",
    "AIFILM_MUSIC_LICENSE": "License note for externally generated music",
    "FRW_API_KEY": "FRW API key for env-plate / lipsync tasks",
    "FRWCLAW_ROOT": "FRW claw project root path",
    "AIFILM_I2V_PROFILE": "I2V operating profile: grok_primary | seedance_first",
    "AIFILM_SEEDANCE_AVAILABLE": "0|1 — whether Seedance I2V is available this season",
    "AIFILM_LIPSYNC_BACKEND": "Lipsync backend: off | auto | musetalk | wav2lip | external",
    "AIFILM_LIPSYNC_ARGV": "External lipsync command as JSON argv array",
    "AIFILM_MUSETALK_ROOT": "MuseTalk installation root path",
    "AIFILM_WAV2LIP_ROOT": "Wav2Lip installation root path",
    "AIFILM_SKIP_PILOT_GATE": "1 = skip pilot approval gate (test emergency only)",
    "AIFILM_SKIP_LOOP_RISK_GATE": "1 = skip loop risk gate (test emergency only)",
    "AIFILM_STRICT_TTS_REHEARSAL": "1 = enforce strict TTS rehearsal checks",
    "AIFILM_HUD_STAGE": "0|1 — HUD sidecar; use AIFILM_HUD_STAGE=0 to suppress",
}


def generate_example() -> str:
    lines: list[str] = [
        "# ai-film-grok config template",
        "# Copy to config.env and chmod 600. Never commit config.env.",
        "",
        "# ── TTS ─────────────────────────────────────────────────────────",
    ]
    for key, help_text in _ENV_HELP.items():
        lines.append(f"# {help_text}")
        if key in _DEFAULT_EXAMPLES:
            val, comment = _DEFAULT_EXAMPLES[key]
            lines.append(f"{key}={val}")
            if comment:
                lines[-1] += f"   # {comment}"
        else:
            lines.append(f"# {key}=")
        lines.append("")
    return "\n".join(lines)


_DEFAULT_EXAMPLES: dict[str, tuple[str, str]] = {
    "AIFILM_TTS_BACKEND": ("edge", "edge | fish | minimax | voicebox | grok | external"),
    "AIFILM_TTS_STRICT_VOICE": ("1", ""),
    "AIFILM_LIPSYNC_BACKEND": ("off", "off | auto | musetalk | wav2lip | external"),
    "AIFILM_GROK_AUTH": ("auto", "auto | oauth | api_key"),
    "AIFILM_GROK_AUTH_PATH": ("~/.grok/auth.json", ""),
    "AIFILM_GROK_API_BASE": ("https://api.x.ai/v1", ""),
    "AIFILM_GROK_CHAT_MODEL": ("grok-4.5", ""),
    "AIFILM_GROK_IMAGE_MODEL": ("grok-imagine-image", ""),
    "AIFILM_GROK_VIDEO_MODEL": ("grok-imagine-video", ""),
    "AIFILM_GROK_TTS_VOICE": ("eve", "eve | ara | leo | carina | zagan | …"),
    "AIFILM_GROK_TTS_LANGUAGE": ("zh", "zh | en | …"),
    "AIFILM_I2V_PROFILE": ("grok_primary", "grok_primary | seedance_first"),
    "AIFILM_SEEDANCE_AVAILABLE": ("0", ""),
    "VOICEBOX_BASE_URL": ("http://127.0.0.1:17493", "alias: AIFILM_VOICEBOX_URL"),
    "VOICEBOX_PROFILE": ("", "alias: AIFILM_VOICEBOX_PROFILE; name or id; one voice one lock"),
    "VOICEBOX_LANGUAGE": ("zh", "alias: AIFILM_VOICEBOX_LANGUAGE"),
    "VOICEBOX_ENGINE": ("qwen", "alias: AIFILM_VOICEBOX_ENGINE; qwen | kokoro | chatterbox | …"),
    "FISH_MODEL": ("s2.1-pro-free", ""),
    "MINIMAX_MODEL": ("speech-2.6-hd", ""),
    "ELEVENLABS_VOICE_ID": ("cgSgspJ2msm6clMCkdW9", "Jessica — young, cute, playful"),
    "ELEVENLABS_MODEL": ("eleven_multilingual_v2", ""),
}


# Also expose the dict for tests / introspection
ENV_HELP = _ENV_HELP
