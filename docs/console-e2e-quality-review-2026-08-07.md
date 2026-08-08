# 控制台功能 e2e 跑通 + 代码质量评审 + 团队技术拉升

> ⚠️ **本板已收口（SUPERSEDED）**：硬化 / 可靠性 / 安全 / 可观测 / 契约缺口统一在 **[单一硬化执行板](./plans/2026-08-08-project-hardening-refactor-todoplan.md)** 跟踪（现状快照 §1.1 已硬化 / §1.2 仍缺口）。本板不再新增 TODO；旧逻辑由 H4–H6 波次退役。

> 资深开发（吴八哥）交付。日期 2026-08-07。
> 范围：`skills/ai-film-grok/scripts/web/console.html` + `scripts/post/review_ui.py` + `scripts/asset_picker.py` + `scripts/smoke_console.py`
> 目标：用真实运行的服务器把"选素材控制台"功能端到端跑通，证明可上线；并据此给团队做代码质量把控与技术拉升。

---

## 0. 结论先行

- ✅ **功能可上线**：扩展后的 `make smoke-console` 在真实 `aifilm review-ui serve` 进程上跑通了 **33 项检查**（原 10 + 新增 23），覆盖"打开→工作台并行加载 6 类素材→选声线→锁定角色并落盘规范文件→选道具→选 BGM→写路径边界"的完整浏览器操作流程。
- ✅ **CI 门禁未破**：`ruff` 通过；`pytest -m console` 77 passed。
- ✅ **质量项收口**：S1 allSettled · S3 CSP（2.41.32）· E4 Shot Card（2.41.34）· **S2 POST shape · S4 可观测降级 · S5 visibility · S8 loopback 注释（2.41.36）**。

---

## 1. 这次 e2e 到底证明了什么（模拟实际操作）

原 `smoke_console.py` 只是**后端契约黑盒**（HTTP 状态/错误码）。它从不验证：
1. 线上服务器返回的是不是 UI 设计师真正交付的那版 film-studio 页面；
2. 前端 `cardHtml()` 读取的字段，后端 `asset_picker.list_assets()` 是否真返回；
3. 用户点"选入生产"后，状态面板和**规范文件**是否真的被驱动。

新增的 e2e 用真实服务器 + 真实 `console.html` + 真实 `asset_picker` 后端，按浏览器里 `console.html` 的实际行为逐条复现：

| 真实操作（浏览器里） | e2e 复现 | 结果 |
|---|---|---|
| 打开 `/console`，看到工作台/选素材/验片三个 tab、琥珀色主题、6 个素材 tab | 断言返回字节含 `data-tab="overview/assets/review"`、`--accent:`、6 个 `data-kind`、且 `loadDashboard/cardHtml/pick` 函数存在 | PASS |
| 工作台启动并行拉取 6 类素材（`loadDashboard` 的 `Promise.all`） | 对 6 类 `GET /api/assets?kind=` 断言 `kind`/`items` 且**非空时每条都带 `cardHtml` 读取的字段** | PASS（bgm 43 / character 1 / voice 3 / prop 1；shot/scene 空为合法降级态） |
| 选声线（点"选用声线"→ `pick()` 带 `expected_revision`） | `GET console-state` 取 R0 → `POST /api/select` 带 R0 → 断言 `revision==R0+1` 且 `console-state` 的 `recent_selections` 含该选择 | PASS（R0→R1→R2→R3→R4 全程连贯） |
| 锁定角色（点"锁定角色"） | `POST select character c1` → 断言响应 `canonical_binding.bound=true` 且直接读 `assets.json` 确认 `characters[].selected=true` | PASS（**控制台真的驱动了管线规范文件，不只是写本地账本**） |
| 选道具 / 选 BGM | 同上流程，断言 `console-state.selection_counts` 增长 | PASS（BGM 命中全局已批准库 43 条） |
| 错误输入 | `POST select kind=nope` → 400；`POST select character=ghost` → 400 | PASS |

**关键价值**：这是首次有测试断言"前端字段契约 ↔ 后端返回形状"一致，且首次证明"控制台点击 → 规范文件落盘"闭环成立。

---

## 2. 代码质量评审（Senior Dev 把关）

按严重程度排序。每条都给文件:行 + 修法。

### S1 · Medium — 工作台加载是"全有或全无"
`console.html:855-870`：`loadDashboard()` 用单个 `Promise.all([...8 个端点]).catch(...)`。只要任一端点 500/超时，**整个工作台白屏**，用户只看到"载入工作台失败"。真实多审核员场景下，某个库（如来自繁忙审核队列的 `shot`）变慢/降级就会拖垮整页。
**修法**：改成每类独立加载——`Promise.allSettled` 或逐类 `await` 包 try，渲染"局部降级"的泳道（项目已有 skeleton/empty 态可复用），而不是整页失败。收益：① 一个库坏不影响其他；② 可渐进绘制，首屏更快。

### S2 · Medium（已部分闭环）— 前端↔后端字段契约无自动守护
`cardHtml()`（`console.html:727+`）读 `it.mood/energy/duration/bpm/path` 等，但此前**没有任何测试**断言 `asset_picker.list_assets` 真返回这些 key。后端改名会静默弄坏渲染。
**修法**：本次 e2e 的"shape parity"检查已闭环 GET 路径。**建议延伸**到 POST 响应：UI 还读 `res.revision`、`res.canonical_binding.bound`、`res.manifest_binding.bound`（`console.html:812,826-827`），把这 3 个字段也写进契约断言，作为永久 CI 门禁。

### S3 · Low/Medium — 服务端 HTML 缺 CSP / X-Frame-Options
`review_ui.py:_send_html` 只发 `X-Content-Type-Options: nosniff`，无 `Content-Security-Policy`。数据虽是内部、`cardHtml` 已用 `esc()` 转义（XSS 风险低），但缺纵深防御。
**修法**：加严格 CSP（页面用内联脚本，故 `script-src 'self' 'unsafe-inline'`，其余收紧）；`/review` 被 iframe 嵌入，用 `X-Frame-Options: SAMEORIGIN`（勿用 DENY，否则挡住自身 iframe）。

### S4 · Low — 吞掉异常，降级不可见
`asset_picker.console_state` 多处裸 `except Exception: pass`（行 471-478/481-491/493-507/526-533）；`_list_bgm`(78-79) 与 `_list_shots`(139-144) 也是 `except: return []`。后果：门禁面板/规范文件读取配置错了，总览**静默降级**，无人知晓。
**修法**：区分"设计为空的返回 `[]`"与"出错的返回 `[]`"——出错时打一条结构化 warning 日志，让运维可见。

### S5 · Low — `expected_revision` 是模块级全局
`pick()` 读写模块级 `expectedRevision`（`console.html` 全局）。单页正确；多窗口不共享该变量时各窗口有各自 revision，但服务端 409 冲突模型仍保护（e2e 已证），仅 UX 可能弹一次陈旧 toast。`syncState()` 每 3s 轮询刷新（行 923）是好模式。
**建议（可选）**：用 `visibilitychange` 重新同步替代固定 3s 轮询，省空闲 CPU。

### S6 · 表扬 — 失败即拒的门禁是范本
`select_asset` 在**任何写之前**检查 `collect_gates().blocking`，且 `gate_panel` 失败开放（未接的重型门禁绝不锁台）。e2e 已证 blocking→403。**团队新写端点应照抄此模式。**

### S7 · 表扬 — 选择哈希绑定 + 版本冲突安全
复用 `review_control` 冲突模型，e2e 证 stale→409。正确且可扩展。

### S8 · 提示 — 仅 loopback 的不变量要写进文档
当前靠 `Origin == 127.0.0.1:port` + token 防跨站，对纯 loopback 评审 UI 足够。若未来暴露出 loopback，**必须**加 CSRF + SameSite cookie + 限流。建议在 `review_ui.py` 顶部注释明确"loopback-only"不变量。

---

## 3. 团队技术拉升建议（可落地）

### 3.1 测试分层（每人都要懂）
| 层 | 工具 | 抓什么 bug | 本功能现状 |
|---|---|---|---|
| 单测 | `pytest -m console` | 纯函数/模块逻辑 | ✅ 77 passed |
| 集成 | `test_web_console.py` via `client` fixture | 路由/契约（内存） | ✅ |
| **真实 e2e** | `make smoke-console`（真实 `aifilm serve` 进程） | **服务真能起、真返回那个 artifact、真实 HTTP 契约** | ✅ 本次补强 |

**教训**：前两层都过了，功能仍可能"上线即坏"——因为没人证明服务器真的把 UI 设计师交付的那版页面吐出来了。真实 e2e 是唯一能抓这类的层，**CI 不能跳过它**。

### 3.2 契约门禁（防漂移）
- 把本次 e2e 的 "shape parity" 固化为永久断言（已完成 GET 路径）。
- 延伸覆盖 POST `/api/select` 响应形状（§2 S2）。
- 前端改字段名 / 后端改 key，CI 直接红。

### 3.3 Code Review 清单（premium 前端 + 失败即拒后端）
- [ ] 任何写操作是否在写之前做失败即拒门禁？（抄 S6）
- [ ] 前端加载是否局部降级而非整页白屏？（S1）
- [ ] 模板插值是否全部 `esc()`？（已做；新组件沿用）
- [ ] 服务端 HTML 是否带 CSP / X-Frame-Options？（S3）
- [ ] 是否有裸 `except: pass` 吞掉可观测错误？（S4，改成日志）
- [ ] 跨标签页/多审核员的状态冲突是否有 409 保护？（已有，新增写端点沿用）

### 3.4 可观测性
- 禁止裸 `except Exception: pass` 隐藏降级；改成结构化日志（warning 级别）。
- 控制台关键动作（选择/锁定/落盘）已有 `recent_selections` 审计轨迹，继续保持。

### 3.5 前端正确模式（已具备，保持）
- 无障碍 tab：`role="tab"` + `aria-selected` + `aria-controls`（✅）。
- skeleton/empty/error 三态（✅，S1 应复用 empty/error 做局部降级）。
- 尊重 `prefers-reduced-motion`（后续增强）。

---

## 4. 如何运行 / 上线状态

```bash
cd /Users/dex/.grok/ai-film-grok
make smoke-console          # 真实服务器 + 33 项真实操作检查
pytest -m console           # 单测/集成（77 passed）
```

- 功能现状：**已上线**（console.html 已在 `f3a96ade` 推送）。本次 e2e 提供"可上线"的客观证据。
- 本次改动：`scripts/smoke_console.py`（扩展真实操作 e2e + 契约守护）。CI `console` 门禁将继续跑它。
- 待跟进：无阻塞项。残余可观测性可在运维侧开 `aifilm.web.asset_picker` WARNING 日志。
