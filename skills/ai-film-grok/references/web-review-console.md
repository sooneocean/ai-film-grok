# 验片 + 选素材 · localhost 互动控制台

> 架构、安全模型、运行方式、数据契约与门禁语义。代码入口：`scripts/web_core.py`、
> `scripts/asset_picker.py`、`scripts/gate_panel.py`、`scripts/review_ui.py`（stdlib）、
> `scripts/web_api.py`（FastAPI 网关）、`scripts/onboarding.py`、`scripts/web/console.html`。

## 1. 定位

一个**仅绑 127.0.0.1** 的本地评审控制台：人在浏览器里看片、选素材（BGM / 角色 /
声线 / 镜头候选 / 场景 / 道具）、推进起步向导，并把选择以**单一真相**方式落回流水线既有
文件。浏览器是薄前端，**绝不发明生产状态**。

### 1.1 导演指挥中心（Phase A–C）

```bash
aifilm director-center open --root <film>
aifilm director-center wait --root <film> --stage pilot
aifilm takes compare --root <film> --shot-id s01
aifilm takes select --root <film> --shot-id s01 --take-id <id>
```

| API | 作用 |
|-----|------|
| `GET /api/live` | 人审收件箱 · queue · activity |
| `GET /api/events` | pipeline-events 尾 |
| `GET /api/takes` · `?shot=` | 多 take 索引 / 对比 |
| `POST /api/takes/review` | Select/Reject take |

放行写 ledger/manifest；Web 不执行 H3/final。

**review_mode**（Phase D）：`async_dailies`|`gate_each`；`director-center set-mode|blockers`。


## 2. 架构

```
                 ┌──────────────────────────────────────────┐
   浏览器 ───────▶│  web_core.py  (框架无关安全内核, 单一真相) │
 (console.html)  │   token / loopback / 安全路径 / 哈希绑定    │
                 └───────────────┬──────────────┬────────────┘
                          stdlib  │              │  FastAPI
                                 ▼              ▼
                        review_ui.py      web_api.py
                          (http.server)    (uvicorn)
                                 └──────┬───────┘
                                        ▼
              asset_picker / gate_panel / onboarding / core.film_io
```

- **两套传输，一套真相**：`review_ui.py`（标准库 `http.server`）与 `web_api.py`
  （FastAPI）都只调用 `web_core` 做鉴权 + loopback 校验，再委托同一批域函数
  （`asset_picker.select_asset`、`gate_panel.collect_gates`、`onboarding.*`、
  `review_control.*`）。路由表在 `scripts/web_routes.py`（单一真相）。
  网关测试（`tests/test_web_api.py` · `tests/test_web_routes.py`）与标准库测试
  （`tests/test_web_console.py`）验证**相同安全契约 + API 覆盖**。无 FastAPI 时网关测试自动跳过。
- 前端 `console.html`：原生 JS，无构建步骤，玻璃拟态 + 磁吸 + 粒子 hero
  （`prefers-reduced-motion` 时全部降级），含深/浅色主题、ARIA tablist、键盘方向键导航、
  焦点环、`aria-live` 状态播报、音频懒加载（`preload="none"`）、长列表分块渲染。

## 3. 安全模型（不可退）

1. **仅 127.0.0.1**：服务器只监听回环地址；`Origin` 必须等于 `http://127.0.0.1:{port}`，
   否则 POST 直接 403。
2. **一次性 token + invite**：`GET /` 用 `?invite=` 兑换后种 `HttpOnly; SameSite=Strict`
   cookie；其余请求靠 `X-Review-Token` 头或 cookie。坏 token → 401。
3. **绝不回传密钥**：服务端错误体只有 `error` / `detail`，不含任何 secret。
4. **路径越界 404**：`/media-lib/..%2f..` 等经 `safe_media_path` 归一化后越界即 404。
5. **哈希绑定 + 冲突 409**：每次写都带上游文件（catalog + film-spec）的 sha256 与
   `expected_revision`；stale 标签页 → 409，**且绝不改动 manifest / ledger**。
6. **门禁 fail-closed 403**：见 §5。

## 4. 数据契约（单真相）

| 写操作 | 落盘位置 | 说明 |
|---|---|---|
| 任意选择 | `receipts/selection-ledger.json`（哈希绑定 + revision） | 审计轨迹，永不丢 |
| 任意选择 | `receipts/<kind>-selection.json` | 各类型选择回执 |
| `kind=shot` | `manifest.json` `clips[shot_id].status="approved"` | **唯一**进 manifest 的类型；缺失时 bootstrap 最小 manifest（schema v2） |
| `kind=voice` | `film-spec.json` `cast_voices[slot]=voice` | 把控制台的声线选择钉进生产 TTS |
| `kind=character` | `assets.json` `characters[].selected=true` | 标记控制台锁定的角色 |
| `kind=bgm/scene/prop` | 仅 ledger + 回执 | BGM 规范在 `bgm-library`；scene/prop 为只读展示（来自 film-spec / assets.json） |
| onboarding `go` | `references.json` · `intake/story/story.md` · `intake-manifest.json` · `style-bible.json` | 落盘规范文件后 fail-soft 触发 `advance_local` |

**铁律**：`manifest.json` 只承载 shot 批准；角色 / 声线 / BGM 各自归属 canonical 文件，
控制台**不得**把非 shot 状态发明进 manifest。

## 5. 门禁语义（fail-closed）

- `gate_panel.collect_gates(root)` 聚合既有硬门禁（成人尺度 / 零旁白 / 声线中文锁 等），
  返回 `{gates, hard_fail, blocking}`。
- `blocking` **仅当某 *required* gate `status=="fail"`** 时为 True。
  `unknown` / `skipped` / `warn` **不阻断**（重门禁模块未接入时降级，不误锁）。
- `asset_picker.select_asset` 在 **写盘之前** 调 `collect_gates`；若 `blocking`，抛
  `WebConsoleForbidden` → 两网关都映射为 **403**，且**完全不写 ledger / 不绑 manifest**
  （与「冲突 409 不改 manifest」同构）。
- 门禁模块缺失时**降级放行**（允许），权威强制仍由流水线自身门禁负责。

## 6. 运行

```bash
# 标准库服务器（零新增依赖 · 生产主入口）
aifilm review-ui serve --root <你的 film 根目录>
# stdout URL → http://127.0.0.1:<port>/console?token=…
# 单壳导航：起步 | 选素材 | 验片(iframe /review) | 门禁 | 仪表

# FastAPI 网关（引入 Web 框架，共享同一安全内核）
python skills/ai-film-grok/scripts/web_api.py --root <film 根> --port 0
# stdout 打印 {"ok":true,"url":"http://127.0.0.1:<port>/console?token=...",...}
```

### 页面路由（B1 单壳）

| Path | 内容 |
|------|------|
| `/` · `/console` · `/studio` | 工作台 shell（`console.html`） |
| `/review` | 验片专页（`_PAGE`；shell 内 iframe 或 ↗ 新标签） |
| invite `/?invite=` | 种 cookie 后 303 → `/console` |

API 速查：`GET /api/gates` · `GET /api/assets?kind=` · `POST /api/select`
（body `{kind,asset_id,expected_revision,value?}`）· `GET /api/console-state`
（总览 + 多标签页同步 + **dispatch 只读投影** + queue 快照）·
`GET|POST /api/onboarding[/step|/go]` · 验片
`GET /api/status` · `POST /api/action|settings|advance|final-review-input`。

**console-state 扩展字段（B2，fail-soft）**：

| 字段 | 来源 | 说明 |
|---|---|---|
| `dispatch_projection` | `receipts/dispatch.json`（**不**在 GET 上重算 `build_dispatch`） | `next_cmd` / `next_why` / `stage_public` / `weapon_line` / `blocked_by` / `copy_cmd` |
| `queue_snapshot` | `review_control.runtime_status` + `takes/` 文件数 | running/unknown/job_counts/takes_count |

实现：`scripts/web/projection.py`（shim `console_projection`）· UI 总览「复制命令」只剪贴板，**不**从浏览器执行 H3/final。

**Web 套件（D1）**：`scripts/web/` 为工作台包（`console.html` · `routes.py` · `projection.py`）；
顶层 `web_routes` / `console_projection` 为 hard-compat shim。

### 完整路由表（单一真相）

机读：`scripts/web_routes.py` → `ROUTES`（`stdlib` / `fastapi` 标志 + `handler_id`）。
双网关须与表对齐；`pytest -m console` 中 `test_web_routes` 断言 FastAPI 注册面覆盖
`fastapi=True` 的全部 `/api/*`。

| Method | Path | Domain | stdlib | FastAPI | loopback POST |
|--------|------|--------|:------:|:-------:|:-------------:|
| GET | `/` | review/console page | ✓ | ✓ | — |
| GET | `/console` | console.html | ✓ | ✓ | — |
| GET | `/studio` | console alias | ✓ | — | — |
| GET | `/review` | review HTML | — | ✓ | — |
| GET | `/api/status` | review_control | ✓ | ✓ | — |
| GET | `/api/final-review-template` | final_review_input | ✓ | ✓ | — |
| POST | `/api/action` | review_control | ✓ | ✓ | ✓ |
| POST | `/api/settings` | review_control | ✓ | ✓ | ✓ |
| POST | `/api/advance` | review_control | ✓ | ✓ | ✓ |
| POST | `/api/final-review-input` | final_review_input | ✓ | ✓ | ✓ |
| POST | `/api/stop` | session stop | ✓ | — | ✓ |
| GET | `/api/gates` | gate_panel | ✓ | ✓ | — |
| GET | `/api/assets` | asset_picker | ✓ | ✓ | — |
| GET | `/api/console-state` | asset_picker | ✓ | ✓ | — |
| GET | `/api/file` | workspace media | ✓ | ✓ | — |
| POST | `/api/select` | asset_picker | ✓ | ✓ | ✓ |
| GET | `/api/onboarding` | onboarding | ✓ | ✓ | — |
| POST | `/api/onboarding/step` | onboarding | ✓ | ✓ | ✓ |
| POST | `/api/onboarding/go` | onboarding | ✓ | ✓ | ✓ |
| POST | `/api/onboarding/brief` | onboarding | ✓ | ✓ | ✓ |
| POST | `/api/onboarding/decompose` | onboarding | ✓ | ✓ | ✓ |
| POST | `/api/onboarding/plan` | onboarding | ✓ | ✓ | ✓ |
| POST | `/api/upload` | onboarding | ✓ | ✓ | ✓ |
| GET | `/media/*` | film media | ✓ | ✓ | — |
| GET | `/media-lib/*` | BGM library | ✓ | ✓ | — |

**错误体契约**：HTTP ≥400 时 JSON 同时含 `error` 与 `detail`（同文案），前端只读 `error` 即可。

**VALID_KINDS**：唯一来源 `asset_picker.VALID_KINDS`（`bgm|character|voice|shot|scene|prop`）；
网关不得再维护本地子集。

## 7. 测试 & 评审

- 控制台测试统一打 `pytest.mark.console`；本地跑：
  `pytest -m console`；CI 全量跑 `tests/`（含网关，fastapi 在 `requirements.lock` 内）。
- 改 `web_core.py` / `asset_picker.py` / `web_api.py` / `review_ui.py` /
  `gate_panel.py` / `console.html` 时，**必须**跑控制台测试 + `make doctor`，
  且 `ruff` 干净（见 `AGENTS.md` 迭代循环）。
- 门禁 / 冲突 / 跨域 / 越界 的安全契约由 `test_web_console.py` + `test_web_api.py` 双网关覆盖。
