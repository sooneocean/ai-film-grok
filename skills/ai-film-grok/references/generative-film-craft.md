# 生成式电影制作工序（想法 → 成片）

> 2026-07-21 · 与工程四层（视觉/语音/设计/FFmpeg）**正交**：本文件管**叙事与决策分层**；工具顺序见 [pipeline-methodology.md](pipeline-methodology.md)。  
> **弹性**：短片可压缩步骤，**不可跳过「前一层确认」**——故事未锁就 bulk 生成 = 漂亮但无法组装的废料。

## 一句话

把模糊想法**逐层转译**成可执行资产。每一层只减少一类模糊度；模型生成候选素材，系统控制的是 **为什么需要这颗镜头、接在哪、缺什么 Coverage、何时重生成 vs 改故事**。

---

## 总梯（逐层减模糊）

```text
想法
→ 创意命题（Concept / Premise / Logline / Theme）
→ 故事（状态变化 · 戏剧问题 · 弧线）
→ 叙事节点（Beats）
→ 剧本（Treatment · Screenplay · 四轨）
→ 声音骨架（Radio Edit）
→ 视觉设计（Visual / Character / Location Bible）
→ 分镜 · Coverage · Shot Package
→ 生成素材（T2I / I2V / TTS / BGM…）
→ Selects
→ 初剪 · 精剪
→ 声音与调色 · 字幕
→ 成片
```

| 六动词 | 中文 | 本 skill 落点 |
|---|---|---|
| **Define** | 定义意图 | Creative Brief · `director_intent` |
| **Structure** | 建立结构 | Beats · `dramatic_function` · film-spec scenes |
| **Visualize** | 视听设计 | style-bible · cast · storyboard · Lens |
| **Generate** | 生成候选 | media-queue · Seedance/Grok · TTS |
| **Select** | 选出有效片段 | register · motion QA · pilot score |
| **Edit** | 组装体验 | assemble · final · Editor’s Cut · HF |

---

## 四大制作区 ↔ 本 skill

| 区 | 回答什么 | 本 skill 产出 / 命令 |
|---|---|---|
| **1 Development** | 拍什么、为何看、情绪落点 | Creative Brief · Premise · Logline · Theme · Beat · Script → [directors-lens.md](directors-lens.md) · `director_intent` · 可选 `receipts/creative-brief.md` |
| **2 Pre-production** | 看到什么、谁一致、怎么连 | Radio Edit（`tts-rehearse`）· Visual/Character Bible（style-bible · lock-style）· Storyboard · Coverage · Shot List → `film-spec` · pilot |
| **3 Production** | 拿到真素材 | still / I2V / TTS / BGM / SFX · `media-queue` · register · 日志/manifest |
| **4 Post** | 组成片 | Selects → plate → Editor’s Cut → HF/Remotion · loudnorm · 字幕 · review-final · export |

**工程执行顺序**（工具层，与上表可并行交错）仍见 [pipeline-methodology.md](pipeline-methodology.md)：  
生成 clips 后常是 **FFmpeg plate → 设计层 → 封装**。

---

## 五锁（Lock · 软建议，用户可压缩）

| 锁 | 确认什么 | 未锁就往下的风险 |
|---|---|---|
| **Concept Lock** | 受众 · 目的 · Premise · Logline · Theme | 全片方向散、重做生成 |
| **Script Lock** | 故事 · Beats · 旁白 · 时长 | VO 与画面对不上、loop |
| **Animatic / Spec Lock** | 镜功能 · Coverage · 节奏 · 预算 · pilot | 漂亮废片、库存对不齐 |
| **Picture Lock** | 镜序 · 时长 · 结构（少再改核心画面） | 后期反复 re-I2V |
| **Master Lock** | 声 · 色 · 字幕 · QC · 导出 | 假交付 |

短片 MVP 可合并锁，但 **Concept → Spec → Generate** 三段不要倒序。

---

## Development 速查（想法 → 故事）

### Creative Brief（限制方向）

```yaml
topic: …
audience: …
format: 60s 竖屏 / 9:16
platform: [Shorts, Reels]
goal: …
emotion: { start, middle, end }
```

可落盘：`receipts/creative-brief.md` 或写入 `director_intent` + description。

### Concept · Premise · Logline · Theme

| 产物 | 作用 | film-spec |
|---|---|---|
| Concept | 独特观看角度 | logline 的前身 |
| Premise | 世界变化 + 冲突源 | theme / logline |
| Logline | 主角+事件+反应+阻碍+代价 | `director_intent.logline` |
| Theme | 真正讨论的问题 | `director_intent.theme` |

选角度四问（弹性 checklist）：**可理解 · 视觉 · 情绪 · 差异**。

### 状态变化 · 戏剧问题 · 弧线

- 开头信念/状态 → 结尾信念/状态  
- 主戏剧问题 + 次问（每段部分作答）  
- 短片可用六段时间骨架（Hook → 建立 → 揭露 → 升级 → 选择 → 余韵）  
- 三条曲线并行更佳：**信息 · 情绪 · 视觉**

---

## Beats（叙事节点）

Beat = 观众理解/情绪/期待变化的最小单位，**不是**「走一步」的空动作。

### 四项验收（软）

1. 有没有**新信息**？  
2. 有没有**状态变化**？  
3. 有没有推动**下一个问题**？  
4. 能否转成**视听证据**（可生成/可拍）？

### 与本 skill 映射

| Beat 字段 | film-spec / 实践 |
|---|---|
| purpose / new info | `dsl.story_beat` · `visible_change` |
| emotion | tone / emotional_arc / sound_plan |
| duration | `duration_sec` · VO 预算 |
| visual_evidence | still + I2V motion |
| sound_evidence | sfx / auto_sfx / VO |

一镜 ≈ 一主 Beat（或一 Beat 多 Coverage）；`dramatic_function` 是 beat 在弧上的角色。

---

## 剧本 · 四轨 · Radio Edit

剧本拆四轨，避免旁白复述画面：

```yaml
time: …
visual: […]
voiceover: […]
dialogue: null | […]
sound: […]
```

**Radio Edit 优先（弹性强推）**：先 TTS 预演/时间码骨架，再 bulk 烧 I2V。  
本 skill：`tts-rehearse` · `vo_budget` / `vo_pacing` · 禁 loop 撑字。

---

## 视觉规则 · Coverage · Shot Package

### Visual / Character Bible

= style-bible + cast masters + lookbook + 可选场景/摄影/色板笔记。  
`lock-style` 后再批量；主角 still 用 `image_edit(cast)`。

### Shot Function（镜头功能 · 软菜单）

Establish · Reveal · Action · Evidence · Reaction · Emotion · Contrast · Transition · Rhythm · Breathing · Orientation · Payoff  

映射到现有：`dramatic_function` + `dsl.camera` + motion；不必新枚举硬编码。

### Coverage 三层（软）

| 层 | 作用 |
|---|---|
| **必要** | 没它不懂故事 |
| **节奏** | 调节快慢、隐藏剪接（insert/环境） |
| **保险** | 主镜失败可替 |

同一 Beat 可备多角度；成片只用 Selects。量产时 **pilot 3 镜** = 必要 Coverage 的 canary。

### Shot Package

一镜一包：构图意图 · 参考 · motion prompt · 路由（Grok still / Seedance I2V / LTX env）· seed/日志。  
本 skill：`media-queue` job + prompt-file + endpoint 回执。

### Model Routing（已有分层）

| 层 | 主力 |
|---|---|
| 身份静帧 | Grok cast edit |
| 人物动态 | Seedance I2V |
| 环境床 | LTX T2V 等 |
| 设计字卡 | HyperFrames / Remotion |
| 旁白 | Edge TTS |

见 [lessons-2026-07-20-layer-routing.md](lessons-2026-07-20-layer-routing.md)。

---

## Production → Selects → Edit

```text
Generate variants
  → Select（identity/motion QA · register）
  → Assembly（assemble / plate）
  → Editor’s Cut（四轴 · 可 re-I2V）
  → Fine + 声色字幕（final · HF）
  → QC · export
```

| 电影用语 | 本 skill |
|---|---|
| Raw / Variants | queue complete 输出 |
| Selects | `register-still/clip` · motion QA |
| Assembly / Rough | `assemble` · `final` 技术成片 |
| Fine / Picture Lock | Editor’s Cut · re-final |
| Master | `review-final` · `export-desktop` |

Critic 角色 = `preflight` + scorecard + `director-notes`：**输出具体缺镜/重生成建议**，不无限空转。

---

## 数据链（概念 · 不必一次全实现）

```text
Beat → Shot → Generation Task → Raw → Select → Edit Event → Timeline
```

当前仓库已覆盖：film-spec shots · media-queue · manifest · mix_report · final_film。  
Beats / Coverage 矩阵可先写在 `receipts/` Markdown，成熟后再 schema。

---

## MVP（插件/短片建议路径）

不必一次跑满好莱坞工序。建议最小闭环：

```text
1. Idea → Creative Brief（或精简 director_intent）
2. Brief → Beat Sheet（dramatic_function 脊柱）
3. Beat → Coverage（必要镜 + pilot 三镜）
4. Coverage → film-spec Shot Package
5. Shot → Model Routing + Generate
6. Clips → Selects → Assembly Timeline（final）
```

输入示例（弹性字段）：

```yaml
idea: …
duration: 60
aspect_ratio: 9:16
style: …
voiceover: true
character_count: 1   # 或 2+ 由用户图/文推断
```

---

## Agent 行为纪律（与「少硬编码」一致）

1. **前层未确认，不烧 bulk 配额**（Concept/Spec 锁可合并，不可倒置）。  
2. **先 Radio/tts-rehearse 再 bulk I2V**（时长远超再改字，不硬 loop）。  
3. **Coverage 缺口用 Critic 语言写清**（缺 reaction / 缺 evidence），再 re-I2V 或改 craft。  
4. **尺度/女主人数跟用户**，本文件不钉比例。  
5. 新规则映射 **P0–P5** + 标明属于 Development / Pre / Prod / Post 哪一区。

---

## 与旧文档关系

| 文件 | 职责 |
|---|---|
| **本文件** | 电影工序 · Beat/Coverage 思想 · 四区 · 五锁 |
| [directors-lens.md](directors-lens.md) | Development→分镜 的可执行步骤 |
| [pipeline-methodology.md](pipeline-methodology.md) | 工具四层 + 工程一键顺序 |
| [editor-cut-pass.md](editor-cut-pass.md) | Post 精剪四轴 |
| [film-spec.md](film-spec.md) | 机器契约字段 |
