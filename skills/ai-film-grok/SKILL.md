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

每步后 dispatch，只跑 `next_action`；先解除 `blocked_by`，再以 `required_proof` 判断能否过关。读 `context_refs` 与 `weapon_route`。失败即停。状态：`receipts/dispatch.json`。

`autopilot`：仅 allowlist 预算动作；整数 tick+实时就绪；人工/质量/容量关即停并写 receipt。

主流程（对外唯一进度）：**定义故事 → 设计演出 → Pilot 样片 → 批量制作 → 选片与粗剪 → 后期母版 → 审片与交付**。
Professional 11-stage 与八环只保留为内部证据／诊断投影，不要求用户同时理解多套阶段名称。
小说/剧本：[story.receive](references/story-reception.md) → `plan run --received-file`；原文不覆盖，lock 须用户确认。
创作会诊：[creative-workshop](references/creative-workshop.md)（默认只编译，`apply` 才写图）。

长片 v1：`plan run --production-mode longform --target-duration 480..900`；锁 graph 后 project→write-spec。9:16、三幕、≤90s 单元、故事/animatic→pilot→全片观看三闸；禁静默换 provider。[longform](references/longform-workflow.md)

## P0

1. **真相**：graph 真、spec 投影；locks+hash 齐再媒体；先 Director’s Lens（[guide](references/directors-lens.md)·[lesson](references/lessons-2026-07-20-directors-lens.md)）。
2. **对白主链**：讲话镜=FRW LTX 2.3 有声I2V→无烧字/口型审；拒绝才 FRW `img2video`→LatentSync。LTX 不接锁 TTS；字幕 FFmpeg/HyperFrames 一次烧入。[workflow](references/dialogue-first-workflow.md)
3. **身份介质**：锁 medium/cast/face；still 只改已批源；moderated 禁 `image_gen` 绕脸；漫剧 manhua。
4. **先验后生**：still 过身份/结构/画风/几何（9:16≥704×1280）才 I2V。
5. **连续性**：`state-index check|plan|approve-state` 先于 bulk；衣着只前进（wardrobe ladder 逐件 I2I）；Continue 硬接批准末帧。
6. **审批/用量**：pilot 用户批；付费绑 hash/预算；`generation-usage.json`；human/paid/external 暂停。
7. **动作供应商**：`grok_primary`：**Grok image_to_video → FRW API I2V → FRW LTX 2.3**（对白讲话镜锁 FRW LTX 有声 I2V，不接 Grok）。每路均须当前影片 canary；未就绪跳过，已启动者仅技术失败可签名降级。禁 Seedance 与 Wan 2.2 本地 I2V。
8. **声线**：口白中文 Edge；角色日文 Edge；字幕中文。禁无 speaker 中日乒乓、说书 `nar_ja`、清空日文轨。BGM=rnb；缺已批 edit/bridge 则 `final` 阻塞。[BGM](references/bgm-generation.md)
9. **成人 MAX**：肉戏≥50%、亲密≥60%、setup≤20%；extreme；四拍+bare；impact≥A；禁静默降 heat。[playbook](references/adult-max-playbook.md)
9b. **毒镜**：禁 futa/喷奶/霓虹生殖器；毒 still 禁 I2V、毒 clip 禁 final。
10. **字幕/画面字**：唯一 owner=HyperFrames；禁双烧与空 SRT。`caption_mode` 与 `transition_fluency` 依 [cut-silk](references/lessons-2026-07-20-cut-silk-bilingual.md)；I2V 出现内生字、水印或乱码即禁入成片：全帧审计→逐帧修复→重编→复审→人工审。
11. **后期单责**：title/sub/end 单引擎；`plate-cards blank`、plate `subs=off` 防双烧（[title-double-burn](references/lessons-2026-07-20-title-double-burn.md)）。
11b. **连载**：`serial validate`；系列圣经、单集事件、追更钩子与权利来源可审计。[workflow](references/serial-narrative-workflow.md)
12. **完成**：`final`≠`final_complete`；review/audit/字幕/export 齐。
13. **安全**：凭据本机；日志禁 token/prompt；外部不自动重试花费。
14. **高动**：平常 mean≥18、肉戏≥20；禁 KB；桌面 final 仅 motion-gate ok。
15. **I2V 画风**：源=style-locked still；首段 MEDIUM LOCK cel。
16. **5090**：未锁视觉走 `weapon_route`；未验 fail closed。
16b. **5090/OOM**：本机仅 1 个 `comfy_video.py`；禁 `pgrep -f` 自杀；邻镜禁静默顶替。[lesson](references/lessons-2026-07-29-comfy-multifilm-contention-oom.md)
17. **口型路由**：默认 off（说书）；近景对白必须人工批准后走 RTX `LatentSync 1.6` → `MuseTalk 1.5`，质差禁切 FRW。[lipsync](references/lipsync.md)

## 阶段

[agent](references/stages/agent.md)→[visual](references/stages/visual.md)→[voice](references/stages/voice.md)→[post](references/stages/post.md)→[deliver](references/stages/deliver.md) · [approval](references/stages/approval.md) · [INDEX](references/INDEX.md)

## 命令

```bash
"$AIFILM" doctor
"$AIFILM" plan run --root "<film>" --text "<story>" --title "<title>" --target-duration 60
"$AIFILM" plan run --root "<film>" --received --production-mode longform --target-duration 600
"$AIFILM" write-spec --root "<film>"
"$AIFILM" longform status --root "<film>"
"$AIFILM" state-index check --root "<film>"
"$AIFILM" pilot report --root "<film>"
"$AIFILM" frw ab catalog --root "<film>"   # 只读；A/B 见 references/frw-ab-workflow.md
# 用户批准后 bulk
"$AIFILM" final --root "<film>" --post-engine hyperframes --lipsync off --music-mood rnb --tts-backend edge
"$AIFILM" review-final --root "<film>"
```

深挖：[hard-defaults](references/hard-defaults.md) · [directors-lens](references/directors-lens.md) · [comfy armory](references/comfy-weapon-armory.md) · [INDEX](references/INDEX.md)
