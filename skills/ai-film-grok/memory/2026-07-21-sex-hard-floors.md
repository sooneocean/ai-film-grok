# Memory · 成人办事剧三条硬底（2026-07-21）

**用户原话链路**：
1. 尺度太小 → 性爱片段至少 20%
2. 办事要脱掉衣服卸铠甲变裸露
3. 讲的内容都要荤梗（实打实荤场景办事剧）

## 产品硬底（`heat_scale=max` 默认 write-spec hard）

| # | 规则 | 字段 / 码 | 课 |
|---|---|---|---|
| 1 | act+climax **时长 ≥50%** 总片板（IRON 2026-07-24；曾 20%→30%→50%） | `sex_floor_strict` · `HEAT_SEX_DURATION_LOW` | [sex-duration-floor](../references/lessons-2026-07-21-sex-duration-floor.md) · [adult-max-iron](../references/lessons-2026-07-24-adult-max-iron.md) |
| 2 | 办事 **卸甲/脱衣** → act≥undressed · climax=**bare**；**延续不回穿**；自动 phase 抬升 | `sex_wardrobe_strict` · `HEAT_SEX_WARDROBE_*` · `HEAT_BARE_PEAK_MISSING` · `HEAT_UNDRESS_BEAT_MISSING` · **`HEAT_WARDROBE_RE_DRESS`** · `apply_wardrobe_continuity` | [sex-undress-ladder](../references/lessons-2026-07-21-sex-undress-ladder.md) |
| 3 | **每镜 nar 荤梗**；act/climax 办事动词；max 默认 **extreme** | `sex_vo_strict` · `HEAT_VO_SPICE_*` | [sex-vo-spice](../references/lessons-2026-07-21-sex-vo-spice.md) |
| 4 | 亲密 ≥60% · setup ≤20% | `heat_arc_strict` · `HEAT_INTIMACY_RATIO_LOW` · `HEAT_SETUP_RATIO_HIGH` | adult-max-iron |

## 代码入口

- `edit_policy.lint_heat_arc`（合入 duration + wardrobe + vo_spice）
- `film_spec.validate` 默认 hard on max
- `preflight` soft 码同名
- 测试：`tests/test_heat_arc_multi.py`

## 一句话

**秒数够 + 衣服卸了 + 耳朵也荤** = 才算办事剧；缺一环观众就觉得尺度小。

## 2026-07-27 加码（最重要）

用户明示：**成人尺度拉到最高 = 全片最优先**；肉戏须 **起承转合全弧**：**前戏 → 插入 → 射出** 都要有（连贯，不可只抱吻或跳切高潮）。
见 [adult-scale-max-sex-arc](../references/lessons-2026-07-27-adult-scale-max-sex-arc.md) · [memory](2026-07-27-adult-scale-max-sex-arc.md)。

## 2026-07-29 加码（毒镜 · 后面不要再犯）

用户：「性器官跟乳汁这些都有很多问题」。
**尺度拉满 ≠ 畸形**：禁 futa/女体阴茎、喷奶母乳、霓虹生殖器；毒 still 禁 I2V、毒 clip 禁 register/final。
见 [poison anatomy memory](2026-07-29-poison-shot-anatomy-iron.md) · [lesson](../references/lessons-2026-07-29-anatomy-milk-futa-comfy-batch.md)。

## 片例

- 片场：`/Users/dex/AI FILM SPACE/0721/xide-private-encore`（席德·私展加演）
- 若重渲：按卸装阶梯 + 全荤 VO 改 act 静帧/旁白

## 版本

plugin ≥ **1.3.0**（commits: sex duration → undress → vo spice）
