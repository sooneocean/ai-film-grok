# Lesson 2026-07-23 · 输入图画风锁 · Style Lock from Ref

> **触发原话**：  
> 「这个画风的人物稳定性很差啊 漫剧生成的视频质感好很多 原因是什么？」  
> 「思考如果是你如何优化锁定输入图的画风 帮我优化 plugins＋skills」  
> **P 码**：**P0 画风/身份** · Define → Visualize  
> **片例**：`lushiran-reunion-ep01`（角色表 → photoreal 街角戏）  
> **代码**：`scripts/style_lock.py` · CLI `aifilm style-lock *` · `lock-style --from-plan/--medium`  
> **互补**：[face-identity-pixel](lessons-2026-07-23-face-identity-pixel.md) · [consistency §1a](consistency.md) · [shaofu-cast](lessons-2026-07-22-shaofu-cast-subs-bgm-final.md)

---

## 一句话

```text
先锁 medium（manhua/anime 稳，photoreal 漂）→ 再锁脸
整页角色表只裁 face-lock；cast master 9:16 用 image_edit
每镜 prompt 必须带 MEDIUM LOCK + cast_locks
```

---

## 根因（为何漫剧更稳）

| 因素 | 写实 photoreal | 漫剧 manhua / anime |
|---|---|---|
| 人脸自由度 | 骨相/毛孔/眼神光，一抖=换人 | 符号化脸型，漂了仍像同人设 |
| 生成路径 | 一镜一静帧 + I2V，脸重画 N 次 | 同线稿/色块公式，全片一致 |
| 参考图 | 礼服设定表 → 工装夜戏，妆造落差大 | 人设与戏服常在同一画风 |
| 双人同框 | 两张脸同时漂 | 同一套笔触更容易一起稳 |

**不是**「Grok 一定差」；是 **同一套一镜一 I2V 管线，介质越写实，身份越难锁**。

---

## 硬规则（S0–S7）

| # | 规则 | 要求 |
|---|---|---|
| **S0 Medium 先锁** | 四选一：`anime` / `manhua` / `semi_real` / `photoreal` → `style_fingerprint` |
| **S1 输入图 plan** | 有用户图 → `aifilm style-lock plan --ref`（裁 face-lock + plan JSON） |
| **S2 禁止 sheet 当 9:16 脸** | 整页设定表只裁 FRONT/脸；master 必须 image_edit 出 9:16 |
| **S3 稳优先默认 manhua** | 用户说「漫剧/稳/一致/质感」→ **默认 manhua**，禁止无确认 photoreal bulk |
| **S4 photoreal 明示低稳** | bulk 前 soft warn；pilot 严拒；配合 face-identity audit |
| **S5 prompt 前缀** | `MEDIUM LOCK` + `cast_locks`（prompt_injector / `style-lock prompt`） |
| **S6 像素路径** | 有角色 still → 只 `image_edit(cast\|face-lock\|已过审 still)` |
| **S7 face-identity** | enroll-bible + audit；见 [face-identity-pixel](lessons-2026-07-23-face-identity-pixel.md) |

### medium 稳定性

| medium | stability | 何时用 |
|---|---|---|
| manhua | high | 竖屏漫剧、用户要稳 |
| anime | high | 二次元明确 |
| semi_real | medium | 要电影光但怕写实漂 |
| photoreal | low | 用户**明确**要真人电影感 |

---

## CLI 工序

```bash
aifilm style-lock recommend --goal "要稳定像漫剧"
# → manhua

aifilm style-lock plan --root "$ROOT" --ref sheet.png \
  --char-id lushiran --name "陆时冉" --medium manhua \
  --face-notes "…" --hair "…" --wardrobe "…"

aifilm style-lock apply --root "$ROOT"
# Agent：image_edit(face-lock) → 9:16 cast master

aifilm lock-style --root "$ROOT" --from-plan \
  --canonical style-v1.png \
  --cast-master canonical/cast/lushiran-master.png \
  --char-id lushiran --medium manhua

aifilm style-lock check --root "$ROOT"
aifilm style-lock prompt --root "$ROOT" --cast lushiran
```

### 产出

| 路径 | 内容 |
|---|---|
| `receipts/style-lock-plan.json` | medium、fingerprint、cast_locks、agent 前缀、face crops |
| `style-bible.json` | apply 后写入 fingerprint / cast_locks / signature |
| `receipts/style-lock.json` | lock-style 后回执 |
| `canonical/cast/*-face-lock-*.png` | 启发式裁脸（须目视复核） |

---

## Agent 开片固定序（更新）

```text
init
  → style-lock recommend（若用户要稳）
  → style-lock plan --ref（有用户图）
  → apply
  → image_edit 出 cast master（禁纯 gen 绕脸）
  → lock-style --from-plan
  → face-identity enroll-bible
  → write-spec / pilot
  → face-identity audit
  → 用户 pilot 批准 → bulk
```

---

## 禁止

- 默认 photoreal bulk「看起来高级」  
- 整页 character sheet 直接当 style-v1 或 I2V 输入  
- 散文 identity 代替 `cast_locks.identity_lock_tokens`  
- 中途 medium 从 manhua 漂回 photoreal 而不 re-lock  

---

## 验收

- [ ] `style_fingerprint.medium_key` 存在  
- [ ] `cast_locks.<id>` 非空  
- [ ] write-spec 后 prompt 含 `MEDIUM LOCK`  
- [ ] `pytest tests/test_style_lock.py` 绿  
- [ ] photoreal 时 style-lock check 有 low-stability soft  

---

## 片例摘要（街角重逢）

| 项 | 内容 |
|---|---|
| 输入 | 用户粉色礼服角色表 |
| 误用风险 | 直接 photoreal + 工装戏 → 脸漂 |
| 纠偏 | face 重锁 master；style-lock manhua 可选；face-identity 暴露 keyframe FAIL |
| 工程副产品 | `render_final` shot_targets KeyError 已修；continuity `require_continuity` def 已修 |
