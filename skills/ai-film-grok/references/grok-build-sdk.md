# Grok Build · SDK 能力矩阵（ai-film-grok 专用）

> 本 skill **为 Grok Build 打造**：agent 在会话内用 **原生工具** 发挥 Grok 最大价值；
> 本地 `aifilm` 管门禁/队列/成片；**OAuth pack**（`grok_oauth.py`）吃满 SuperGrok 订阅额度做批处理。
> 官方 `xai-sdk` pip **不必装**——本 pack 用 REST + `~/.grok/auth.json`（stdlib only）。

## 一句话

```text
Grok 脑（推理+工具）→ Imagine 静帧/I2V（会话原生或 OAuth 批处理）→ edge|grok TTS → HF/FFmpeg
每环先 aifilm dispatch；鉴权优先 OAuth，fallback API Key
```

## OAuth Pack（最大化订阅额度）

| 模块 | REST | 会话原生 | 批处理 CLI |
|------|------|----------|------------|
| Chat / Structured | `/chat/completions` | 本会话模型 | `grok-oauth chat [--json]` |
| Image gen | `/images/generations` | `image_gen` | `grok-oauth image` |
| Image edit | `/images/edits` | `image_edit` | `grok-oauth image-edit` |
| Video I2V | `/videos/generations` + poll | `image_to_video` | `grok-oauth video --wait` |
| TTS + speech tags | `/tts` · `/tts/voices` | （无一等工具） | `grok-oauth tts` · `--tts-backend grok` |
| Timestamps → lipsync 辅助 | TTS `with_timestamps` | — | `--timestamps` sidecar |
| 原生口型 | — | — | **无**；FRW lipsync / 本地 MuseTalk |

入口：`aifilm grok-oauth doctor --deep` · 详见 [grok-oauth.md](grok-oauth.md)。
---

## 六大模块 → Grok Build 落点

| 模块 | 主要能力 | Grok Build 原生 | skill 落点 | 视频制作价值 |
|------|----------|-----------------|------------|--------------|
| **Text / Reasoning** | Grok 4.5、Reasoning、Structured Outputs、长上下文 | 本会话模型 + 输出 JSON/Markdown | Idea–Beats–Shots：Lens、film-spec、`director_intent`、lint 文案 | 剧本拆解、分镜规划、Prompt 工程、一致性检查、dispatch 决策 |
| **Tools** | Web / X Search、Code、Collections、Function Calling | `web_search` · `x_*` · shell/脚本 · 可选 MCP | 资料搜集、FFmpeg 脚本、自动化、`aifilm` CLI | 事实接地、代码管线、状态管理 |
| **Image（Imagine）** | T2I、Edit、Restyle、Multi-ref、高分辨率 | **`image_gen` · `image_edit`**（必用 `/imagine` 纪律） | L0 身份：style-v1 · cast · lookbook · keyframe | 定妆、关键帧、视觉圣经、风格锁定 |
| **Video（Imagine）** | I2V 为主；可 T2V（非 1.5） | **`image_to_video` · `reference_to_video`** | bulk `grok_primary` 或 OAuth `video --wait`；continue 末帧再 I2V | 真动态；**不**宣称 first-last-frame |
| **Voice** | TTS（tags）/ STT / S2S | 会话内**无**一等 TTS 工具 | **edge** 默认 · **grok opt-in** · Voicebox/CosyVoice/MiniMax | 旁白、对白、混音 |
| **Files & Collections** | 上传、RAG、文档搜 | 工作区文件 + `receipts/`；可选 Collections/MCP | film-root 即项目记忆；style-bible / lens / beat-sheet | 剧本/角色/世界观可恢复 |

**诚实边界（Grok Build 实测纪律）**

| 宣称 | 本 skill 态度 |
|------|----------------|
| Text-to-Video 无源图 | **无**；先 still 再 `image_to_video`（见 `/imagine` Video 节） |
| Video Editing / Extension | 非默认主路径；接戏用 **promote 末帧 + 再 I2V**；长镜用多镜剪辑 |
| 最高 2K still | 跟工具/账号能力；成片默认 9:16 **720p** 动（FRW/Grok I2V 配额与质量） |
| Grok Voice TTS | 未进 `tts_backend` 默认链；要云端情感用 MiniMax/Fish；中文稳用 edge |
| STT / S2S | 成片旁白以 film-spec `nar` 为准；STT 仅辅助（改稿/听写），不替代 Radio |
| xai-sdk 在 Build 会话 | **不必装**也能拍完整片；SDK 给本地脚本/CI |

---

## 八环 × Grok 原生（自动调配表）

| craft | Grok 做什么 | 本地 / FRW 做什么 | 禁止 |
|-------|-------------|-------------------|------|
| **Idea** | 推理 brief；web 查题材事实 | `init` · creative-brief | 无命题 bulk 出图 |
| **Story** | 长上下文：premise/logline/theme；Structured 填 `director_intent` | receipts/directors-lens | 原文插图化 |
| **Beats** | 拆 beat 四项；对 dramatic_function | write-spec lint | Beat=空走位 |
| **Shots** | 每镜 Prompt 工程；Coverage；`image_edit` 构图预演 | film-spec · pilot | ECU 裁头、shot 水印进画面 |
| **Media** | **Still**：`image_edit(cast)` / `image_gen` 空镜；**I2V primary** Grok | FRW Seedance/LTX 仅技术失败 fallback；edge TTS；BGM | 半片混 provider；并行多 I2V 429 |
| **Selects** | 视觉审 identity/motion（读图） | register · selects report | 有文件=可选 |
| **Rough** | 剪辑建议 Editor’s Cut | assemble · plate | continue 缝 dissolve |
| **Verified** | 十一维人审措辞 | final · review-final · export | 技术 final 冒充交付 |

入口：`aifilm dispatch --root`（`routing.grok_build` 含本表指针）。

---

## Image（Imagine）· 锁身份（P1）

加载：`/imagine` skill 纪律（reference-first、一致性、失败不绕审）。

| 任务 | 工具 | 要点 |
|------|------|------|
| 风格样张 style-v1 | `image_gen` | 9:16；medium+signature；无角色脸抽卡反复 |
| 定妆 cast | `image_gen` 一次 master → 之后全 `image_edit(cast)` | 一角一脸 |
| 每镜 keyframe | `image_edit` + cast/style 参考 | 禁纯 `image_gen` 换脸 |
| Restyle / 换装 | `image_edit` | 只描述变更 |
| Multi-image 合成 | `image_edit` 多参考 | 优于乱 `reference_to_video` |
| 真实人名 | 先 search 再 `image_edit` 真参考 | 见 imagine skill |

锁：`aifilm lock-style --canonical --cast-master`。

---

## Video（Imagine）· 真动态

| 任务 | 工具 | 何时用 |
|------|------|--------|
| 默认动作第一路 | **FRW LTX 2.3** `img2video-audio` | `AIFILM_I2V_PROFILE=ltx23_primary` + approved canary |
| 第二路 | **Grok** `image_to_video` / OAuth `video --wait` | live canary；技术切换须签名回执 |
| 第三路 | **FRW Wan** | canary 与响应均须证明 Wan 身份 |
| 本地尾路 | verified Comfy/local | queue、RAM、VRAM 与 pilot 全部过闸 |
| Grok I2V 会话 | `image_to_video` 6s/10s · 720p | pilot / 交互 |
| Grok I2V 批处理 | `aifilm grok-oauth video --image … --wait` | 无会话 bulk、脚本队列 |
| 多参考动 | 优先 edit 成单帧再 I2V；`reference_to_video` 少用 | 用户明确要求时 |
| 接戏 | extract last → promote keyframe → **只对该图** I2V | 禁 cast 重起 |
| T2V 环境床 | FRW `ltx-t2v` | 第一选择；失败后 Grok no-face；**不**用 T2V 锁脸 |

注册：Grok 动 → `--source-endpoint image_to_video`；FRW → `frw_seedance_*` 等。
---

## Text / Reasoning · 结构化出片

Agent 应用模型能力直接产出（再 `write-spec` 校验），不要只丢散文：

| 产出 | 建议结构 |
|------|----------|
| Creative Brief | YAML/JSON：audience · format · goal · emotion |
| director_intent | logline · theme · dramatic_question · start/end_state |
| Beat sheet | 表：新信息 · 状态 · 下一问 · dramatic_function |
| film-spec shots | id · nar · dsl.action/motion · visible_change · shot_role · camera_axis |
| Prompt 包 | still_prompt · i2v_prompt 分文件；无 shot ID 水印进画面 |

长上下文：整片 film-spec + style-bible + 上镜 last frame 描述放进推理，再写下一镜。

---

## Tools · 何时开搜 / 写代码

| 工具 | 用途 |
|------|------|
| `web_search` | 时代/器物/地点事实；真实人物身份 |
| `x_keyword_search` / `x_semantic_search` | 趋势、口碑、素材线索（非必须） |
| Shell + FFmpeg | 探针、reencode、本地成片（经 aifilm） |
| 自定义/MCP | Collections、Drive、日历等 — 可选；**片记忆默认在 film-root** |

Code Interpreter 类任务：生成/修补 `aifilm` 脚本、filtergraph、自动化 — 写入 repo，不口述伪代码交差。

---

## Voice · 与 Grok 会话的关系

Grok Build **会话文本** ≠ 成片音轨。

| 需求 | 路径 |
|------|------|
| 中文说书默认 | `tts_backend: edge` + Neural 固定 |
| **SuperGrok TTS 升档** | **显式** `--tts-backend grok` / `AIFILM_TTS_BACKEND=grok`（`eve` 等；speech tags） |
| 克隆/更自然 | Voicebox / CosyVoice external |
| 云情感 | MiniMax/Fish 固定 voice_id |
| 听写用户口述 brief | 用户粘贴文本或本地 STT；写入 brief |
| 对口型 | 默认 off；Grok TTS `--timestamps` 助对齐；近景 FRW/本地 lipsync |

见 [voices.md](voices.md) · [audio-fallback.md](audio-fallback.md) · [grok-oauth.md](grok-oauth.md)。
---

## Files & Collections · 项目长期记忆

**默认记忆 = film root（可 git / 可恢复）**

```text
<film>/
  brief.json | receipts/creative-brief.md
  receipts/directors-lens.md | beat-sheet.md
  style-bible.json | cast/
  film-spec.json | timeline.json | manifest.json
  receipts/dispatch.json | frw-key-capability.json | mix_report.json
```

| 需求 | 做法 |
|------|------|
| 世界观/角色卡 | style-bible + cast masters + optional `docs/world.md` |
| 跨 session 续作 | 同一 `--root`；先 `dispatch` |
| RAG 大设定集 | 可选 xAI Collections / 本地索引；**权威仍以 film-spec 为准** |
| 上传参考图 | 放入 cast/ 或 refs/；`image_edit` 引用路径 |

---

## 与 FRW / 本地四层如何叠（P5）

```text
【Grok Build 会话】
  Reasoning → film-spec / prompts
  image_gen / image_edit → stills（身份）
  image_to_video → 动（兜底/Grok 路径）
  web_search → 事实
【本地 aifilm】
  write-spec · pilot · queue · register · final · review
【FRW】
  Seedance / LTX bulk 动 + env
【语音本地/云】
  edge · voicebox · …
【设计】
  HyperFrames / Remotion
```

同源纪律：同一角色 **禁止** 半片 Grok still、半片 FRW still 混剪。

---

## Grok OAuth Pack（推荐 · SuperGrok）

```bash
grok login
aifilm grok-oauth doctor --deep
aifilm grok-oauth image --prompt "…" --out still.png
aifilm grok-oauth image-edit --image cast.png --prompt "…" --out kf.png
aifilm grok-oauth video --image kf.png --prompt "…" --out clip.mp4 --wait
aifilm grok-oauth tts --text "…" --out vo.mp3 --language zh
```

详见 [grok-oauth.md](grok-oauth.md)。鉴权：`auth.json` OAuth → 可选 `XAI_API_KEY`。
**不强制** `pip install xai-sdk`；需要 OpenAI 兼容壳时见 `adapters/xai_openai_compat.example.py`。

**Grok Build 内做片：优先原生工具；批处理 / 离线：优先 OAuth pack。**

---

## Agent 检查单（每片）

- [ ] `dispatch` 定环
- [ ] `grok-oauth doctor` 绿（有 bulk/OAuth 需求时）
- [ ] Still：Grok `image_edit(cast)` 或 OAuth `image-edit`，加载 `/imagine`
- [ ] I2V：会话 `image_to_video` 或 `grok-oauth video --wait`；register 真 endpoint
- [ ] 文本：Structured 字段进 film-spec，不是只有故事散文
- [ ] 事实：该搜的先 `web_search`
- [ ] 声：edge 默认；升档才 `grok`；不把 Neural 塞 EL
- [ ] 记忆：写回 film-root receipts
- [ ] 交付：十一维 + export

权威交叉：[craft-spine.md](craft-spine.md) · [grok-media-pipeline.md](grok-media-pipeline.md) · [consistency.md](consistency.md) · [auto-dispatch.md](auto-dispatch.md)
