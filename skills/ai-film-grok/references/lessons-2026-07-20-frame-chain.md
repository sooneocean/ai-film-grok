# 镜间动作串接（Frame Chain · 2026-07-20）

**触发失败**：戏服玩心夜 / 用户反馈「画面流畅度不够；first–last frames 逻辑没做到，动作没有串起来」。

## 根因（不是 xfade 能救的）

| 层 | 现状 | 后果 |
|---|---|---|
| **Grok I2V** | 只有 **frame-1** 起点（`motion_first_last: false`） | 无法原生 lock 上镜末帧 → 下镜首帧 |
| **旧 skill** | 每镜 still 都从 **cast master 平行重画** | 姿势/重心/手位每镜重置 → 像幻灯片 |
| **旧 skill** | 只写镜内 `dsl.motion` + final **xfade** | 叠化遮住跳切，**不能**造动作连贯 |
| **旧 skill** | continuity lint 只查 cast / 景别 / 轴线 | **不查 end_pose → start_pose** |

类比：xfade 像两张照片之间抹奶油；frame-chain 是要求 **上一张的结束姿势 = 下一张的开始姿势**。

## 产品规则（升级为 Continuity Chain 铁律）

**权威全文**：[continuity_chain.md](continuity_chain.md)。本页保留操作摘要。

Grok **没有**真·first/last-frame endpoint。用 **文件级字节复用** 近似：

```
still[i] / keyframe[i]
   ↓ image_to_video  （motion → end hold）
clip[i]  (register-clip 核准)
   ↓ extract-frame --which last --promote-keyframe shot[i+1]
keyframes/shot[i+1].png   ===  逐字节 ==  上镜 last frame
   ↓ image_to_video（input 仅此文件；禁止 cast 重起）
clip[i+1]
```

### 硬纪律（四条）

1. **长片**（≥6 镜 / ≥36s / `long_form`）必须维护 **`continuity_chain.md`**。
2. **continue 缝**：下镜首帧 **SHA ==** 上镜已核准末帧；**禁止**从角色参考/cast 起跳。
3. **连接点九项**：pose · gaze · hands_props · travel · axis · hair · wardrobe · weather · lighting。
4. **禁止掩盖**：加长 dissolve、定格、倒放、无关插镜挡跳切。

另：I2V 串行；motion = start→主动作→end hold；短 soft xfade 仅 pose 接上后润色。

## film-spec 字段（每镜 `dsl`）

```json
"dsl": {
  "action": "hand turns door latch shut",
  "start_pose": "side profile at door, fingers on latch, body weight on near leg",
  "end_pose": "latch fully shut, hand lowering, half-step into room, look toward vanity",
  "chain_mode": "continue",
  "chain_from": "shot01",
  "motion": "fingers turn latch shut, hand lowers, half-step in, hold end_pose, then soft breath, idle not speaking"
}
```

| 字段 | 含义 |
|---|---|
| `start_pose` | 本镜 **关键帧 / I2V 第 1 帧** 应呈现的姿势（英文短句） |
| `end_pose` | 本镜 **I2V 结束 hold** 应停住的姿势；= 下镜 `start_pose` 的输入 |
| `chain_mode` | `continue`（默认，soft/hold）· `cut`（hard）· `bridge`（转场镜） |
| `chain_from` | 可选，显式上镜 id |

**衔接检验（agent 自检）**：读 `shot[i].end_pose` 与 `shot[i+1].start_pose`，闭眼应像同一动作的两段，不是两张定妆照。

## 生成步骤（agent 必做）

```bash
# 1) 写满 start_pose / end_pose / chain_mode 后
"$AIFILM" write-spec --root "<root>"
# 看 _frame_chain：soft 缝缺 pose → FRAME_CHAIN_GAP

# 2) 仅 shot01（或 hard 后的第一镜）可用 cast 作主锚
# image_edit(cast) → keyframes/shot01.png → I2V → clips/shot01.mp4

# 3) 抽末帧作下镜种子
"$AIFILM" extract-frame --root "<root>" --shot-id shot01 --which last \
  --out "<root>/keyframes/shot02-seed.png"

# 4) still02 = image_edit(seed 第一 + cast 第二)，prompt 只写「从 seed 姿势继续到 start_pose/action」
# 禁止 prompt 重写全身定妆导致姿态重置

# 5) I2V02 motion 以 start_pose 为 implicit frame1，以 end_pose hold 收尾
```

### still prompt 模板（连续缝）

```text
{signature_block}
Identity lock: {identity_lock}
Continue from the attached previous-shot last frame (same body pose, weight, hand position).
Evolve only to: {start_pose} / action: {action}.
Do not reset stance from a full-body cast turnaround. Idle not speaking. No text.
```

### I2V motion 模板

```text
From current pose: {action leading to end_pose}, then hold end pose, soft breath, idle not speaking.
Camera: {one axis only}.
```

## Lint / 门禁

| 代码 | 级 | 条件 |
|---|---|---|
| `FRAME_CHAIN_GAP` | soft（`frame_chain_strict` → write-spec hard） | soft/hold 缝上镜缺 `end_pose` 或下镜缺 `start_pose` |
| `FRAME_CHAIN_ORPHAN` | soft | soft 缝下镜 `chain_mode=cut` 或未声明 continue |

```bash
"$AIFILM" lint-continuity --root "<root>"   # 含 frame-chain soft codes（见 continuity_lint + _frame_chain）
"$AIFILM" preflight --root "<root>"         # soft: frame_chain
```

## Pilot 注意

- Pilot 三镜若 **不连续**（hook + reaction + action 跳镜），**不能**代表全片流畅度。
- 建议 pilot 至少含 **一对相邻 soft 缝**（如 shot01→shot02）验证 frame-chain 流程。
- score **motion** 过 = 单镜能动；score **流畅** 需肉眼看相邻 clip 末/首是否像接戏。

## 何时升级真 first/last

需要 **可验证** 的像素级 first/last 时：走 FRW/Comfy 等后端（consistency 降级规则），仍共用 film-spec 的 `start_pose`/`end_pose`。  
**禁止**宣称 Grok I2V 已做 first/last lock。

## 与既有规则关系

- 不取代 [vo-motion-link](lessons-2026-07-17-vo-motion-link.md)（口白=主动作）
- 不取代 [motion-transition](lessons-2026-07-20-motion-transition.md)（xfade 节奏）
- **叠加**：先 pose 链 → 再口白锁 → 再 xfade 润色

## 验收（导演）

- [ ] soft 缝：上 clip 末 0.5s 与下 clip 首 0.5s，角色重心/手位/朝向连续
- [ ] 无「每镜重新摆拍」感
- [ ] hard 缝故意跳时，join=hard 且观众读得懂切点
- [ ] 未用加大 dissolve 掩盖 pose 断裂
