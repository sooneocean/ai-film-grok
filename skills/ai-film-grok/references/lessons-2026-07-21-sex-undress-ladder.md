# Lesson 2026-07-21 · 办事卸甲阶梯（Sex Undress Ladder）

> **触发原话**：「如果要办事，需要脱掉衣服卸下铠甲变成裸露的状态」  
> **P 码**：P0 交付 · P1 身份/定妆 · P4 语义  
> **互补**：  
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
3. **分镜延续 + 衣服不回穿**（2026-07-21 强化）：`wardrobe_state` rank 只可前进  
   `full(0) → armored(1) → partial(2) → undressed(3) → bare(4)`  
   后镜未写状态 → write-spec **继承前镜**；后镜写更「穿好」的状态 → **`HEAT_WARDROBE_RE_DRESS` hard fail**  
4. 码：`HEAT_SEX_WARDROBE_DRESSED` · `HEAT_UNDRESS_BEAT_MISSING` · `HEAT_WARDROBE_RE_DRESS` · hardcore 另有 `HEAT_SEX_WARDROBE_WEAK`

### 延续规则（agent / 作者）

| 规则 | 做法 |
|---|---|
| 卸装只前进 | afterglow / 后续镜 **禁止** 回到 full/armored |
| 未写状态 | `apply_wardrobe_continuity` 继承上一镜 |
| 有卸装动作 | 仍 full/armored 时自动至少抬到 `partial` |
| 静帧/I2V | prompt 注入 `Costume continuity: wardrobe_state=… NEVER re-dress` |
| 跨镜 cast | 禁止对 undressed 镜再 `image_edit(full armor cast)` 当办事 |

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

### 静帧 / I2V（agent）

1. cast master 可全装  
2. **act 镜禁止**直接 `image_edit(cast full armor)` 当办事  
3. 路径：full → **undress still**（卸甲）→ act still（bare/undressed）→ `image_to_video`  
4. prompt 必含卸装结果词；禁 only「seductive in full tech dress straddle」

### 双轨抗审核

- 画面：suggestive **undressed** 姿态（非硬核器特写）  
- 若审核拦 bare：降到 partial **但仍须半脱**，加重 VO；**禁止**回退全装铠甲  

---

## 验收

```bash
"$AIFILM" write-spec --root "<root>"
# _heat_arc.wardrobe.ok true
# no HEAT_SEX_WARDROBE_DRESSED / HEAT_UNDRESS_BEAT_MISSING
```

pytest：`tests/test_heat_arc_multi.py`（wardrobe cases）。
