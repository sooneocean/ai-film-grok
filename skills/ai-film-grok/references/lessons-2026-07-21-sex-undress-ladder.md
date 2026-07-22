# Lesson 2026-07-21 · 办事卸甲阶梯（Sex Undress Ladder）

> **触发原话**：「如果要办事，需要脱掉衣服卸下铠甲变成裸露的状态」  
> **强化原话**（2026-07-21 成片事故）：「衣服好像又回穿了…脱下来就要脱下来 不能再穿回去」  
> **P 码**：P0 交付 · P1 身份/定妆 · P4 语义  
> **互补**：  
> - [wardrobe-no-redress-still](lessons-2026-07-21-wardrobe-no-redress-still.md) → **静帧源链**（像素不回穿 · undress-anchor）  
> - [sex-duration-floor](lessons-2026-07-21-sex-duration-floor.md) → 性爱秒数 ≥20%  
> - [intercourse-impact-benchmark](lessons-2026-07-21-intercourse-impact-benchmark.md) → 骨盆可读  
> - [ecchi-story.md](ecchi-story.md) → 服装失序清单  

---

## 失败解剖

| 用户感受 | 工程事实 | 根因 |
|---|---|---|
| 在办事但尺度小 | heat=act + 跨坐 | **铠甲/完整裙装仍在**＝姿势日历 |
| 有失序 | 只滑肩带 | **未完成卸甲**；act 主镜仍 full |
| 角色设定有甲 | cast master 全装 | **未做脱衣 beats**；I2V 从全装 still 起 |

**一句话**：办事 ≠ 全装跨坐；**先卸甲/脱衣 → 裸露可读 → 再沉腰节奏**。

---

## 衣着阶梯（wardrobe_state）

| 状态 | 白话 | 可用 phase |
|---|---|---|
| `full` | 定妆完整 | setup only |
| `armored` | 铠甲/战斗装完好 | setup；**禁 act/climax** |
| `partial` | 半脱/失序/肩带崩/裙掀 | foreplay；act 最低可接受（非 hardcore） |
| `undressed` | 主装已卸、大面积裸露 | **act 默认** |
| `bare` | 顶格裸露可读 | act/climax 优先 |

### 硬闸（`heat_scale=max` 默认 `sex_wardrobe_strict`）

1. **act/climax** 不得为 `full` / `armored` / 未声明且无裸露词  
2. 必须存在 **卸甲/脱衣动作拍**（`HEAT_UNDRESS_BEAT_MISSING`）  
3. **分镜延续 + 衣服不回穿**（2026-07-21 强化 → **2026-07-21 必触发**）：  
   `wardrobe_state` rank 只可前进  
   `full(0) → armored(1) → partial(2) → undressed(3) → bare(4)`  
   - 后镜未写状态 → write-spec **继承 peak**  
   - 后镜写更「穿好」的状态 → **自动 clamp 回 peak**（`clamped_ids`）+ 仍可报 `HEAT_WARDROBE_RE_DRESS`  
   - 后镜 `dsl.start_pose` / `subject` 必须从**已脱状态开场**（`start_pose_ids`）  
   - subject 仍写 full wardrobe → `HEAT_WARDROBE_TEXT_CONFLICT` hard fail  
4. 码：`HEAT_SEX_WARDROBE_DRESSED` · `HEAT_UNDRESS_BEAT_MISSING` · `HEAT_WARDROBE_RE_DRESS` · `HEAT_WARDROBE_TEXT_CONFLICT` · hardcore 另有 `HEAT_SEX_WARDROBE_WEAK`

### 延续规则（agent / 作者）— **必触发**

| 规则 | 做法 |
|---|---|
| 卸装只前进 | afterglow / 后续镜 **禁止** 回到 full/armored；write-spec **clamp** |
| 未写状态 | `apply_wardrobe_continuity` 继承 peak |
| 有卸装动作 | 仍 full/armored 时自动至少抬到 `partial` |
| 下一镜开场 | `start_pose` = already undressed from prior；**禁止**站回全装再脱一次 |
| 静帧/I2V | prompt **必**含 `Costume continuity HARD`；undressed 时 **不** fallback 到 `default_wardrobe` |
| 跨镜 still | 禁止对 undressed 镜再 `image_edit(full cast 全装)`；用上一镜末帧或 undress still |
| 双轨审核 | 软画面仍须 **半脱/已脱** 可读；VO 补荤；**禁止**为过审回穿全装 |

### 用户痛点（为何必触发）

> 「前面脱完，后面衣服又穿起来」= 剧情错。  
> 根因：agent 每镜从 cast master 全装重起 + prompt 丢了 Costume continuity + subject 仍写 full wardrobe。  
> 修复：write-spec clamp + start_pose 锁 + prompt HARD 行 + text conflict 硬闸。

### 写法（film-spec）

```json
{
  "heat_phase": "foreplay",
  "wardrobe_state": "partial",
  "dsl": {
    "action": "removes armor plates, dress slides off shoulders",
    "visible_change": "armor discarded; bare shoulders",
    "wardrobe_state": "partial"
  }
}
```

```json
{
  "heat_phase": "act",
  "wardrobe_state": "undressed",
  "dsl": {
    "subject": "adult heroine undressed bare skin",
    "action": "straddle-seat hips-sink skin-to-skin",
    "wardrobe_state": "undressed"
  }
}
```

### 静帧 / I2V（agent）— **像素层 · 比 JSON 更硬**

> 片例 `xide-hardcore-thrust`：spec 已 bare，仍因 **每镜 image_edit(全装 cast)** 回穿。完整 SOP → [wardrobe-no-redress-still](lessons-2026-07-21-wardrobe-no-redress-still.md)。

1. cast master **仅** setup / 卸装动作起稿可用全装  
2. 卸装峰值 still 批准后立刻落盘：  
   `canonical/wardrobe/undress-anchor.png`（= 本片衣着真相源）  
3. **peak 之后每一镜**（含 act/climax/afterglow）：  
   - **只** `image_edit(undress-anchor | 上一已脱 still)`  
   - prompt 只改姿势/机位，**必写** `do NOT put clothes back on` / `Keep clothing state`  
   - **禁止** `image_edit(全装 cast master)`（身份可另 ref，衣着源必须是已脱图）  
4. I2V：首帧=已脱 keyframe；motion 写 `Keep first-frame clothing — never re-dress`  
5. 路径：full cast → **undress peak** → undress-anchor → act… → afterglow（**全程不回 cast 全装**）  
6. 并行 bulk 多镜 cast 重起 = **直接 P0 事故**

### 双轨抗审核

- 画面：suggestive **undressed** 姿态（非硬核器特写）  
- 若审核拦 bare：降到 partial **但仍须半脱**，加重 VO；**禁止**回退全装铠甲  
- **禁止**用「过审」当借口从 cast 全装重画 act 镜（那是回穿，比审核 fail 更严重）

---

## 验收

```bash
"$AIFILM" write-spec --root "<root>"
# _heat_arc.wardrobe.ok true
# no HEAT_SEX_WARDROBE_DRESSED / HEAT_UNDRESS_BEAT_MISSING / HEAT_WARDROBE_RE_DRESS
# test -f canonical/wardrobe/undress-anchor.png   # peak 之后 bulk 前
```

**像素抽检**（交付前）：从 undress peak 起每镜 clip t≈1s，半脱标记（丝袜半褪 / 甲落地 / 裙开）仍在；整齐全装 = fail。

pytest：`tests/test_heat_arc_multi.py`（wardrobe cases）。
