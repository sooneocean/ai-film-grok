---
name: ai-film-grok
description: Grok Build 专用 AI 短片 skill：Idea→Verified 导演工序、Grok Imagine 静帧/I2V、TTS/声音、设计后期与证据化交付。触发：AI 电影、漫剧、Grok Imagine、dispatch、成片、/ai-film-grok。
---

# AI Film Grok

把想法收成可恢复、可验收的 9:16 动态成片。真实 I2V/footage、混音、像素字幕与人工审片缺一不可；静图轮播、Ken Burns 或只有关键帧不算成片。

## 单一入口

```bash
SKILL_DIR="$HOME/.grok/plugins/ai-film-grok/skills/ai-film-grok"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"

"$AIFILM" dispatch --root "<film>"          # 默认 compact，当前一步所需信息
"$AIFILM" dispatch --root "<film>" --full   # 完整审计包
"$AIFILM" advance --root "<film>"           # 只跑 allowlist 内本地动作
```

每步后再 dispatch，只执行 `next_action`；`next_cmd` 仅兼容显示。读取 `context_refs`（最多三份），完整状态在 `receipts/dispatch.json`。

工序：Idea → Story → Beats → Shots → Media → Selects → Rough → Verified。
工具层：Agent → Visual → Voice → Design/Post → Deliver。

收到小说、剧本或故事文本时先 `story.receive`：按
[story-reception.md](references/story-reception.md) 产出 `StoryReception v1`，
展示导演摘要与假设，再 `plan run --received-file`。原文不可覆盖；story lock
前必须用户确认。

## 创作工作室（按需）

剧本会诊、台词节奏、留存、导演提示词或声音设计读取
[creative-workshop.md](references/creative-workshop.md)。`workshop` 默认只编译决定；仅显式
`apply --expected-graph-revision` 可写回未锁定故事图，绝不改供应商默认或提交外部生成。
产物在 `receipts/workshop/` 并绑定输入 SHA-256。

## P0 核心

1. **故事真相**：`drama-graph.json` 是真相，`film-spec.json` 是投影。严格校验、四级 locks 与当前 projection hash 未齐不进媒体；先 Director’s Lens（[directors-lens.md](references/directors-lens.md)）。
2. **用户原文保真**：用户剧本、对白、主题与动作是脊柱，模板不得整句覆盖。
3. **身份与介质**：参考图先锁 medium/cast/face。有角色 still 只编辑已批准来源；moderated 禁止 `image_gen` 绕脸。漫剧默认 manhua，不静默跳 photoreal。
4. **先验后生**：still 的身份、结构、画风、几何通过后才 I2V；9:16 keyframe 至少 720×1280。
5. **连续性**：`state-index check|plan` 先于 bulk；衣着只前进，Continue 镜硬接批准末帧。
6. **审批/用量**：pilot 必须用户批准；付费/外部动作绑定 hash、预算并探测。生成写 `receipts/generation-usage.json`，缺真实 cost 为 `unknown`；Imagine 后执行 `usage record`。`advance` 遇 human/paid/external 暂停。
7. **供应商**：I2V 默认 `grok_primary`；Seedance 仅恢复路径，`frw_video_model=seedance-2-fast-i2v` 不得静默启用。
8. **声音（P0 分轨）**：口白/说书中文 Edge；角色开口日文 Edge；字幕中文 `nar`。禁止无 `speaker` 的中日乒乓、说书镜填 `nar_ja` 或赶片清空日文轨。亲密 BGM 默认 rnb；外部 TTS/lipsync 不静默开启。详见 [voice lesson](references/lessons-2026-07-24-ep2-voice-heat-final.md)。
9. **成人尺度 MAX（P0 · 最重要 · 2026-07-27）**：成人片 **尺度拉到最高是第一优先**（压过装饰性优化）。IRON：act+climax ≥50%、亲密 ≥60%、setup ≤20%；act≥undressed、climax=bare、`spice=extreme`，phase 只升不降；`challenge_max_scale` 默认 true，禁静默降 `heat_scale`。**肉戏须连贯起承转合：前戏 → 插入 → 射出 全有**（禁只抱吻/跳切无纳入/无高潮射出拍）。详见 [adult-scale-max-sex-arc](references/lessons-2026-07-27-adult-scale-max-sex-arc.md) · [hard-defaults](references/hard-defaults.md) · [adult-max-iron](references/lessons-2026-07-24-adult-max-iron.md)。
10. **字幕像素门**：交付 MP4 必须看得到中文字幕；SRT 不等于烧字。HF 失字时显式 stage_caption recovery，禁止清空 `final.srt`。`sub_lead=0` 防 SRT 重叠；长片直调 `render_final.py`。
11. **后期单一责任**：title/subtitle/end card 只由一个 post engine 负责；`plate-cards blank`、plate `subs=off` 防双烧。
12. **完成定义**：`final` 技术成功不等于 `final_complete`；review receipt、post audit、字幕 attestation、review-final、重拍关闭与 export 回读必须齐全。
13. **安全**：凭据仅从本机读取；日志、metrics、manifest 禁存 token、授权头或 prompt。外部调用不自动重试花费。
14. **高动态常态（P0 · 2026-07-27）**：平常镜 mean≥18、肉戏≥20（目标≥24）；包络 1:00→片尾≥18。禁止 Ken Burns/微抖/弱 raw 装片；多 take 取最高动且时长够；肉戏 10s 优先 6s×2。**桌面 final 仅** `receipts/i2v-final-gate.json` ok。见 [high-motion-style-lock](references/lessons-2026-07-27-high-motion-style-lock-final.md)。
15. **I2V 画风锁（P0 · 同案）**：每镜 I2V 源=过审 style-locked still；prompt 首段 **MEDIUM LOCK cel 动漫**（禁 photoreal/半写实光泽）；高动重跑与末帧连戏均不得以 mean 换 medium fail。抽帧 style audit 过再交付。

## 阶段执行

按阶段只读对应卡：[agent](references/stages/agent.md)（故事/locks）→ [visual](references/stages/visual.md)（pilot/media）→ [voice](references/stages/voice.md)（双语声轨）→ [post](references/stages/post.md)（剪辑/字幕）→ [deliver](references/stages/deliver.md)（screening/export）；人工或付费暂停读 [approval](references/stages/approval.md)。`context_refs` 最多三份；深挖再查 [INDEX](references/INDEX.md)。

## 最小命令

```bash
"$AIFILM" doctor
"$AIFILM" plan receive --root "<film>" --file "story-reception.json"
"$AIFILM" plan run --root "<film>" --received-file "<film>/receipts/story-reception.json"
"$AIFILM" plan run --root "<film>" --text "<story>" --title "<title>" --target-duration 60
"$AIFILM" plan validate --root "<film>" --strict
"$AIFILM" graph project --root "<film>" --force
"$AIFILM" write-spec --root "<film>"
"$AIFILM" state-index check --root "<film>"
"$AIFILM" pilot report --root "<film>"
"$AIFILM" usage status --root "<film>"
# 用户明确批准后才 pilot approve / bulk
"$AIFILM" final --root "<film>" --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge --compose-preset auto
"$AIFILM" review-final --root "<film>"   # 完整观看后填十一维证据
```

按需读取：[hard-defaults](references/hard-defaults.md) · [双语剪辑](references/lessons-2026-07-20-cut-silk-bilingual.md)（`caption_mode`、`transition_fluency`） · [避免双烧](references/lessons-2026-07-20-title-double-burn.md) · [完整索引](references/INDEX.md)。
