# 实战复盘：设计后期 + Pilot 闭环（2026-07-17）

承接 [lessons-2026-07-16-kei.md](lessons-2026-07-16-kei.md)。  
本轮主题：**把 HyperFrames/Remotion 接进 skill 却不拆 Grok I2V 主链**；**pilot 可评分、可路由、禁止自批**。

## 一句话

设计后期是「化妆」，不是「替你拍戏」；pilot 是「试妆试戏」，不是 agent 自己打勾。

## 现象对照

| # | 现象 | 根因 | 规则（已/应落地） |
|---|------|------|------------------|
| 1 | 想用 Remotion/HF 重做整条流水线 | 把合成器当成生成器 | **I2V 仍是唯一角色戏来源**；HF/Remotion 只做标题/字幕/叠层 |
| 2 | multiclip 成片 motion continuity 挂 | 片头/片尾黑场垫时长，抽帧像幻灯 | **镜头从 t=0 叠 I2V**；片头片尾半透明叠层，不垫黑场 |
| 3 | underlay 双重字幕 | FFmpeg 已烧字幕 + HF 再烧 | `--post-engine hyperframes` 时 FFmpeg **默认 `--subs off`**（只留 SRT） |
| 4 | HF 渲完无声轨 | 合成只有 muted video | **ensure_audio_mux**：从 film_final 或 VO/BGM stems 混轨 |
| 5 | agent 自批 pilot 混过 bulk | 无用户短语痕迹 | `pilot approve` 必须 `user_phrase`（「pilot 过」等）；**禁止** agent/bot |
| 6 | pilot 过了却不知三维过不过 | 只有 approval 没有 scorecard | 先 `pilot score`（identity/style/motion）再 approve |
| 7 | score fail 没挂到重拍单 | 失败只写 JSON 不入 notes | score fail **默认写 director_notes** |
| 8 | 第 4 镜 queue 失败只报 gate | 错误无可执行 next | gate 文案带 `pilot report → score → approve` |
| 9 | 成片后 agent 不知下一步 | status 只有 gates | **`status.next_actions` / `next_cmd`**；`aifilm next` 一条命令 |
| 10 | doctor 因无 HF 整片判死 | 可选路径当硬依赖 | `designed_post` **soft**；缺 HF 仍可 ffmpeg final |
| 11 | final hyperframes 双份 JSON | ffmpeg stdout + compose stdout 混打 | 单 emit：`{ffmpeg, compose, post_engine}` |
| 12 | 长 HF render 像卡死 | capture_output 吞进度 | render **流式打 stderr** |
| 13 | raw 中间片占磁盘 | 混音后未清 raw | 默认删 `film_hyperframes_raw`；`--keep-raw` 保留 |
| 14 | Studio 预览步骤碎 | 手敲 npx + 找端口 | `aifilm compose-preview` 起 background + URL + open |
| 15 | 中文 TTS 又走 ElevenLabs 400 | auto + 全局 ARGV | 成片 **`--tts-backend edge`**；preflight 警告 external 风险 |
| 16 | 色气片又写成 dark BGM | mood 覆盖 CLI | preflight 检查 sound_plan.mood；色气勿 dark |
| 17 | 导出桌面丢 pilot 证据 | 只拷 film-spec | export-desktop 带 pilot-approval/scorecard/notes |

## 正确分工（类比）

| 角色 | 工具 | 白话 |
|------|------|------|
| 摄影组 | Grok Imagine I2V | 拍出真运动镜头 |
| 剪辑台默认 | `aifilm final` (ffmpeg) | 旁白+BGM+烧录字幕，稳 |
|  retro 后期 | HyperFrames | 字卡、片头、调色、Studio 预览 |
| 实验时间线 | Remotion | React 字幕；**已接** `final --post-engine remotion [--npm-install]`（与 HF 对称） |
| 试妆试戏 | pilot 3 镜 | 用户点头后才能量产 |

## Agent 自检清单（2026-07-17 增补）

- [ ] `aifilm preflight --root …` 无 hard fail（或已读懂 soft warning）  
- [ ] `aifilm next --root …` 的下一步与当前阶段一致  
- [ ] pilot：`report` → 用户看三镜 → `score` 三维 → 用户原话 `approve`  
- [ ] 未 `user_approved` 时 **不超过 3 个不同 shot_id** 进 queue  
- [ ] 色气：`sound_plan.mood` ∈ rnb/soul/sensual，**不是** dark  
- [ ] 中文：`--tts-backend edge`（除非已锁中文 provider voice）  
- [ ] 设计后期：`compose-preview` 用户点头后再 `compose-render` / `--post-engine hyperframes|remotion`  
- [ ] underlay 前确认 plate **未 burn 字幕**（或走 `final --post-engine hyperframes|remotion` 的 subs off）；否则双烧 gate 会拦  

- [ ] multiclip 成片：抽帧**无大段纯黑标题垫**  
- [ ] final 后 `review-final` 七维含 **style**  
- [ ] 换 final 文件后旧 review 作废（register-final 会清）  

## 推荐命令序

```bash
aifilm doctor
aifilm preflight --root "$ROOT"
aifilm next --root "$ROOT"
# final 默认内置 preflight hard 门；应急才 --skip-preflight

# pilot
aifilm pilot pick --root "$ROOT"
# … 生成 3 镜 still+clip 并 register …
aifilm pilot report --root "$ROOT"
aifilm pilot score --root "$ROOT" --shots … --score-identity pass --score-style pass --score-motion pass --reviewer … --notes …
aifilm pilot approve --root "$ROOT" --user-phrase "pilot 过"

# 量产 → 成片
aifilm final --root "$ROOT" --tts-backend edge --music-mood rnb --lipsync off
# 或设计字幕：
aifilm final --root "$ROOT" --post-engine hyperframes --tts-backend edge --music-mood rnb
aifilm compose-preview --root "$ROOT"   # 调字卡
aifilm compose-render --root "$ROOT"    # 需要重渲时

aifilm review-final --root "$ROOT" --approve …
aifilm export-desktop --root "$ROOT" --name "…"
```

## 代码入口

| 能力 | 文件 |
|------|------|
| 设计后期导出 | `scripts/export_composition.py` |
| HF 渲染注册 | `scripts/compose_render.py` |
| Studio 预览 | `scripts/compose_preview.py` |
| pilot scorecard | `scripts/pilot_review.py` |
| 下一步路由 | `scripts/next_actions.py` |
| 一键体检 | `aifilm preflight` / `aifilm next` |

## 与 Kei 教训的关系

- Kei 解决：**拍什么、别 loop、别混 provider、BGM/TTS/字幕**  
- 本文件解决：**后期怎么接合成器、pilot 怎么可验收、agent 怎么知道下一步**  
- 两边都成立；冲突时 **一致性 + 用户批准** 优先于速度。
