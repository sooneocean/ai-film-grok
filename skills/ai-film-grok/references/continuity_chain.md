# Continuity Chain（长片动作串接 · 硬纪律）

> 用户铁律（2026-07-20）：长片必须建链；下镜首帧**逐字节**复用上镜已核准末帧；连接点九项核对；禁止用后期掩盖断裂。

本文件是 **agent 运行时纪律**。每部 **长片** 还必须在 film root 维护一份可写可检的：

```text
<film-root>/continuity_chain.md
```

模板见 [templates/continuity_chain.example.md](../templates/continuity_chain.example.md)。

---

## 0. 何时算「长片」（必须建链）

满足 **任一** 即视为长片，`write-spec` / `preflight` 会要求 `continuity_chain.md`：

| 条件 | 阈值 |
|---|---|
| 镜数 | **≥ 6** |
| 计划总时长 | `sum(duration_sec)` **≥ 36** |
| 显式开关 | film-spec `"long_form": true` 或 `"require_continuity_chain": true` |

短片（≤5 镜且 &lt;36s）**仍建议**建链；soft/hold 缝仍遵守末帧复用规则。

---

## 1. 四条铁律（不可协商）

### ① 长片必须建立 `continuity_chain.md`

在 `write-spec` 通过后、**批量 still/I2V 之前** 写好并维护：

- 全片动作脊柱（谁在哪、朝哪走）
- **每个连接点**（shotA → shotB）的九项核对表
- 每缝的 `chain_mode`：`continue` | `cut` | `bridge`
- 末帧 / 首帧文件路径与 **SHA-256**（continue 缝必须相等）

```bash
"$AIFILM" continuity-chain init --root "<root>"   # 从 film-spec 生成骨架
"$AIFILM" continuity-chain check --root "<root>"  # 检文件 + 字节复用 + 清单
```

### ② 下镜首帧 = 上镜已核准末帧（逐字节）

对 **`chain_mode: continue`**（以及 soft/hold 默认连续戏）的接缝：

| 必须 | 禁止 |
|---|---|
| `keyframes/shot[N+1].png` 的 **SHA-256 ==** 上镜已核准 last frame | 从 **cast / style master / 角色参考图** 重新 `image_gen` 或 `image_edit` 起跳 |
| 用 `extract-frame --which last` 抽出后 **原样 promote 为下镜 keyframe** | 先「重画一张像一点的」再当首帧 |
| I2V 的 input 就是该 keyframe（frame-1） | 用无关静图冒充连续 |

```bash
# 上镜 clip 已 register-clip 且 motion/identity 核准后：
"$AIFILM" extract-frame --root "<root>" --shot-id shot01 --which last \
  --promote-keyframe shot02
# → 写出 keyframes/shot02.png，SHA 与末帧相同，并记入 receipts/frame-chain.json
```

**语义澄清**：

- 「逐字节复用」= **下镜 I2V 的 frame-1 文件 hash = 上镜 last frame hash**。
- Grok 没有原生 first/last endpoint；用 **文件级复用** 近似。
- 若必须改构图/景别：开 **`cut` 缝**（hard join），或换 FRW first/last 后端——**不得**在 continue 缝上偷偷重绘首帧。

### ③ 每个连接点九项核对（写进 continuity_chain.md）

| # | 维度 | 问什么 |
|---|---|---|
| 1 | **姿势 pose** | 重心、躯干扭转、手脚开合是否接得上 |
| 2 | **视线 gaze** | 看向哪；下镜是否延续同一注意点 |
| 3 | **手与道具归属** | 谁拿着什么；左右手；道具不可瞬移/消失 |
| 4 | **行进方向 travel** | 屏幕左右/纵深推进方向是否同轴 |
| 5 | **镜头轴线 axis** | 180° 线是否守住；破轴须标 `axis_break` + hard |
| 6 | **发型 hair** | 长短、束法、被风吹向是否连续 |
| 7 | **服装 wardrobe** | 开合、湿干、肩带/扣件状态 |
| 8 | **天气 weather** | 雨/雾/夜空不可无故突变 |
| 9 | **光线 lighting** | 主光方向、色温、动机光是否接戏 |

任一为 **FAIL** → 该缝 **不得** `register-still` / `register-clip` 下镜；先重做或改 `cut`。

### ④ 禁止用后期掩盖断裂动作

**明确禁止**用以下手段「糊过去」：

| 禁止手段 | 为什么 |
|---|---|
| **加长 dissolve / 乱 soft xfade** | 叠化不能创造动作连续 |
| **定格 / 冻帧** 顶时长 | 假运动；loop-risk 已另拦 |
| **倒放** 接戏 | 破坏物理因果 |
| **无关插镜**（空镜、闪切道具）专门挡跳切 | 掩盖而非解决 |

### 转场与 match-cut（2026-07-20 实战）

字节复用后，**接缝已经是 match cut**。此时再叠 soft dissolve / smoothleft / hblur 会：

- 双影叠化、动作「糊一层」
- 观感比硬切 **更不顺**（像幻灯片抹奶油，不是连续戏）

| 接缝类型 | 推荐 `transition_intents` | 原因 |
|---|---|---|
| **continue + byte_identical** | **`hard`**（match cut） | 末帧=首帧，硬切最顺 |
| cut / 时间跳跃 / 破轴 | `hard` | 故意断 |
| 仅非链式、无字节复用的氛围缝 | 短 soft 0.12–0.20 | 没有 match 可切时才叠 |
| afterglow 收尾（无字节链） | `hold` 可选 | 余韵；**有字节链仍优先 hard** |

```json
"transition_intents": ["hard", "hard", "hard", "hard", "hard"],
"transition_default": "hard",
"transition_sec": 0.12
```

改 intents **只 re-final**，不必重 I2V。

允许：非链缝的短 soft；**禁止**在 byte_identical continue 缝上用 0.28+ dissolve「润色」。

### 动能流畅（字节对齐仍「一镜一顿」时）

姿势对了仍割裂，通常是 **镜尾 hold + 成片撑满 6s 播收住**。必须叠加：

1. **`cut_on: mid_motion`**：motion 禁止 `hold/idle/settle` 收尾；末帧仍在动  
2. **promote 动作中帧**：`extract-frame --which 5.2`（非 last 发呆帧）+ `out_point_sec`  
3. **`visual_fit: "vo"`**：final 按旁白长度切画面，不硬撑 `duration_sec` 槽  

完整方法栈：[lessons-2026-07-20-action-fluency.md](lessons-2026-07-20-action-fluency.md)。

---

## 2. 工作流（agent 逐步）

```
write-spec（含 start_pose/end_pose/chain_mode）
    → continuity-chain init|手写 continuity_chain.md
    → shot01 still（仅链首/cut 后可用 cast）
    → I2V → register-clip
    → extract-frame --promote-keyframe shot02   # 字节级首帧
    → 九项核对写入 chain 文件（pose…lighting）
    → I2V shot02（input = 该 keyframe，禁止另起 cast still）
    → … 串到片尾
    → continuity-chain check
    → final：**continue 缝 hard match-cut**（勿 soft soup）
```

**串行**：continue 缝上 **禁止**并行多镜 still/I2V。

---

## 3. 与 film-spec / 队列的接口

### dsl 字段（每镜）

```json
"dsl": {
  "start_pose": "...",
  "end_pose": "...",
  "chain_mode": "continue",
  "chain_from": "shot01",
  "motion": "… hold end_pose …"
}
```

### receipts/frame-chain.json（工具写入）

```json
{
  "joins": [
    {
      "from": "shot01",
      "to": "shot02",
      "mode": "continue",
      "last_frame_sha256": "…",
      "first_frame_sha256": "…",
      "byte_identical": true,
      "checklist": {
        "pose": "pass", "gaze": "pass", "hands_props": "pass",
        "travel": "pass", "axis": "pass", "hair": "pass",
        "wardrobe": "pass", "weather": "pass", "lighting": "pass"
      }
    }
  ]
}
```

`byte_identical` 必须为 true 才允许 continue 缝进入 bulk register。

### 门禁

| 检查 | 级 | 时机 |
|---|---|---|
| 长片缺 `continuity_chain.md` | **hard** | preflight / write-spec（`require_continuity_chain`） |
| continue 缝 first≠last SHA | **hard** | `continuity-chain check`；可选 register-still |
| 九项未勾或含 fail | **hard**（check --strict）/ soft | check / preflight |
| 用 dissolve 等掩盖 | **政策** | review-final motion/流畅维度 fail |

---

## 4. 不可宣称

- 未字节级复用末帧 → 不得说「动作已串接 / match cut」。
- 仅靠 xfade → 不得说「流畅成片」。
- 未建 `continuity_chain.md` 的长片 → 不得宣称正式长片交付完成。

---

## 5. 相关

- 历史复盘与 Grok 限制：[lessons-2026-07-20-frame-chain.md](lessons-2026-07-20-frame-chain.md)
- 运镜单页：[shot-motion.md](shot-motion.md)
- 轴线/cast lint：`scripts/continuity.py`
