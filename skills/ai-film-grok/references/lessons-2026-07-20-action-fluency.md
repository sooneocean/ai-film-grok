# 动作流畅度（接戏仍「一镜一顿」· 2026-07-20）

**用户反馈**：continuity chain 逻辑对了，但片段之间仍明显割裂。

## 诊断：字节对齐 ≠ 动能对齐

| 层 | 已做 | 仍割裂的原因 |
|---|---|---|
| **身份/姿势** | last frame SHA = next first frame | 解决了「人跳变」 |
| **转场** | hard match-cut（勿 soft 叠化） | 叠化会更糊；硬切正确但仍可能「顿」 |
| **动能** | 未管 | 镜尾 **hold/idle** → 下镜 **从静止再起动** = 每 6s 重踩油门 |
| **成片时长** | `duration_sec: 6` 当地板 | VO 只 3s 时仍 **播满/慢放/冻尾 6s**，专把「收住」播给观众再切 |

类比：接力赛若每人跑到终点站定再把棒递给下一位，即使棒没错，整场仍像分段表演。

---

## 流畅度方法栈（按优先级）

### A. 切在动作中（Mid-action cut）— 最重要

**禁止** continue 缝的 motion 以这些收尾：

- `hold end_pose` / `idle` / `soft blink then hold` / `freeze`

**改为**：

- 镜尾 = **动作未完成的一帧**（手还在拧、身还在倾）
- 下镜 motion **接同一动词的后半段**，禁止「从站定重新举手」

```text
# 差（会顿）
motion: turn latch shut, hand lowers, hold, soft breath, idle

# 好（切在动中）
motion: fingers turning latch mid-rotation, body still committing into room — cut mid-action, no settle hold
# 下镜
motion: finishes latch shut from mid-turn, hand continues down, steps toward vanity without restarting
```

film-spec 建议字段：

```json
"dsl": {
  "cut_on": "mid_motion",
  "end_pose": "hand mid-turn on latch, weight still shifting (NOT settled)",
  "motion": "… continuous motion through end frame, no settle hold, idle not speaking"
}
```

`cut_on`: `mid_motion`（continue 默认）| `hold`（仅 afterglow/cut 缝）。

### B. Join handle（切点 ≠ 文件末尾）

I2V 常 6s，真正接戏切点应在 **动作峰值前 0.3–0.8s**：

```bash
# 在 t=5.2s 抽帧作下镜首帧（仍在动），不要 --which last（常是收住帧）
"$AIFILM" extract-frame --root <root> --shot-id shot01 --which 5.2 \
  --promote-keyframe shot02
```

并写：

```json
"shot01": { "out_point_sec": 5.2 }
```

final 只播到 `out_point_sec`，下镜从 promote 帧起 —— **切点字节对齐 + 动能未泄**。

### C. 成片跟 VO 切，不要硬撑满槽（visual_fit）

| `visual_fit` | 行为 |
|---|---|
| `"slot"`（旧默认） | `target = max(VO+pad, duration_sec)` → 常撑满 6s |
| **`"vo"`（连续戏推荐）** | `target ≈ VO+pad` → 自然在动作前半段切开，少播「收住尾巴」 |

```json
"visual_fit": "vo",
"transition_intents": ["hard","hard","hard","hard","hard"],
"transition_default": "hard"
```

**只 re-final 即可**验证听感/卡点；像素接戏仍靠 chain。

### D. 转场：字节链 = hard match-cut

已证：soft dissolve 在 byte_identical 缝上会双影更糊。  
continue 缝 → **hard**；改 intents **只 re-final**。见 [continuity_chain.md](continuity_chain.md)。

### E. 镜间共用「运动矢量」

连续 2–3 镜写同一能量方向：

- 身体：always advancing toward vanity / always leaning in  
- 镜头：一条轴做完（dolly 贯穿两镜）再换轴  
- 禁止：镜 A 推近收住 → 镜 B 又从中景重新推近

### F. 一动词跨两镜（split verb）

| 镜 | 只演半个动作 |
|---|---|
| shot02 | 手 **开始** 拧锁 |
| shot03 | 锁 **拧死** + 呼吸（可切景别） |

闭眼听旁白仍一句事，画面是同一动作的两刀。

### G. 成片禁止用这些「假顺」

- 加长 dissolve / hblur 盖跳  
- 定格、倒放  
- stream_loop 把同一动作再播一遍（hook/action 已禁）  
- 无关空镜挡缝  

---

## Agent 检查单（continue 链）

- [ ] motion **无** settle/hold 收尾（`cut_on: mid_motion`）  
- [ ] promote 用 **动作中帧**（`--which <sec>` 或 last 仅当 last 仍在动）  
- [ ] `out_point_sec` 与 promote 时刻一致  
- [ ] `visual_fit: "vo"` + story joins **hard**  
- [ ] 相邻镜共享 travel / 主轴  
- [ ] final 日志无大段 freeze_sec 顶满 6s 槽  

---

## 与既有文档

- 字节复用：[continuity_chain.md](continuity_chain.md)  
- 转场节奏：[lessons-2026-07-20-motion-transition.md](lessons-2026-07-20-motion-transition.md)  
- 口白=动作：[lessons-2026-07-17-vo-motion-link.md](lessons-2026-07-17-vo-motion-link.md)  
- **观感胶水（字幕/片头）**：[lessons-2026-07-20-designed-post-fluency.md](lessons-2026-07-20-designed-post-fluency.md) + HyperFrames/Remotion（不能替代本节动能规则）
