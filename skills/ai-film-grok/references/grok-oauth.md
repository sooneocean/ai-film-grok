# Grok OAuth Pack · 最大化 SuperGrok 订阅额度

> 你有 **Grok OAuth**（`~/.grok/auth.json`，`grok login`）时，本 skill 走 **api.x.ai** 的完整多模态包：  
> **chat · image · image-edit · video(i2v) · TTS**。零第三方 SDK 依赖（stdlib only）。  
> **Grok Build 会话内**仍优先原生 `image_gen` / `image_edit` / `image_to_video`。  
> OAuth 用于：机位探测、**批处理 bulk**、离线 structured 规划、会话外补 still/clip/VO。

## 一句话

```bash
grok login                                   # 浏览器 OAuth（一次）
aifilm grok-oauth doctor --deep              # token + models + TTS 旗标
aifilm grok-oauth video --image kf.png \
  --prompt "subtle motion" --out clip.mp4 --wait --duration 6 --resolution 720p
aifilm grok-oauth tts --text "更衣室里，她没回头。" --out vo.mp3 --language zh
```

## 鉴权解析顺序

| 模式 `AIFILM_GROK_AUTH` | 行为 |
|-------------------------|------|
| **`auto`（默认）** | 有 `auth.json` → OAuth；否则 `XAI_API_KEY` |
| `oauth` | 只用 `~/.grok/auth.json`（可 `AIFILM_GROK_AUTH_PATH`） |
| `api_key` | 只用 `XAI_API_KEY`（CI） |

Token 将过期（默认 <5 分钟）时自动 **OIDC refresh** 并回写 `auth.json`（chmod 600）。  
**永不**把 token 写进 film-spec / 日志 / 聊天。

## 能力包（OAuth 实测）

| 能力 | 端点 | CLI | 成片用法 |
|------|------|-----|----------|
| **Chat / Agent** | `POST /v1/chat/completions` | `grok-oauth chat` | 离线拆 brief / director_intent / beats JSON（`--json`） |
| **T2I** | `POST /v1/images/generations` | `grok-oauth image` | 批处理 still；会话优先 `image_gen` |
| **I2I / Edit** | `POST /v1/images/edits` | `grok-oauth image-edit` | cast 锁脸 keyframe；多 ref `--ref` |
| **I2V / T2V** | `POST /v1/videos/generations` + poll | `grok-oauth video --wait` | **批处理 bulk**（`grok_primary` 离线） |
| **TTS** | `POST /v1/tts` · `GET /v1/tts/voices` | `grok-oauth tts` · `voices` | **opt-in**：`--tts-backend grok`（默认仍 edge） |
| **Timestamps** | TTS `with_timestamps` | `--timestamps` | 字幕 / 本地 lipsync 对齐（非原生口型） |
| **STT / Voice Agent** | 企业 Voice API | — | **未接**成片默认（WebSocket 实时，非 VO 管线） |
| **原生 lipsync** | — | — | **无** Grok 原生对嘴；近景用 FRW lipsync 或本地 MuseTalk |

### 模型（以 `doctor` 列表为准）

常见：`grok-4.5` · `grok-4.3` · `grok-imagine-image` · `grok-imagine-image-quality` ·  
`grok-imagine-video` · `grok-imagine-video-1.5`（**仅 I2V**）。

Env 覆盖：

| 变量 | 默认 |
|------|------|
| `AIFILM_GROK_CHAT_MODEL` | `grok-4.5` |
| `AIFILM_GROK_IMAGE_MODEL` | `grok-imagine-image` |
| `AIFILM_GROK_VIDEO_MODEL` | `grok-imagine-video` |
| `AIFILM_GROK_TTS_VOICE` | `eve` |
| `AIFILM_GROK_TTS_LANGUAGE` | `zh` |

## 命令

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"
# 或 plugin: $HOME/.grok/plugins/ai-film-grok/skills/ai-film-grok/scripts/aifilm

"$AIFILM" grok-oauth doctor --deep
"$AIFILM" grok-oauth refresh

# Chat（JSON 规划）
"$AIFILM" grok-oauth chat --prompt "输出 60s 竖屏 logline JSON" --json \
  --system "只输出 JSON：logline,theme,beats[]"

# Still
"$AIFILM" grok-oauth image --prompt "anime girl soft light 9:16 no text" \
  --out /tmp/still.png --aspect 9:16

# Edit（锁脸）
"$AIFILM" grok-oauth image-edit --image cast/hero-v1.png \
  --prompt "same face, locker room soft light, 9:16, no text watermark" \
  --out keyframes/shot01.png

# I2V bulk（异步 poll）
"$AIFILM" grok-oauth video --image keyframes/shot01.png \
  --prompt "subtle breath, soft camera drift, keep identity" \
  --out clips/shot01_grok.mp4 --wait --duration 6 --resolution 720p

# 只提交 / 稍后取回
"$AIFILM" grok-oauth video --image kf.png --prompt "…"   # → request_id
"$AIFILM" grok-oauth video-status --request-id <id> --wait --out clip.mp4

# TTS（opt-in；支持 speech tags）
"$AIFILM" grok-oauth voices
"$AIFILM" grok-oauth tts --text "她停了一下。[pause] 没回头。" \
  --out audio/vo/shot01.mp3 --voice eve --language zh --timestamps
```

适配器（批处理脚本）：

```bash
python3 scripts/adapters/grok_oauth_image.py --prompt "…" --out still.png
python3 scripts/adapters/grok_oauth_image_edit.py --image cast.png --prompt "…" --out kf.png
python3 scripts/adapters/grok_oauth_video.py --image kf.png --prompt-file p.txt --out clip.mp4
python3 scripts/adapters/grok_oauth_tts.py --text "…" --out vo.mp3 --language zh
```

## 与 skill 管线怎么叠

| 场景 | 用什么 |
|------|--------|
| Grok Build **交互**出图/I2V | **原生工具**（OAuth 登录即配额） |
| **pilot 批准后 bulk** I2V 无会话 | `grok-oauth video --wait` → `register-clip --source-endpoint image_to_video` |
| 离线 cast keyframe | `grok-oauth image-edit` + cast master |
| 离线拆剧本 JSON | `grok-oauth chat --json` → 写 film-spec → `write-spec` |
| 成片 TTS 默认 | 仍 **edge**（可复现、零依赖） |
| 成片 TTS 升档（SuperGrok） | `final --tts-backend grok` 或 `AIFILM_TTS_BACKEND=grok` |
| 对口型 | 近景：Grok TTS `--timestamps` + 本地 lipsync；或 `frw-lipsync` |
| `capability` / `doctor` | `grok_oauth` 字段含 pack / has_tts / has_imagine_video |

`dispatch` 的 `routing.grok_build` 会提示 OAuth 路径；总表见 [grok-build-sdk.md](grok-build-sdk.md)。

## Speech tags（Grok TTS）

| 类型 | 示例 |
|------|------|
| 内联 | `[pause]` `[laugh]` `[sigh]` |
| 包裹 | `<whisper>…</whisper>` `<slow>…</slow>` `<soft>…</soft>` |

```text
她推开门。[pause] <whisper>有人在。</whisper>
```

## 诚实边界

| 宣称 | 事实 |
|------|------|
| OAuth = 免费无限 | 走订阅/团队额度；video 按秒计费（API key 路径尤其明显） |
| 原生 lip-sync 成片 | **无**；timestamps 助对齐，口型靠 FRW/本地 |
| TTS 替代 edge 默认 | **否**；grok 是显式 opt-in |
| STT 进 film-spec | 听写 brief 可另接；不替代 `nar` Radio |
| 官方 `xai-sdk` pip | 可选；本 pack **不依赖**，用 REST + OAuth |

## 故障

| 现象 | 处理 |
|------|------|
| auth.json missing | `grok login` |
| HTTP 401 | `aifilm grok-oauth refresh` 或重新 login |
| video poll timeout | 加大 `--timeout`；查 `video-status` |
| 1.5 模型无图 | `grok-imagine-video-1.5` 仅 I2V，必须 `--image` |
| TTS 403 旧路径 | 用 `/v1/tts`（本 pack 已用）；勿用 `/audio/speech` |
| 只要 CI | `AIFILM_GROK_AUTH=api_key` + `XAI_API_KEY` |

安全：`auth.json` 仅本机 600；skill 子进程不回显 Bearer。
