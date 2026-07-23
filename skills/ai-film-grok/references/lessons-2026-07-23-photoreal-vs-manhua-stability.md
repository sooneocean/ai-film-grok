# Lesson 2026-07-23 · 写实不稳 vs 漫剧质感（介质选择）

> **触发原话**：「这个画风的人物稳定性很差啊 漫剧生成的视频质感好很多 原因是什么？」  
> **P 码**：**P0 叙事/介质路由** · Idea → Visualize  
> **片例**：街角重逢写实成片 vs 用户对漫剧管线观感  
> **落地**：[style-lock-from-ref](lessons-2026-07-23-style-lock-from-ref.md) · [face-identity-pixel](lessons-2026-07-23-face-identity-pixel.md)

---

## 一句话（给文科用户）

```text
写实 = 每帧都要画成「真人照片」→ 模型稍偏就像换演员
漫剧 = 用同一套简笔画规则画角色 → 偏一点仍像同一个人
要稳，先换「颜料」（medium），不是只加一句「锁脸」
```

---

## 决策表（Agent 默认）

| 用户信号 | 默认 medium | 说明 |
|---|---|---|
| 漫剧 / 竖屏漫 / 稳 / 一致 / 质感好 | **manhua** | 首选 |
| 二次元 / 番 / anime | **anime** | |
| 半写实 / 插画电影感 | **semi_real** | 折中 |
| 明确「真人」「写实电影」「实拍感」 | **photoreal** | 须 style-lock + face-identity + 严 pilot |

**禁止**：无确认把都市言情默认成 photoreal bulk。

---

## 工程含义

1. medium 写进 `style_fingerprint`，prompt 带 `MEDIUM LOCK`  
2. photoreal 时 face-identity audit **允许且应当**出现 FAIL → 修 still  
3. 同剧情可做 **manhua 对照 pilot** 再让用户选介质  
4. 稳定性差时的第一反应：**改 medium 或重做 still**，不是加长 I2V prompt  

---

## 与八环位置

```text
Idea/Story 已定
  → 介质路由（本课）      ← 别拖到 Media 才发现
  → style-lock + cast
  → face-identity
  → Beats/Shots/Media
```
