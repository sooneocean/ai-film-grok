# 片例库（Case Study Library）

> 2026-07-22 · 结构化经验沉淀：记录**什么有效**，不只是踩了什么坑。
> 与 `references/lessons-*.md`（踩坑日记）互补——后者管「别再犯」，本目录管「值得复用」。

## 为什么需要片例库

lessons 是按日期 + 问题索引的——适合查「这个 bug 怎么修」，不适合查「同类型题材该怎么拍」。
导演学的是 case study：某场戏的组合为什么有效、某条 P0–P5 在实际成片里起了什么作用、
受众反馈验证了哪个节奏假设。本目录把经验从「日期流水」升级为「可检索的片型知识」。

## 目录结构

每部成片一个子目录，命名 `<日期>-<片名简称>/`：

```text
memory/case-study/
├── README.md                    ← 本文件（框架说明）
├── 2026-07-22-雨夜后座/
│   ├── overview.md             ← logline / 受众 / 片长 / 风格 / heat_scale
│   ├── decisions.md            ← 关键导演决策 + 对应 P0–P5
│   ├── results.md              ← 成片 hash / 七维 review / 受众反馈（如有）
│   └── takeaways.md           ← 复盘：什么有效 / 什么会改 / 可迁移结论
└── _template/
    └── overview.md             ← 新片例模板
```

## overview.md 字段

```yaml
title: 雨夜后座
logline: 一句话命题
audience: 完播优先的短视频观众
duration_sec: 42
aspect_ratio: "9:16"
style: anime / photoreal / …
heat_scale: max | normal | none
tts_backend: edge
i2v_provider: grok
final_hash: <final_film sha256>
date: 2026-07-22
```

## decisions.md 字段

| 决策 | 内容 | 对应能力 | 效果（成片验证） |
|------|------|----------|------------------|
| 后视镜 OTS 代替直接正反打 | 用偷窥视角制造距离感 | P2 时空 / P3 动能 | 完播率 ↑（如有数据） |
| 锁骨水珠 insert 替台词 | 感官物件代替说明 | P0 可观测变化 / P4 语义 | 观众反馈「有感觉」 |
| 旁白第三人称 + BGM duck | 保距离感不失控 | P4 语义 / P5 分层 | — |

## results.md 字段

- `final_film` sha256 + 导出路径
- 七维 review-final 分数（identity/style/motion/escalation/audio/subs/dead_air）
- screening_evidence 时间点
- 受众反馈（如有完播率/评论/点赞）——没有就标 `未采集`

## takeaways.md 字段

- **什么有效**：可复用的组合（不是单条规则，是组合）
- **什么会改**：如果重拍，换什么
- **可迁移结论**：换题材时哪些结论成立、哪些是题材绑定的

## 与 lessons 的关系

| | lessons-*.md | case-study/ |
|---|---|---|
| 索引 | 日期 + 问题 | 片名 + 题材 |
| 回答 | 别再犯什么 | 值得复用什么 |
| 粒度 | 单条规则 | 一部片的决策组合 |
| 晋升 | lessons → references 稳定 | case-study → references 的题材 playbook |
