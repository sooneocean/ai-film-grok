# Editor’s Cut Pass（剪辑师过片 · 规划与剪辑拆开）

> 映射 **P3 动能 · P4 语义 · P5 分层**  
> 案例：[`lessons-2026-07-20-editor-cut-ecchi-scale.md`](lessons-2026-07-20-editor-cut-ecchi-scale.md)（《薇薇安·夜锁》用户验收后沉淀）

## 一句话

**生成规划是导演+摄影；成片前必须再换「剪辑师」帽子。**  
两套逻辑拆开：先把戏拍够，再按画面 / 动作 / 声音 / 剧情做全方位优化——**禁止**把第一次 `final` 当最终艺术交付。

## 两阶段（硬纪律）

| 阶段 | 角色 | 负责 | 禁止 |
|---|---|---|---|
| **A · Production Plan** | 导演 / 摄影 | Director’s Lens · film-spec · still · I2V · register | 边拍边当剪辑「凑合能拼」；用设计后期掩盖无戏镜 |
| **B · Editor’s Cut** | 剪辑师 | 看完整 inventory 后重切节奏 · 改 craft · 改 VO 贴点 · 点 SFX · 点名 re-I2V 弱镜 · 再 final | 只 re-final 不审片；只加 dissolve 装流畅 |

```text
Director’s Lens → write-spec → pilot → bulk still/I2V
  → 【阶段 A 完成：inventory 齐】
  → Editor’s Cut Pass（本文件）
  → re-final（ffmpeg plate ± hyperframes）
  → review-final → export
```

## 何时强制跑 Editor’s Cut

满足任一：

1. 用户明确要求「过了 / 成片」之前的最后一关  
2. 成片时长偏离 brief ≥15%（例：目标 60s 实际 46s）  
3. scorecard 任一维 borderline / 用户说「尺度不够 / 腻 / 平」  
4. 有 ≥2 镜 `motion_score < 5` 或 I2V 曾 moderation 软化  
5. 色气题材 `heat_scale` ≥ `hot`（默认成人漫剧）

**Agent 默认**：clips 齐后、`final` 交付前，至少做一轮 **Editor Cut 清单**（可落盘 `receipts/editor-cut.md`），再 render。

## 剪辑师四轴清单（必须逐轴打勾）

落盘建议：`receipts/editor-cut.md`  
**2026-07-21**：资深蒙太奇 + 重口男向 → 必写「蒙太奇设计」块；见 [lessons-2026-07-21-montage-hardcore-male.md](lessons-2026-07-21-montage-hardcore-male.md)。

### 0. 蒙太奇设计（Montage Plan · 新增必填）

- [ ] 节奏图：慢→加速→峰值→释放（秒级）  
- [ ] `edit_craft` **≥4 种**不同 craft；**禁止**全 `cut_on_action` / 全 soft  
- [ ] 60s 级：insert_cut **≥2** · smash_cut **≥1** · montage_jump **≥1 段**  
- [ ] 景别峰谷：远/中/贴/插跳变（禁 5 镜同 MCU）  
- [ ] 声画：峰值前 duck；落锁/解扣/床响 SFX 点名  

### 0b. 景别情绪堆叠（Size Ladder · 2026-07-21）

- [ ] 写出每镜 `shot_size` 阶梯表（L0 全景 → L4 局部）  
- [ ] 配额：宽≥1 · 中≥2 · 近≥2 · 局部特写≥2  
- [ ] act→climax **单调收紧**（不突然退回全景演办事）  
- [ ] 运镜与景别匹配（特写少乱晃；全景不裁头 push-in）  
- [ ] 详课：[lessons-2026-07-21-size-ladder-hardcore-stack.md](lessons-2026-07-21-size-ladder-hardcore-stack.md)  


### 1. 画面（Picture）

- [ ] 景别节奏：远→中→贴→插→全 是否有峰谷（禁 5 镜同 MCU）  
- [ ] 弱镜：身份漂 / 死气 / 审核软化 / **角落 shot 水印** → **re-still + re-I2V**，不靠字卡遮  
- [ ] 插镜机会：扣子、门锁、床单指节、锁骨汗、膝锁（insert_cut）是否落在高潮前  
- [ ] 片头/字幕：plate-cards blank + 设计后期只画一次  

### 2. 动作（Action / Motion）

- [ ] 每个 hook/approach/action：主动词是否可闭眼猜出  
- [ ] act/climax：**狠动词** sink/grind/lock/yank（禁 soft lean 当主句）  
- [ ] `motion_score < 5` → 强制 re-I2V（更狠动词：snap/yank/sink/lock）  
- [ ] continue 缝：是否 byte promote；硬切在 mid_motion  
- [ ] 高潮镜（办事完成）：必须有 **身体主动作**（沉腰/锁腿/攥床单），禁止只靠 blink  

### 3. 声音（Sound）

- [ ] VO：hook/高潮/收束金句是否够狠；**重口男向**身体动词说满；拖腔禁 atempo≪1  
- [ ] BGM：色气默认 rnb；高潮段是否 duck 更深 / seed 可换 take  
- [ ] SFX：落锁 whoosh/click、解扣 metal、床垫 soft thump、心跳 sensory——写进 `sound_plan.events` 或靠 auto_sfx 后人工加  
- [ ] mixed.wav 优先；禁 I2V 静音轨当终声  

### 4. 剧情（Story / Escalation）

- [ ] 起承转合是否可口述 15 秒电梯稿  
- [ ] **看点**（权力差 / 性格翻转 / 金句）与 **刺激点**（距离阶梯 / 服装失序 / 办事完成）是否双线都到顶  
- [ ] **尺度**：用户「重口/男向」→ `heat_scale:max` + 亲密核 **≥70%** 片长目标；setup **≤2 镜**；act **≥4** + climax **≥2**（60s/10 镜）  
- [ ] **女主**：single 勿强加 dual；multi 才查 focal/dual  

- [ ] afterglow 是否钩子未完（禁说教）  
- [ ] 若目标时长不足：优先 **加 act/climax 镜**（第二高潮拍 / 感官 insert），禁止 loop  


## 可改什么 · 改法路由

| 问题 | 只改什么 | 命令/动作 |
|---|---|---|
| 节奏平、转场无趣 | craft / intents / styles / transition_sec | 改 film-spec → **只 re-final** |
| 旁白不够色 / 不对点 | `nar` / `nar_en` / vo_rate | 改 spec → tts-rehearse → re-final |
| 某镜动作死 | motion prompt + still | re-I2V → re-register → re-final |
| 尺度不够 | heat_scale 升档 + 重写距离阶梯镜 | 见 [ecchi-story.md](ecchi-story.md) §最大尺度 |
| 时长差 15%+ | 加镜或升 10s 镜 | write-spec + 新 still/I2V |
| 接戏跳 | promote 字节链 | extract-frame → re-I2V 下游 |

**禁止**：用更长 dissolve / Ken Burns / 定格 假装剪辑优化。

## 与设计后期的边界（P5）

| Editor’s Cut | HyperFrames/Remotion |
|---|---|
| 决定镜序语义、哪镜重拍、VO/SFX 点位 | 只做字幕/片头/统一 grade/观感胶水 |
| 可触发 re-I2V | **不能**替代 re-I2V |
| 产出 `receipts/editor-cut.md` | 产出 compose package |

先 Editor’s Cut 决策 → 再 `final --post-engine hyperframes`。

## 最小收据模板

```markdown
# Editor’s Cut · <title>
Date:
Heat scale:
Target duration / Actual plate:

## 四轴
- Picture: pass|fail — …
- Action: pass|fail — …
- Sound: pass|fail — …
- Story: pass|fail — …

## 变更清单
1. re-I2V: shotXX — reason
2. nar rewrite: shotYY
3. craft: join N → smash_cut
4. add shot: …

## 再 final
- command: …
- expected duration:
```

## 相关

- [editorial-craft.md](editorial-craft.md) — 接缝 craft 菜单  
- [ecchi-story.md](ecchi-story.md) — 色气最大尺度  
- [postproduction.md](postproduction.md) — final 管线  
- [principles.md](principles.md) — P3–P5  
