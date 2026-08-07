# AI Film 控制台 · UI/UX 优化设计方案

> 设计方：UI Designer ｜ 日期：2026-08-07  
> 对象：真实 Web 控制台 `skills/ai-film-grok/scripts/web/console.html`（接 `web_api.py`，CI 门禁已绿）  
> 配套可交互原型：`prototype/console.html`（演示重皮肤 + 仪表盘 + 富化资产审阅方向）

---

## 0. 执行摘要

探查后澄清：**你有两个不同的界面**，本方案针对"真正在用的那一个"。

| 界面 | 文件 | 作用 | 现状 |
|------|------|------|------|
| **真实控制台（本次目标）** | `skills/ai-film-grok/scripts/web/console.html` + `web_api.py` | 验片 · 选素材 · 门禁 · Onboarding | 功能完整、a11y 有底子，但**视觉是典型 AI 味** |
| 静态审阅页 | `tools/gen_review.py` → `bgm-library/review/index.html` | 人工审阅生成候选（approve/reject） | 手抄命令、无设计系统（另一处待统一） |

真实控制台**能用、接好了后端、过得了 CI**——它不是从零建，而是一次**视觉重皮肤 + 信息架构升级 + 资产卡片富化**。核心三个动作：

1. **去 AI 味**：把紫+青渐变 / 径向辉光 / 毛玻璃 / emoji 换成"电影制作工作室"独特美学（温暖墨底 + 单一琥珀强调），建立可复用 token 系统。
2. **补仪表盘**：现有"状态总览"只有几条计数，升级为 KPI Bento + 管线健康 + 活动流。
3. **富化资产审阅**：卡片加波形/指标/筛选/对比，去掉 emoji、补齐空/加载态。

---

## Part 1 · UX 诊断（针对真实控制台，已核对源码）

| # | 断点 | 源码现状 | 严重度 | 代价 |
|---|------|----------|--------|------|
| U1 | **视觉=典型 AI 味** | `--accent:#a78bfa`(紫)+`--accent2:#34d399`(青) 双渐变；`body` 两枚径向辉光 blob；面板 `backdrop-filter:blur` 毛玻璃；🌓 emoji 图标 | 🔴 高 | 一眼"AI 生成感"，不专业、无品牌记忆点 |
| U2 | **无真正仪表盘** | "状态总览"仅 `stats` 几枚计数 + 审计列表，无 KPI/趋势/管线健康/活动流 | 🔴 高 | 进控制台看不到"生产全局"，决策靠翻 tab |
| U3 | **资产卡片单薄** | `.card` 只放标题+meta+裸 `<audio>`+「pick」按钮；无波形、无峰值/RMS/静音指标、无配方摘要、无拒绝路径 | 🟠 中 | 选素材时无法快速判断质量，只能盲听 |
| U4 | **筛选太浅** | 仅 `kind` 切换 chips（bgm/character/voice/shot/scene/prop），无 mood/energy/stem/status/搜索 | 🟠 中 | 大库里找一条资产靠肉眼滚动 |
| U5 | **无空/加载/错误态** | 网格用 `aria-live` 更新但无 skeleton/empty，异步靠 toast 兜底 | 🟡 低 | 拉取慢或空库时界面"发呆" |
| U6 | **emoji 当图标** | 🌓 主题键、📷 上传、✨ 拆解、✅ 启动、🚀 Go | 🟡 低 | 粗糙；与"精致工作室"调性冲突（应换线性图标） |
| U7 | **无对比/批量** | 选素材一次一条，无并排对比、无批量勾选 | 🟡 低 | 挑 BGM/声线时难横向比较 |
| U8 | **动效偏"网感"** | 卡片 hover 上浮 + 渐变描边、canvas 粒子 hero（`opacity .35` 常驻） | 🟢 优化 | 非必要 GPU 开销；reduced-motion 已尊重，但默认偏花 |

**结论**：U1–U2 是"看起来专不专业 / 一眼掌不掌握全局"——最该先改；U3–U4 是选素材效率；U5–U8 是打磨。后端（`web_api.py` 的 `/api/assets`、`/api/gates`、`/api/console-state`、`/api/onboarding/*`）**一律不动**，只改前端。

---

## Part 2 · 信息架构

现有 tab：起步 Onboarding · 选素材 · 门禁 · 状态总览 · 验片↗。建议**在"选素材"前插入"仪表盘"**，并把"状态总览"并入仪表盘，重组为：

```
AI·Film 控制台
├─ 仪表盘 Dashboard*        ← 新增：KPI Bento + 管线健康 + 活动流（取代弱总览）
├─ 选素材 Assets
│   └─ bgm / character / voice / shot / scene / prop（保留）
│       筛选升级：搜索 + mood/energy/stem + 状态 + 对比模式
├─ 门禁 Gates               ← 保留（硬门禁 fail-closed）
├─ 起步 Onboarding          ← 保留（v2 AI 拆解）
└─ 验片 ↗                  ← 保留外链
```

- 侧栏/顶栏常驻：搜索、环境标识、主题、审阅人（沿用现有 token 鉴权）。
- 仪表盘数据直接复用 `/api/console-state` 聚合，不新增后端契约。

---

## Part 3 · 设计系统（替换现有 AI 味 token）

> 用一套温暖"电影工作室"token 替换 `console.html` 顶部 `:root`，并落地 `ui/tokens.css` 双写。

### 3.1 色彩（双主题，去紫青/去辉光）
**深色（默认）**
| Token | 值 | 用途 |
|-------|----|------|
| `--bg` | `#15130f` | 页面底（温暖墨，非纯黑） |
| `--surface` | `#1e1a15` | 面板/卡片 |
| `--raised` | `#272019` | 抬升层 |
| `--line` | `rgba(255,245,230,.09)` | 分隔/边框 |
| `--text-hi` | `#f3ede2` | 主文字 |
| `--text-mid` | `#b9b0a2` | 次文字 |
| `--text-lo` | `#7d7568` | 弱文字 |
| `--accent` | `#e8a463` | 单一琥珀强调（**替换紫青双渐变**） |
| `--ok` | `#84b86a` / `--warn` `#e0b15f` / `--bad` `#d97a5f` / `--info` `#7ba6c4` | 语义色 |

**浅色**：`--bg:#f6f3ee` `--surface:#fffdfa` `--text-hi:#211d18` `--accent:#c8843f`（保对比）。
> 对比度：正文 `#f3ede2` on `#1e1a15` ≈ 13:1（≫ AA 4.5:1）。

### 3.2 字体 / 间距 / 圆角
- 标题 **Space Grotesk**，正文 **Sora**（替换 `system-ui`）；等宽 **JetBrains Mono** 仅用于 ID/命令。
- 间距 4px 节奏 `4/8/12/16/24/32`；圆角 `8/12/16/pill`。
- **去掉** `body` 径向辉光 blob 与常驻 canvas 粒子 hero（U8）；面板去 `backdrop-filter` 毛玻璃，改实色 + 1px 边。

### 3.3 组件（在现有基础上重皮肤）
`Tab`(去渐变填充→实色选中) · `Panel`(实色+细边，去 blur) · `Card`(加波形/指标/配方折叠) · `Chip`(选中态用 accent 实色) · `Button.pick`(去紫青渐变→accent 实色) · `StatCard`(Bento) · `Gate`(保留状态点) · `Toast`(保留) · `EmptyState`/`Skeleton`(新增) · 线性图标替换全部 emoji。

### 3.4 可访问性（保留已有好底子）
- 保留 `:focus-visible` 焦点环、`prefers-reduced-motion`、`role=tab` 键盘导航、`aria-live`。
- 新增：44px 触控区、搜索 `label`、对比模式 `aria`。

---

## Part 4 · 关键界面规范

### 4.1 仪表盘（新增，复用 `/api/console-state`）
- **Bento KPI**：待选/已选/门禁状态/缺口覆盖/管线健康，每卡含微趋势。
- **管线健康条**：BGM/TTS/Video/各生成器 状态药丸 + 在制数。
- **活动流**：最近选择/门禁/生成事件时间线。
- **快捷操作**：刷新门禁 · 重新生成审阅页 · 提交生成。

### 4.2 选素材（富化，接 `/api/assets`）
- **筛选栏**：搜索框 + kind chips + mood/energy/stem/状态段选（后端已按 kind 返回，前端做客户端过滤即可）。
- **资产卡升级**：波形可视化 + 播放/暂停 + 峰值/RMS/静音/BPM 指标 chip + mood/energy/stem 标签 + 配方折叠摘要 + 「选入生产」+「跳过/拒绝」（替换只一个 pick 按钮，U3）。
- **对比模式**（U7）：勾选 2–3 条并排试听/比较指标。
- **状态**：`Skeleton`（拉取中）/ `EmptyState`（该 kind 为空）/ 错误提示（API 失联）。

### 4.3 门禁 / Onboarding（保留 + 去 emoji）
- Gates 面板保留 fail-closed 语义与状态点；仅去 emoji、统一图标。
- Onboarding v2 流程完整保留；🌓/📷/✨/✅/🚀 换线性图标，拆解步骤流保留 reduced-motion 友好。

---

## Part 5 · TODO Plan（落地清单）

> 全部为**前端改造**，不碰 `web_api.py` / `review_ui.py` 后端契约。优先级 P0→P3，工作量人日估算。

### P0 · 去 AI 味 + 设计系统
- [ ] **T1** 用 `ui/tokens.css`（温暖墨+琥珀双主题）替换 `console.html` `:root`；移除 `body` 辉光 blob 与常驻 canvas hero — P0 · 1d · 验收：双主题下无紫青/辉光/毛玻璃；对比度全过 AA。
- [ ] **T2** 全站 emoji → 线性 SVG 图标（主题/上传/拆解/启动/Go/搜索）— P0 · 0.5d。
- [ ] **T3** 字体：`Space Grotesk`+`Sora`+`JetBrains Mono`（Google Fonts，系统兜底），替换 `system-ui` — P0 · 0.5d。

### P1 · 仪表盘
- [ ] **T4** 新增 Dashboard tab，Bento KPI + 管线健康 + 活动流，消费 `/api/console-state` — P1 · 1.5d · 验收：数量与总览一致。
- [ ] **T5** 把现有"状态总览"合并进仪表盘，移除冗余 tab — P1 · 0.5d。

### P2 · 选素材富化
- [ ] **T6** 资产卡升级：波形 + 指标 chip + 配方折叠 + 选入/跳过双按钮 — P2 · 2d · 验收：盲听→可秒判峰值/静音。
- [ ] **T7** 筛选栏：搜索 + mood/energy/stem/状态；客户端过滤 `/api/assets` 结果 — P2 · 1.5d。
- [ ] **T8** 对比模式：勾选 2–3 条并排比较 — P2 · 1d。
- [ ] **T9** 空/加载/错误态：Skeleton + EmptyState + API 失联提示 — P2 · 1d。

### P3 · 打磨
- [ ] **T10** 响应式终检（窄屏 tab 抽屉/横向滚动）+ 键盘可达性走查 — P3 · 1d。
- [ ] **T11** 动效收敛：保留 hover/过渡，去掉非必要粒子，统一缓动 `cubic-bezier(.16,1,.3,1)` — P3 · 0.5d。
- [ ] **T12** 设计 QA：与 token 一致性扫描 + `ruff`/现有 `pytest -m console` 仍全绿（仅改前端，后端不动）— P3 · 0.5d。

**里程碑**：P0（~2d）→ 视觉焕新、去 AI 味；P1（~2d）→ 仪表盘可用；P2（~5.5d）→ 选素材效率跃升；P3（~2d）→ 打磨。总计约 **11.5 人日**。后端契约零改动，CI 门禁不受影响。

---

## 附录 · 与现有架构的衔接

- **零后端改动**：所有数据已存在于 `/api/assets`、`/api/gates`、`/api/console-state`、`/api/onboarding/*`。前端只改呈现。
- **文件落点**：设计 token 抽成 `ui/tokens.css`；`console.html` 仅引用 + 改结构。保持 `web_api.py` / `post/review_ui.py` 不动，CI `console` job 继续绿。
- **静态审阅页（gen_review）**：作为"生成候选人工审阅"独立链路，后续可复用同一套 token 重皮肤，并接入 approve/reject 闭环（见旧方案 T9/T14 思路），本次不纳入。
- **原型说明**：`prototype/console.html` 为**设计方向演示**（数据内联、播放器为可视化占位），用于对齐美学与布局，不等同于改完的真实控制台；真实改造按 T1–T12 在 `console.html` 上落地。
