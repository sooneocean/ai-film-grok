# 2026-07-21 · Grok OAuth Pack 最大化

## 做了什么
把 ai-film-grok 的 `grok_oauth.py` 从 doctor/chat/image 扩成完整 OAuth 多模态包（参考 grok-sdk-packager 能力清单）：

| 能力 | 状态 | 端点 |
|------|------|------|
| chat + JSON mode | ✅ | /chat/completions |
| image gen | ✅ | /images/generations |
| image edit | ✅ | /images/edits |
| video I2V async+poll | ✅ | /videos/generations + GET /videos/{id} |
| TTS + speech tags + timestamps | ✅ | /tts · /tts/voices |
| STT / Voice Agent | 刻意不做默认 | 非成片管线 |
| 原生 lipsync | 无（诚实） | FRW/本地 + TTS timestamps |

## 鉴权
- 优先 `~/.grok/auth.json` OAuth（SuperGrok）
- fallback `XAI_API_KEY`
- 零 `xai-sdk` 依赖

## 成片默认不变
- I2V: grok_primary
- TTS: edge（grok 仅 opt-in `--tts-backend grok`）

## 实测（sooneocean@, tier 5）
- doctor --deep: 26 TTS voices, imagine-video ok
- tts zh eve: 41KB mp3 + timestamps
- i2v 1s 480p: 98KB mp4, ffprobe ~1.04s
- image-edit cast: 292KB png

## CLI
`aifilm grok-oauth {doctor,refresh,chat,image,image-edit,video,video-status,tts,voices}`
