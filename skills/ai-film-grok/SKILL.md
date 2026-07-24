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

## P0 核心

1. **故事真相**：`drama-graph.json` 是真相，`film-spec.json` 是投影。严格校验、四级 locks 与当前 projection hash 未齐不进媒体；先 Director’s Lens（[directors-lens.md](references/directors-lens.md)）。
2. **用户原文保真**：用户剧本、对白、主题与动作是脊柱，模板不得整句覆盖。
3. **身份与介质**：参考图先锁 medium/cast/face。有角色 still 只编辑已批准来源；moderated 禁止 `image_gen` 绕脸。漫剧默认 manhua，不静默跳 photoreal。
4. **先验后生**：still 的身份、结构、画风、几何通过后才 I2V；9:16 keyframe 至少 720×1280。
5. **连续性**：`state-index check|plan` 先于 bulk；衣着只前进。Continue 镜用已批准末帧硬接下一镜。
6. **审批/用量**：pilot 必须用户批准；付费/外部动作绑定 hash、预算并实时探测。生成请求写 `receipts/generation-usage.json`，只认真实 `usage.cost_in_usd_ticks`，缺值为 `unknown`；原生 Imagine 后执行 `aifilm usage record`。详见 [generation usage](references/generation-usage-accounting.md)；`advance` 遇 human/paid/external 暂停。
7. **供应商**：I2V 默认 `grok_primary`；Seedance 仅恢复路径，`frw_video_model=seedance-2-fast-i2v` 不得静默启用。
8. **声音**：角色日文 Edge（Nanami/Keita）+ 中文字幕；旁白中文 Edge。亲密 BGM 默认 rnb；外部 TTS/lipsync 不静默开启。
9. **字幕像素门**：交付 MP4 必须看得到中文字幕；SRT 不等于烧字。HF 失字时显式 stage_caption recovery，禁止清空 `final.srt`。
10. **后期单一责任**：title/subtitle/end card 只由一个 post engine 负责；`plate-cards blank`、plate `subs=off`，防双烧。见 [title-double-burn](references/lessons-2026-07-20-title-double-burn.md)。
11. **完成定义**：`final` 技术成功不等于 `final_complete`。镜头 review receipt、post audit、字幕可读 attestation、十一维 review-final、重拍关闭与 export 回读必须齐全。
12. **安全**：凭据仅从本机读取；日志、metrics、manifest 禁存 token、授权头或 prompt。外部调用不自动重试花费。

## 阶段执行

| 阶段 | 只读哪张卡 | 目标 |
|---|---|---|
| Idea/Story/Beats | [agent.md](references/stages/agent.md) | brief、Lens、Graph、locks、write-spec |
| Shots/Media/Selects | [visual.md](references/stages/visual.md) | style/cast/state、pilot、verified media |
| Voice | [voice.md](references/stages/voice.md) | 日文对白、中文旁白、BGM/SFX/mix |
| Rough/Design/Post | [post.md](references/stages/post.md) | edit、HF/Remotion、字幕、post audit |
| Verified/Deliver | [deliver.md](references/stages/deliver.md) | screening、Master gate、export read-back |
| 人工/付费暂停 | [approval.md](references/stages/approval.md) | 说明批准对象与 hash，不代签 |

`context_refs` 由 `registry/context-routing.json` 按阶段、skill 与 issue code 选择；深挖再查 [INDEX](references/INDEX.md)。

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
