---
name: ai-film-grok
description: Grok Build 专业 AI 电影导演系统：把灵感收成可验收的 7 段成片主流程（定义故事→设计演出→Pilot 样片→批量制作→选片与粗剪→后期母版→审片与交付）。拍摄走多武器可插拔（Grok 静帧 + I2V、5090 本机 MiniMax H3 I2V/R2V/FLF、FRW LTX 对白原声），工程层以可验证门禁（input fidelity、style-bible、transition、cinematic、十一维 scorecard）守交付；支持 8–15 分钟竖屏长片与短剧/漫剧。触发：AI 电影、漫剧、长片、dispatch、成片、H3 5090。不作为 Photo/Ken Burns 静态轮播，也不替代真人 A-roll（→ aifilm shortform）。
---

# Film Grok

产出可验收的 9:16 成片。

## 入口

```bash
SKILL_DIR="$HOME/.grok/plugins/ai-film-grok/skills/ai-film-grok"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"
"$AIFILM" dispatch --root "<film>"          # compact
"$AIFILM" dispatch --root "<film>" --full
"$AIFILM" advance --root "<film>"
```

每步后 dispatch，只跑 `next_action`；先 `blocked_by` 再 `required_proof`。读 `context_refs`/`weapon_route`。失败即停。`receipts/dispatch.json`。
路由族谱：[routing-map](references/routing-map.md)。
`autopilot`：allowlist 预算 + 本地吞吐；人审/质量/容量关即停写 receipt。

主流程：**定义故事 → 设计演出 → Pilot 样片 → 批量制作 → 选片与粗剪 → 后期母版 → 审片与交付**。
映射：idea/story/beats→agent · shots/media→visual · rough/voice→voice+post · verified→deliver。
八环/11-stage=内部；规则 `hard-defaults`；context 只 stages。

**路径选择：** AI 剧情/漫剧/H3 成片 → **主产线** `plan run`…`final`；真人 A-roll 15–60s 编排 → `aifilm shortform`；决策树 [shortform-director](references/shortform-director.md)。

小说/剧本：[receive](references/story-reception.md)→[debrief](references/script-value-debrief.md)→`plan run`→`fidelity check`；lock 须确认。
会诊：[creative-workshop](references/creative-workshop.md)。长片：`plan run --production-mode longform`；[longform](references/longform-workflow.md)
**短版选型**：默认主产线 `plan run`（shortform）；仅 15–60s topic/A-roll/C-roll 编排用 `aifilm shortform`；禁后期 lipsync。

## P0

1. **真相**：graph 真、spec 投影；locks+hash 齐再媒体；先 Director’s Lens（[guide](references/directors-lens.md)）。
2. **对白主链**：讲话镜=**Grok Video / 5090 H3 原音**（禁后期对嘴）；[workflow](references/dialogue-first-workflow.md)
3. **身份介质**：锁 medium/cast/face；still 只改已批源；moderated 禁 `image_gen` 绕脸；漫剧 manhua。
4. **先验后生**：still 过身份/结构/画风/几何（9:16≥704×1280）才 I2V。
5. **连续性**：`state-index` 先于 bulk；衣着只前进；Continue 硬接批准末帧。
6. **审批/用量**：pilot 用户批；付费绑 hash/预算；human/paid/external 暂停。
7. **动作（5090 主产线）**：**`h3_primary`**（推荐有 5090）= 全镜本地 H3；默认 **`h3 run-next --execute --max 5`**（多 agent 不占满）。挂机排水仅用户点名独占：`h3 cycle --until-empty --execute --i-own-the-gpu`。ETA `h3 capacity-plan`。场景：有 end→FLF；无 last→I2V；高动→R2V；无脸 env→T2V。`hybrid_h3`= 双轨。Grok 仅 pilot/云 escape。禁 Seedance/Wan。[矩阵](references/weapon-lane-matrix.md) · [multi-agent](memory/2026-08-06-multi-agent-gpu-no-hog.md)
8. **声线（中文唯一）**：口白=中文；每场≥1 台词；Edge；BGM=rnb。[对白](references/dialogue-first-workflow.md)
9. **成人 MAX**：肉戏≥50%·亲密≥60%·setup≤20%；extreme；四拍+bare；**不回穿**；大尺度做不到→全裸诱惑→**模型极限勿硬上**。[playbook](references/adult-max-playbook.md) · [2026-08-06](memory/2026-08-06-wardrobe-no-redress-fullnude-fallback.md)
9b. **毒镜**：禁 futa/喷奶/霓虹生殖器；毒 still 禁 I2V。
10. **字幕**：`caption_mode`+`caption_text` 中文硬烧；`transition_fluency` 见 [cut-silk](references/lessons-2026-07-20-cut-silk-bilingual.md)
11. **后期单责**：title/sub/end 单引擎；plate 可 `subs=off`。
11b. **连载**：`serial validate`。[workflow](references/serial-narrative-workflow.md)
12. **完成**：`final`≠`final_complete`；**`gate-auto`/`cinematic-gate` 绿** 才 export。
13. **安全**：凭据本机；日志禁 token；外部不自动重试花费。
14. **高动**：mean≥18、肉戏≥20；桌面 final 仅 motion-gate ok。
15. **I2V 画风**：源=style-locked still；首段 MEDIUM LOCK cel。
16. **5090**：未锁视觉走 `weapon_route`；本机 1×`comfy_video`；禁 pgrep 自杀。
17. **口型/原音**：**v2.40 移除** 后期对嘴（仅 `--lipsync off`）；有声镜靠模型原音 `prefer_native`。[lipsync](references/lipsync.md)
18. **零旁白 IRON**：`dialogue_drama` 默认 `zero_narration_strict`；`nar` 硬底 0%。
19. **DP+5-Track**：焦段/三点光；DX/FX/BG/MX/SUB；-16 LUFS。[5track](references/5track-audio-master.md)
20. **真片+gate-auto**：**运镜只在 Grok/H3 视频内**；still 不进 timeline。`aifilm gate-auto` 机写 mean→i2v-final→sex_sfx→five-track→true-video→variety→cinematic。[memory](memory/2026-08-04-gate-auto.md)

## 阶段

[agent](references/stages/agent.md)→[visual](references/stages/visual.md)→[voice](references/stages/voice.md)→[post](references/stages/post.md)→[deliver](references/stages/deliver.md) · [approval](references/stages/approval.md) · **[H3 日课](references/stages/h3-core-day.md)** · [INDEX](references/INDEX.md)

## 命令

```bash
"$AIFILM" doctor
"$AIFILM" plan run --root "<film>" --text "<story>" --title "<title>" --target-duration 60
"$AIFILM" write-spec --root "<film>"
"$AIFILM" fidelity apply --root "<film>"; "$AIFILM" design-go --root "<film>"
"$AIFILM" pilot pack --root "<film>"; "$AIFILM" bulk-preflight --root "<film>"
"$AIFILM" ship-prep --root "<film>"; "$AIFILM" gate-auto --root "<film>"
"$AIFILM" final --root "<film>" --post-engine hyperframes --music-mood rnb --tts-backend edge
"$AIFILM" closeout run --root "<film>"; "$AIFILM" review-final --root "<film>"
```

深挖：[hard-defaults](references/hard-defaults.md) · [deliver](references/stages/deliver.md) · [5track](references/5track-audio-master.md) · [weapon-lane](references/weapon-lane-matrix.md)
