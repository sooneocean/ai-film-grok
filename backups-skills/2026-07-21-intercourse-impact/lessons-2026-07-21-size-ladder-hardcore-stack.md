# Lesson 2026-07-21 · 景别情绪堆叠 + 成人剧情再升级（未注意的部分）

> **片例**：`velvet-stage-dual`  
> **用户原话**：  
> 「剧情尺度还是太小…需要更加成人的剧情跟镜头…从全景到中景到近景到特写的情绪堆叠分镜运镜剪辑技巧…优化 skill 没注意到的部分」  
> **P 码**：P0 · P3 · P4 ·（与蒙太奇课互补）  
> **互补**：[montage-hardcore-male](lessons-2026-07-21-montage-hardcore-male.md) 管 craft/镜比；**本课管景别阶梯 + 剧情升级设计**  

## 之前 skill「没钉死」的缺口

| 缺口 | 旧状态 | 后果 |
|---|---|---|
| **景别只按 beat 默认** | hook→MF / action→MF 表 | 连续 5–8 镜都是 **medium**，无「越来越近」的压迫感 |
| **无情绪堆叠验收** | 只禁 SIZE_FLAT 三连 | 全片无 **WS→MS→CU→ECU 单向加压** 设计 |
| **运镜与景别脱节** | camera_axis 轮换独立 | 全景却 push-in 裁头；特写却 orbit 乱晃 |
| **成人剧情仍「舞台暧昧」** | heat max 写了 | 缺 **权力仪式→失序→办事完成** 的**可见剧情动词**；镜在「抱」不在「办」 |
| **coverage 缺「加压链」** | 有单镜 shot_size | 无 **escalation chain** 字段/清单 |
| **insert 当补丁** | 有 insert 但孤立 | insert 不在「景别堆叠」的阶梯上，像乱插广告 |

**抽象**：  
观众感到「尺度小」= **景别不收紧 + 剧情动词不够荤 + 剪辑不加压**。三者要同一条弧。

---

## R-S · 景别情绪堆叠（Size Ladder）

### S0 一句话

**成人 60s 必须设计一条「越来越近」的压迫链**：  
`全景/大全 → 中全 → 中景 → 近景 → 特写/局部`，在 **act→climax** 顶到最近；afterglow 可略松，但**禁止**全程中景横跳。

### S1 竖屏景别枚举（film-spec `dsl.camera.shot_size`）

| 级 | shot_size 写法 | 白话 | 成人用途 |
|---|---|---|---|
| L0 | `wide` / `medium full`（偏宽） | 全景·大全 | 台口/空间权力/双人入画 |
| L1 | `medium full` | 中全（头到膝/脚） | 走近、推坐、跨坐起势 |
| L2 | `medium` | 中景（腰上） | 贴身、解衣、主导 |
| L3 | `close-up` | 近景（头肩/胸） | 喘、眼神、权力翻转 |
| L4 | `close-up` 物件 / 局部 | 特写（手/锁/腿/指） | insert 加压（**禁 face fills frame 裁头**） |

> 本 skill framing：**禁止** `extreme close-up` 填脸裁头；L4 用 **物件/肢体局部** 特写，脸 CU 保留 headroom。

### S2 60s 成人强制阶梯（Selects 验收）

对成片 **8–12 镜** 必须能勾：

| 阶梯检查 | 最低要求 |
|---|---|
| 至少 1 镜 L0/L1 宽 | 建立空间（台/厢/床） |
| 至少 2 镜 L2 中景 | 身体关系可读 |
| 至少 2 镜 L3 近景 | 情绪/喘/反应 |
| 至少 2 镜 L4 局部特写 | 锁/手/腿/布（insert） |
| **act→climax 段** | 连续镜的「最近级」**单调不减**（可跳级收紧，禁止突然退回全景再演办事） |
| 连续 3 镜同 size | **fail** `SIZE_STACK_FLAT`（比旧 SIZE_FLAT 更严：成人片） |

### S3 情绪堆叠时间表（与 heat_phase 对齐）

```text
setup     : L0/L1 为主（空间压迫）
foreplay  : L1→L2→L3（距离收紧）
act       : L2/L1 动作为主 + L4 insert 打断加压
climax    : L3 脸/反应 + 可选 L4 攥布
afterglow : L3 耳语/对视（可略松一级）
```

**运镜绑定**：

| 景别级 | 允许 camera_axis | 禁止 |
|---|---|---|
| L0 宽 | pan / locked / slow dolly | 脸 push-in 裁头 |
| L2 中 | dolly_in / pan_with / orbit_soft | 无动作的空 push |
| L3 近 | static_hold / slight push stop | 大 orbit 晃脸 |
| L4 特写 | locked / ecu_hold | 乱甩、变焦抽风 |

### S4 film-spec / Editor 必写

每镜 `dsl.camera.shot_size` **显式**；Editor’s Cut 增加：

```markdown
## 景别堆叠（Size Ladder）
| 序 | id | size | phase | 是否加压 |
| 1 | shot01 | medium full | setup | 建立 |
| … | … | close-up 物件 | act | insert 加压 |
- 链：MF → CU闩 → M失序 → … → CU脸
- 验收：L0≥1 L2≥2 L3≥2 L4≥2；act 段无回退全景
```

---

## R-H2 · 成人剧情再升级（比「max」更可执行）

### H2-0 用户再说「尺度还是太小」时

不要只改 VO 形容词——必须 **三件套**：

1. **剧情动词升级**（权力+办事）  
2. **景别堆叠**（S2）  
3. **镜头内容**（跨坐/沉腰/锁腿/办完反应 ≥ 库存可见）

### H2-1 剧情节拍（重口 60s 必见）

| 节拍 | 必须看见 | 禁止用什么冒充 |
|---|---|---|
| 边界关闭 | 落锁/关门/帘合 | 只对视 |
| 失序 | 外套/肩带/裙摆明显位移 | 只脸红 |
| 主导确立 | 谁骑/谁压/谁锁腕 | 双人并排站 |
| 办事进行 | 沉腰/顶撞节奏 **可见**（姿态） | soft lean 当主句 |
| 完成 | 腿软/失声/攥布/余颤 | 只微笑 |
| 钩子 | 「下一场换你」类未完 | 说教/晚安 |

### H2-2 分镜库存设计（没注意到的）

| 旧习惯 | 新要求 |
|---|---|
| 先拍 10 镜「好看站姿」 | 先写 **Size Ladder + heat 节拍表**，再生成 |
| 双人永远同景别双人入画 | 同一 beat 准备 **宽关系镜 + 近反应镜 + 局部 insert** 三选 |
| 特写=脸 | 成人特写优先 **手/腰/腿/锁/布**，脸留给 climax/reaction |
| 剪辑时再想景别 | write-spec 前 Director’s Lens 就要标 size |

### H2-3 VO 与画面同动词

`nar` 的动词必须在 `dsl.action` / `motion` 里看见：  
说「沉腰」→ 画面必须 sink；说「锁」→ 画面 lock。  
禁止：画面只拥抱，VO 说办事完成（假重口）。

---

## Agent 执行清单（补洞）

```text
Define/Structure
  [ ] 画 Size Ladder 表（每镜 size + phase）
  [ ] 画重口节拍表（边界/失序/主导/进行/完成/钩子）

Visualize
  [ ] still 按 size 生成；L4 简化构图（防首帧毒化）
  [ ] 同 beat 至少准备 1 关系镜 + 1 加压 insert

Generate
  [ ] motion 跟 size 匹配；L3/L4 少乱晃
  [ ] F2 结构 QA + 发色 + 零工程字

Select/Edit
  [ ] selects 满足 S2 四级景别配额
  [ ] craft 蒙太奇 + size 阶梯同时过
  [ ] 用户「尺度小」→ 查三件套，不单改字幕
```

## 反例 / 正例

| 反例 | 正例 |
|---|---|
| 10 镜全是 medium 双人抱 | MF 台口→CU 闩→M 解衣→MF 跨坐→CU 手→M 沉腰→CU 失神 |
| 特写全是脸 | 加压用 闩/指/腿；完成才给 CU 脸 |
| 全景里演 climax | climax 前已收到 L2/L3；完成用 L3+L4 |
| 只加荤 VO | VO + 景别收紧 + 办事姿态三对齐 |

## 关联

- [shot-motion.md](shot-motion.md) §2 覆盖表 → 改为阶梯优先  
- [ecchi-story.md](ecchi-story.md) 重口男向  
- [editorial-craft.md](editorial-craft.md) · [editor-cut-pass.md](editor-cut-pass.md)  
- [lessons-2026-07-21-keyframe-first-frame-poison.md](lessons-2026-07-21-keyframe-first-frame-poison.md)（L4 特写尤要结构干净）  
