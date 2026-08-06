# 流水线方法论（工具层 + 工序层）

> 2026-07-21 · **P5 分层表达**
> 两条正交轴：**电影工序**（减叙事模糊）× **工具层**（减实现模糊）。
> 工序详解：[generative-film-craft.md](generative-film-craft.md) · 可执行路由：SKILL.md · 弹性默认：[hard-defaults.md](hard-defaults.md)

## 一句话

**先把想法锁成可剪的故事与镜功能，再生成真动态与声音，再设计叠层与混音导出。**
前一层没确认就 bulk 生成 → 漂亮废片。Ken Burns / 字卡不得冒充 I2V。

---

## 轴 A · 电影工序（逐层减模糊）

**对外唯一进度：七段主流程**（默认 `dispatch.phase`）：

```text
定义故事 → 设计演出 → Pilot 样片 → 批量制作 → 选片与粗剪 → 后期母版 → 审片与交付
```

每次 dispatch 只给一个 `next_action`；`blocked_by` 说明当前不能前进的原因，
`required_proof` 说明过关证据，`optional_actions` 只作辅助而不竞争主线。

**Professional 11 阶段**（`dispatch.workflow`）是内部证据排序与旧项目相容投影：

```text
概念锁 → 剧本锁 → 部门与视觉锁 → 镜头与动态分镜锁 → Pilot 批准
→ 批量生成 → 每日样片审核 → 选片与粗剪 → 画面锁定 → 后期锁定 → 母版锁定
```

`agent → visual → voice → design → post → deliver → done` 同样仅是兼容旧
receipt、HUD 与路由的**内部执行层**，不得作为第二套用户进度。

**创作八环检查表**（`aifilm craft`，不是项目进度）：

```text
Idea → Story → Beats → Shots → Media → Selects → Rough Cut → Verified MP4
```

详表：[craft-spine.md](craft-spine.md) · 音频：[audio-fallback.md](audio-fallback.md)

展开工序（可压缩，不可倒序）：

```text
想法 → 创意命题 → 故事 → Beats → 剧本 → Radio Edit
    → 视觉 Bible → 分镜/Coverage/Shot Package
    → 生成 → Selects → 初剪/精剪 → 声色字幕 → 成片
```

六动词：**Define → Structure → Visualize → Generate → Select → Edit**

四大区：Development · Pre-production · Production · Post
五锁（软）：Concept · Script · Spec/Animatic · Picture · Master

完整 checklist 与 Beat/Coverage 定义 → [generative-film-craft.md](generative-film-craft.md)。

---

## 轴 B · 工具四层（产品交付）

**Grok Build 宿主**（会话内，见 [grok-build-sdk.md](grok-build-sdk.md)）：

```text
Reasoning / Structured / Web·X Search
        + image_gen · image_edit · image_to_video
        + film-root 记忆
        ↓
本地 aifilm 门禁 · FRW bulk · edge TTS · HF · FFmpeg
```

```text
用戶 Prompt / 劇本
        ↓
Grok Agent（規劃 + Prompt 優化 + 角色一致性 + Imagine）
        ↓
1. 視覺生成     Grok still + FRW LTX / FRW API / Grok I2V
2. 語音生成     Edge TTS + tts-rehearse + SRT
3. 動態合成     HyperFrames（優先） / Remotion
4. 最終後處理   FFmpeg 拼板 · 混音 · 導出
        ↓
最終 MP4 + 預覽 + 可下載資產
```

| 工具层 | 职责 | 禁止 |
|---|---|---|
| Agent | Lens · film-spec · lock-style · pilot · next | 原文插图化；自批 pilot |
| 1 视觉 | 真动态 clip | Ken Burns 当戏；T2V 锁脸 |
| 2 语音 | 旁白时间轴 | loop 撑字；Neural→ElevenLabs |
| 3 设计 | 标题/双字幕/grade | 替代 I2V；接戏缝 dissolve |
| 4 后处理 | 合并混音导出 | xfade 糊接戏断 |

**双烧**：设计路径 `plate-cards blank` + `subs off`。

---

## 两轴对照（agent 调度用）

| 创作检查表 | 工序位置 | 工具层 / 命令 |
|---|---|---|
| Idea–Story | Development | `init` · Lens · `director_intent` · `craft` |
| Beats–Shots | Pre | `write-spec` · pilot · `tts-rehearse` |
| Media | Production | `capability` · queue · frw · TTS/BGM |
| Selects | Production | `register` · `selects report` |
| Rough | Post | assemble · compose-preview · Editor’s Cut |
| Verified | Master | `final` · review-final · export |

---

## 产品顺序 vs 工程一键

**产品心智**：视觉素材齐 → 语音锁定 → 设计层 → 交付。

**CLI 现实** `final --post-engine hyperframes`：

```text
approved clips
  → [4 局部] FFmpeg plate（VO/BGM · subs off）
  → [3] HyperFrames/Remotion
  → [4 封装] register / export
```

FFmpeg 服务后处理层，也会先做设计 underlay；**交付默认仍是 HyperFrames 路径**。

---

## 分层路由（视觉内部）

| 层 | 主力 | Fallback |
|---|---|---|
| L0 身份静帧 | Grok `image_edit(cast)` | FRW i2i（慎） |
| L1 人物 A-roll | FRW LTX 2.3 | FRW API I2V → Grok Video 1.5 |
| L2 环境床 | FRW LTX T2V | Grok no-face → verified local |
| L3 设计 | HyperFrames | Remotion |

---

## 证据与完成

| 完成 | 证据 |
|---|---|
| Development | logline/theme 或 directors-lens 回执 |
| Spec Lock | write-spec 通过 · pilot 用户批准 |
| Production | approved clips + motion |
| Voice | tts-rehearsal 或 mix_report |
| Master | final_film + 十一维 review-final + export |

intent ≠ executed ≠ human_review。

---

## 映射原则（P0–P5）

- **P1 身份**：L0 Grok still
- **P0/P3 动态**：I2V + mid_motion
- **P4 语义**：Beat = story_beat / visible_change / nar=action=motion
- **P5 分层**：工序层与工具层各司其职

新 lessons：标 P 码 + Development/Pre/Prod/Post + 是否仅建议。
