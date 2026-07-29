---
name: ai-film-grok
description: Grok Build 专用 AI 短片 skill：Idea→Verified 导演工序、Grok Imagine 静帧/I2V、TTS/声音、设计后期与证据化交付。触发：AI 电影、漫剧、Grok Imagine、dispatch、成片、/ai-film-grok。
---

# AI Film Grok

把想法收成可恢复、可验收的 9:16 动态成片。真 I2V/footage、混音、字幕与人审缺一不可。

## 入口

```bash
SKILL_DIR="$HOME/.grok/plugins/ai-film-grok/skills/ai-film-grok"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"
"$AIFILM" dispatch --root "<film>"          # compact
"$AIFILM" dispatch --root "<film>" --full
"$AIFILM" advance --root "<film>"
```

每步后 dispatch，只跑 `next_action`；读 `context_refs`（≤3）与 `weapon_route`。ready+授权+未锁 provider 才 probe 直用，失败即停。状态：`receipts/dispatch.json`。

骨架：Concept→Script→Look→Animatic→Pilot→Bulk→Dailies→Selects/Rough→Picture→Post→Master。  
小说/剧本：[story.receive](references/story-reception.md) → `plan run --received-file`；原文不覆盖，lock 须用户确认。  
创作会诊：[creative-workshop](references/creative-workshop.md)（默认只编译，`apply` 才写图）。

## P0

1. **真相**：`drama-graph` 真，`film-spec` 投影；locks+hash 齐再媒体；先 Director’s Lens（[directors-lens.md](references/directors-lens.md)·[lesson](references/lessons-2026-07-20-directors-lens.md)）。
2. **对白主链**：剧情先对白剧本再锁；原文是脊柱，禁模板覆盖。[workflow](references/dialogue-first-workflow.md)
3. **身份介质**：锁 medium/cast/face；still 只改已批源；moderated 禁 `image_gen` 绕脸；漫剧 manhua。
4. **先验后生**：still 过身份/结构/画风/几何（9:16≥704×1280）才 I2V。
5. **连续性**：`state-index check|plan|approve-state` 先于 bulk；衣着只前进（wardrobe ladder 逐件 I2I）；Continue 硬接批准末帧。
6. **审批/用量**：pilot 用户批；付费绑 hash/预算；`generation-usage.json`；human/paid/external 暂停。
7. **供应商**：I2V=`grok_primary`；恢复路径才 `frw_video_model=seedance-2-fast-i2v`（[frw-degrade-dispatch.md](references/frw-degrade-dispatch.md)），禁静默 bulk。
8. **声线**：口白中文 Edge；角色日文 Edge；字幕中文。禁无 speaker 中日乒乓、说书 `nar_ja`、清空日文轨。BGM=rnb；缺已批 edit/bridge 则 `final` 阻塞。[BGM](references/bgm-generation.md)
8b. **对白 i2i**：先做 performance-state；FRW 有精确 I2I receipt 才优先，否则查 `comfy capacity`；忙就等，禁抢队列。[lesson](references/lessons-2026-07-29-dialogue-i2i-frw-priority-and-5090-readdress.md)
9. **成人 MAX**：肉戏≥50%、亲密≥60%、setup≤20%；extreme；四拍+bare；impact≥A；禁静默降 heat。[playbook](references/adult-max-playbook.md)
9b. **毒镜**：禁 futa/喷奶/霓虹生殖器；毒 still 禁 I2V、毒 clip 禁 final。
10. **字幕**：像素内中文；HF 失字 recovery；`sub_lead=0`；禁空 SRT。`caption_mode`/`transition_fluency` 见 [cut-silk](references/lessons-2026-07-20-cut-silk-bilingual.md)。
11. **后期单责**：title/sub/end 单引擎；`plate-cards blank`、plate `subs=off` 防双烧（[title-double-burn](references/lessons-2026-07-20-title-double-burn.md)）。
11b. **可选连载**：serial 先过 `serial validate`；系列圣经、首 30 秒承诺、单集主事件、追更钩子、成人/权利来源必须可审计（[workflow](references/serial-narrative-workflow.md)）。
12. **完成**：`final`≠`final_complete`；review/audit/字幕/export 齐。
13. **安全**：凭据本机；日志禁 token/prompt；外部不自动重试花费。
14. **高动**：平常 mean≥18、肉戏≥20；禁 KB；桌面 final 仅 motion-gate ok。
15. **I2V 画风**：源=style-locked still；首段 MEDIUM LOCK cel。
16. **5090**：未锁视觉走 `weapon_route`；未验 fail closed。
16b. **多片抢 5090 + 本机 OOM**：**本机同时只 1 个** `comfy_video.py`；禁 `pgrep -f comfy_video` 自杀；邻镜 meat 禁静默顶替（须 FALLBACK+PARTIAL）。[lesson](references/lessons-2026-07-29-comfy-multifilm-contention-oom.md)
17. **bulk→final**：[evirus ch04](references/lessons-2026-07-29-evirus-ch04-bulk-final-iron.md) — bare 续接、双轮 register、长超时 final、禁内衣装插入。
18. **收尾门**：[closeout](references/lessons-2026-07-29-closeout-gates-chaebol.md) — heat codes、sensory、truth_contract、真 concat 钟、清 quality 缓存、review→audit→export。
19. **抗重复·抗无聊**：[shot-variety](references/lessons-2026-07-29-shot-variety-anti-boring.md) — 门绿≠好看；motion 禁复制；景别真变；主戏≥4.5s；contact 可读差。
20. **5090 独占 / pilot I2V**：[gpu-priority](references/lessons-2026-07-29-comfy-gpu-priority-pilot-i2v.md) — 一机一 owner；禁误 interrupt/误杀 zsh；`TN`→CONT；experimental=`stage=pilot`+`--allow-experimental`；clips 文件数才算。

## 阶段

[agent](references/stages/agent.md)→[visual](references/stages/visual.md)→[voice](references/stages/voice.md)→[post](references/stages/post.md)→[deliver](references/stages/deliver.md) · [approval](references/stages/approval.md) · [INDEX](references/INDEX.md)

## 命令

```bash
"$AIFILM" doctor
"$AIFILM" plan run --root "<film>" --text "<story>" --title "<title>" --target-duration 60
"$AIFILM" write-spec --root "<film>"
"$AIFILM" state-index check --root "<film>"
"$AIFILM" pilot report --root "<film>"
# 用户批准后 bulk
"$AIFILM" final --root "<film>" --post-engine hyperframes --lipsync off --music-mood rnb --tts-backend edge
"$AIFILM" review-final --root "<film>"
```

深挖：[hard-defaults](references/hard-defaults.md) · [directors-lens](references/directors-lens.md) · [comfy armory](references/comfy-weapon-armory.md) · [INDEX](references/INDEX.md)
