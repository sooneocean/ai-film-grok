# 底层泛化能力（Generalization Layer）

> 本文件是 **一切流水线的宪法**。具体 playbook（frame-chain、meaningful motion、HF/Remotion…）只是这些能力的**实例化**。  
> **之后 skill 任何新增规则，必须能映射到下列至少一条泛化能力**；不能只加「这一部片的补丁」。

## 为何需要底层

用户要求：效果验证后，能力要**可复用、可迁移**，不是只服务《戏服玩心夜》或某一风格。  
agent 在新题材（恐怖 / 公路 / 双人对话 / 16:9）上仍应自动启用同一套抽象，而不是重发明流程。

## 六大泛化能力（P0–P5）

| ID | 能力 | 白话 | 必问 | 当前实例化 |
|---|---|---|---|---|
| **P0 可观测变化** | Observable Change | 每一生产单元（镜）必须有可指认的状态 A→B | 这一镜世界哪变了？ | `visible_change` · meaningful-motion · vo-motion-link |
| **P1 身份连续** | Identity Continuity | 跨镜主体可识别，禁止无故换模/换服/换脸 | 还是同一个人吗？ | style-bible · cast master · lock-style · identity score |
| **P2 时空连续** | Spatiotemporal Continuity | 姿势、轴线、道具、光与天气可接戏 | 上一秒后果还在吗？ | continuity_chain · 九项核对 · promote 字节首帧 · **continue 强 hard** |
| **P3 动能连续** | Momentum Continuity | 切在动作中，不站定再起跑；机位轴轮换 | 动能断了吗？一镜一机位主轴？ | mid_motion · visual_fit:vo · hard match-cut · **`camera_axis` 轮换** |
| **P4 语义绑定** | Semantic Binding | 口白 / beat / 动态同一事件 | 闭眼听能否猜画面？ | nar=action=motion · beat 语义 lint |
| **P5 分层表达** | Layered Expression | 戏/拼/合成床/设计后期各司其职，禁越权 | 这层该不该做？谁锁脸？ | **产品四层**（视觉→语音→HF/Remotion→FFmpeg，见 [pipeline-methodology.md](pipeline-methodology.md)）+ **视觉内 L0–L3**（Grok still · I2V 脸 · LTX 无脸床 · HF）· plate-cards blank |

## 生产单元契约（任何一镜）

每个 shot 在进入 `media-queue` 前，agent 内心（或 film-spec 字段）必须能填：

```text
P0 visible_change:  <状态 A → 状态 B>
P4 story_beat:      <一句戏剧功能>
P4 action/motion:   <可见过程；主动词领先>
P2 start/end_pose:  <接戏两端（continue 缝）>
P3 cut_on:          mid_motion | hold
```

缺 P0/P4 的 hook·approach·action → soft lint（`MOTION_NO_MEANING` / `BEAT_SEMANTICS_MISS`）；  
`meaningful_motion_strict` / `vo_motion_strict` / `frame_chain_strict` 可升 hard。

## 流水线如何「挂载」泛化层

```
Director’s Lens（文本→故事→storyboard） → P0 P4 语义先写死（visible_change / beat）
init / lock-style          → P1
write-spec                 → P0 P4（lint）+ P2/P3（intents 强 hard · camera_axis）
continuity-chain           → P2
I2V hero + promote → P1 P2 P3（脸只走已验证 I2V；FRW LTX→FRW API→Grok）
LTX T2V env beds           → P5 合成层（无脸；拼进时间线，不锁身份）
final ffmpeg               → P3（visual_fit vo + hard；env↔hero 可 soft）
final hyperframes|remotion → P5（blank plate + 字幕/片头；不替代 P0–P4）
review-final               → P0–P5 人工十一维（含 style/motion）
```

**禁止**：只用 P5（设计后期）掩盖 P0–P4 失败；只用 motion QA「能动」代替 P0「有戏」。  
**禁止**：跳过 Lens 把原文插图化——那是 P0/P4 在源头就空了。

权威：[directors-lens.md](directors-lens.md)。

## 新增规则检查单（改 skill 前）

- [ ] 能标到 P0–P5 中的哪一条？
- [ ] 有可跑 lint / 命令 / 字段，而不只是散文提醒？
- [ ] 对非色气题材仍成立？（换 logline 试一次）
- [ ] 是否与已有实例冲突？（chain vs soft soup、meaningful vs 纯微动）
- [ ] 文档入口：本文件 + 对应 lessons；SKILL.md 只留指针

## 题材迁移（同一能力，不同皮）

| 题材 | P0 示例 visible_change |
|---|---|
| 色气更衣室 | 门闩开→关；距离远→半掌 |
| 恐怖走廊 | 灯亮→灭；门缝无人→有影 |
| 公路片 | 车内→车外雨；地图折痕加深 |
| 双人对话 | 两人隔桌→一方起身逼近 |

P1–P5 流程不变，只改 bible / cast / nar / motion 词表。

## 相关实例（非完整列表）

| 实例 | 主能力 |
|---|---|
| [directors-lens](directors-lens.md) / [lessons-directors-lens](lessons-2026-07-20-directors-lens.md) | P0 P4（叙事上游） |
| [meaningful-motion](lessons-2026-07-20-meaningful-motion.md) | P0 P4 |
| [editor-cut-pass](editor-cut-pass.md) / [lessons-editor-cut-ecchi-scale](lessons-2026-07-20-editor-cut-ecchi-scale.md) | P3 P4 P5（规划≠剪辑；成人 max 尺度） |
| [continuity_chain](continuity_chain.md) | P2 |
| [action-fluency](lessons-2026-07-20-action-fluency.md) | P3 |
| [vo-motion-link](lessons-2026-07-17-vo-motion-link.md) | P4 |
| [designed-post-fluency](lessons-2026-07-20-designed-post-fluency.md) | P5 |
| [style-bible](style-bible.md) / [consistency](consistency.md) | P1 |
| [sediment-cn-codex](lessons-2026-07-20-sediment-cn-codex.md)（构图铁律·库存·时长真相·TTS预演·证据分层） | P0 P2 P4 P5 |
| [vo-atempo three-axis](lessons-2026-07-20-vo-atempo-three-axis.md) | P2 P4 |
| [vo-drag + motion-snap](lessons-2026-07-20-vo-drag-motion-snap.md)（星声） | P2 P3 P4 |
| [editorial-craft](editorial-craft.md) / [lessons-editorial-craft](lessons-2026-07-20-editorial-craft.md) | P2 P3 P4 P5 |
| [character-stance](character-stance.md) / [lessons-stance](lessons-2026-07-20-character-stance.md) | P1 P2 P3 P4 |
| [frw-degrade-dispatch](frw-degrade-dispatch.md)（授权降级 · 官方 FLF） | P1 P2 |
