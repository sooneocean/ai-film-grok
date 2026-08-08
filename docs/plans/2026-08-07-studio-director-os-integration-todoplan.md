# 导演 OS × 总控台 · 整合 Todo Plan（贴合对齐）

**结论先行：** 你的系统已经有两个导演面 —— **导演 OS（单片操作台）** 和 **总控台（studio 多片总览）**，但两者**没打通**：总控台只显示静态进度条，看不到导演 OS 的直播健康度（卡点 / 门禁失败 / 待审 take / 队列）。本 plan 用「**总控台 = 片厂总览、工作台 = 某片操作台、共享同一份 live 真相**」的统一心智模型，把导演 OS 的 live 数据反向灌进总控台，并让总控台成为「跨片调度台」而非装饰性看板。

**战略约束（沿用 FP-OS plan）：** 扩展现有实体，**禁止新建第二套 DirectorAgent / 第二份 live 投影**。总控台 live 直接复用 `web/director_live_ext.project_director_live`。

| 项 | 值 |
|----|-----|
| 基线 | 运行时 checkout `2.41.36`（总控台已内置；director-center live 已内置单片） |
| 工作树 | `/Users/dex/.grok/plugins/ai-film-grok` |
| 北极星 | 导演在总控台一眼看出「哪部片需要我」→ 一键进该片导演 OS 处理 |
| 不做 | 第二套导演系统 / 总控台另起 live 源 / 重命名用户 7 段进度 |

---

## 0. 现状雷达（两个面各自的真相）

| 面 | 入口 | 数据来源 | 现状 |
|----|------|----------|------|
| **导演 OS（单片）** | 控制台 tab：工作台 / 选素材 / 选Take / 验片 / 门禁 / 起步 | `loadDashboard` → `/api/live`（= `project_director_live(film_root)`） | ✅ **活的**：dispatch.next_cmd/blocked_by、queue.running/failed/reviewable、gates.blocking/hard_fail、human_inbox、activity |
| **总控台（多片）** | tab：总控台（studio） | `build_studio` → `summarize_film`（只读 `manifest.json`） | ⚠️ **静态**：id/title/genre/status/progress%/clips_approved；**无 live** |
| CLI | `aifilm director-center open/status/stop/wait/set-mode/blockers` | 同 `project_director_live` + SSE | ✅ 单片 loopback 指挥中心 |

**标签页清单（控制台）：** `工作台(overview)` · `总控台(studio)` · `选素材(assets)` · `选Take(dailies)` · `验片(review)` · `门禁(gates)` · `起步(onboarding)`。

**关键 seam：** `selectFilm(id)` 已能从总控台切 active film 并 `activateTab('overview')` —— 即「进该片导演 OS」的动作已存在，但**总控台卡片本身不显示该片 live 状态**，且总控台没有跨片「需关注」聚合。

---

## 1. 整合愿景（单一心智模型）

```text
导演 OS（一个 OS，两层视图）
├── 总控台 (studio)        = 片厂总览 / 跨片调度台  ← 新增：每片 live 健康度 + 跨片「需关注」聚合
│     └─ 卡片点「打开此片」→ 切换 active film → 跳该片工作台（已有）
└── 工作台 (overview)      = 某片操作台            ← 已有 live（director-center）
      选素材 / 选Take / 验片 / 门禁 / 起步          ← 已有，live 同源
```

**守则不变量：** 全仓只有一份 live 投影（`project_director_live`）；总控台 live = 对 studio 内每部片调一次该函数聚合而成，绝不另写投影。

---

## 2. 差距清单（为什么「不贴合」）

| # | 差距 | 影响 |
|---|------|------|
| G1 | 总控台卡片只有静态进度，无 blocked_by / gates.hard_fail / queue.failed / reviewable / multi_take | 导演看不出哪部片「卡住/失败/待审」，总控台沦为装饰 |
| G2 | 无跨片「需关注」聚合（阻塞 M / 待审 K / 失败 F / 运行中 R） | 不能从总控台调度，必须逐片点进去 |
| G3 | 总控台无「需关注」优先级排序 / 筛选维度 | 长片单时找不到最该处理的片 |
| G4 | 切换片后总控台卡片不反映「当前在处理的片」与其实时状态 | 总控台与工作台两张皮 |
| G5 | 术语 5 个面（总控台 / director-center / 指挥台 / 选Take / 工作台）语义重叠 | 导演心智混乱，不知自己在「片厂总览」还是「某片操作台」 |
| G6 | dailies/待审 与 总控台 不同源聚合 | 同一「待审 take」在两处数字可能不一致 |

---

## 3. 分 Phase Todo（贴合整合，增量扩展）

> 估点：S≤0.5d · M≈1–2d · L≈3–5d（单人 coding agent 量级）。

---

### Phase 0 — 单一真相 & 术语对齐（先做 · 1d）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|-----|
| **P0.1** | **总控台 live 聚合端点** | `GET /api/studio/live`：对 studio 内每部片并发调 `project_director_live`，返回 `{films:[{id, live}], rollup:{blocked, failed, reviewable, running, multi_take, inbox}}`；带短 TTL 缓存（避免 N 部片同步扫盘卡 UI） | `post/review_ui.py` studio 路由 + `studio.py` 加 `build_studio_live` | 端点返回每片 live + 汇总；并发 + TTL；单测 | M |
| **P0.2** | **术语映射表 + 导航心智** | `references/studio-director-os-map.md`：总控台=片厂总览、director-center=单片 live、指挥台=工作台内动作；tab 面包屑（总控台 › 片名 › 工作台） | stages 指针一行 | 文档 + tab 面包屑落地 | S |
| **P0.3** | **SSE 复用确认** | 复用现有 `web/sse_stream.py` 的 `director-center-sse`；总控台订阅多片 live 增量，不新写流 | `sse_stream` | 现有 SSE 单测不回归 | S |

**完成定义：** 任何 agent 都知道「总控台 live 来自 `/api/studio/live`，复用 `project_director_live`」。

---

### Phase 1 — 总控台卡片接 live 健康度（核心 · 2d）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|-----|
| **P1.1** | **卡片 live 徽章** | `studioCardHtml` 加 live 行：阻塞(blocked_by 数) · 门禁(hard_fail/blocking) · 队列(running/failed/reviewable) · 待审(inbox) · 多 take；从 `/api/studio/live` 取 | `console.html` `studioCardHtml` + `renderStudio` 合并 live | 卡片显示徽章；无 live 时降级空态 | M |
| **P1.2** | **派生「需关注」状态** | 在 draft/producing/released 之上，加 `attention = blocked_by∨hard_fail∨failed>0∨reviewable>0`；用于配色（红/黄/绿）与角标 | `summarize_film` 或前端派生 | 卡片红/黄/绿一致；单测 | S |
| **P1.3** | **排序 / 筛选新增维度** | 总控台默认按「需关注」优先排；筛选加 `阻塞 / 待审 / 失败 / 运行中` | `studioFiltered` + 筛选 UI | 筛选项命中正确片 | M |

**MVP 勾：** 总控台从「进度看板」升级为「可调度看板」。

---

### Phase 2 — 工作室级「需关注」总览（slate triage · 2d）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|-----|
| **P2.1** | **总控台顶部汇总条** | studio 顶显示：共 N 部 / 阻塞 M / 待审 K / 失败 F / 运行中 R；点条跳转对应筛选 | `renderStudio` 顶部 stats | 数字 = `/api/studio/live` rollup | S |
| **P2.2** | **「今日需处理」面板** | 跨片聚合所有 pending_review takes + hard_fail gates + blocked_by，按片分组，每条可「跳到该片 Take/门禁 tab」 | 新 `studio-attention` 面板 + 复用 `selectFilm`+`activateTab` | 点击跳转正确片正确 tab | M |
| **P2.3** | **空/降级态** | live 不可用时（片未起 director-center session）卡片显示「未启动 live」，不报错 | `studioCardHtml` 三态 | 单测/手测 | S |

---

### Phase 3 — 从总控台一键进该片导演 OS（贴合动作 · 1–2d）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|-----|
| **P3.1** | **「打开此片」携带 live** | 卡片「打开此片」→ `selectFilm(id)`（已有）→ 跳工作台（已有 live）；卡片加「当前处理中」高亮 | `selectFilm` + 卡片态 | 切换后卡片高亮 + 工作台 live 正确 | S |
| **P3.2** | **卡片内联快捷动作（不离开总控台）** | 如「标已看」「复制 director-center 启动命令」；命令来自 `project_director_live.console_hint` | 卡片按钮 | 点击不跳 tab 也能处理轻动作 | M |
| **P3.3** | **live 同源校验** | 总控台 `/api/studio/live` 与工作台 `/api/live` 同调 `project_director_live`，数字必一致；加契约测 | 测试 | 同片两处数字相等 | S |

---

### Phase 4 — 实时刷新 & SSE（降负载 · 2d）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|-----|
| **P4.1** | **总控台订阅多片 SSE** | 总控台用现有 `director-center-sse` 增量更新卡片，替代轮询 `/api/studio/live` | `console.html` SSE 客户端 | 片状态变 → 卡片即时更新；单测 | M |
| **P4.2** | **工作台 live 统一走 SSE** | 工作台 `/api/live` 也切 SSE（与总控台同源），降轮询负载 | `loadDashboard` + SSE | 两处刷新一致；perf 不回归 | M |

---

### Phase 5 — 导演 OS 各面收口（深层贴合 · 2d）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|-----|
| **P5.1** | **dailies/待审 与总控台同源** | 总控台「待审」数 = `takes_api` 的 `pending_review` 聚合，与选Take tab 同源 | `takes_api` + 总控台 rollup | 两处待审数相等 | M |
| **P5.2** | **指挥台与总控台协同** | 在总控台可对「当前选中片」触发 `cmdGo`/`cmdAdvance`（作用于 active film），不另开面板 | `cmdGo`/`cmdAdvance` 复用 | 总控台触发 → 该片工作台状态变 | M |
| **P5.3** | **统一 tab 命名 + 面包屑** | 明确：总控台(片厂总览) / 工作台(某片操作台) / 选Take / 验片 / 门禁；加面包屑 `总控台 › <片名>` | `console.html` tab + 面包屑 | 导演清楚所在层级 | S |

---

## 4. 推荐执行波次

| Wave | 内容 | 用户价值 | 依赖 |
|------|------|----------|------|
| **W0** | P0.1 + P0.2 + P0.3 | 总控台有 live 数据源 + 术语清晰 | ✅ done 2026-08-07 |
| **W1** | P1.1 + P1.2 + P1.3 | **卡片显示卡点/门禁/待审/队列** | ✅ done 2026-08-08 |
| **W2** | P2.1 + P2.2 + P2.3 | 跨片「需关注」调度台 | W1 |
| **W3** | P3.1 + P3.2 + P3.3 | 一键进片 + 内联动作 + 同源 | W1 |
| **W4** | P4.1 + P4.2 | SSE 实时刷新 | W2 |
| **W5** | P5.1 + P5.2 + P5.3 | 各面收口统一 | W3 |

**第一可演示里程碑：** W0+W1 —— 总控台卡片从「进度条」变成「带卡点/门禁/待审徽章的可调度卡」。

---

## 5. 明确不做 / 延后（防范围爆炸）

| 不做 | 原因 |
|------|------|
| 新建 `DirectorAgent` / 第二份 live 投影 | 复用 `project_director_live`；守 FP-OS 反模式 |
| 总控台内联视频播放器 | 验片 tab 已负责；总控台只做调度入口 |
| 重命名用户 7 段进度 | 用投影表，不改用户可见进度名 |
| 总控台直接改片（写 manifest） | 一切写操作走该片导演 OS（工作台/CLI），总控台只调度 |
| 全量产品化 | 先 CLI + 控制台；本 plan 纯前端 + 一个聚合端点 |

---

## 6. 验收总表（对照差距 G1–G6）

| # | 能力 | 目标 Wave | 机读证明 |
|---|------|-----------|----------|
| G1 | 卡片显示 live 健康度 | W1 | 卡片徽章单测 |
| G2 | 跨片「需关注」聚合 | W2 | rollup 单测 |
| G3 | 需关注排序/筛选 | W1 | 筛选单测 |
| G4 | 切换片高亮+实时态 | W3 | 卡片态单测 |
| G5 | 术语/面包屑统一 | W0/W5 | 文档 + UI |
| G6 | 待审同源 | W5 | 数字一致性测 |

---

## 7. 需用户拍板的决策点

1. **总控台 live 默认开还是按需？** 默认开（W1 即带），但 N 部片并发扫盘 → 用 TTL 缓存 + SSE 控负载；长片单（>50）是否需要分页/虚拟滚动？
2. **「打开此片」默认落哪个 tab？** 现跳「工作台」（含 live）。是否改为跳「选Take」（若该片有 pending_review）更贴合调度？
3. **术语**：是否把 tab `选Take` 改名 `Take/审片`、`总控台` 保留？还是全改中文心智（`片厂总览` / `某片操作台`）？
4. **写操作边界**：总控台是否允许内联触发 `go/advance`（P5.2），还是严格只读、只做跳转入口？

---

## 8. 工程落地约定

```bash
# 每波结束
make -C "$(git rev-parse --show-toplevel)" check-all
# 功能变更：bump plugin.json + CHANGELOG
# 改 scripts 指纹：make lock-runtime
# 测试：扩 test_web_studio.py（studio live 聚合）+ test_review_ui（端点）+ 现有 console 契约测
# commit message 英文；沟通中文
```

**Provenance：** live 数据只来自 `project_director_live`；总控台不写片，只调度。
**失败语义：** live 不可用时卡片降级（显示「未启动 live」），禁静默假绿。
