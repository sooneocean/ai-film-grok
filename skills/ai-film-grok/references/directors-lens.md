# Director’s Lens（文本 → 故事 → Storyboard → film-spec）

> **映射**：P0 可观测变化 · P4 语义绑定 ·（下游）P1–P3 生产连续性  
> 权威入口：用户给**任意文本/brief** 开新片时，agent **必须先走本文件**，再写 `film-spec.json` / `write-spec`。  
> 禁止：把原文逐句「插图化」成 still 列表，再假装有分镜。  
> **工序位置**：Development → Pre 的可执行切片；完整 Beat/Coverage/Radio/五锁见 [generative-film-craft.md](generative-film-craft.md)。

## 一句话

先**减叙事模糊**（命题·状态变化·Beats·四轨），再用**电影语言**预演剪辑，最后落到可生产的 `film-spec`——不要故事未锁就生成。

## 与本 skill 的关系（别另起炉灶）

| Director’s Lens 产出 | 落到 ai-film-grok |
|---|---|
| 主题 / 人物弧光 / 冲突高潮 | `director_intent.logline` + `tone` + `emotional_arc`（≥3） |
| 可选：主题句、幕结构、节奏图 | `director_intent.theme` / `act_structure` / `pace_chart` / `visual_motifs`（可选字段） |
| Scene 列表 | `scenes[].title` + `summary` + 情绪/地点写进 summary |
| Shot 列表 | `scenes[].shots[]` |
| Shot 类型 | `dsl.camera.shot_size` |
| Camera angle | `dsl.camera.angle` |
| 运镜 + 表演动作 | `dsl.motion`（**主动词在前**，微动在后） |
| 一镜世界变化 | `dsl.visible_change` + `dsl.story_beat` |
| 旁白 / 潜台词 | `nar`（≤55 字；快节奏 ≤28）+ 可选 `nar_en` |
| 戏剧功能 | `dramatic_function` 枚举（见下映射表） |
| 转场 | `transition_intents` + `transition_styles`（continue 缝强制 **hard**） |
| 音效/节奏 | `sound_plan`（mood + sfx_accent / duck / mute） |
| 视觉风格 | `style-bible.json`（medium / palette / signature）——**不是**每镜散文里重复 |

**交付物顺序**（硬纪律）：

```text
用户文本
  → Phase A 故事重构（Markdown 可给用户过目）
  → Phase B 场景分解
  → Phase C rough shot list（可先 6–12 镜）
  → Phase D 精炼 storyboard 面板 → 直接写成 film-spec.json
  → write-spec → pilot → bulk …
```

中间产物建议落盘（可选但推荐）：

- `<root>/receipts/directors-lens.md` — 完整导演重构 + 节奏/情感地图  
- `<root>/film-spec.json` — **唯一**进生产的契约（本 skill 机器门禁只认它）

## 核心思维（四条，禁止跳过）

1. **先重构叙事弧线**  
   Setup → Confrontation → Resolution（短片可用压缩三幕；长片可用五幕）。  
   强调人物动机、冲突升级、高潮、情感弧光；**Show, don’t tell**。

2. **视觉优先**  
   每一段先问：「这个时刻**画面**如何最有力地传达情绪/信息？」  
   再写旁白。旁白服务画面，不是画面服务解说。

3. **动态思考**  
   静态帧 + 运镜 + 转场 = 电影语言。  
   Storyboard 是**预演剪辑与节奏**，不是装饰性画板。

4. **迭代**  
   rough（幕结构 + 场景 + 镜数）→ detailed（每镜 shot 字段齐）→ 用户反馈再改 → 才 bulk。

## 本 skill 硬约束（方法论落地时必须服从）

| 约束 | 规则 |
|---|---|
| 片长形态 | 默认竖屏短片 **6–12 镜** × 约 6s（色气骨架见 [ecchi-story.md](ecchi-story.md)）；长片 ≥6 镜 / ≥36s 走 [continuity_chain.md](continuity_chain.md) |
| 场景数 | 短片 **1–4 个 scene** 即可（不必硬凑 5–15）；长片可 5–15 |
| 旁白 | 每镜 `nar` **≤55 字**；推荐 ≤28–42；一镜一句一动作 |
| 构图 | **禁止** `extreme close-up` / `fills frame` / `push-in on face` 等裁头词 → 用 `close-up` 且保留 headroom；见 framing lint |
| ECU 改写 | 方法论里的 ECU → 本 skill 用 **close-up + 物件/局部主体**（锁、水珠、指尖），不要写 face fills frame |
| 身份 | 角色镜必须能接到 cast master；禁止每镜换服换模 |
| 连续 | continue 缝：字节复用末帧 + **hard** match-cut；禁止 dissolve 糊接戏 |
| 动态 | hook/approach/action **禁止**只有 blink+breath+push-in；须 `visible_change` |
| 色气 BGM | 默认 `rnb`；`dark` 仅恐怖 |

## Phase A — 文本分析与故事重构

对用户文本提取并**重写**（可写进 `receipts/directors-lens.md`）：

| 块 | 内容 |
|---|---|
| **Theme** | 一句话主题（可进 `director_intent.theme`） |
| **Characters** | 谁、动机、弧光（从 A 状态 → B 状态） |
| **Conflict** | 外冲突 + 内冲突 |
| **Climax** | 视觉化高潮时刻（必须能「看见」） |
| **Act structure** | Setup / Rising / Climax / Falling / Resolution（短片可合并） |
| **Show rewrite** | 把说明句改成动作、象征、潜台词 |
| **Cinematic enhance** | 可加子情节/象征/节奏起伏，**忠于原意** |

落到 `director_intent` 最小集：

```json
"director_intent": {
  "logline": "一句话卖点（≥8字）",
  "tone": "气质/语气",
  "emotional_arc": ["建立", "升温", "爆发", "余韵"],
  "theme": "可选·主题句",
  "act_structure": {
    "setup": "第一幕：世界/人物/激励事件",
    "confrontation": "第二幕：阻碍/升级/中点转折",
    "resolution": "第三幕：高潮/结尾/新常态",
    "setup_ratio": 0.20,
    "confrontation_ratio": 0.50,
    "resolution_ratio": 0.30
  },
  "pace_chart": [
    {"label": "慢燃", "start_ratio": 0.0, "end_ratio": 0.25, "cut_freq": "slow", "intensity": 3},
    {"label": "加速", "start_ratio": 0.25, "end_ratio": 0.55, "cut_freq": "medium", "intensity": 6},
    {"label": "高潮", "start_ratio": 0.55, "end_ratio": 0.80, "cut_freq": "rapid", "intensity": 9},
    {"label": "释放", "start_ratio": 0.80, "end_ratio": 1.0, "cut_freq": "slow", "intensity": 4}
  ],
  "visual_motifs": ["雨=冷静外表", "锁=私密边界"]
}
```

`act_structure_strict: true` / `pace_chart_strict: true` → write-spec 硬校验 act_structure + pace_chart 非空且结构合法。
否则为可选；`theme` / `visual_motifs` 仍不被硬校验。

## Phase B — 场景分解（Scene Breakdown）

每个 scene 必须有**目的**（推进情节 / 揭示性格 / 制造悬念 / 余韵邀请）：

| 字段（写 summary 或 scene 扩展） | 含义 |
|---|---|
| 地点 / 时间 | 时空锚 |
| 情绪基调 | 观众该感受什么 |
| 主要目的 | 本场为什么存在 |
| 关键 beats | 2–5 个可拍 beat |

短片示例（色气 1 场即可）：

```text
Scene 1 · 雨夜出租车 · 压迫→靠近→感官→余韵
  purpose: 完播钩子 + 距离阶梯
  beats: 上车 / 后视镜 / 锁骨水珠 / 落锁 / 未完成邀请
```

## Phase C — Shot-by-Shot（Frames）

每个 shot 在进入 film-spec 前，agent 内心必须填满下表（再映射到 JSON）：

| Storyboard 列 | film-spec 字段 | 备注 |
|---|---|---|
| Shot 编号 & 时长 | `id` · `duration_sec`（默认 6） | |
| Shot 类型 | `dsl.camera.shot_size` | establishing / wide / medium full / medium / close-up … |
| Camera angle | `dsl.camera.angle` | eye level / slight low / high / dutch（慎用） |
| Camera movement | 写入 `dsl.motion` 前半 | static · pan · tracking · push-in · pull-back · handheld … |
| 视觉描述 | `subject` · `action` · `environment` · `framing` | 构图：三分、负空间、前景层次 |
| 动作起止 | `start_pose` · `end_pose` · `chain_mode` · `cut_on` | continue 链必备 |
| 旁白/对白 | `nar` · 可选 `nar_en` | 说书人默认第三人称 |
| 音效提示 | `sound_plan.events` | whoosh / heartbeat / mute / duck |
| 情感/叙事作用 | `dramatic_function` + `dsl.story_beat` | 见映射表 |
| 世界变化 | `dsl.visible_change` | **P0 硬语义** |
| 转场到下镜 | 全局 `edit_craft[i]` → `transition_intents` | continue → match_cut/cut_on_action；见 [editorial-craft.md](editorial-craft.md) |

### dramatic_function 映射（方法论 beat → 本 skill 枚举）

| 叙事意图 | dramatic_function |
|---|---|
| 世界/人物登场、压迫感建立 | `hook` |
| 靠近、空间变窄、关系升温 | `approach` |
| 感官细节、触感/气味/温度 | `sensory` |
| 对方/观众代入反应 | `reaction` |
| 局势改变的身体行动 | `action` |
| 余韵、钩子、未完成 | `afterglow` |
| 时空跳转、纯过渡 | `bridge` |

节拍骨架按 `genre` 切换（详见 [beat-spines.md](beat-spines.md)）：
- `adult`（默认）：`hook → approach → sensory → reaction → action → afterglow`
- `drama`：`hook → approach → action → reaction → action → afterglow`（三幕弧）
- `mystery`：`hook → approach → sensory → reaction → action → afterglow`（信息驱动）
- `arthouse`：`hook → sensory → approach → reaction → action → afterglow`（氛围驱动）
- `documentary`：`hook → approach → sensory → reaction → action → afterglow`（事实驱动）

七值枚举不变，但语义随 genre 上下文变化（去 type-bias）。

### 剪辑语法（Phase C 后半 · 反呆板线性）

不要假设「镜号顺序 = 唯一剪辑」——用 **接缝 craft** 制造节奏：

| 想要的感觉 | craft | 备注 |
|---|---|---|
| 接戏不断 | `match_cut` / `cut_on_action` | continue 链 |
| 冲击 | `smash_cut` | action→reaction |
| 细节炸点 | `insert_cut` | 接 sensory 物件镜 |
| 连打蒙太奇 | `montage_jump` | action 连切 |
| 场内丝滑 | `soft_glue` / `whip_soft` | 勿连跑超 3 |
| 余韵 | `mood_hold` | afterglow 前 |
| 换场 | `scene_bridge` | 跨 scene |

**闪回 / 平行叙事**：在 rough shot list 里直接写成 A/B 交错顺序（A1→B1→A2…），final 不会自动重排时间轴。完整菜单：[editorial-craft.md](editorial-craft.md)。

### 角色立场（多 POV · 提高画面层次）

每镜写清 **谁的戏 + 机位语法**（write-spec 可补，导演最好先定）：

| 字段 | 例 |
|---|---|
| `focal_character` | hero / partner |
| `viewpoint` | ots → reverse → reaction_to |
| `look_axis` | left / right（正反打对翻） |

双人戏最小单元：`ots(hero)` → `reverse(partner)` → `reaction_to(hero)`。  
单主角说书：也用 reaction_to / ots 模拟「你」的立场。见 [character-stance.md](character-stance.md)。

### 景别 / 角度词表（生产安全版）

| 方法论常用 | 本 skill 推荐写法 | 避免 |
|---|---|---|
| Establishing / Wide | `wide` 或 `medium full` + 环境信息 | 角色过小难认 |
| Medium | `medium` / `medium full` | |
| Close-up | `close-up` + headroom | `extreme close-up` face fill |
| ECU 物件 | `close-up` 主体改锁/水珠/指尖 | face fills frame |
| Low angle | `slight low` / `low` | 每镜都仰 |
| High angle | `high`（脆弱/俯视） | 滥用致跳切 |
| Dutch | `dutch` 仅不安/惊悚 | 色气默认不用 |
| OTS / POV | 写进 `subject`/`framing` 文案 | |

### 运镜词表 → motion 写法

| 意图 | motion 线索（示例片段） |
|---|---|
| 沉浸 / 权力 | slow push-in … |
| 释放 / 抽离 | pull-back reveals … |
| 跟随 | pan-with / tracking alongside … |
| 紧张 | handheld micro-shake …（慎） |
| 锁定反应 | locked static, only eyes/breath … |
| 眩晕/顿悟 | dolly zoom **仅高潮 1 镜** |

**三镜防腻**：连续 3 镜 ≥2 维变化（景别 · 主动词 · 机位轴）。见 [lessons-2026-07-17-vo-motion-link.md](lessons-2026-07-17-vo-motion-link.md)。

## Phase D — Storyboard 面板 → film-spec 一镜模板

每个面板最终长这样（再序列化进 JSON）：

```markdown
### shot03 · 6s · sensory
- size/angle: close-up / eye level
- motion: water bead slides down collarbone, soft breath, micro push-in — idle not speaking
- visible_change: 水珠从锁骨静止 → 滑落一寸
- story_beat: 感官贴上来，还没碰
- nar: 后视镜里，锁骨上的水珠还没干。
- sfx: heartbeat
- join→next: soft dissolve（若 chain_mode=cut）| hard（若 continue）
```

JSON 形态对齐 [film-spec.example.json](../templates/film-spec.example.json)。

## Phase E — 转场与整体节奏

| 故事需要 | transition_intent | 典型 style |
|---|---|---|
| 震惊 / 行动断点 | `hard` | （concat，无 xfade） |
| 连续升温 | `soft` | dissolve / smoothleft / hblur … |
| 余韵停顿 | `hold` | fade / dissolve 略长 |
| **continue 字节接戏** | **永远 `hard`** | match-cut；禁止 0.28s dissolve 糊缝 |
| 声画错位感 | 依赖 `audio/mixed.wav` 连续轨 | 天然 L/J-cut；勿为 J/L 单独造假 |

节奏图（`pace_chart`）与 `emotional_arc` 对齐检查：

```text
慢燃(hook/approach) → 加速(sensory/reaction) → 爆发(action) → 释放(afterglow)
```

改转场 **只 re-final**；改运镜像素才 re-I2V。

## Phase F — 整体把控清单（write-spec 前自检）

- [ ] 色调/灯光/介质与 style-bible **一致**（P1）
- [ ] 每镜有 visible_change（P0）；hook/approach/action 非纯微动
- [ ] nar = action 主动词 = motion 首要可见运动（P4）
- [ ] 连续 3 镜景别/动词/机位不三连同款
- [ ] 无 extreme CU / fills frame 裁头词
- [ ] continue 链 start/end_pose + cut_on 写清
- [ ] transition_intents 长度 = n_shots−1；continue 缝 hard
- [ ] sound_plan.mood 合理（色气 rnb）
- [ ] 总时长粗估：镜数 × ~6s ± 转场；长片 continuity_chain 已 init

## Agent 超级流程（接到文本时照抄）

```text
1. 用 Director’s Lens 重写故事（Phase A–B），可先给用户看 Markdown 过目
2. rough shot list：先定镜数与 dramatic_function 脊柱（短片 6–12）
3. detailed：每镜填 size/angle/motion/nar/visible_change/story_beat/join
4. 写成 film-spec.json（含 director_intent 扩展字段可选）
5. "$AIFILM" write-spec --root …
6. 用户批准故事/分镜方向后：lock-style → pilot → bulk（既有纪律）
```

**用户迭代口令示例**（反馈时优先改哪一层）：

| 用户说 | 改哪里 |
|---|---|
| 更重情感象征 | Phase A motifs + 关键镜 visible_change 的象征物 |
| 更多动态运镜 | motion 机位轴；禁三连 push-in |
| 节奏太平 | pace_chart + transition_intents 加 hard 断点 |
| 不够色气 | [ecchi-story.md](ecchi-story.md) 升级清单 + 距离阶梯 |
| 像插图幻灯片 | 补 meaningful motion + mid_motion continue |

## 禁止宣称

- 只写了 Markdown storyboard、未 `write-spec` → 不得声称「已进入生产」
- 原文句句配图、无弧线重构 → 不得声称「Director’s Lens 已完成」
- 只有 HF/Remotion 字卡、无 I2V → 不得声称「电影分镜已成片」

## 相关

- [film-spec.md](film-spec.md) — 字段契约  
- [shot-motion.md](shot-motion.md) — 运镜/转场配方  
- [ecchi-story.md](ecchi-story.md) — 色气六镜骨架  
- [principles.md](principles.md) — P0–P5  
- [lessons-2026-07-20-directors-lens.md](lessons-2026-07-20-directors-lens.md) — 本次沉淀  
- [lessons-2026-07-20-meaningful-motion.md](lessons-2026-07-20-meaningful-motion.md)  
- [lessons-2026-07-20-cut-silk-bilingual.md](lessons-2026-07-20-cut-silk-bilingual.md)  
