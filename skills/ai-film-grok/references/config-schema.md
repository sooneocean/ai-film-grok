# Config Schema (config_loader.py)

Centralized configuration loader at `scripts/config_loader.py`. Replaces duplicated
`_load_config_env()` across adapters and backend files.

## Usage

```python
from config_loader import get_config, generate_example, ConfigSchema

cfg = get_config()
print(cfg.tts_backend)       # → str, default "edge"
print(cfg.fish_api_key)      # → str, "" if unset
print(cfg.seedance_available)  # → bool, default False
```

## Env Var Reference

### Grok OAuth

| ConfigSchema field | Env vars (first wins) | Type | Default | Description |
|---|---|---|---|---|
| `grok_auth` | `AIFILM_GROK_AUTH` | str | `auto` | OAuth mode: auto \| oauth \| api_key |
| `xai_api_key` | `XAI_API_KEY` | str | — | CI fallback API key (not for production OAuth) |
| `grok_auth_path` | `AIFILM_GROK_AUTH_PATH` / `GROK_AUTH_JSON` | str | — | Custom auth.json path |
| `grok_api_base` | `AIFILM_GROK_API_BASE` / `XAI_BASE_URL` | str | `https://api.x.ai/v1` | xAI API base URL |
| `grok_chat_model` | `AIFILM_GROK_CHAT_MODEL` | str | `grok-4.5` | OAuth chat model |
| `grok_image_model` | `AIFILM_GROK_IMAGE_MODEL` | str | `grok-imagine-image` | OAuth image model |
| `grok_video_model` | `AIFILM_GROK_VIDEO_MODEL` | str | `grok-imagine-video` | OAuth I2V model |
| `grok_tts_voice` | `AIFILM_GROK_TTS_VOICE` | str | `eve` | Grok TTS voice |
| `grok_tts_language` | `AIFILM_GROK_TTS_LANGUAGE` | str | `zh` | Grok TTS language |
| `grok_probe_tts` | `AIFILM_GROK_PROBE_TTS` | bool | `False` | Deep TTS probe in doctor |

### TTS

| ConfigSchema field | Env vars (first wins) | Type | Default | Description |
|---|---|---|---|---|
| `tts_backend` | `AIFILM_TTS_BACKEND` | str | `edge` | Active backend: auto\|edge\|fish\|minimax\|voicebox\|grok\|external |
| `tts_strict_voice` | `AIFILM_TTS_STRICT_VOICE` | bool | `True` | Fail on missing voice_id |
| `tts_voicebox_fallback` | `AIFILM_TTS_VOICEBOX_FALLBACK` | bool | `False` | Try Voicebox on explicit backend failure |
| `tts_argv` | `AIFILM_TTS_ARGV` | str | — | External TTS JSON argv |

### Fish Audio

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `fish_api_key` | `FISH_API_KEY` / `FISH_AUDIO_API_KEY` / `AIFILM_FISH_API_KEY` | str | — |
| `fish_voice_id` | `FISH_VOICE_ID` / `AIFILM_FISH_VOICE_ID` / `FISH_REFERENCE_ID` | str | — |
| `fish_model` | `FISH_MODEL` / `AIFILM_FISH_MODEL` | str | `s2.1-pro-free` |

### MiniMax

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `minimax_api_key` | `MINIMAX_API_KEY` / `AIFILM_MINIMAX_API_KEY` | str | — |
| `minimax_voice_id` | `MINIMAX_VOICE_ID` / `AIFILM_MINIMAX_VOICE_ID` | str | `Chinese (Mandarin)_Lyrical_Voice` |
| `minimax_model` | `MINIMAX_MODEL` / `AIFILM_MINIMAX_MODEL` | str | `speech-2.6-hd` |
| `minimax_group_id` | `MINIMAX_GROUP_ID` | str | — |

### Voicebox

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `voicebox_base_url` | `VOICEBOX_BASE_URL` / `AIFILM_VOICEBOX_URL` | str | `http://127.0.0.1:17493` |
| `voicebox_profile` | `VOICEBOX_PROFILE` / `VOICEBOX_PROFILE_ID` / `AIFILM_VOICEBOX_PROFILE` | str | — |
| `voicebox_language` | `VOICEBOX_LANGUAGE` / `AIFILM_VOICEBOX_LANGUAGE` | str | `zh` |
| `voicebox_engine` | `VOICEBOX_ENGINE` / `AIFILM_VOICEBOX_ENGINE` | str | `qwen` |

### CosyVoice

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `cosyvoice_base_url` | `COSYVOICE_BASE_URL` / `AIFILM_COSYVOICE_URL` | str | `http://127.0.0.1:9880` |
| `cosyvoice_endpoint` | `COSYVOICE_ENDPOINT` | str | `/tts` |
| `cosyvoice_payload_style` | `COSYVOICE_PAYLOAD_STYLE` | str | `shengwang` |
| `cosyvoice_ref_wav` | `COSYVOICE_REF_WAV` / `AIFILM_COSYVOICE_REF` | str | — |
| `cosyvoice_speaker` | `COSYVOICE_SPEAKER` | str | `default` |
| `cosyvoice_language` | `COSYVOICE_LANGUAGE` | str | `zh` |
| `cosyvoice_prompt_text` | `COSYVOICE_PROMPT_TEXT` | str | — |
| `cosyvoice_ref_as_b64` | `COSYVOICE_REF_AS_B64` | bool | `False` |

### ElevenLabs

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `elevenlabs_api_key` | `ELEVENLABS_API_KEY` | str | — |
| `elevenlabs_voice_id` | `ELEVENLABS_VOICE_ID` | str | `cgSgspJ2msm6clMCkdW9` |
| `elevenlabs_model` | `ELEVENLABS_MODEL` | str | `eleven_multilingual_v2` |

### Music / BGM

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `music_gen_base_url` | `MUSIC_GEN_BASE_URL` / `ACESTEP_BASE_URL` | str | `http://127.0.0.1:7860` |
| `music_gen_endpoint` | `MUSIC_GEN_ENDPOINT` | str | `/generate` |
| `music_gen_extra_json` | `MUSIC_GEN_EXTRA_JSON` | str | — |
| `music_argv` | `AIFILM_MUSIC_ARGV` | str | — |
| `music_prompt` | `AIFILM_MUSIC_PROMPT` | str | — |
| `music_timeout` | `AIFILM_MUSIC_TIMEOUT` | int | `600` |
| `music_require` | `AIFILM_MUSIC_REQUIRE` | bool | `False` |
| `music_license` | `AIFILM_MUSIC_LICENSE` | str | — |

### I2V

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `i2v_profile` | `AIFILM_I2V_PROFILE` | str | `grok_primary` |
| `seedance_available` | `AIFILM_SEEDANCE_AVAILABLE` | bool | `False` |

### Lipsync

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `lipsync_backend` | `AIFILM_LIPSYNC_BACKEND` | str | `off` |
| `lipsync_argv` | `AIFILM_LIPSYNC_ARGV` | str | — |
| `musetalk_root` | `AIFILM_MUSETALK_ROOT` | str | — |
| `wav2lip_root` | `AIFILM_WAV2LIP_ROOT` | str | — |

### FRW

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `frw_api_key` | `FRW_API_KEY` | str | — |
| `frwclaw_root` | `FRWCLAW_ROOT` | str | — |

### Pipeline Gates

| ConfigSchema field | Env vars (first wins) | Type | Default |
|---|---|---|---|
| `skip_pilot_gate` | `AIFILM_SKIP_PILOT_GATE` | bool | `False` |
| `skip_loop_risk_gate` | `AIFILM_SKIP_LOOP_RISK_GATE` | bool | `False` |
| `strict_tts_rehearsal` | `AIFILM_STRICT_TTS_REHEARSAL` | bool | `False` |
| `hud_stage` | `AIFILM_HUD_STAGE` | bool | `True` |

## Env var resolution order

1. Already-set `os.environ` values (highest priority, never overridden)
2. `config.env` file at skill root or `~/.grok/skills/ai-film-grok/config.env`
3. Default values in `ConfigSchema`

## `generate_example()`

Produces a complete `.env.example` with all documented vars.

```python
from config_loader import generate_example
print(generate_example())
```
