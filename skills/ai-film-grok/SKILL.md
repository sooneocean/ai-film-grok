---
name: ai-film-grok
description: Grok Imagine AI 剧情片：短片/8–15 分钟竖屏长片、I2V、声音、后期与证据交付。触发：AI 电影、漫剧、长片、dispatch、成片。
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

`autopilot`：allowlist 预算 + 本地吞吐；人审/质量/容量关即停写 receipt。

主流程：**定义故事 → 设计演出 → Pilot 样片 → 批量制作 → 选片与粗剪 → 后期母版 → 审片与交付**。  
映射：idea/story/beats→agent · shots/media→visual · rough/voice→voice+post · verified→deliver。  
八环/11-stage=内部；规则 `hard-defaults`；context 只 stages。

小说/剧本：[receive](references/story-reception.md)→[debrief](references/script-value-debrief.md)→`plan run`→`fidelity check`；lock 须确认。  
会诊：[creative-workshop](references/creative-workshop.md)。长片：`plan run --production-mode longform`；[longform](references/longform-workflow.md)

## P0

1. **真相**：graph 真、spec 投影；locks+hash 齐再媒体；先 Director’s Lens（[guide](references/directors-lens.md)）。
2. **对白主链**：讲话镜=FRW LTX 2.3 I2V；[workflow](references/dialogue-first-workflow.md)
3. **身份介质**：锁 medium/cast/face；still 只改已批源；moderated 禁 `image_gen` 绕脸；漫剧 manhua。
4. **先验后生**：still 过身份/结构/画风/几何（9:16≥704×1280）才 I2V。
5. **连续性**：`state-index` 先于 bulk；衣着只前进；Continue 硬接批准末帧。
6. **审批/用量**：pilot 用户批；付费绑 hash/预算；human/paid/external 暂停。
7. **动作（5090 主产线）**：**`h3_primary`**（推荐有 5090）= 全镜本地 H3 主生成（时间换无限产能）；`hybrid_h3`= Grok soft bulk + meat H3。场景：有 end→FLF；无 last→I2V；高动→R2V；无脸 env→T2V。Grok 仅 pilot/云 escape。禁 Seedance/Wan。[矩阵](references/weapon-lane-matrix.md) · [plan](../../docs/plans/2026-08-05-h3-primary-capacity.md)
8. **声线（中文唯一）**：口白=中文；每场≥1 台词；Edge；BGM=rnb。[对白](references/dialogue-first-workflow.md)
9. **成人 MAX**：肉戏≥50%·亲密≥60%·setup≤20%；extreme；四拍+bare。[playbook](references/adult-max-playbook.md)
9b. **毒镜**：禁 futa/喷奶/霓虹生殖器；毒 still 禁 I2V。
10. **字幕**：`caption_mode`+`caption_text` 中文硬烧；`transition_fluency` 见 [cut-silk](references/lessons-2026-07-20-cut-silk-bilingual.md)
11. **后期单责**：title/sub/end 单引擎；plate 可 `subs=off`。
11b. **连载**：`serial validate`。[workflow](references/serial-narrative-workflow.md)
12. **完成**：`final`≠`final_complete`；**`gate-auto`/`cinematic-gate` 绿** 才 export（机读过闸，禁手点循环）。
13. **安全**：凭据本机；日志禁 token；外部不自动重试花费。
14. **高动**：mean≥18、肉戏≥20；桌面 final 仅 motion-gate ok。
15. **I2V 画风**：源=style-locked still；首段 MEDIUM LOCK cel。
16. **5090**：未锁视觉走 `weapon_route`；本机 1×`comfy_video`；禁 pgrep 自杀。
17. **口型**：默认 off；近景对白人批后 LatentSync→MuseTalk。[lipsync](references/lipsync.md)
18. **零旁白 IRON**：`dialogue_drama` 默认 `zero_narration_strict`；`nar` 硬底 0%。
19. **DP+5-Track**：焦段/三点光；DX/FX/BG/MX/SUB；-16 LUFS。[5track](references/5track-audio-master.md)
20. **真片+gate-auto**：**运镜只在 Grok/H3 视频内**；still 不进 timeline。`aifilm gate-auto` 机写 mean→i2v-final→sex_sfx→five-track→true-video→variety→cinematic。仅 pilot / 多 take PK / review-final 须人。[memory](memory/2026-08-04-gate-auto.md)

## 阶段

[agent](references/stages/agent.md)→[visual](references/stages/visual.md)→[voice](references/stages/voice.md)→[post](references/stages/post.md)→[deliver](references/stages/deliver.md) · [approval](references/stages/approval.md) · [INDEX](references/INDEX.md)

## 命令

```bash
"$AIFILM" doctor
"$AIFILM" plan run --root "<film>" --text "<story>" --title "<title>" --target-duration 60
"$AIFILM" write-spec --root "<film>"
"$AIFILM" fidelity apply --root "<film>"; "$AIFILM" design-go --root "<film>"
"$AIFILM" pilot pack --root "<film>"
"$AIFILM" bulk-preflight --root "<film>"
# 用户批准后 bulk → gate-auto → final
"$AIFILM" ship-prep --root "<film>"
"$AIFILM" gate-auto --root "<film>"
"$AIFILM" final --root "<film>" --post-engine hyperframes --music-mood rnb --tts-backend edge
"$AIFILM" closeout run --root "<film>"
"$AIFILM" review-final --root "<film>"
```

深挖：[hard-defaults](references/hard-defaults.md) · [deliver](references/stages/deliver.md) · [5track](references/5track-audio-master.md) · [weapon-lane](references/weapon-lane-matrix.md)
