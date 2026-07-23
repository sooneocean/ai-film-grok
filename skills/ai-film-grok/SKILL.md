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
**算力纪律（P0 · 2026-07-22）**：**先验后生**——图/视频都先验证再烧下一级算力；坏输入上生成 = 双倍成本。见 [verify-before-generate](references/lessons-2026-07-22-verify-before-generate.md)。
**用户原文保真（P0 · 2026-07-22）**：用户剧本/诗白是脊柱；禁止 adult-max「展厅落锁」模板整句覆盖；多段输入各自独立，不克隆测试骨架；口白动词=画面动作。见 [user-source-fidelity](references/lessons-2026-07-22-user-source-fidelity.md)。
**用户定妆脸锁（P0 · 2026-07-22 少婦案）**：用户主角图/角色表 → 裁 FRONT+脸 → cast master；有角色 still **只** `image_edit(cast|face|已过审 still)`；审核 moderated **禁止**纯 `image_gen` 绕脸；整页 sheet 禁止直接当 9:16 脸锁。见 [shaofu-cast-subs-bgm-final](references/lessons-2026-07-22-shaofu-cast-subs-bgm-final.md)。
**输入图画风锁（P0 · 2026-07-23）**：开片先锁 **medium**（`manhua`/`anime` 稳；`photoreal` 低稳须明示）。有用户参考图 → `aifilm style-lock plan --ref` → `apply` → `lock-style --from-plan`；prompt 强制 `MEDIUM LOCK` + `cast_locks`。用户要漫剧质感/稳定性 → **默认 manhua，禁止无确认跳 photoreal bulk**。见 [style-lock-from-ref](references/lessons-2026-07-23-style-lock-from-ref.md) · [consistency §1a](references/consistency.md)。
**像素 face-identity（P0 · 2026-07-23）**：`aifilm face-identity enroll-bible` → `audit` 写 `receipts/face-identity.json`；post_audit 检查 `verified`。cast master + face-lock 多 anchor；still 可 `--require-face-identity`。见 `scripts/face_identity.py`。
**字幕空窗（P0 · 同案）**：`post-engine hyperframes` 默认 plate `subs=off`；HF 未成功烧字时 **必须** 走 stage_caption 恢复；**禁止**为过 review 清空 `final.srt`。
**字幕进画面（P0 · 2026-07-23）**：交付主 mp4 **像素内**必须有中文字幕（抽帧可见）；有 SRT 外挂 ≠ 完成。
**成片分阶段（P0 · 2026-07-23 逻辑修复）**——**禁止假定** HF 已烧字：
1. `stage_plate`：`render_final --subs off`（VO+BGM+clips only）
2. `stage_hf`：HyperFrames export+render **负责设计字幕**
3. `stage_caption`：验像素；HF 未进画面 → **显式** `burn_srt_pil` recovery（非静默假定）
4. `stage_deliver`：写 `receipts/final-stages.json` + `caption_owner`
见 [subs-always-burn-hard](references/lessons-2026-07-23-subs-always-burn-hard.md) · `scripts/final_stages.py`。
**色气 BGM（P0 · 同案）**：色气/heat 亲密默认 **rnb 曲库** `assets/bgm/rnb/*`（显式 `--music`）；勿用 dark；procedural 仅曲库缺失时。
**final 超时（P0 · 同案）**：`aifilm final` 调 render_final 默认 **≥1200s**（`--plate-timeout`）；短超时会假失败。

**专业导演系统（v1.15）**：创作判断不再只存在 Prompt。`production-book.json` 总控 Graph、Visual/Audio/Post Bible、版本锁、审批 ledger、精准 stale 传播、Dailies/Selects、Picture Lock 与 Master Gate；模型评分永远只作 advisory。见 [professional-director-system.md](references/professional-director-system.md)。

**premium_vertical 质量档（v1.24）**：`director init --quality-target premium_vertical` 启用高质量竖屏创作门禁；缺少 authored beats、shot performance、Director Board 或摄影意图时，`preflight` 会在 Pilot/付费生成前 fail closed。旧项目默认 `standard`，不会被静默升级。

```text
【工序八环】Idea → Story → Beats → Shots → Media → Selects → (Cut) → Rough → Verified MP4
【工具】Agent → 1视觉 → 2语音 → 3设计(HF) → 4FFmpeg → 交付
【四工具闭环】Seedance(运镜) → I2V(Grok/Seedance) → video-use(剪辑) → HF/Remotion(设计后期)
【六动词】Define → Structure → Visualize → Generate → Select → Edit
【自动调配】每回合优先 aifilm dispatch --root <film> → 执行 next_action（兼容 next_cmd）
```

主脊详解：[craft-spine.md](references/craft-spine.md) · 音频三阶梯：[audio-fallback.md](references/audio-fallback.md) · 调度：[auto-dispatch.md](references/auto-dispatch.md)
剪辑与字幕细则：[lessons-2026-07-20-cut-silk-bilingual.md](references/lessons-2026-07-20-cut-silk-bilingual.md) · [lessons-2026-07-20-transition-motion-v2.md](references/lessons-2026-07-20-transition-motion-v2.md) · [lessons-2026-07-20-title-double-burn.md](references/lessons-2026-07-20-title-double-burn.md)
FRW 降级路线：[frw-degrade-dispatch.md](references/frw-degrade-dispatch.md)；Seedance 为恢复路径，不是 first-last-frame 默认流程：`frw_video_model=seedance-2-fast-i2v`、`frw newvideo`、`seedance_first`、[lessons-2026-07-20-seedance-quality.md](references/lessons-2026-07-20-seedance-quality.md)。
设计后期默认 `plate-cards blank` + `subs off`，避免标题双烧。

**四工具闭环（v1.22 · 2026-07-23）**：从脚本→动效→剪辑→渲染全程 AI 闭环。
Seedance 运镜词库（`cinema_prompt.py` → `dsl.camera_prompt`）补齐审美短板；I2V provider 抽象层（`i2v_provider.py`，Grok/Seedance 注册表）消除散乱；video-use 真人素材通路（`ingest-footage` + `auto-cut`）补上唯一缺环；HyperFrames/Remotion designed-post 打磨（时长分卷、转场受控、TikTok 字幕）。见 [four-tool-closed-loop.md](references/four-tool-closed-loop.md)。

**客观质检 + 参考反推 + 产品片 + VO lint（v1.25 · 2026-07-23）**：从 reference-driven-cinematic-video 抽取 5 项能力，补齐交付门禁与产品片赛道。
① 成片级 FFmpeg 客观质检（`quality_check_video.py` → `quality-check`，8 项加权 0-100 分）——`review-final` 前置门禁，低于阈值不进人审；② 参考视频反推（`reference_audit.py` → `analyze-reference`，probe + contact sheet + keyframes + shot-grammar）；③ 独立 SRT 生成器（`subtitle_srt.py`，统一三引擎 + 重叠校验，修 P0「HF 失字」）；④ 产品片 brief 扩展（`product_brief.py` → `brief expand`，5 拍场景计划 + claim 检测，见 [product-brief-intake.md](references/product-brief-intake.md)）；⑤ VO 文案去 AI 味 lint（`vo_lint.py`，brochure phrase / AI cadence / 长句检测，接入 `write-spec`）。

### Agent 自动调配（强制）

开任何片子、每完成一步后：

```bash
"$AIFILM" dispatch --root "<root>"
# 读 JSON：craft_stage · next_action · next_cmd · context_digest · routing
#        + graph · jobs_summary · execution_plan_digest（v1.4.6+）
# 本回合只做 next_cmd；做完再 dispatch。禁止跳环 bulk。
```

| 字段 | 含义 |
|------|------|
| `craft_stage` | 八环当前位置 |
| `next_cmd` | **唯一**推荐命令 |
| `next_action` | 可直接执行、带输入 hash／transaction／审批等级的结构化动作 |
| `context_digest` | rigor、部门锁、stale、素材版本、导演意见与批准／预算范围 |
| `agent_do` / `agent_instruction` | 本回合 checklist |
| `routing` | TTS/BGM/I2V 自动兜底策略摘要 |
| `hard_gates` | 不可跳过的门禁 |
| `graph` | Vertical Drama Graph 摘要（ep/sc/bt/sh · kf/clip） |
| `jobs_summary` / `execution_plan_digest` | 执行图 job 计数 + primary_job（Skill Registry 映射） |

**竖屏漫剧图 + Skill 表（Phase 1–4）**：

```bash
# Phase 3：一句话/剧本 → Graph + film-spec 种子
"$AIFILM" plan run --root "<root>" --text "雨夜出租车…" --title "雨夜后座" --target-duration 40 --force
"$AIFILM" write-spec --root "<root>"       # 校验 VO 预算 + 注入 prompts
"$AIFILM" plan status --root "<root>"

# Phase 1：film-spec → drama-graph（只读派生；与 planned 图并存时以现文件为准）
"$AIFILM" graph derive --root "<root>"
"$AIFILM" graph validate --root "<root>"
"$AIFILM" graph status --root "<root>" --with-jobs

# Phase 2：能力表
"$AIFILM" skill list
"$AIFILM" skill show --id story.normalize
"$AIFILM" skill run --skill-id dispatch.orchestrate --payload-file action.json --dry-run

# 专业导演总控与部门合同（新项目默认 professional；旧项目默认 legacy）
"$AIFILM" director init --root "<root>" --rigor professional
"$AIFILM" director status --root "<root>"
"$AIFILM" department list --root "<root>"
"$AIFILM" department edit --root "<root>" --id visual --payload-file patch.json --expected-revision 1 --dry-run

# Phase 4：角色/场景/道具 + 状态照槽位（与 state-index 对齐）
"$AIFILM" assets sync --root "<root>"
"$AIFILM" assets check --root "<root>"
"$AIFILM" state-index check --root "<root>"
```

蓝图：[docs/plans/2026-07-21-vertical-drama-upgrade.md](../../../docs/plans/2026-07-21-vertical-drama-upgrade.md) · Registry：`registry/skills.json`

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
| `post` | Post 锁画 | 十一维审批 | `review-final` |
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

完整表见 [hard-defaults.md](references/hard-defaults.md)。**仅工程/一致性**最低线（P0 红线，其余见 hard-defaults §量产十条）：

1. **write-spec 过** → 才 queue；**pilot 用户批准** → 才 bulk（无批准 ≤3 shot_id）
2. **先验后生**：still/视频验证完再烧下一级；坏输入只修上游不盲重烧（[verify-before-generate](references/lessons-2026-07-22-verify-before-generate.md)）
3. **卸装不回穿**：`wardrobe_state` 只前进；peak 后禁全装 cast 源；末帧门验不回穿（[wardrobe-no-redress-still](references/lessons-2026-07-21-wardrobe-no-redress-still.md) · [i2v-endframe-no-redress](references/lessons-2026-07-22-i2v-endframe-no-redress.md)）
4. **静帧几何**：keyframe ≥720×1280 且 9:16；禁横图/缩略图/压糊 jpg（[keyframe-no-compress](references/lessons-2026-07-22-keyframe-no-compress.md)）
5. **用户原文保真**：禁模板整句覆盖用户诗白/对白；`USER_SOURCE_NAR_POLLUTED` hard fail（[user-source-fidelity](references/lessons-2026-07-22-user-source-fidelity.md)）
6. **交付**：十一维全 pass + 完整观看 → `final_complete`；HF 失字必 burn；禁空 SRT

**弹性（跟 brief）**：`heat_scale` / 亲密核镜比 / 单·多女主——由 Prompt 与参考图推断。
**`heat_scale=max` 例外硬底**（详见 [hard-defaults.md](references/hard-defaults.md) §叙事与规划）：性爱时长 ≥30% · 卸甲脱衣不回穿 · 旁白全程荤梗 · 静帧源链 undress-anchor。


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
"$AIFILM" bible init --root "<root>"
# 有用户角色图 / 要稳：先 medium + face 锁（勿直接 photoreal bulk）
"$AIFILM" style-lock recommend --goal "要稳定像漫剧"   # 可选
"$AIFILM" style-lock plan --root "<root>" --ref "<user-sheet.png>" \
  --char-id <id> --name "<名>" --medium manhua   # 或 anime / semi_real / photoreal
"$AIFILM" style-lock apply --root "<root>"
# Agent：image_edit(face-lock) → cast master 9:16；可选 style-v1
"$AIFILM" lock-style --root "<root>" --from-plan \
  --canonical "<style-v1.png>" --cast-master "<cast-master.png>" --char-id <id>
"$AIFILM" style-lock check --root "<root>"
# 編輯 style-bible.json 补全第二角色等...
"$AIFILM" bible lock --root "<root>"
"$AIFILM" write-spec --root "<root>"
# write-spec 會自動根據 bible 生成 prompts/*.txt 並檢查衝突
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
- **Keyframe-first · 状态照门**：`state-index check|plan` 查缺口 → 可补生成状态照/keyframe；`canonical/cast-states/<id>/{full,partial,undressed,bare}.*`；每镜 still 主 ref=状态照[wardrobe_state]；I2V 只吃 keyframe。详 [keyframe-first-state-index](references/keyframe-first-state-index.md)
- **卸装不回穿（P0）**：`wardrobe_state` 只前进；peak still → `canonical/wardrobe/undress-anchor.png`；partial\|undressed\|bare 镜禁用全装 cast 当 ref，只许 `image_edit(state photo|undress-anchor|已脱 still|promote 末帧)` + 只改姿势。详 [wardrobe-no-redress-still](references/lessons-2026-07-21-wardrobe-no-redress-still.md)
- **生成 first/last（串行）**：`register-clip` 后自动抽上镜 last → 下镜 `keyframes/<next>.png`；下镜 I2V 只吃该 keyframe；按末帧衣着/姿势写 motion prompt。详 [first-last-gen](references/lessons-2026-07-21-first-last-gen.md)
- **先验后生（P0）**：still 落盘 → 先验（几何+身份+结构）→ 过才 register/ref/bulk；keyframe 全过闸 → 才 `image_to_video`；坏输入停下游只修 still。详 [verify-before-generate](references/lessons-2026-07-22-verify-before-generate.md)
- **静帧几何门（P0）**：keyframe 写入即验 W×H；9:16 须 ≥720×1280；禁缩略图/横图/压糊 jpg；`pick_best_keyframe`。详 [keyframe-no-compress](references/lessons-2026-07-22-keyframe-no-compress.md)
- **人物动 bulk**：`image_to_video` 720p 串行（防 429）；register `--source-endpoint image_to_video`（禁假装 seedance）；continue 末帧 promote → 再 I2V
- **无角色/环境床**：FRW `ltx-t2v`（`env-plate`，无限额度）；**口型**（可选）：近景 `lipsync:true` → `frw-lipsync probe`→run；说书默认 off。详 [ltx-env-plate.md](references/ltx-env-plate.md) · [i2v-grok-primary.md](references/i2v-grok-primary.md) · [frw-lipsync.md](references/frw-lipsync.md)

```bash
# write-spec 已自動生成 prompt，直接使用
"$MEDIA_QUEUE" --budget-units 12 add --root "<root>" --shot-id shot01 \
  --operation image_to_video --prompt-file "prompts/shot01.txt" --input "<kf.png>"
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
# 机位一页："$AIFILM" capability [--root "<root>"]
# 同句对照试听："$AIFILM" tts-ab --root "<root>" --shot shot01 --backends edge,voicebox
```

中文 **edge 默认**；质量档：SuperGrok→`grok`(OAuth)·本机克隆→`voicebox`·最高自然度→CosyVoice 2`external`·情感精修→MiniMax。失败 opt-in 兜底 `AIFILM_TTS_VOICEBOX_FALLBACK=1`（不静默换声）。场景表见 [voices.md](references/voices.md) · [grok-oauth.md](references/grok-oauth.md)。

**BGM**：色气/heat 亲密优先 `assets/bgm/rnb/*` + `--music-mood rnb`（禁 dark）；曲库空才程序 v3。**声线**：旁白 `nar`+BGM 主导，娇喘轨 `vocal_color` 默认关。**声轨**：`write-spec` 按 beat 写 `audio_recipe`；`edit_strategy.mode=voice_coupled`（heat max 默认）。见 [bgm-generation.md](references/bgm-generation.md) · [audio-recipe.md](references/audio-recipe.md) · [voice-tracks.md](references/voice-tracks.md) · [edit-strategy-voice-coupled.md](references/edit-strategy-voice-coupled.md) · [shaofu-cast-subs-bgm-final](references/lessons-2026-07-22-shaofu-cast-subs-bgm-final.md)。

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
  --score-escalation pass --score-audio pass --score-subs pass --score-dead-air pass \
  --score-rhythm pass --score-emotion pass --score-theme pass --score-performance pass
"$AIFILM" export-desktop --root "<root>" --name "<中文名>"
```

`final` 技术成功 ≠ `final_complete`。fail → `director-notes`。

**审片证据**（v1.6+）：`register-clip --status approved` 前须先 `review-shot`（抽首/中/末帧 + 联系表 + 五维评分 + 时间点）；content channels 镜头另记 `--performance-evidence kind@seconds:note`（完整观看后的人工事实，非自动判定）。`review-final` 须十一维 `--screening-evidence`；失败重拍单只能显式 resolve。`performance-timeline`（v1.11.4）将已批准镜头表演事实按全片时间排序，review-final 时校验收据与证据帧仍绑定，但不把自动分析伪装成导演判断。

**完整环**：Define/Structure（Lens）→ Visualize（lock）→ Generate → Select（register）→ Edit（Editor's Cut · [editor-cut-pass.md](references/editor-cut-pass.md)）→ final(hyperframes) → review → export。

---

## 正式成片门禁

`final_complete` 仅当：允许的 endpoint + 不可变 hash · 解码/运动达标 · 人审身份/style/运动 · 可解码音轨 · **十一维全 pass**。hash 变 → 审批失效。
**不可宣称**（证据不足禁说）：见 [hard-defaults.md](references/hard-defaults.md) §不可宣称。

---

## 安全

- 外部 TTS/lipsync：仅 `AIFILM_TTS_ARGV` / `AIFILM_LIPSYNC_ARGV` JSON argv
- 子进程最小环境；不传 key/token/SSH agent/proxy
- lipsync 权重须 clean + hash + 用户确认；禁 `os.system` 上游
- 日志/manifest/队列禁密钥与 prompt 明文

---

## 按需加载（细节不进主脊）

> 完整分类导航见 [references/INDEX.md](references/INDEX.md)（92 个文件按功能 + 日期分组）。

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
| **多轨声线** 默认 nar+BGM；娇喘轨 opt-in | [voice-tracks.md](references/voice-tracks.md) |
| **声线耦合剪辑** craft/可变转场/vo-fit | [edit-strategy-voice-coupled.md](references/edit-strategy-voice-coupled.md) |
| **媒体队列 · Grok/FRW** | [grok-media-pipeline.md](references/grok-media-pipeline.md) |
| **生成式电影工序**（Beat/Coverage/五锁） | [generative-film-craft.md](references/generative-film-craft.md) |
| 工具四层 + 对照表 | [pipeline-methodology.md](references/pipeline-methodology.md) |
| 弹性默认 | [hard-defaults.md](references/hard-defaults.md) |
| 导演方法论总纲（三阶段 + 考验矩阵） | [director-methodology.md](references/director-methodology.md) |
| 叙事上游执行 | [directors-lens.md](references/directors-lens.md) · [lessons-2026-07-20-directors-lens.md](references/lessons-2026-07-20-directors-lens.md)（**先 Director’s Lens**，防插图化） |
| 画风身份 | [consistency.md](references/consistency.md) · [style-bible.md](references/style-bible.md) |
| 规格 | [film-spec.md](references/film-spec.md) · schema · `caption_mode` / `transition_fluency` / `camera_axis` |
| 接戏 | [continuity_chain.md](references/continuity_chain.md) |
| 后期 | [postproduction.md](references/postproduction.md) · [post-compose.md](references/post-compose.md) · [hf-remotion-capability-matrix.md](references/hf-remotion-capability-matrix.md) |
| 量产 | [production-discipline.md](references/production-discipline.md) |
| 色气 / 剪辑 | [ecchi-story.md](references/ecchi-story.md) · [editor-cut-pass.md](references/editor-cut-pass.md) · [editorial-craft.md](references/editorial-craft.md) |
| 成人办事剧单入口（v1.10） | [adult-max-playbook.md](references/adult-max-playbook.md) · sex≥30% · extreme VO · 肉体 SFX · 蒙太奇 · 多体位 · [pose-packs](references/pose-packs/coitus-beats.md) |
| **踩坑 lessons**（P0 红线已在上方门禁/视觉段引用） | `references/lessons-2026-07-*.md`（新规则须标 P 码 + 层）· [keyframe-first-state-index.md](references/keyframe-first-state-index.md) · **2026-07-23**：[style-lock-from-ref](references/lessons-2026-07-23-style-lock-from-ref.md) · [face-identity-pixel](references/lessons-2026-07-23-face-identity-pixel.md) · [photoreal-vs-manhua-stability](references/lessons-2026-07-23-photoreal-vs-manhua-stability.md) |
