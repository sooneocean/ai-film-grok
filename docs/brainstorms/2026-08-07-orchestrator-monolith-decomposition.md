---
date: 2026-08-07
topic: orchestrator-monolith-decomposition
---

# 编排型巨石函数系统性拆解

## Summary

对当前仍超标的编排型巨石函数做**系统性分解**：把 `run_preflight`（约 2120 行）这类「单函数顺序控制流」逐一拆成可单测的 stage 模块，入口只做「组装薄壳」。复用仓库已验证的 `final/` stage 序列模式与 pack 拆分法，破除「拆到一半留 allowlist 白名单」的现状，让每个巨函数的 span 显著下降且主函数变成可跳读的 stage 序列。

---

## Problem Frame

仓库经过 W0–W7 包边界重构后，**目录已分化（hub 1018 ≤2000 合规）**，但这只是「门牌贴好」——真正的巨石从未清除：`gates/preflight.py` 的 `run_preflight` 主函数实测 **2128 行 span**，`spine/dispatch.py` 的 `build_dispatch` **1282**，`post/closeout.py` 的 `closeout_status` **994**，`plan/film_spec_validate_body.py` 的 `apply_bgm_shots_and_edit_body` **941**，`workflow_pack.py` 的 `ship_prep` **829**。

这些函数当前被 `tests/test_mega_fn_budget.py` 的 **`ALLOWLIST` 白名单**明确允许超标——即护栏承认「它们未拆」，但并未产生拆解动作。问题是**单函数控制流过厚**：改任何一处都要通读整本、假绿风险高、无法做细粒度单测。热路径（`final`）已示范过解法（449 主函数 + stage 叶子），但同套解法未推广到其余重石。用户裁定：铁律（如「挡路才拆 / 禁虚荣拆解」）不构成约束，本方案按**系统性拆解**执行。

## 目标与成功标准

- **成功信号（每石）**：对应巨石函数的 span 显著下降（目标每石 < 600 行，强烈参考 `render_final` 的 458 结果），且能在 `ALLOWLIST` 中移出，`make check-all` 绿、行为零漂移。
- **成功信号（全套）**：`test_mega_fn_budget` 无新白名单新增；非热路径巨石逐一被 stage 化或纯叶化。

---

## 待拆巨石清单（实测 2026-08-07 · 按函数 span）

| Pri | 模块 | 文件LOC | 最长函数 | span | 形态 | 既有参考 |
|-----|------|--------:|----------|----:|------|------|
| P0 | `gates/preflight.py` | 2185 | `run_preflight` | **2128** | doctor/开工总检全状态 | `final/` stage 序列 |
| P1 | `spine/dispatch.py` | 1544 | `build_dispatch` | **1282** | 每回合主流程调度 | `dispatch_compact` |
| P1 | `post/closeout.py` | 1417 | `closeout_status` | **994** | 收工总检 | `heat_phase` pack |
| P1 | `plan/film_spec_validate_body.py` | — | `apply_bgm_shots_and_edit_body` | **941** | 契约校验体 | `film_spec_validate_provider` |
| P2 | `workflow_pack.py` | 2898 | `ship_prep` | **829** | 收工编排 | 同上 |
| P2 | `cli/cli_post.py` | 2734 | `cmd_final` / `add_post_parsers` | 795 / 747 | CLI 装配厚 | CLI 抽取 |
| P2 | `post/export_composition.py` | 2132 | `write_hyperframes` / `write_remotion` | 785 / 538 | 导出 writer | harness |
| P2 | `plan/story_plan.py` | 3121 | `project_graph_to_film_spec` | 697 | 规划投影 | story_plan 双路径 |

## 范围

- **范围内**：上表 8 个巨石函数的**系统性拆解**，含 `final/` 已完成重演的复用、`ALLOWLIST` 相应摘除、行为零漂移验证。
- **范围外**：不重开已 ship 的 W0–W05 / heat facade；不删 hard-compat shim；不重写 IRON 产品规则；不做双 checkout 根治（另板）。

## Outstanding Questions

- `run_preflight` 是否确有纯副作用分离边界，或是结构性天然纠缠（影响「先 harness 还是先拆叶」的顺序）——由 planer 在计划阶段确认。