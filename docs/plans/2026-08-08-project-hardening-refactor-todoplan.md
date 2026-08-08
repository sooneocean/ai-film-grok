# 项目硬化 + 重构总控 TODO Plan（2026-08-08 · 单一硬化执行板）

> **角色**：Senior Developer（高级开发工程师）· 全栈工程 / 代码质量把控
> **日期**：2026-08-08 · **仓库**：ai-film-grok
> **定位**：本档是 **硬化（reliability / security / observability / contract）单一执行板**。结构债（巨石函数 / package 布局）已由其他板接管并 **DONE 或 SHIPPED**，本档 **不再重列**，只补其未覆盖的硬化缺口。

---

## 0. 范围与边界（不重复已 ship 的板）

| 已有板 | 状态 | 本档关系 |
|--------|------|----------|
| `docs/plans/2026-08-05-project-module-refactor.md` | **W0–W7 DONE**（package 布局） | 不重开 |
| `docs/plans/2026-08-07-monolith-orchestrator-relief-todoplan.md` | **SHIPPED core**（orchestrator 舒缓 / mega-fn 预算 / 残留在 bug-driven） | 不重开；其 residual（body/preflight/closeout/dispatch）仅在 thrash 时动 |
| `docs/senior-dev-code-quality-plan-2026-08-06.md` | Phase 0–5 路线图（质量维度） | 本档把其中 **尚未落地的硬化项** 抽成可勾选波次（H2/H5 对应其 P0-1/P0-2/P0-3） |
| `docs/console-e2e-quality-review-2026-08-07.md` | S1–S8 评审（多数已被 2.41.36–37 闭环） | 本档标注每项 **已闭/待办**，不重复 |
| `docs/REVIEW_CHECKLIST.md` | PR 合入门禁清单 | 本档 H2/H5 强化其中"静默 except = blocker"与 lint 门 |

**本档新增、他板未覆盖的硬化维度**：① fail-soft 投影顶层防护与错误边界；② 双 checkout 对账流程（H0）；③ 形状守护延伸到 POST 与 studio-live（H3）；④ 前端韧性/无障碍/主题一致性（H4）；⑤ Director OS 整合硬化 W2–W5（H6）。

---

## 1. 现状快照（实测 · 2026-08-08）

### 1.1 已硬化（✅ 勿当 TODO）

| 项 | 证据 | 来源 |
|----|------|------|
| HTML 页 CSP + X-Frame-Options + nosniff | `review_ui.py:220-226` 发 `Content-Security-Policy`/`X-Frame-Options: SAMEORIGIN` | console-review S3 闭环（2.41.36） |
| SSE 流 nosniff | `review_ui.py:384-388` | — |
| 后端 per-film fail-soft | `studio.py:234-238` `_film_live` 包 `project_director_live` 于 `try/except` → 坏片降级为 `null` | W1 实现 |
| 前端工作台非全有全无 | `console.html:1004` `loadDashboard` 用 `Promise.allSettled` | console-review S1 闭环 |
| Studio 加载 fail-soft | `console.html:1654-1658` `loadStudio` `Promise.all(...).catch(()=>null)` + `mergeStudioLive` 容 null | W1 实现 |
| asset_picker 静默吞异常清零 | `961eddc7 fix: director-center quality closeout S2/S4/S5/S8 (2.41.36)` | console-review S4 闭环 |
| GET 路径 shape parity（前端字段 ↔ 后端返回） | `smoke_console.py` 33 项真实 e2e 已固化 | console-review S2 部分 |

### 1.2 仍缺口（🔴/🟠 本档要收）

| 优先级 | 缺口 | 证据 | 风险 |
|--------|------|------|------|
| 🔴 H1 | `/api/studio/live` 缺 **顶层** 防护：per-film 已 fail-soft，但 `build_studio_live` 聚合层（studio.py:296-333）若抛（如 ThreadPoolExecutor 异常、rollup 组装错）会 500 整页 | studio.py:296-333 无顶层 `try` | 总控台整页挂 |
| 🔴 H2 | **fail-open 闸门**：`production_gates.py:518-519` `except Exception: pass` 后 `return {"ok": True}`；`:709-710` 静默 `return {}` | 代码质量计划 P0-1 | 闸门本应 fail-closed，却吞异常放行——正确性隐患 |
| 🔴 H2 | 全仓 **0 模块 `import logging`**，库代码 `print(json.dumps(...))`（约 185 处） | 代码质量计划 §2 | 运维不可观测 |
| 🟠 H3 | **POST `/api/select` 响应形状无守护**：UI 读 `res.revision`/`res.canonical_binding.bound`/`res.manifest_binding.bound`（console.html:812,826-827），仅 GET 路径被 e2e 锁 | console-review S2 延伸 | 后端改 key 静默弄坏前端 |
| 🟠 H3 | studio-live `rollup` 形状（blocked/failed/reviewable/running/multi_take/inbox）无契约断言 | `tests/test_web_studio.py` 仅测形状存在，未锁 key 集合 | 聚合字段漂移 |
| 🟠 H4 | `prefers-reduced-motion` 未尊重（动画对前庭敏感用户不友好） | console-review §3.5 后续增强 | a11y |
| 🟠 H4 | `loadStudio`/`loadDashboard` 固定 3s 轮询（console.html:923 `syncState`）；可选 `visibilitychange` 省空闲 CPU | console-review S5 | 资源浪费 |
| 🟠 H5 | `test-full`（slow，368 例）未必阻塞合并；无 mypy 门；ruff 未开 `C901` 复杂度 | 代码质量计划 §0 P0-3 | 存量债无门拦 |
| 🔴 H0 | **双 checkout 漂移**：plugin 树有未提交 W0/W1 导演总控台工作（HEAD `f86095aa` 2.41.37），dev 树已提交 `@52c9fd3b` 2.41.25；`workflow_pack.py` 曾出现未提交中途写入导致 `IndentationError` | 两树 git status | 手拷风险 / 启动即崩 |
| 🟠 H6 | Director OS 整合 W2–W5 未做（W0/W1 已 ship）：W2 跨片"今日需处理"面板、W3 内联操作 + 同源校验、W4 SSE 实时、W5 收口 | `2026-08-07-studio-director-os-integration-todoplan.md` | 整合半途 |

---

## 2. 铁律（binding）

1. **单一 live 投影源**：`web/director_live_ext.project_director_live` 是唯一真相；**禁止第二套 DirectorAgent / 第二份 live 投影**（H1/H6 共用约束）。
2. **fail-closed 优先于 fail-open**：任何正确性闸门抛异常必须显式 `raise FilmError(...)` 或返回 `{ok:False, reason}`，**绝不静默 `return {ok:True}`**（H2）。
3. **无静默 except**：`except Exception` 必须 `logger.warning(...)` + 重抛或显式降级；裸 `except: pass` 是 **CR blocker**（H2）。
4. **形状守护即 CI 门**：前端读的任何后端 key（GET/POST/studio-live/投影）必须有对应断言，改名即红（H3）。
5. **不重开已 ship 的结构板**：巨石函数仅在 bug/thrash 触发时 peel；不虚荣冲刺 LOC（引自 monolith-relief 铁律 §5）。
6. **双 checkout 只改当前 `git rev-parse` 树**：改前 `git rev-parse --show-toplevel` 确认；禁止手拷文件（H0）。
7. **行为 vs 结构分 commit**；peel / 硬化 commit 禁 retune heat / `i2v_provider` / pilot / adult floor（引自 IRON）。

---

## 3. 硬化波次（可勾选）

### Wave H0 · 双 checkout 对账 & 单一真相（半日 · 最高优先级）

> 目标：先止血"两树漂移 + 未提交中途写入导致启动崩"，再立流程防复发。

- [ ] **H0.1** 在 plugin 树把未提交 W0/W1 导演总控台工作落盘：`review_ui.py` / `studio.py` / `console.html` / `workflow_pack.py` / `cli_post.py` / `tests/test_web_studio.py` + 两份 untracked plan（`2026-08-07-studio-director-os-integration-todoplan.md`、`references/studio-director-os-map.md`）→ 单 PR 提交（版本 bump 2.41.38 + CHANGELOG）。**提交前先 `ast.parse` 校验 `workflow_pack.py` 无 `IndentationError`**（防中途写入假绿）。
- [ ] **H0.2** 对齐两树：dev 树 `@52c9fd3b`（2.41.25，含"director command center studio mode"）需 `git pull` / `git merge` plugin 树 2.41.37+ 的导演总控台增量，使两树 HEAD 一致。**禁止手拷**。
- [ ] **H0.3** 在 `AGENTS.md` 顶部加"双 checkout 操作铁律"段：① 改前 `git rev-parse --show-toplevel` 确认当前树；② 长写入（如 workflow_pack 大改）期间勿启动服务器，或先 `ast.parse` 自检；③ 提交即同步两树。
- [x] **H0.4** 本档置顶为 **硬化单一执行板**；旧板（module-refactor / monolith-relief / code-quality / console-review）header 指针指向本档"现状快照 §1.1/§1.2"（只改指针，不重列）。**已收口（2026-08-08）**：4 旧板 header 均已加 SUPERSEDED 指针 → 本档 §1.1/§1.2。

**Done 信号**：两树 HEAD 一致 · W0/W1 工作已提交 · AGENTS 有双 checkout 铁律 · 本档为硬化唯一板。

---

### Wave H1 · 可靠性硬化（fail-soft 投影 + 顶层防护）

> 目标：让总控台"单点坏不白屏"，且唯一 live 投影源有错误边界。

- [ ] **H1.1** `build_studio_live`（studio.py:296-333）包一层 **顶层 `try/except`**：聚合抛异常时返回 `{generated_at, active_film_id, films:[], rollup:{}, degraded:True, error: <safe msg>}` 而非 500。`/api/studio/live` 路由捕获后仍 200 + `degraded` 旗，前端渲染"总控台降级"横幅而非白屏。
- [ ] **H1.2** 新增 `web/projection.py` 顶层守卫 `safe_project_live(root, **kw)`：调 `project_director_live` 包 `try/except`，失败返回**确定性降级形状**（与正常形状同 key 集、值为空/零），供所有调用方复用（单模式 / studio / SSE 同源）。
- [ ] **H1.3** `review_ui.py` 单模式 `/api/live` 复用 `safe_project_live`；验证坏片根目录（缺 manifest / 坏 spec）返回降级形状而非 500。
- [ ] **H1.4** 前端：`renderStudioLive` / `loadStudio` 读 `degraded` 旗 → 顶部琥珀色"总控台部分降级"提示（复用现有 skeleton/empty 态），不阻断其余 UI。
- [ ] **H1.5** 配套测：`tests/test_web_studio.py` 加 `test_studio_live_top_level_guard_degrades`（mock `project_director_live` 抛异常 → 仍 200 + `degraded:True`）；`test_projection_safe_degrade_shape` 锁降级形状 key 集 == 正常 key 集。

**Verify：**
```bash
cd "$ROOT/skills/ai-film-grok"
python3 -m pytest tests/test_web_studio.py -q
# 真起服务：aifilm review-ui serve --studio ~/films --port 62999
# curl -s localhost:62999/api/studio/live | python3 -c 'import sys,json;d=json.load(sys.stdin);print("degraded" in d, d.get("degraded"))'
```

**Iron：** 降级形状必须与正常形状 **key 集一致**（否则前端判空逻辑失效）；不得为"不报错"而隐藏 `degraded`。

---

### Wave H2 · 可观测性 & 静默 except 清零

> 目标：fail-closed 闸门 + 结构化日志替代静默吞异常。对应 code-quality 计划 P0-1/P0-2。

- [ ] **H2.1** 引入 `util/logger.py`（封装 stdlib `logging`，带 `module`/`film_id` 上下文字段）；库代码 `print(json.dumps(...))` 改 `logger.debug(structure)`。CLI 输出层（stdout 进度）保留 `print`，业务/库代码禁 `print`。
- [ ] **H2.2** **fail-closed 化 `production_gates.py`**：`518-519` 与 `709-710` 的 `except Exception: pass → return {ok:True}/{}` 改为：记录 `logger.error` + 抛 `FilmError("gate evaluation failed", code="GATE_EVAL")` 或返回 `{ok:False, reason:"gate evaluation error"}`。**先补表征测试锁当前（错误）行为，再改**。涉及 `gates/` 全部 `except Exception` 审计（production_gates / preflight / narrative_rebind / cinematic_gate / quality_gates）。
- [ ] **H2.3** 全仓静默 except 清零：用 `grep -rnE "except Exception" scripts/ | grep -iE "pass|return \{\}"` 列清单，逐个改为 `log + re-raise/显式降级`。`asset_picker.py` 已清（2.41.36），勿重复。
- [ ] **H2.4** `REVIEW_CHECKLIST.md` 把"静默 except = CR blocker"（已有 C5.4）加粗，并在 `make check-all` 加 ruff 规则 `B902`（bare except）/ `BLE001`（`except Exception` 无处理）作新代码门。

**Verify：**
```bash
cd "$ROOT/skills/ai-film-grok"
python3 -m pytest tests/test_production_gates.py -q   # 含 fail-closed 表征测试
grep -rnE "except Exception" scripts/gates/ | grep -iE "pass|return \{\}"  # 期望空
```

**Iron：** 闸门 fail-closed 语义不得在硬化 commit 改（如 silent 改 heat/pilot）；只动异常处理，不动物理判定。

---

### Wave H3 · 契约/形状守护（shape parity 延伸）

> 目标：把 console-review S2 的 shape parity 从 GET 延伸到 POST 与 studio-live，锁成永久 CI 门。

- [ ] **H3.1** `smoke_console.py` 加 **POST `/api/select` 响应形状断言**：每次 `pick()` 后断言 `res` 含 `revision`(int)、`canonical_binding.bound`(bool)、`manifest_binding.bound`(bool)（对应 console.html:812,826-827 读取字段）。后端改 key → CI 红。
- [ ] **H3.2** `tests/test_web_studio.py` 加 `test_studio_live_rollup_keys`：断言 `rollup` 严格等于 `{blocked,failed,reviewable,running,multi_take,inbox}`（不多不少），且每片 `live` 形状与 `project_director_live` 正常输出 key 集一致。
- [ ] **H3.3** 加 `test_projection_shape_parity`：锁 `project_director_live` 输出 key 集（dispatch/queue/gates/human_inbox/activity/session）；任何 key 增删 = 测试红（防止投影源静默漂移，H1 降级形状同此 key 集）。
- [ ] **H3.4** 把上述断言接入 CI `console` 作业（`make smoke-console` 已跑 33 项，叠加 H3.1–H3.3），作为 **required status check**。

**Iron：** 形状守护只断言"key 存在 + 类型"，不绑定业务值，避免脆性。

---

### Wave H4 · 前端韧性 + 无障碍 + 主题

> 目标：复用既有三态、补 a11y、省资源。对应 console-review S1/S5/§3.5 后续项。

- [ ] **H4.1** 三态复用：每类素材泳道（assets tab）独立 `try/catch` 渲染 skeleton/empty/error（S1 已 `allSettled`，这里补"单泳道 error 态"UI 而非整列空）。
- [ ] **H4.2** `prefers-reduced-motion`：CSS `@media (prefers-reduced-motion: reduce)` 关掉非必要过渡/磁吸动画（保留功能性状态切换）。
- [ ] **H4.3** `visibilitychange` 同步替代固定 3s 轮询（console.html `syncState`）：tab 隐藏时停轮询，可见时立即同步一次（S5 省空闲 CPU）。
- [ ] **H4.4** 主题一致性：总控台 studio 面包屑 / 筛选栏 / 卡片在 light/dark/system 三态下对比度达标；复用现有 `--accent` 令牌，不新造色。
- [ ] **H4.5** 模板插值全 `esc()`：新组件沿用；加 `smoke_console` 断言"含 `<script>` 注入的测试素材名被转义"（XSS 纵深防御回归）。

**Verify：** 手测（真浏览器）三态 + 系统主题切换 + reduced-motion；`make smoke-console` 含 XSS 转义断言。

---

### Wave H5 · 测试/门禁硬化（ruff C901 / mypy / CI）

> 目标：把 code-quality 计划 P0-3 落成机器门。

- [ ] **H5.1** `ruff` 开 `C901`（mccabe 复杂度）+ `BLE001`/`B902` 作 **新代码门**（存量债不归本 PR，但禁止新增）；`make check-all` 覆盖本 PR 触及文件零新增错误。
- [ ] **H5.2** 新增 `make type`（mypy 增量）：先扫已干净的 `util/validators.py` + `util/errors.py`，每清一个模块把文件名加进扫描列表；逐步扩到 `core/gates/final`（不一次性强开全树门禁，会红）。
- [ ] **H5.3** `test-full`（slow，368 例）设为 **required status check**（否则不拦合并）；`console` 作业 + `make smoke-console` 永久常驻。
- [ ] **H5.4** CI 加"README/GRAPH 全部版本指针 == plugin.json"校验（含非 marker 块硬编码指针，code-quality §5 P5-2 已手动修一次，需防回归）。
- [ ] **H5.5** `requirements.lock` 复核（code-quality P5-3 已修），CI secret-scan 保持绿。

---

### Wave H6 · Director OS 整合硬化（W2–W5 收口）

> 目标：把 `2026-08-07-studio-director-os-integration-todoplan.md` 剩余波次做完，且严守"单一 live 投影源"。

- [ ] **H6.1 (W2)** 跨片"今日需处理"面板：在 `renderStudioLive` 顶部加聚合 `attention` 队列（来自 H1 rollup + 各片 `attention` 标记），点击跳该片对应 tab（复用 W0 smart-jump）。
- [ ] **H6.2 (W3)** 内联操作（go / advance / 选片）+ **同源校验**：所有操作只经 `project_director_live` 真相校验，禁止新建 DirectorAgent；内联动作调用既有 CLI/后端入口，不重写编排。
- [ ] **H6.3 (W4)** SSE 实时硬化：`web/sse_stream.py` 复用 `safe_project_live`（H1.2）；断线重连 + 心跳；SSE 端点加 `X-Content-Type-Options: nosniff`（已有）；限流防刷。
- [ ] **H6.4 (W5)** 收口：更新整合 plan 状态头为 DONE；`references/studio-director-os-map.md` 加"双 checkout"与"fail-soft"段落；`REVIEW_CHECKLIST.md` 加一条"导演总控台写操作须经失败即拒门禁 + 单投影源"。

**Iron（整合）：** 禁止第二套 DirectorAgent / 第二份 live 投影（W0 铁律）。

---

## 4. 执行序（给短令用）

```text
先 H0（对账落盘，止血两树漂移）
→ H1（顶层 fail-soft，单点坏不白屏）
→ H2（fail-closed 闸门 + 日志，正确性最高杠杆）
→ H3（shape parity 延伸，防后端改名弄坏前端）
→ H4（a11y/主题/轮询，体验收尾）
→ H5（lint/test 机器门，锁住后续所有改动）
→ H6（Director OS W2–W5 收口）
```

每波结束跑 `make check-all` + 相关 `pytest -m console` / `make smoke-console`，并 `make lock-runtime`（若指纹变）。

---

## 5. 成功定义（一轮结束）

| 标准 | 信号 |
|------|------|
| 可靠性 | `/api/studio/live` 顶层防护就位；坏片/坏聚合 → `degraded:True` 200 而非 500；前端有降级横幅 |
| 正确性 | `production_gates` 及 `gates/` fail-closed；无 `except Exception: pass → ok`；`grep` 静默吞异常为空 |
| 可观测 | 库代码无裸 `print(json)`；关键动作/降级有 `logger.warning/error` |
| 契约 | GET/POST/studio-live/投影源 形状均有 CI 守护；改名即红 |
| a11y | `prefers-reduced-motion` 生效；三态复用；主题对比度达标 |
| 门禁 | ruff C901/BLE001 新代码门；mypy 增量；test-full + console 为 required |
| 单一真相 | 双 checkout HEAD 一致；AGENTS 有操作铁律；本档为硬化唯一板 |
| 整合 | Director OS W2–W5 DONE；无第二投影源 |

---

## 6. 与历史板关系

| 旧板 | 关系 |
|------|------|
| module-refactor W0–W7 | **DONE** · 本档不重复 |
| monolith-orchestrator-relief | **SHIPPED** · 结构债以它为真相；残留在 thrash 才动 |
| code-quality-plan Phase 0–5 | 质量路线图；本档 H2/H5 抽其 **未落地硬化项** 成可勾选波 |
| console-e2e-quality-review S1–S8 | 多数已闭环（2.41.36–37）；本档 §1.1 标注、只收 S2 延伸/H4 后续 |
| studio-director-os-integration-todoplan | 本档 H6 接其 W2–W5 收口 |

**非目标（本档不做）：** 虚荣 LOC 冲刺、heat 再拆、一夜删 shim、整文件 migrate `workflow_pack`/hub、为瘦包做垂直大搬家、重写 IRON 产品规则当"硬化"。

---

*Baseline probe: 2026-08-08 · plugin 2.41.37（含未提交 W0/W1）· dev 2.41.25 · CSP 已闭环 · per-film fail-soft 已闭环 · 静默 except 主要在 gates/production_gates 与日志缺失。*
