---
date: 2026-08-07
topic: orchestrator-monolith-decomposition
---

# Orchestrator Monolith Decomposition（编排型巨石函数系统性拆解）

## Summary

把仍超标的**编排型单函数总控**逐一拆成可单测的 stage 模块，入口只做「组装薄壳」，复用已验证的 `final/` stage 序列 + pack 拆分方法论。目标函数 span 全部显著下降并离开 `ALLOWLIST`，行为零漂移。**今日实测事实**：`test_mega_fn_budget.py` 门禁**当前是红的**——`cmd_final`（857）与 `ship_prep`（829）超 800 行门槛却未入白名单。本次为独立、以实测为据的拆解文档，不另改 08-07 orchestrator 板，不重开已 ship 的 W0–W7 / heat。

---

## Problem Frame

仓库经 W0–W7 包边界重构后目录已分化（hub 1018 ≤2500 合规），但真巨石早已不在「放错目录的文件」，而是 **8 个 1k–3.1k 行的编排型单函数**。今日实测（2026-08-07，AST span，与 `test_mega_fn_budget.py` 同法计算）：

| 模块 | 最长函数 | span | 是否已入 ALLOWLIST |
|------|---------|-----:|:---:|
| `gates/preflight.py` | `run_preflight` | 2128 | ✅ 已挂 |
| `spine/dispatch.py` | `build_dispatch` | 1282 | ✅ 已挂 |
| `post/closeout.py` | `closeout_status` | 994 | ✅ 已挂 |
| `plan/film_spec_validate_body.py` | `apply_bgm_shots_and_edit_body` | 941 | ✅ 已挂 |
| `workflow_pack.py` | `ship_prep` | **829** | ❌ **未挂（触发红）** |
| `cli/cli_post.py` | `cmd_final` | **857** | ❌ **未挂（触发红）** |

> span 以 `test_mega_fn_budget.py` python 计算为准（AST `end_lineno - lineno + 1`，链路) ；文件 LOC 以 `wc -l` 为准。实测确认：`test_mega_fn_budget` 汇报 `cmd_final span=857`、`ship_prep span=829` 两个 offender。

**病根**：叶子已抽走，但**控制流仍顺序写在单函数里**——`run_preflight` 一个函数做 doctor/开工/全状态总检，改一处要通读整本，无法做细粒度单测，假绿成本比行数更贵。`final/` 已示范同套解法（主函数压到 ~458 + stage 叶子），但未推广到其余重石。用户裁定铁律（「挡路才拆 / 禁虚荣拆解」）不构成约束，本方案按**系统性拆分**执行。

---

## Actors

- A1. **维护开发者（agent / maintainer）**：执行拆分，迁移行为，写/改测试，兜住行为零漂移。
- A2. **终端用户（拍片 worker）**：走 `aifilm doctor | dispatch | preflight | final` 等公开 CLI；行为漂移直接伤其成片。
- A3. **下游 CI**：跑 `test_mega_fn_budget` + 全量 pytest，作为最终质量门。

---

## Key Flows

- F1. **单石拆解循环**（每石同一套）
  - **Trigger**：「继续推进」或某巨石在 thrash 挡路
  - **Actors**：A1
  - **Steps**：S0 探针（取 span + 调用图 + 现有测覆盖）→ S1 Harness（缺 failure-mode 测试先补）→ S2 纯副作用 leaf 出片 → S3 编排函数压成 stage 序列收薄壳 → 更新 ALLOWLIST 相对项 → 行为 vs 结构分离 commit
  - **Outcome**：主 span 显著降、每 stage 可单测、公开 CLI 与 shim hard-compat 不变
  - **Covered by**：R1–R6
- F2. **ALLOWLIST 回流**
  - **Trigger**：拆分把某函数压到 ≤800，或新增 >800 函数
  - **Actors**：A1
  - **Steps**：函数 <800 → 从 `ALLOWLIST` 摘除；新 >800 → 显式入 allowlist 或拆
  - **Outcome**：门禁只反映真实 span，不 Stale、不漏挂
  - **Covered by**: R7
- F3. **行为零漂移回归**
  - **Trigger**：每次拆分合入
  - **Actors**：A1, A3
  - **Steps**：相关热路径 / 功能区 suite 全绿 → 手跑真实 CLI（`doctor` / `dispatch` / fixture `final`）+ `make check-all`
  - **Outcome**：结构 peel 不动逻辑；`test_w3_package_shims` 与相关 suite 全绿
  - **Covered by**: R8–R10

---

## Requirements

### 编排型拆解
- R1. 每个巨石按 S0–S3（over）拆分；**优先级递减**：`run_preflight`(P0) > `build_dispatch`(P1) > `closeout_status`(P1) > `apply_bgm_shots_and_edit_body`(P1) > `ship_prep`(P2) > `cmd_final`(P2)。
- R2. 每个拆完巨石的主 span **目标 < 600** 行（参考 `render_final` 458 水平）；若真实跨域纠缠无法达此，则改为明确命名的 stage 序列而非单函数。
- R3. 纯副作用 leaf 拆分前须有 S1 harness：缺 failure-mode（垃圾输入 / 缺文件 / 门红诚实）先补；禁止 silent `pass` 假绿。
- R4. `run_preflight`：按检查段拆成 `preflight_*` 纯 report builder（env / tools / root / gates / receipts），入口只聚合再发布。
- R5. `build_dispatch`、`closeout_status`、`apply_bgm_shots_and_edit_body`：按契约节拆 leaf，入口薄壳，参考既有 `final/` 与 `heat_phase` pack。
- R6. `ship_prep`、`cmd_final`：优先「参数装配 vs 领域调用**拆离**」 + 大函数只留 orchestrator；不误操为「巨型 stage 序列」。

### 兼容与门槛
- R8. 公开 `aifilm` 子命令、flag 名、shim hard-compat **不变**；peel commit 禁 retune heat / i2v_provider / pilot / adult floor。
- R9. 行为零漂移：任何 stage peel 须 `test_w3_package_shims`、`test_mega_fn_budget`、相关功能区 suite 全绿才合入。
- R10. 结构 peel 与行为 / 产品改变**分离 commit**：每 PR 单一类别，不混装。

### 文档与护栏
- R11. 本文档为**结构债单一真相**；拆分状态完成后回写相应 plan 板。**用户裁定（2026-08-07）覆写**原「不另开第三份 monolith plan」铁律：系统拆解（目标 <600）授权新执行板，原 `2026-08-07-monolith-orchestrator-relief-todoplan.md` 作为已 ship 历史证据保留。
- R12. `test_mega_fn_budget` 当前两个 red offender（`cmd_final` 857、`ship_prep` 829）在拆解后必须回到绿线并摘除白名单；不得靠加白名单掩盖。

---

## Acceptance Examples

- AE1. **Covers R1, R4.** Given `preflight.py` 的 `run_preflight` span=2128，when 走 R4 段拆并把主函数压到 <600，then `test_mega_fn_budget` 中可将 `run_preflight` 从 ALLOWLIST 摘下（stale 不报错），且 `aifilm doctor` 手跑输出与拆分前后对等覆盖。
- AE2. **Covers R2.** 对任一拆完巨石，`test_mega_fn_budget` 无新 >800 函数无 allowlist 覆盖；主 span 记录 <600。
- AE3. **Covers R8, R9.** 拆分后运行 `aifilm final --root <fixture> --post-engine ffmpeg`（或等价路径），receipt 中 `delivery_class / manifest / plate` 语义不变（plate≠master）。
- AE4. **Covers R6.** `cmd_final` 拆分后 CLI 子命令字符串与 flag 名不变，`rg "final" cli_post` 的解析仍存在，且 main span <600。
- AE5. **Covers R12.** `test_mega_fn_budget` 从红转绿：现存 `cmd_final=857`、`ship_prep=829` 两项被解（拆 / 转化），无新 stale。

---

## Success Criteria

- **每石**: 主 span <600，相关检测 + 所有被测区全部绿。
- **全套**: `test_mega_fn_budget` 由「**红**」转「**绿**」，现存两 red offender 消解；从 ALLOWLIST 摘除而非加白名单掩盖。
- **行为零漂移**: 手跑真实 CLI（doctor / dispatch / 一个 10 镜 fixture final）等价，不是「测试过就行」。
- **可审性**: 每个新 stage / leaf 有单测 + hotpath 命中；本文档作为单一染色板与实测对账一致。

## Scope Boundaries

- **不重拆**: `plan/film_spec_validate_body.py` 的 `apply_bgm_shots_and_edit_body` 若已属 forest leaf 不再多拆（仅 orchestrator）。
- **不重开**：W0–W7 包边界、hub ≤2500、heat facade（内部可读）——不在清单。
- **不删 shim**：hard-compat shim 整批不删。
- **不虚荣冲刺**：不为「全 <1500 LOC」硬拆；达标（<600）即可。
- **不碰政策**：不重建 IRON、不动 `i2v_provider` / h3 政策 / adult floor / pilot。

## Key Decisions

- **目标 span = `<600`（用户裁定，2026-08-07）**：对齐 `render_final` 的 458 水平；每个拆段抽成 `_attach_<name>(root, hard, soft)` 纯 leaf。此标准统一用于 8 个巨石，作最强可审性。
- 拆分顺序 = **风险 × 触达**（`run_preflight` 最多触达最先拆），非行数虚荣排序。
- **命令与 CLI 不变**：peel 只改内部文件组织，不改公开调用路径。
- **行为 vs 结构分离** commit：结构 peel 永远默认不改行为。

## Dependencies / Assumptions

- **依赖**：`final/` pack 方法论、`test_mega_fn_budget` 门禁、`test_w3_package_shims` hard-compat 契约。
- **假设**：`run_preflight` 可切分（与 08-07 wave3「premium leaf」一致）；ffmpeg / providers 在 CI 可用（非拆分引入）。
- **已验证（codegraph, 2026-08-07）**：
  - `run_preflight` 检查段**安全可拆**→每个段已是「懒导入纯 report leaf + `hard/soft.append`」形态，自带 `try/except` 边界；已有现成样板 `append_premium_vertical_issues(root, hard, soft)`（`gates.preflight_premium`）。抽出成 `_attach_<name>(root, hard, soft)` 即可，无跨段可变依赖。
  - `build_dispatch` **已有契约测试覆盖**——`test_dispatch.py`、`test_dispatch_compact.py`、`test_workflow_wire_primary.py`、`test_narrative_control.py` 直接覆盖；且其 `if craft_stage == …` 分支是天然拆分边界（每分支产出独立 `pre()` 条目）。

## Outstanding Questions

- [Affects R2][User 决策 · **已定**] `run_preflight` 目标「压到 <600」→ 用户已裁定统一 **<600**（2026-08-07）。
- [Affects R6][Technical · 待 planning 查勘] `cmd_final` 的 CLI parser 与领域调用「拆边界」如何定位（拆进 parser 还是拆进独立 scope）。
- [已研究 · 已解决] R4 `run_preflight` 可分拆 → 见上「已验证」。
- [已研究 · 已解决] R5 `build_dispatch` 有契约覆盖 → 见上「已验证」。
