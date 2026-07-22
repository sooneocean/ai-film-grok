# Lesson 2026-07-21 · 生成时按 first/last 帧优化（剧情实况）

> **触发原话**：卸甲后回穿；每镜从 cast 全装重起；「前面脱完后面又穿上」  
> **P 码**：P0 交付 · P1 身份 · P2 时空连续  
> **互补**：  
> - [keyframe-first-state-index](keyframe-first-state-index.md) · 状态照 → keyframe → I2V  
> - [sex-undress-ladder](lessons-2026-07-21-sex-undress-ladder.md) · 卸装不回穿  
> - [continuity_chain](continuity_chain.md) · 字节级末帧→首帧  
> - [lessons-2026-07-20-frame-chain](lessons-2026-07-20-frame-chain.md)

---

## 失败解剖

| 用户感受 | 工程事实 | 根因 |
|---|---|---|
| 衣服脱了又穿上 | 每镜 still 从 cast master 全装 `image_edit` | **没用上镜 last frame 当本镜 first** |
| 姿势跳 | 新静帧重新摆 pose | 生成未串行；I2V 输入与上镜末帧无关 |
| 剧情断 | 旁白在办事，画面又全装 | 状态字段写 bare，**像素仍是 full** |

**一句话**：生成优化必须以 **剧情里已经发生的像素**（上镜 last = 下镜 first）为准，不是以定妆图为准。

---

## 生成协议（必触发）

```text
shot[i] still  →  I2V  →  register-clip(approved)
                              │
                              ▼ auto (default on heat max / undress / continue)
                    extract last frame
                              │
                              ▼ byte copy
                    keyframes/shot[i+1].png  ==  first frame of next I2V
                              │
                              ▼
                    下镜 I2V 只吃该 keyframe；禁 cast 全装重起
```

### Agent 硬规矩

1. **串行**：continue / 卸装链 **禁止**并行多镜 still+I2V  
2. **register-clip 后**：工具自动 `auto_promote_next`（见 manifest / emit）  
3. **下镜 I2V 输入** = `keyframes/<next>.png`（promoted），**不是** `canonical/cast/*`  
4. 若必须改景别：标 `chain_mode: cut` 才允许新 still；**衣着仍不得回穿**  
5. 微修姿势：只对 **promoted 帧** `image_edit`，prompt 含 `Costume continuity HARD`  

### 按实际 first/last 优化 prompt

| 看到 last frame… | 下一镜 I2V prompt 应… |
|---|---|
| 衬衫已开、短裤还在 | 从 half-undress 继续脱/动作，禁「full wardrobe」 |
| 已趴桌、已脱 | 从 bent/undressed 起手，写 visible_change 相对上一末帧 |
| 哭脸特写 | 接戏同脸同泪痕，别重置妆发 |

---

## 工具契约

| 命令 | 行为 |
|---|---|
| `register-clip --status approved` | 若规则命中 → 自动抽 last → promote 下镜 keyframe + `receipts/frame-chain.json` |
| `extract-frame --promote-keyframe` | 手动能；与 auto 同语义 |
| film-spec `auto_promote_next: false` | 显式关闭（默认开：max/hot/undress/continue） |

`should_auto_promote_next` 命中：

- `chain_mode` ∈ continue|hold|soft  
- 或 prev/next `wardrobe_state` ≥ partial  
- 或 `heat_scale` ∈ max|hot（默认串行）  
- 排除：`chain_mode` ∈ cut|bridge  

---

## 验收

```bash
# register 后应见
# auto_promote_next.ok true · next_keyframe=… · byte_identical true
"$AIFILM" register-clip --root … --shot-id shot03 … --status approved …

# 下镜 I2V 输入 hash == 上镜 last
shasum keyframes/shot04.png keyframes/_last_shot03.png
```

pytest：`tests/test_frame_promote.py`（若有）· continuity_chain helpers。
