# 总控台 × 导演 OS · 术语与导航心智

> W0 收口文档（来自 `docs/plans/2026-08-07-studio-director-os-integration-todoplan.md` P0.2）。
> 目的：让导演在任何时刻都清楚自己身处「片厂总览」还是「某片操作台」，
> 且总控台与工作台**共用同一份 live 投影**（`web.director_live_ext.project_director_live`），
> 不出现两套数据、两套心智。

## 两层心智（唯一真相）

| 层 | 入口 | 数据来源 | 角色 |
|----|------|----------|------|
| **总控台**（片厂总览） | 标签页 `总控台`（`data-tab="studio"`） | `GET /api/studio`（静态 manifest）+ `GET /api/studio/live`（聚合 live） | 跨片统览 / 排序 / 调度 / 一键进片 |
| **工作台**（某片操作台） | 标签页 `工作台`（`data-tab="overview"`）等 | `GET /api/live`（单片 live） | 单片生产 / 审批 / 指挥 |

- 总控台不写片，只调度（选片 / 触发 `go`/`advance` 作用于 active film）。
- 两处 live 必出自同一函数 `project_director_live`，数字一致（契约测守护）。

## 标签页命名（已对齐）

| `data-tab` | 显示名 | 说明 |
|------------|--------|------|
| `studio` | 总控台 | 多片统览（仅 studio 模式出现，默认落地） |
| `overview` | 工作台 | 当前 active 片的宏观工作台（含 live） |
| `assets` | 选素材 | 资产挑选 / 锁定 |
| `dailies` | Take | 日更 / 多 take 统览 |
| `review` | 审片 | 队列 · 批准/驳回 · 终片审核 |
| `gates` | 门禁 | 硬/软门禁健康 |
| `onboarding` | 起步 | 从故事到可生产 |

> 历史命名：`选 Take` → `Take`，`验片` → `审片`（中文影视行业习惯，避免与「选片」混淆）。

## 面包屑（导航锚）

总控台内层级用面包屑表达：

```
总控台 › <片名> › <工作台/审片/门禁>
```

- 点「总控台」段 → 回到总控台；
- 点「打开此片」→ 智能跳转（见下）。

## 「打开此片」智能跳转（decision 2）

切换 active film 后，按该片 live 注意力选默认落点：

1. `gates.hard_fail` 非空 → 跳 **门禁**
2. 否则 `queue.reviewable > 0` → 跳 **审片**
3. 否则 `dispatch.blocked_by` 非空 → 跳 **门禁**
4. 否则 → 跳 **工作台**

## 写操作边界（decision 4）

- 总控台允许内联触发 `go`/`advance`，作用于**当前 active film**（P5.2 落地）。
- 同时保留只读跳转入口：任何卡片都能「打开此片」进工作台，不强制写。

## 术语速查

- **live / 实时**：来自 `project_director_live`，含 dispatch 卡点、队列 running/failed/reviewable、门禁 hard_fail、待审 inbox。
- **attention（需关注）**：该片 `blocked_by` 非空 ∨ `hard_fail` 非空 ∨ `failed>0` ∨ `reviewable>0`。
- **rollup（跨片聚合）**：`{blocked, failed, reviewable, running, multi_take, inbox}`，总控台顶部汇总条与「今日需处理」面板的数据源。
