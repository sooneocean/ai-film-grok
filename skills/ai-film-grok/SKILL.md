---
name: ai-film-grok
description: Grok Build 专用 AI 短片 skill：八环 Idea→Verified 自动调配（dispatch）+ Imagine 静帧/I2V bulk（grok_primary）+ OAuth 多模态包（chat/image/edit/video/tts）+ edge TTS（opt-in grok）+ HF/FFmpeg。触发：AI 电影、漫剧、Grok Imagine、dispatch、成片、/ai-film-grok。
---

# AI Film Grok

把模糊想法**逐层**收成可恢复、可验收的真实动态成片（I2V + 混音字幕）。静图轮播、Ken Burns、只有关键帧 ≠ 成片。

**本 skill 为 Grok Build 打造**：会话内优先 **Grok 推理 + Imagine 工具 + Web/X 检索**；本地 `aifilm` 管门禁与成片。能力总表 → [grok-build-sdk.md](references/grok-build-sdk.md)。

**双轴主脊**：
- **电影工序**（减叙事模糊）：[craft-spine.md](references/craft-spine.md) · [generative-film-craft.md](references/generative-film-craft.md)
- **工具四层**（减实现模糊）：[pipeline-methodology.md](references/pipeline-methodology.md)
- 弹性默认：[hard-defaults.md](references/hard-defaults.md) · 宪法：[principles.md](references/principles.md)（P0–P5）

**原则**：工程门禁硬；**叙事/尺度/女主/工序深度软**——跟 Prompt 与参考图走。前一层未确认不 bulk 生成。

```text
【工序八环】Idea → Story → Beats → Shots → Media → Selects → Rough → Verified MP4
【工具】Agent → 1视觉 → 2语音 → 3设计(HF) → 4FFmpeg → 交付
【六动词】Define → Structure → Visualize → Generate → Select → Edit
【自动调配】每回合优先 aifilm dispatch --root <film> → 只执行 next_cmd
```

主脊详解：[craft-spine.md](references/craft-spine.md) · 音频三阶梯：[audio-fallback.md](references/audio-fallback.md) · 调度：[auto-dispatch.md](references/auto-dispatch.md)

### Agent 自动调配（强制）

开任何片子、每完成一步后：

```bash
"$AIFILM" dispatch --root "<root>"
# 读 JSON：craft_stage · next_cmd · agent_instruction · routing
# 本回合只做 next_cmd；做完再 dispatch。禁止跳环 bulk。
```

| 字段 | 含义 |
|------|------|
| `craft_stage` | 八环当前位置 |
| `next_cmd` | **唯一**推荐命令 |
| `agent_do` / `agent_instruction` | 本回合 checklist |
| `routing` | TTS/BGM/I2V 自动兜底策略摘要 |
| `hard_gates` | 不可跳过的门禁 |

`dispatch` **不会**自批 pilot、不会静默改 film-spec、不会默认开 lipsync。用户说「可以 / 一路做完」才 unlock 批量。

**一键工程顺序**（勿与工序心智搞反）：  
`final --post-engine hyperframes` = `[4] FFmpeg plate（subs off）→ [3] HF → [4] 封装`。

**工具栈（Grok Build + OAuth 最大化 · I2V=`grok_primary`）**

| 层 | Grok Build 原生 | OAuth 批处理（`grok-oauth`） | 本地/外部 |
|----|-----------------|------------------------------|-----------|
| 脑 | 推理 · Structured · 长上下文 | `chat [--json]` | film-spec / Lens / dispatch |
| 搜 | `web_search` · `x_*` | — | 事实接地 |
| 静帧 | **`image_gen` / `image_edit`**（`/imagine`） | `image` · `image-edit` | lock-style · cast |
| 动态 | **`image_to_video` bulk** | **`video --wait` I2V** | register；FRW env 可选 |
| 语音 | 会话≠成片音轨 | **`tts`（opt-in）** speech tags | **edge 默认** · Voicebox |
| 记忆 | 工作区 | — | film-root + receipts |
| 成片 | — | — | FFmpeg · HyperFrames · review |

**I2V 运营模式**：`AIFILM_I2V_PROFILE=grok_primary`（默认）→ `i2v_provider=grok`。见 [i2v-grok-primary.md](references/i2v-grok-primary.md)。  
**Grok OAuth Pack**：`aifilm grok-oauth doctor --deep` → chat/image/edit/video/tts。  
**队列一键 I2V**：`aifilm queue-run-oauth --root … --max N`（claim→OAuth→complete）。详 [grok-oauth.md](references/grok-oauth.md)。  
Seedance 恢复：`AIFILM_I2V_PROFILE=seedance_first` + canary 201。出图前加载 **`/imagine`**。
---

## 阶段 → 下一步（agent 路由）

| `stage` | 工序区（约） | 你该做的 | 典型命令 |
|---|---|---|---|
| `agent` | Development + Pre | Brief/Lens → lock-style → write-spec → **pilot** | `init` `lock-style` `write-spec` `pilot *` |
| `visual` | Production | still → **Grok I2V** → register · continue | `media-queue` `image_to_video` `register-clip` |
| `voice` | Pre/Prod 声轨 | Radio / 真测旁白 | `tts-rehearse --backend edge` |
| `design` | Post 设计 | Studio → 设计成片 | `compose-preview` · `final --post-engine hyperframes` |
| `post` | Post 锁画 | 七维审批 | `review-final` |
| `deliver`/`done` | Master | 导出 | `export-desktop` |

开场固定（**优先 dispatch，其余按需**）：

```bash
# Plugin 优先；兼容旧 user skill 路径
SKILL_DIR="$HOME/.grok/plugins/ai-film-grok/skills/ai-film-grok"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"
MEDIA_QUEUE="$SKILL_DIR/scripts/media-queue"

"$AIFILM" doctor
"$AIFILM" grok-oauth doctor --deep    # OAuth 绿：chat/image/video/tts
"$AIFILM" dispatch --root "<root>"    # 自动调配：craft+机位+next_cmd（主入口）
# 明细拆查（可选）：
# "$AIFILM" capability --root "<root>"   # 含 grok_oauth 字段
# "$AIFILM" craft --root "<root>"
# "$AIFILM" audio-plan --root "<root>"
# "$AIFILM" preflight --root "<root>"
# "$AIFILM" next --root "<root>"
```

`dispatch` 写 `receipts/dispatch.json` + `~/.grok/hud/aifilm-dispatch.*`。  
`status`/`next`/`stage` 仍含 `pipeline_stage` → `receipts/pipeline_stage.json`。关 HUD：`AIFILM_HUD_STAGE=0`。

---

## 硬门禁（工程 · 不可跳）

完整表见 [hard-defaults.md](references/hard-defaults.md)。**仅工程/一致性**最低线：

1. **write-spec 过**（intent / beat / vo_budget）→ 才 queue  
2. **pilot 用户批准** → 才 bulk（无批准 ≤3 shot_id）  
3. **continue**：末帧 SHA = 下镜 keyframe；缝 **hard**；禁 cast 重起  
4. **VO 预算**：`nar`≤55 字；pacing；hook/action 不 loop  
5. **双烧**：设计路径 `plate-cards blank` + `subs off`  
6. **交付**：七维全 pass + 完整观看 → `final_complete`  
7. **失败**：`media-queue fail/requeue`；禁手改 queue JSON  
8. **同源**：禁半片 Grok + 半片 FRW still/2V  

**弹性（跟 brief）**：`heat_scale` / 亲密核镜比 / 单·多女主——由 Prompt 与参考图推断。  
**例外硬底**（`heat_scale=max` write-spec 默认 hard）：  
1) 性爱片段 act+climax **时长 ≥20%**（`sex_floor_strict`）  
2) **办事必须卸甲/脱衣**到 `wardrobe_state`=partial\|undressed\|bare，且有卸装动作拍（`sex_wardrobe_strict`）  
见 [ecchi-story.md](references/ecchi-story.md) · [sex-duration-floor](references/lessons-2026-07-21-sex-duration-floor.md) · [sex-undress-ladder](references/lessons-2026-07-21-sex-undress-ladder.md)。  

---

## 生产流程（按层，命令级）

### 0 · Agent（Development → Pre · 未锁不 bulk）

短片可压缩，但顺序勿倒：**Concept/故事 → Spec → Generate**。详工序 [generative-film-craft.md](references/generative-film-craft.md)。

| 步 | 产出 |
|---|---|
| Creative Brief / 命题 | 受众·片长·情绪 · Premise/Logline/Theme → `director_intent` |
| Beats + 剧本四轨 | 信息/情绪变化 · VO/画面/声 分行 → [directors-lens.md](references/directors-lens.md) |
| Radio 优先 | 时长远超先改字 → `tts-rehearse`（可与 write-spec 交错） |
| Visual Bible | style-v1 + cast + lookbook → `lock-style` |
| Coverage / pilot | 必要镜 canary → score → **用户** `pilot approve` |
| Shot Package | [film-spec.example.json](templates/film-spec.example.json) → `write-spec` |

```bash
"$AIFILM" init --theme "<theme>" --title "<title>" --aspect 9:16 --root "<abs-root>"
"$AIFILM" lock-style --root "<root>" --canonical "<style-v1.png>" \
  --cast-master "<cast/id-v1.png>" --signature "<signature_block>"
"$AIFILM" write-spec --root "<root>"
"$AIFILM" pilot pick --root "<root>" && "$AIFILM" pilot report --root "<root>"
# 用户原话批准后：
"$AIFILM" pilot approve --root "<root>" --user-phrase "可以" --shots shot01,shot03,shot04
```

**film-spec 要点**：`vo_mode` · `tts_backend` · `i2v_provider`/`frw_*` · `director_intent` · 每镜 `dramatic_function` + `nar` + `dsl`（action/motion/visible_change）。  
成人/女主：**按用户 brief 填** `heat_scale` / `cast_mode`；不要关键词自动钉 max，不要无证据造第二女主。  
max 成片规划时先算性爱时长：act+climax 秒数 / 全片秒数 ≥ **0.20**（重口男向目标 **0.40**）。  
**未过 write-spec → 禁止 media-queue。** 指标：`_heat_arc.sex_duration_ratio` · `_multi_heroine.resolved`。

批准词：「可以」「ok」「好的」「行」；含「一路做完」→ `run_to_completion` 不得再停问。

### 1 · 视觉（Grok Imagine 最大化 · Seedance 暂关）

- **加载** `/imagine`：reference-first、一角一脸、失败不绕审  
- 静帧：空镜 `image_gen`；有角色 **`image_edit(cast)`**（禁反复纯 gen 抽脸）  
- **人物动 bulk**：**`image_to_video` 720p** 串行（一次 claim 一件，防 429）  
- register：`--source-endpoint image_to_video`（**禁止**假装 seedance）  
- 无原生 T2V；`reference_to_video` 少用  
- continue：末帧 promote → 只对该 keyframe 再 `image_to_video`  
- **无角色/环境床**：FRW **`ltx-t2v`**（平台 ltx-文生视频，无限额度，已测 completed）  
  ```bash
  "$AIFILM" env-plate --root "<root>" --shot-id shot_env01 \
    --prompt "empty scene, soft light, no people, no faces" --wait
  # → clips/*_ltx_t2v.mp4 + keyframes 首帧 + register frw_ltx_t2v
  ```  
- **对白口型（可选更顺）**：近景 + `lipsync:true` → `aifilm frw-lipsync probe` → 201 再 `run`（face still + VO wav）；说书默认 off  
  见 [frw-lipsync.md](references/frw-lipsync.md)  
- 详：[ltx-env-plate.md](references/ltx-env-plate.md) · [i2v-grok-primary.md](references/i2v-grok-primary.md)

```bash
"$MEDIA_QUEUE" --budget-units 12 add --root "<root>" --shot-id shot01 \
  --operation image_to_video --prompt-file "<p.txt>" --input "<kf.png>"
"$MEDIA_QUEUE" claim --root "<root>"
# Grok Build: image_to_video(image=kf, prompt=…, duration=6)  # 串行！
"$AIFILM" register-clip --root "<root>" --shot-id shot01 --source "<clip.mp4>" \
  --source-endpoint image_to_video --identity-approved --motion-approved \
  --review-note "provider=grok model=image_to_video res=720p profile=grok_primary"
```

队列契约：[grok-media-pipeline.md](references/grok-media-pipeline.md)。

### 2 · 语音

```bash
"$AIFILM" tts-rehearse --root "<root>" --backend edge
# 机位一页（TTS/FRW/runtime）："$AIFILM" capability [--root "<root>"]
# 同句对照试听：        "$AIFILM" tts-ab --root "<root>" --shot shot01 --backends edge,voicebox
```

中文 **edge 默认**（零依赖、可复现）。**质量档**（不改默认）：SuperGrok → **`grok`**（OAuth TTS + speech tags，`--tts-backend grok`）；本机克隆 → `voicebox`；中文最高自然度本地 → **CosyVoice 2** `external`；情感精修 → MiniMax。场景表见 [voices.md](references/voices.md) · [grok-oauth.md](references/grok-oauth.md)。**失败 opt-in 兜底**：`AIFILM_TTS_VOICEBOX_FALLBACK=1`（不静默换声）。有回执则 vo_pacing **优先 measured**。混音在 final plate（sidechain / loudnorm / auto_sfx）。

**BGM 抗重复（定稿）**：**听感兜底** = 纯乐器曲库池 `assets/bgm/rnb/*`（≥3 首 + seed 轮换）；**工程硬兜底** = 程序 v3 multi-style（`--music-seed` / `audio_policy.music_seed`）。ACE-Step/`[inst]` 等只**离线灌库**；HeartMuLa 不当默认 BGM。见 [bgm-generation.md](references/bgm-generation.md)。

**场景自适应声轨**：`write-spec` 按 beat 写每镜 `audio_recipe`；片级 `audio_policy`（默认不自动唱）。见 [audio-recipe.md](references/audio-recipe.md) · `audio-plan`。

### 3 · 设计 + 4 · 后处理

```bash
# 推荐交付（内部含 FFmpeg plate）
"$AIFILM" final --root "<root>" --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge --compose-preset auto
# 建议先：compose-preview 或 --require-preview
# 纯 FFmpeg 烧字：--post-engine ffmpeg
# Remotion：--post-engine remotion --npm-install
```

改 compose 前加载 `/hyperframes`（+ core）或 `/remotion-best-practices`。[post-compose.md](references/post-compose.md)

### 交付

```bash
"$AIFILM" review-final --root "<root>" --approve --reviewer "<you>" \
  --notes "已完整观看" \
  --score-identity pass --score-style pass --score-motion pass \
  --score-escalation pass --score-audio pass --score-subs pass --score-dead-air pass
"$AIFILM" export-desktop --root "<root>" --name "<中文名>"
```

`final` 技术成功 ≠ `final_complete`。fail → `director-notes`。

**完整环**：Define/Structure（Lens）→ Visualize（lock）→ Generate → Select（register）→ Edit（Editor’s Cut · [editor-cut-pass.md](references/editor-cut-pass.md)）→ final(hyperframes) → review → export。

---

## 正式成片门禁

`final_complete` 仅当：允许的 endpoint + 不可变 hash · 解码/运动达标 · 人审身份/style/运动 · 可解码音轨 · **七维全 pass**。hash 变 → 审批失效。  
**不可宣称**（证据不足禁说）：见 [hard-defaults.md](references/hard-defaults.md) §不可宣称。

---

## 安全

- 外部 TTS/lipsync：仅 `AIFILM_TTS_ARGV` / `AIFILM_LIPSYNC_ARGV` JSON argv  
- 子进程最小环境；不传 key/token/SSH agent/proxy  
- lipsync 权重须 clean + hash + 用户确认；禁 `os.system` 上游  
- 日志/manifest/队列禁密钥与 prompt 明文  

---

## 按需加载（细节不进主脊）

| 主题 | 文件 |
|---|---|
| **Grok Build / SDK 能力总表** | [grok-build-sdk.md](references/grok-build-sdk.md) |
| **Grok OAuth Pack**（chat/image/edit/video/tts） | [grok-oauth.md](references/grok-oauth.md) |
| **I2V grok_primary**（Seedance 关） | [i2v-grok-primary.md](references/i2v-grok-primary.md) |
| **FRW LTX T2V 环境床** | [ltx-env-plate.md](references/ltx-env-plate.md) |
| **FRW 口型 音画同步** | [frw-lipsync.md](references/frw-lipsync.md) |
| **自动调配** dispatch | [auto-dispatch.md](references/auto-dispatch.md) |
| **工序八环主脊** Idea→Verified | [craft-spine.md](references/craft-spine.md) |
| **音频三阶梯** TTS/BGM/Lipsync | [audio-fallback.md](references/audio-fallback.md) |
| **媒体队列 · Grok/FRW** | [grok-media-pipeline.md](references/grok-media-pipeline.md) |
| **生成式电影工序**（Beat/Coverage/五锁） | [generative-film-craft.md](references/generative-film-craft.md) |
| 工具四层 + 对照表 | [pipeline-methodology.md](references/pipeline-methodology.md) |
| 弹性默认 | [hard-defaults.md](references/hard-defaults.md) |
| 叙事上游执行 | [directors-lens.md](references/directors-lens.md) · [lessons-2026-07-20-directors-lens.md](references/lessons-2026-07-20-directors-lens.md)（**先 Director’s Lens**，防插图化） |
| 画风身份 | [consistency.md](references/consistency.md) · [style-bible.md](references/style-bible.md) |
| 规格 | [film-spec.md](references/film-spec.md) · schema · `caption_mode` / `transition_fluency` / `camera_axis` |
| 接戏 | [continuity_chain.md](references/continuity_chain.md) |
| 后期 | [postproduction.md](references/postproduction.md) · [post-compose.md](references/post-compose.md) · [hf-remotion-capability-matrix.md](references/hf-remotion-capability-matrix.md) |
| 量产 | [production-discipline.md](references/production-discipline.md) |
| 色气 / 剪辑 | [ecchi-story.md](references/ecchi-story.md) · [editor-cut-pass.md](references/editor-cut-pass.md) · [editorial-craft.md](references/editorial-craft.md) |
| 剪辑丝滑 / 双语字 | [lessons-2026-07-20-cut-silk-bilingual.md](references/lessons-2026-07-20-cut-silk-bilingual.md) · [lessons-2026-07-20-transition-motion-v2.md](references/lessons-2026-07-20-transition-motion-v2.md) |
| 标题双烧 | [lessons-2026-07-20-title-double-burn.md](references/lessons-2026-07-20-title-double-burn.md)（`plate-cards blank` + `subs off`） |
| FRW 降级 / Seedance | [frw-degrade-dispatch.md](references/frw-degrade-dispatch.md) · [lessons-2026-07-20-seedance-quality.md](references/lessons-2026-07-20-seedance-quality.md) · `frw_video_model` / `seedance-2-fast-i2v` · `frw newvideo`（恢复时 `seedance_first`，**不是 first-last-frame**） |
| 踩坑 lessons | `references/lessons-2026-07-*.md`（新规则须标 P 码 + 层） |
| **发色硬锁** | [lessons-2026-07-21-hair-color-lock.md](references/lessons-2026-07-21-hair-color-lock.md) · [consistency.md](references/consistency.md) §1b |
| **禁 shot 水印** | [lessons-2026-07-21-no-shot-watermark.md](references/lessons-2026-07-21-no-shot-watermark.md) · [consistency.md](references/consistency.md) §1c · **致命** |
| **蒙太奇+重口男向** | [lessons-2026-07-21-montage-hardcore-male.md](references/lessons-2026-07-21-montage-hardcore-male.md) · [editorial-craft.md](references/editorial-craft.md) · [ecchi-story.md](references/ecchi-story.md) §重口 |
| **首帧毒化** | [lessons-2026-07-21-keyframe-first-frame-poison.md](references/lessons-2026-07-21-keyframe-first-frame-poison.md) · [consistency.md](references/consistency.md) §1d · **坏 still=整 clip 废** |
| **景别情绪堆叠** | [lessons-2026-07-21-size-ladder-hardcore-stack.md](references/lessons-2026-07-21-size-ladder-hardcore-stack.md) · 全景→中→近→特写加压 + 成人六拍剧情 |
| **性交冲击力标竿** | [lessons-2026-07-21-intercourse-impact-benchmark.md](references/lessons-2026-07-21-intercourse-impact-benchmark.md) · 性交六拍 + Mute Frame 测试 + 冲击七刀（成片「尺度小」根因课） |
| **性爱时长硬底 ≥20%** | [lessons-2026-07-21-sex-duration-floor.md](references/lessons-2026-07-21-sex-duration-floor.md) · act+climax `duration_sec` 加权 · write-spec `sex_floor_strict` |
| **办事卸甲阶梯** | [lessons-2026-07-21-sex-undress-ladder.md](references/lessons-2026-07-21-sex-undress-ladder.md) · full→partial→undressed/bare · 禁铠甲完整跨坐 |
| **FRW key 能力 / 403·502** | [lessons-2026-07-21-frw-key-capability.md](references/lessons-2026-07-21-frw-key-capability.md) · [frw-degrade-dispatch.md](references/frw-degrade-dispatch.md) |
