# Lesson 2026-07-21 · 性爱片段时长硬底（Sex Duration Floor ≥20%）

> **触发原话**：「影片的尺度还是太小了…让影片内容至少有 20% 是性爱片段」  
> **P 码**：P0 交付 · P4 语义 · 叙事刺激点  
> **互补**：  
> - [ecchi-story.md](ecchi-story.md) → 亲密核 vs 性爱片段  
> - [intercourse-impact-benchmark](lessons-2026-07-21-intercourse-impact-benchmark.md) → 静帧可读「正在结合」  
> - [montage-hardcore-male](lessons-2026-07-21-montage-hardcore-male.md) → 镜比与蒙太奇  

---

## 失败解剖

| 用户感受 | 旧工程事实 | 根因 |
|---|---|---|
| 尺度太小 | heat max + 荤 VO | **亲密核含前戏**；agent 用「暧昧」撑 60s |
| 要性爱片段 | 有跨坐/贴身镜 | **无 duration 加权闸**；只数镜不数秒 |
| 至少 20% | soft warn only | **write-spec 不挡**；bulk 已锁死软片 |

**一句话**：性爱 KPI = **`heat_phase ∈ {act, climax}` 的 `duration_sec` 之和 / 全片板总秒数 ≥ 20%**。  
前戏、setup、afterglow **不计入**性爱片段。

---

## 规则（代码真相）

| 项 | 值 |
|---|---|
| 性爱 phases | `act` + `climax` only |
| 默认底 | `DEFAULT_SEX_DURATION_FLOOR = 0.20` |
| max write-spec | `sex_floor_strict` **默认 true** → `HEAT_SEX_DURATION_LOW` hard fail |
| hot | soft floor 0.15（warning） |
| hardcore_male | target / floor **0.40**（`audience_profile`） |
| 覆盖 | `sex_min_duration_ratio` · `sex_floor_strict:false` |
| 实现 | `edit_policy.lint_heat_arc` · `film_spec.validate` · `preflight` soft |

### 60s 速算

| 目标 | act+climax 最少秒 | 10×6s 约等于 |
|---|---|---|
| 硬底 20% | ≥12s | ≥2 满板镜 |
| 大尺度建议 35% | ≥21s | ≥4 镜 |
| 重口 40% | ≥24s | ≥4 镜 |

**规划口诀**：先锁性爱秒数，再填 setup/foreplay；禁止先写 6 镜暧昧再「挤」1 镜办事。

### Agent 检查清单

1. write-spec 前读 `_heat_arc.sex_duration_ratio`  
2. fail → 加 act/climax 镜 **或** 把关键性爱镜 `duration_sec` 提到 10  
3. 审核软化 still：仍标 `heat_phase=act`，靠 VO+姿态顶格；**不要**把办事镜改成 setup 逃闸  
4. 用户明确降火 → 降 `heat_scale` 或 `sex_floor_strict:false`（须用户同意）

---

## 验收

```bash
"$AIFILM" write-spec --root "<root>"
# _heat_arc.sex_duration_ratio ≥ sex_duration_floor
# HEAT_SEX_DURATION_LOW 不得出现（max + sex_floor_strict）
```

pytest：`tests/test_heat_arc_multi.py`（sex duration cases）。
