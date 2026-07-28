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

"$AIFILM" dispatch --root "<film>"          # compact 默认
"$AIFILM" dispatch --root "<film>" --full
"$AIFILM" advance --root "<film>"
```

每步后再 dispatch，只执行 `next_action`；读 `context_refs`（≤3）与 `weapon_route`。路由 ready、已授权且未锁 provider 就 live probe 后直用，失败即停。状态在 `receipts/dispatch.json`。

导演骨架：Concept→Script→Look→Animatic→Pilot→Bulk→Dailies→Selects/Rough→Picture→Post→Master；八环与工具层只是投影。

小说/剧本先 [story.receive](references/story-reception.md) → `plan run --received-file`；原文不可覆盖，lock 前须用户确认。

## 创作工作室

会诊/台词/提示词/声音见 [creative-workshop](references/creative-workshop.md)；默认只编译，显式 `apply` 才写图。

## P0 核心

1. **故事真相**：`drama-graph.json` 真相，`film-spec.json` 投影；locks + projection hash 齐再进媒体；先 Director’s Lens（[directors-lens.md](references/directors-lens.md)）。
2. **用户原文保真**：用户剧本/对白/主题是脊柱，模板禁整句覆盖。
3. **身份与介质**：先锁 medium/cast/face；角色 still 只编辑已批来源；moderated 禁 `image_gen` 绕脸；漫剧默认 manhua。
4. **先验后生**：still 过身份/结构/画风/几何（9:16 默认 ≥704×1280；接受 provider 原生 704×1280，不强制放大）才 I2V。
5. **连续性**：`state-index check|plan` 先于 bulk；衣着只前进；Continue 硬接批准末帧。
6. **审批/用量**：pilot 须用户批；付费绑 hash/预算；`generation-usage.json`；`advance` 遇 human/paid/external 暂停。
7. **供应商**：I2V 默认 `grok_primary`；恢复路径才用 `frw_video_model=seedance-2-fast-i2v`（见 [frw-degrade-dispatch.md](references/frw-degrade-dispatch.md)），禁静默 bulk。
8. **声音分轨**：口白中文 Edge；角色日文 Edge；字幕中文 `nar`。禁无 speaker 中日乒乓、说书填 `nar_ja`、清空日文轨。亲密 BGM=rnb。[voice lesson](references/lessons-2026-07-24-ep2-voice-heat-final.md)
9. **成人尺度 MAX**：act+climax≥50%、亲密≥60%、setup≤20%；spice=extreme、phase 只升；关键动作与特写须完整，禁静默降 heat。见 [sex-arc](references/lessons-2026-07-27-adult-scale-max-sex-arc.md) · [hard-defaults](references/hard-defaults.md) · [playbook](references/adult-max-playbook.md)
10. **字幕像素门**：成片须可见中文字幕；HF 失字须 recovery，禁清空 SRT；`sub_lead=0`；长片可直调 `render_final.py`。
11. **后期单一责任**：title/subtitle/end card 单引擎；`plate-cards blank`、plate `subs=off` 防双烧。
12. **完成定义**：`final` 技术成功 ≠ `final_complete`；review/post audit/字幕 attestation/export 回读须齐。
13. **安全**：凭据本机读；日志/manifest 禁 token/prompt；外部调用不自动重试花费。
14. **高动态**：平常 mean≥18、肉戏≥20（目标≥24）；禁 KB/弱 raw；**桌面 final 仅** `i2v-final-gate.json` ok。[high-motion](references/lessons-2026-07-27-high-motion-style-lock-final.md)
15. **I2V 画风锁**：源=style-locked still；首段 MEDIUM LOCK cel；禁以 mean 换 medium fail。
16. **5090 武器库**：dispatch 为未锁 provider 的视觉需求写 `weapon_route`；只用实跑 Qwen/Wan，实验仅 pilot；锁与人审优先，未验 fail closed。[规则](references/comfy-weapon-armory.md)

## 阶段

[agent](references/stages/agent.md)→[visual](references/stages/visual.md)→[voice](references/stages/voice.md)→[post](references/stages/post.md)→[deliver](references/stages/deliver.md)；暂停 [approval](references/stages/approval.md)。深挖 [INDEX](references/INDEX.md)。

## 最小命令

```bash
"$AIFILM" doctor
"$AIFILM" plan run --root "<film>" --received-file "<film>/receipts/story-reception.json"
"$AIFILM" plan run --root "<film>" --text "<story>" --title "<title>" --target-duration 60
"$AIFILM" plan validate --root "<film>" --strict
"$AIFILM" graph project --root "<film>" --force
"$AIFILM" write-spec --root "<film>"
"$AIFILM" state-index check --root "<film>"
"$AIFILM" pilot report --root "<film>"
"$AIFILM" usage status --root "<film>"
"$AIFILM" semantic-index query --root "<film>" --query "红夹克快递员"
"$AIFILM" comfy probe
"$AIFILM" comfy inventory
"$AIFILM" comfy capacity
"$AIFILM" route explain --root "<film>" --shot-id "shot01"
# 用户批准后才 pilot approve / bulk
"$AIFILM" final --root "<film>" --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge --compose-preset auto
"$AIFILM" review-final --root "<film>"
```

按需：[production routing](references/production-routing-control-plane.md) · [semantic-index](references/semantic-index.md) · [Comfy LAN](references/comfy-lan-control.md) · [hard-defaults](references/hard-defaults.md) · [双语剪辑](references/lessons-2026-07-20-cut-silk-bilingual.md)（`caption_mode`、`transition_fluency`） · [防双烧](references/lessons-2026-07-20-title-double-burn.md) · [Directors Lens 课](references/directors-lens.md) · [INDEX](references/INDEX.md)
