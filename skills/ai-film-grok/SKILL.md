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

`autopilot`：allowlist 预算 + **本地吞吐**（closeout/preflight/variety…）；人审/质量/容量关即停写 receipt。

主流程：**定义故事 → 设计演出 → Pilot 样片 → 批量制作 → 选片与粗剪 → 后期母版 → 审片与交付**。  
映射：idea/story/beats→agent · shots/media→visual · rough/voice→voice+post · verified→deliver。  
八环/11-stage=内部；规则 `hard-defaults`；context 只 stages。

小说/剧本：[story.receive](references/story-reception.md) → `plan run --received-file`；lock 须用户确认。  
会诊：[creative-workshop](references/creative-workshop.md)（默认编译，`apply` 才写图）。  
长片：`plan run --production-mode longform --target-duration 480..900`；[longform](references/longform-workflow.md)

## P0

1. **真相**：graph 真、spec 投影；locks+hash 齐再媒体；先 Director’s Lens（[guide](references/directors-lens.md)·[lesson](references/lessons-2026-07-20-directors-lens.md)）。
2. **对白主链**：讲话镜=FRW LTX 2.3 有声I2V→无烧字/口型审；拒绝才 FRW `img2video`→LatentSync。LTX 不接锁 TTS；字幕 FFmpeg/HyperFrames 一次烧入。[workflow](references/dialogue-first-workflow.md)
3. **身份介质**：锁 medium/cast/face；still 只改已批源；moderated 禁 `image_gen` 绕脸；漫剧 manhua。
4. **先验后生**：still 过身份/结构/画风/几何（9:16≥704×1280）才 I2V。
5. **连续性**：`state-index check|plan|approve-state` 先于 bulk；衣着只前进（wardrobe ladder 逐件 I2I）；Continue 硬接批准末帧。
6. **审批/用量**：pilot 用户批；付费绑 hash/预算；`generation-usage.json`；human/paid/external 暂停。
7. **动作**：`grok_primary`=Grok→FRW API→LTX 2.3（安全对白锁 LTX）。**`hybrid_h3`**：云 bulk=Grok；restricted/肉戏→本地 MiniMax H3（`aifilm h3`，verified；**bulk 仍要 pilot 批**）。禁 Seedance/Wan 本地 I2V。H3 原声 `prefer_native`。
8. **声线·对白优先**：默认对白主链·**中文**（有对白=角色中文口型；禁旁白当主声）。**场硬闸=每场 ≥1 条 on/off_camera 台词；无对白场拒收**（逃生仅 `narration_reason`）。对白镜画面=说话者；**肉戏对白走 H3 i2v/r2v**。工具组=grok i2v · 5090 H3 · LTX 对白棚。Edge；BGM=rnb。[对白](references/dialogue-first-workflow.md)·[BGM](references/bgm-generation.md)
9. **成人 MAX**：肉戏≥50%·亲密≥60%·setup≤20%；extreme；四拍+bare；禁静默降 heat。[playbook](references/adult-max-playbook.md)
9b. **毒镜**：禁 futa/喷奶/霓虹生殖器；毒 still 禁 I2V。
10. **字幕**：`caption_text` 中文；`caption_mode`+`transition_fluency` 见 [cut-silk](references/lessons-2026-07-20-cut-silk-bilingual.md)。**正式 master** = HF owner（plate `subs=off`）。**Ship / 门红 PARTIAL** = **PIL 像素硬烧优先**；对白 cue **抽帧人眼可读**。[huangdao §G](references/lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md)·[stages/post](references/stages/post.md)
11. **后期单责**：title/sub/end 正式链单引擎；plate 默认可 `subs=off`（字已硬烧或 HF 后烧）。[title-double-burn](references/lessons-2026-07-20-title-double-burn.md)
11b. **连载**：`serial validate`；圣经/事件/钩子可审计。[workflow](references/serial-narrative-workflow.md)
12. **完成**：`final`≠`final_complete`；review/audit/字幕/export 齐。
13. **安全**：凭据本机；日志禁 token/prompt；外部不自动重试花费。
14. **高动**：mean≥18、肉戏≥20；桌面 final 仅 motion-gate ok。
15. **I2V 画风**：源=style-locked still；首段 MEDIUM LOCK cel。
16. **5090**：未锁视觉走 `weapon_route`；未验 fail closed。本机仅 1×`comfy_video`；禁 pgrep 自杀。[oom](references/lessons-2026-07-29-comfy-multifilm-contention-oom.md)
17. **口型**：默认 off；近景对白须人批后 LatentSync→MuseTalk，质差禁切 FRW。[lipsync](references/lipsync.md)

## 阶段

[agent](references/stages/agent.md)→[visual](references/stages/visual.md)→[voice](references/stages/voice.md)→[post](references/stages/post.md)→[deliver](references/stages/deliver.md) · [approval](references/stages/approval.md) · [INDEX](references/INDEX.md)

## 命令

```bash
"$AIFILM" doctor
"$AIFILM" plan run --root "<film>" --text "<story>" --title "<title>" --target-duration 60
"$AIFILM" write-spec --root "<film>"
"$AIFILM" state-index check --root "<film>"
"$AIFILM" pilot pack --root "<film>"          # GO 包 → pilot-go.json
"$AIFILM" variety-precheck --root "<film>"    # 设计期抗无聊
"$AIFILM" bulk-preflight --root "<film>"      # bulk 单门
# 用户批准后 bulk → final
"$AIFILM" final --root "<film>" --post-engine hyperframes --lipsync off --music-mood rnb --tts-backend edge
"$AIFILM" closeout run --root "<film>"        # plate 后收尾链（不自动批分）
"$AIFILM" review-final --root "<film>"
# 吞吐：select-shortlist · gpu-lease · tunnel-probe · queue-progress
```

深挖：[hard-defaults](references/hard-defaults.md) · [stages/visual](references/stages/visual.md) · [stages/deliver](references/stages/deliver.md) · [INDEX](references/INDEX.md)
