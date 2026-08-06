# Lessons · Director’s Lens 叙事上游（2026-07-20）

> 权威：[directors-lens.md](directors-lens.md)
> **已晋升**：稳定规则见 directors-lens.md；本档保留为踩坑时间线。

## 问题

skill 生产环从 `write-spec` / pilot / I2V 很完整，但**用户给一段文本**时，agent 容易：

1. 把原文逐句「插图化」成 still 列表；
2. 跳过叙事弧线重构，直接堆 6 镜好看帧；
3. Oscar 级 storyboard 词表（ECU、Dutch、J-cut…）与本 skill 硬约束（构图 lint、continue hard、VO 预算）脱节。

结果：成片技术门禁过了，故事仍像 PPT。

## 沉淀（可迁移）

| 项 | 做法 |
|---|---|
| **上游强制** | 任意文本/brief → 先 [directors-lens.md](directors-lens.md) Phase A–D，再写 film-spec |
| **字段映射** | 幕结构/情感地图 → `director_intent`；shot 表 → `dsl.camera` + `motion` + `visible_change` + `nar` |
| **安全词表** | ECU face → close-up + 物件主体；continue 缝永远 hard |
| **短片默认** | 6–12 镜，1–4 scene；不必硬凑 5–15 场 |
| **可选落盘** | `receipts/directors-lens.md` 给人看；机器只认 film-spec |

## 泛化映射

| 能力 | 本课实例 |
|---|---|
| **P0** | 每镜 `visible_change` 在 storyboard 阶段就写死 |
| **P4** | Show don’t tell → nar/action/motion 同一事件 |
| **P1–P3/P5** | 下游不变；Lens 不替代 lock-style / chain / HF |

## 验收

- [ ] SKILL.md 默认决策含「先 Director’s Lens、后 write-spec」
- [ ] references/directors-lens.md 存在且链到 film-spec / shot-motion
- [ ] film-spec.example 可选字段含 theme / act_structure / pace_chart 示例
- [ ] 文档测试 `test_directors_lens_docs.py` 通过

## 非目标

- 不新建独立 cinematic-storyboard skill（避免双源真相）
- 不把 Markdown storyboard 变成 write-spec 硬依赖（可选收据即可）
- 不放宽 framing / vo_budget 硬门禁
