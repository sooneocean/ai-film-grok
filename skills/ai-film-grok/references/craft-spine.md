# Craft Spine · 八环工序主脊

> 2026-07-21 · **Idea → Verified MP4**
> 与工具四层正交：本文件管**叙事/决策分层**；工具见 [pipeline-methodology.md](pipeline-methodology.md)。
> 原则：每环 = 问题 + 输入 + 产出 + 门禁强度 + 失败回退；前环未确认不 bulk。

## 八环总表

```text
Idea → Story → Beats → Shots → Media → Selects → Rough Cut → Verified MP4
```

| # | craft_stage | 问题（只答这一句） | 门禁 | 产出证据 | 失败回退 |
|---|-------------|-------------------|------|----------|----------|
| 1 | `idea` | 为何存在、给谁、多长、情绪落点？ | soft | brief.json / creative-brief | — |
| 2 | `story` | 谁要什么、状态怎么变？ | soft→semi | director_intent · directors-lens | idea |
| 3 | `beats` | 观众每步多懂什么/情绪怎么变？ | soft | dramatic_function 脊柱 · beat-sheet | story |
| 4 | `shots` | 用哪些镜证明 Beat？Coverage？ | hard | write-spec · pilot 用户批 | beats |
| 5 | `media` | 哪条模型路径拿真素材？ | hard 工程 | clips/queue · capability · canary | shots |
| 6 | `selects` | 这段能否进时间线？ | hard | register approved | media |
| 7 | `rough` | 顺序与节奏是否成立？ | soft | assemble/plate · rough-cut 回执 | selects/beats |
| 8 | `verified` | 能否声称可发布？ | hard | final + 十一维 + export | rough/media |

**短片可压缩** Idea+Story、跳过 beat-sheet 文档，但 **不得倒序**：Shots 前要有意图；Media 前要 pilot；Verified 前要 human_review。

## 与工具层对照

| craft | 工具层 stage（约） | 典型命令 |
|-------|-------------------|----------|
| idea–shots | agent | init · Lens · lock-style · write-spec · pilot |
| media–selects | visual | capability · queue · frw · register |
| media（声） | voice | tts-rehearse · tts-ab |
| rough | design/post | assemble · compose-preview · Editor’s Cut |
| verified | post→deliver | final · review-final · export-desktop |

## 每环卡片（agent 必守）

### idea
- **禁止**：无命题 bulk I2V；关键词自动钉 heat max
- **命令**：`aifilm init`；可选写 `receipts/creative-brief.md`
- **下一环**：有 theme/title/audience 或用户明确跳过 brief

### story
- **禁止**：原文插图化
- **命令**：Director’s Lens → `director_intent`
- **下一环**：logline + theme（或等价 description）非空

### beats
- **禁止**：Beat=无信息「走一步」
- **字段**：`dramatic_function` · `dsl.story_beat` · `visible_change`
- **可选**：`receipts/beat-sheet.md`
- **lint**：`BEAT_SEMANTICS_MISS` / `MOTION_NO_MEANING`

### shots
- **hard**：`write-spec`；pilot 用户批准后 bulk（无批 ≤3 shot）
- **字段**：nar · dsl · shot_role · camera_axis · continue
- **Radio**：可交错 `tts-rehearse`，VO 预算 hard

### media
- **开场**：`capability`（TTS/FRW/BGM/lipsync）
- **I2V**：FRW LTX 2.3 → FRW API I2V → Grok Video 1.5；每路先过影片级 canary，`capability --suggest-i2v`
- **TTS**：edge 默认；Voicebox 质量/FALLBACK；禁 Neural→EL
- **BGM**：片级模板 → skill `assets/bgm/` → 程序化 rnb
- **Lipsync**：默认 off；说书强制 off；canary 后 auto
- **失败**：fail/requeue；禁手改 queue JSON

### selects
- **hard**：register + identity/motion approved
- **命令**：`aifilm selects report`
- **禁止**：有文件自动当 selects

### rough
- **产出**：silent/plate；`receipts/rough-cut.json`（可选）
- **禁止**：continue 缝 dissolve；无 selects 上调色冒充剪辑
- **可压缩**：用户赶交付可缩短 Editor’s Cut

### verified
- **hard**：`final` 技术成功 ≠ `final_complete`
- **十一维** review-final + 完整观看 + hash
- **export-desktop**
- **禁止**：假交付；双烧

## 音频嵌套（不另起主脊）

| 环 | TTS | BGM | Lipsync |
|----|-----|-----|---------|
| shots | VO 预算 · 近景才标 lipsync | mood 进 sound_plan | 仅对白近景 |
| media | edge / voicebox / tts-ab | template→skill→procedural | canary 单镜 |
| rough | measured 优先 | 可 silent 看戏 | off 看结构 |
| verified | mix_report | sidechain+loudnorm | 说书 off |

详：[audio-fallback.md](audio-fallback.md) · [voices.md](voices.md)

## CLI

```bash
# 自动调配（推荐主入口）
"$AIFILM" dispatch --root "<film>"
"$AIFILM" dispatch --root "<film>" --print-cmd-only

# 明细
"$AIFILM" craft --root "<film>"
"$AIFILM" capability --root "<film>"
"$AIFILM" audio-plan --root "<film>"
"$AIFILM" selects --root "<film>"
"$AIFILM" next --root "<film>"
```

调度说明：[auto-dispatch.md](auto-dispatch.md)

## 与 P0–P5

| 环 | 主能力 |
|----|--------|
| story–beats | P4 语义 · P0 变化 |
| shots–selects | P0–P3 · P1 身份 |
| media | P1–P3 · P5 分层路由 |
| rough–verified | P3 节奏 · P5 设计不越权 |

权威宪法：[principles.md](principles.md)
