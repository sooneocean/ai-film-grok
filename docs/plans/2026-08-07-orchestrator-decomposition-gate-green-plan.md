---
title: "refactor: Green the mega-fn gate and decompose run_preflight to <600"
type: refactor
status: active
date: 2026-08-07
origin: docs/brainstorms/2026-08-07-orchestrator-monolith-decomposition.md
---

# 编排型巨石拆解 Wave A：门禁转绿 + run_preflight 压到 <600

## Summary

把当前**红色**的 `test_mega_fn_budget` 门禁拉回绿线——先将两个未入白名单的 >800 超限函数（`cmd_final` 857、`ship_prep` 829）按已有 `final/` stage / `_attach_*` 纯叶模式拆到 <600 的既定标准；随后把 P0 巨石 `run_preflight`（span 2108）按检查段抽成纯 `_attach_<name>(root, hard, soft)` leaf、入口只做组装薄壳，主 span 压到 <600。全部复用已验证模式（`final/` stage 序列、`gates.preflight_premium.append_premium_vertical_issues`），行为零漂移，公开 `aifilm` CLI 与 shim hard-compat 不变。

---

## Problem Frame

`test_mega_fn_budget.py` 当前**失败**（RED）：门槛 800 行、`ALLOWLIST` 只有 4 项，而 `cli_post.cmd_final`（857）与 `workflow_pack.ship_prep`（829）超限却未入白名单，报 2 个 offender。同时 P0 巨石 `run_preflight`（2108 行）是 doctor/开工总检的单函数顺序控制流，改一处须通读整本、无法做细粒度单测。

本计划把两件事绑在一起做：先修好门禁（快、低风险、立刻恢复绿的 CI 信号），再拆最大的可收益函数。两者共用同一 `_attach_*` / stage-leaf 模式与 `<600` 目标（用户已裁定统一 **<600**，见 origin R2/Key Decision）。

---

## Requirements

- R1. 让 `test_mega_fn_budget` 由**红转绿**：现存 `cmd_final=857`、`ship_prep=829` 两 offender 解掉（各自主函数 span <600），且不从白名单掩盖。→ AE5（origin）
- R2. `run_preflight` 主函数 span <600，拆成纯 `_attach_<name>(root, hard, soft)` leaf（每段一个），入口只组装。→ AE1（origin）
- R3. 每个新 stage leaf 有独立单测 / hotpath 命中（happy+edge+error）。→ AE2（origin）
- R4. 行为零漂移：公开 `aifilm` 子命令字符串、flag 名、shim hard-compat **不变**；peel commit 禁 retune heat / `i2v_provider` / pilot / adult floor。→ AE3, AE4（origin）
- R5. 结构 peel 与行为/product 改变分离 commit（单一类别 PR）。

**Origin actors:** A1（维护 agent/maintainer）、A2（终端拍片 worker）、A3（下游 CI）
**Origin flows:** F1（单石拆解循环 S0–S4）、F2（ALLOWLIST 回流）、F3（行为零漂移回归）
**Origin acceptance examples:** AE1（run_preflight <600 + doctor 等价）、AE2（无新 >800 无 allowlist 覆盖）、AE3（final receipt 语义不变）、AE4（cmd_final CLI 字符串不变）、AE5（门禁从红转绿）

---

## Scope Boundaries

- **非目标**：不拆 `build_dispatch`、`closeout_status`、`apply_bgm_shots_and_edit_body`、`export_composition` writers、`story_plan.project_graph_to_film_spec`（均留到后续 wave，同一模式）。
- 不重开的已 ship 波：W0–W7 包边界、heat facade、`film_spec_validate` provider/soft/heat、final stages。
- **不删 hard-compat shim**；不改公开 CLI 字符串。
- **不碰政策/IRON**：`i2v_provider`、adult floor、heat 规则、pilot 自批。
- 不为「全员 <1500」硬拆；达标（主函数 <600）即可。

### Deferred to Follow-Up Work

- 其余 5 个巨石（build_dispatch / closeout_status / apply_bgm_shots_and_edit_body / write_hyperframes / project_graph_to_film_spec）→ 后续独立 wave，同一 `<600` 标准与同一 `_attach_*` / stage 序列法。见 origin Scope Boundaries `不重拆`/Definition。

---

## Context & Research

### Relevant Code and Patterns

- `final/` pack & stage 序列：`post/render_final.py` → `render_final` ~458 行 + 多个 `final/stages_*.py` leaf，每段 lazy import + 独立可测。**这是拆 `run_preflight` 的直接模板**。
- **既成样板**：`gates/preflight_premium.py` 的 `append_premium_vertical_issues(root, hard, soft)` —— 正是「纯 leaf 增补 hard/soft」的理想形态，`run_preflight` 已在用它；拆新段就复制这个形态。
- 现有 `preflight_issues` 模块：`_issue` / `_append_probe_error` / `_is_heat_max_iron` 已提供 hard/soft append 与错误收集助手。
- `run_preflight`（preflight.py:48）当前调用链（codegraph 验证）：`load_pilot_approval` · `read_json(manifest/spec/style/pilot-scorecard)` · `load_post_plan` · `preflight_premium.append_premium_vertical_issues` · `narrative_control.validate_narrative_graph` · `framing_lint.lint_framing_iron` · `tts_rehearsal.{measured_vo_by_shot,bind_receipt_to_spec_timing}` · `loop_risk_shots_from_spec` · `edit_policy.{default_visual_fit,lint_equal_duration_ppt,lint_heat_arc}` —— 全是「纯读 + append」，无跨段可变依赖 → 安全切成 `_attach_*`。
- `cmd_final`（cli_post.py:157）：依赖 `assert_review_advance_allowed` / `require_current_canonical_truth` / 复数 `skip_*` / `ensure_ready_for_final` / `resolve_final_defaults` / `load_post_plan` / `run_preflight` / `write_audit` / `production_gates.*` / `shot_inventory` / `true_video_policy` / `post_route` —— 每个都是独立 gate，入口只做「收集结果→按序 raise/mux cmd」。参数装配（`cmd = [sys.executable, str(script), ...]` 那段）与领域 gate 层次天然可分离组。
- `ship_prep`（workflow_pack.py:1729）：依赖 `ensure_take_means` / `scan_manifest_true_video` / `variety_precheck` / `variety_pixel_bind` / `select_shortlist` / `build_effect_scorecard` / `read_json` + summary gate —— 结构上同样是「分块收集 → 汇总收口」，每块可抽成 `_prep_*` leaf。

### Institutional Learnings

- 铁律：**挡路才拆 / 纯叶优先 / 行为 vs 结构分 commit / CLI+shim hard-compat 不变 / 禁虚荣 <1500 LOC**（见 closed board 铁律 §5）。用户裁定覆写「禁虚荣」禁令，允许系统性拆解 + 目标 <600。
- **诚实语义**：plate≠master、`delivery_class`、native XOR、caption 双烧禁 —— 拆时**不改**这些语义（见 closed board Iron）。

### External References

- 无（codebase 已有 strong pattern，无需外部资料；见 ce-plan Phase 1.2 决策）。

---

## Key Technical Decisions

- **目标 span = `<600`（用户裁定）**：统一用于 `run_preflight` 及本波触及的函数；reference 基准为 `render_final` 458。
- **`cmd_final` / `ship_prep` 本轮仅修门禁**：目标是让两者各自主函数 <600（不只是掉到 800 白名单下）；但**不要求**这波就把它们完全 stage 到 floor——只需「门禁绿 + 拆出的本体有单测」。Deep 拆解（`closeout`/`ship_prep` 全展开）留在 Deferred。
- **拆分模式统一 `_attach_*` 纯 leaf**：不做「巨型 stage 序列」，做「stage leaf 增补 hard/soft」——恰好 `run_preflight` 已有的 `append_premium_vertical_issues` 形态即标准。
- **行为 vs 结构分 commit**：每个结构 peel commit 是「默认不改行为」；无干 commit-N 加 retune。
- **门禁为最终质量网**（CI `doctor`+pytest）：本地不可把它当门禁；peel 合入以上述 green 为准。

---

## Implementation Units

### U1. 修复 test_mega_fn_budget 门禁红（cmd_final → <600）

**Goal:** 把 `cli_post.cmd_final` 主函数从 span 857 压到 <600，同时让 `test_mega_fn_budget` 绿、CLI 字符串不变。

**Requirements:** R1, R4
**Dependencies:** 无

**Files:**
- Modify: `skills/ai-film-grok/scripts/cli/cli_post.py`
- Test 边：`test_mega_fn_budget.py`（本仓现红→期望绿）；确认现有 `tests/test_post_plan.py` 覆盖
- 参考：`final/` stage 序列模式

**Approach:**
- 将 `cmd_final` 中**参数装配（构建 `cmd = [sys.executable, str(script), ...]` 那一大段 + `--out-name/--voice/--tts-backend/...`）拆到独立函数 `_build_render_cmd(root, args, post_engine)`。
- 将「阶段化审查序列」拆成独立叶子（`_assert_final_ready(root, args, skip_contract, ...)` 之类的 gather，各 gate 调已有纯函数）。入口只留「组装 gather→mux cmd→写 receipt→调用」薄壳。
- 保持 `subcommand string + flag 名` 不变；只改内部组织。

**Execution note:** characterization-first —— 拆分前先锁定 `test_mega_fn_budget` + `test_post_plugin` 绿；再安全移动代码，边拆边验证行为不变。

**Patterns to follow:** `final/stage_*.py` 的 lazy-import + 每 stage 小函数；`post_route` 的「resolve → apply → write receipt」三步形态。

**Test scenarios:**
- Happy：`cmd_final` 主函数 span <600 且 `test_mega_film_budget` 不再报 `clv_cmd_final` offender。
- Edge：各项 `--flag`（`--out-name`/`--tts-backend`/`--prefix`）在移入 `_build_render_cmd` 后生成的 `cmd` list 与拆分前逐字节相同。
- Error：`FilmError`（如 `post_plan` owner mismatch）—— raise 时机与 message 不变。
- Integration：真跑一次 `aifilm final --root <existing fixture> --post-engine ...`，产物与 `run_preflight` gate/receipt 语义一致。

**Verification:** `test_mega_fn_budget` 绿（两条 offender 消失）且 `test_w3_package_shims` / 相关 CLI 测绿。

---

### U2. 修复 test_mega_fn_budget 门禁红（ship_prep → <600）

**Goal:** 把 `workflow_pack.ship_prep` 从 span 829 压到 <600，让门禁绿，收工编排语义不变。

**Requirements:** R1, R4
**Dependencies:** 无

**Files:**
- Modify: `skills/ai-film-grok/scripts/workflow_pack.py`
- Test: 确认 `test_ship_prep_throughput`、`test_w4_gate_slim`（覆盖它的既有测试）
- Test 边：`test_mega_fn_budget`

**Approach:**
- 把 `ship_prep` 拆成一系列 `_prep_<name>(root, …)` leaf（如 `_prep_manifest`、`_prep_audio`、`_prep_variety`、`_prep_shortlist`、`_prep_scorecard`…），每 leaf 做「读 JSON → 判定 → 错误收集/写 receipt」，`ship_prep` 只剩组装的 orchestrator。
- 参考 `final/stage_*.py`；**不改** `delivery_class`/native/mix 语义。

**Patterns to follow:** `final/stage_*.py` 与 `_append_*` 序列。

**Test scenarios:**
- Edge: span 上限（<600）已被 `test_mega_fn_budget` 测量捕捉，无专用测试必要；但仍保「无新 >800 无 allowlist 覆盖」。
- Error: `ship_prep` 在缺文件 / 无 plate / 后段失败时 `WorkflowPackError` 行为不变。
- Integration: `aifilm closeout-multi`（或 `ship-prep` 入口）在 fixture 上仍成功且相关 receipt 不变。

**Verification:** `test_mega_fn_budget` 绿、无新增白名单残留、收工/交付语义未变。

---

### U3. run_preflight 检查段拆成 _attach_ 纯 leaf

**Goal:** 把 `gates/preflight.run_preflight` 从 span 2108 压到 <600 stack，每个检查段成 `_attach_<name>(root, hard, soft)` 纯 leaf（与既有 `append_premium_vertical_issues` 同形态），入口只组装。

**Files:**
- Modify: `skills/ai-film-grok/scripts/gates/preflight.py`（精简 `run_preflight` 主体为 stage 调用）
- Modify: `skills/ai-film-grok/tests/test_mega_fn_budget.py`（**必须同步**：`run_preflight` 从 `ALLOWLIST` 摘除的同时，删除 line ~102-105 `required` 元组里的 `("gates/preflight.py", "run_preflight")` 条目——否则 peel 后 remove-allowlist 触发 `stale` 断言（test line 88-89/97-100），而保留 allowlist 触发 `required in ALLOWLIST` 断言（line 106）死锁；两步必须同 commit）
- 新增：`skills/ai-film-grok/scripts/gates/preflight_*.py`（如 `_attach_env`/`_attach_structure`/`_attach_narrative`/`_attach_framing`/`_attach_tts_rehearsal`/`_attach_loop_drag`/`_attach_equal_slot`/`_attach_heat` — 与既有 `preflight_premium` 同目录、同形态）
- Test: `skills/ai-film-grok/tests/test_preflight_harness_w3.py`（既有 harness）——补新增 leaf 的 case

**Requirements:** R2, R3
**Dependencies:** 无

**Approach:**
- 沿用 `run_preflight` 现有结构：它已是「每段 lazy import 纯域 + append 到 `hard`/`soft`」。这一步把每个 `try:`（post_plan / premium / structure / narrative / framing / tts / loop / vo_drag / equal_slot / heat…）抽成独立 `_attach_<name>(root, hard, soft)`。
- `run_preflight` 主函数只剩：`root` check → `load pilot/spec/style` → 依序 `_attach_x(...)` → return `{hard, soft}`。
- 复用 `preflight_issues._issue / _append_probe_error`；不发明第二个错误收集路径。

**Patterns to follow:** `preflight_premium.append_premium_vertical_issues`（完美模板）、`_issue`、`_append_probe_error`。

**Execution note:** characterization-first：先在 `test_preflight_harness_w3` 补齐每个新 `_attach_*` 的 fail-mode 覆盖（垃圾 root / 缺文件 / 门红诚实），再切叶。

**Test scenarios:**
- Happy: 每个 `_attach_*` 在「最小可用 root（manifest+film-spec+style）→ hard=[] soft=[]」；带 heat（`heat_scale=max`）→ 相应 code 被补。
- Edge: `root` 不存在 / 是文件 / 无 manifest / 无 spec → 对应 leaf 抛 `PreflightError` 或 append 软/硬 issue（null/[]）。
- Error: `narrative_validate` / `framing_lint` 库缺失或抛异常 → `_append_probe_error` 分支不被吞。
- Integration: `run_preflight` 整体输出与拆分前后完全一致（leaf 数量、code 顺序、fix 文案不可变），由 `aifilm doctor` 手跑确认覆盖率相当。

**Verification:** `test_preflight_harness_w3` 绿 + `run_preflight` span <200 + 整体 `test_mega_fn_budget` 绿（`run_preflight` 不再需要 allowlist 且它已超 800→须摘）。⚠️ 摘除 `ALLOWLIST` 时必须同时从测试 `required` 元组移除 `run_preflight` 条目（见 Files），否则 `test_mega_fn_budget` 会因 `required in ALLOWLIST` / `stale` 冲突而红——这是本单元的「合法红」入口，与门禁对立无关。

---

### U4. 行为零漂移回归 + 门禁最终绿（收口）

**Goal:** 合入前整体回归：所有 target span <600、门禁绿、行为等价、无新 allowlist。

**Requirements:** R3, R4, R5
**Dependencies:** U1–U3

**Files:**
- 无新文件（验证起）

**Approach:**
- 分别跑相关 suite（`test_mega_fn_budget` 红→绿、`test_w3_package_shims`、`test_final_hotpath_contracts`、`test_preflight_harness_w3`、`test_post_plan.py`）。
- 手跑一个 10 镜 fixture（有真 receipts 的存在）走 `doctor` + `final`，确认 `delivery_class/manifest/plate` 语义不变、`preflight verdict` 覆盖率相当。
- peel 后：若改动脚本指纹变 → `make lock-runtime`；按仓规 bump plugin.json + CHANGELOG（若为可交付功能/行为变更波，则 bump）。

**Verification:** `make check-all` 绿（validate+ruff+doctor+pytest -m 'not slow'）。

---

## System-Wide Impact

- **Interaction graph:** `run_preflight` 有 32 个 caller（`cli_quality_ops`、`cli_post`、多测试），被 `cmd_final` / doctor 调用——它变只影响层次、不变签名与返回形状。
- **Error propagation:** 所有 gate 错误仍由 `FilmError`/`PreflightError` 抛到 CLI，不变。
- **State lifecycle:无持久态改动（只读域函数），无 partial-write 风险。
- **API surface parity:** 无公开 CLI / flag / shim 改变。
- **Integration coverage:** 以 `test_preflight_harness_w3` + `test_w3_package_shims` + 手动 doctor/final 回归扫跨 layer。
- **Unchanged invariants:** `delivery_class`、plate≠master、`i2v_provider`、heat/adult floor、pilot 自批——peel 波不得触碰。

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `run_preflight` 某段与后续段有跨段可变依赖（序遍历顺序被破坏） | 已由 codegraph 验证为「逐段纯读 + append」，无共享可变；若发现依赖，先加 `_append_probe_error` 保守处理再拆 |
| `build_render_cmd` 参数装配被移后 byte-identical 破坏 | characterization-first：拆分前后对 `cmd` list 逐字节对比测锁定 |
| 门禁改 test 逻辑（用 allowlist 掩盖而非真拆） | R1 明确禁止新增白名单项；拆分后函数必须 <600 才可移除 allowlist，门禁测试保持 hard |
| CI 因本波合入覆盖不均而绿红翻转 | 采用 `make check-all` + lock-runtime（脚本指纹）双重保护 |

---

## Documentation / Operational Notes

- 更新 `docs/plans/2026-08-07-monolith-orchestrator-relief-todoplan.md` header：标注被本计划接管（`run_preflight`）+ 关闭波状态；不重开历史。
- 若触发 plugin 版本语义变化 → 依仓库 `plugin.json` + `CHANGELOG.md` semver 规则 bump。
- `docs/brainstorms/2026-08-07-orchestrator-monolith-decomposition.md` 为本结构债**单一真相**。

---

## Sources & References

- **Origin document:** [2026-08-07-orchestrator-monolith-decomposition.md](docs/brainstorms/2026-08-07-orchestrator-monolith-decomposition.md)
- Help 板（已 ship 证据）：[2026-08-07-monolith-orchestrator-relief-todoplan.md](docs/plans/2026-08-07-monolith-orchestrator-relief-todoplan.md)
- Related code: `skills/ai-film-grok/scripts/gates/preflight.py` · `skills/ai-film-grok/scripts/cli/cli_post.py` · `skills/ai-film-grok/scripts/workflow_pack.py` · `skills/ai-film-grok/scripts/gates/preflight_premium.py`
- Verify gate: `skills/ai-film-grok/tests/test_mega_fn_budget.py` · `skills/ai-film-grok/tests/test_preflight_harness_w3.py`