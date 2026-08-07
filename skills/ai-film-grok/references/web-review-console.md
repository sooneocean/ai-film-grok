# 验片 + 选素材 · localhost 互动控制台

> 架构、安全模型、运行方式、数据契约与门禁语义。代码入口：`scripts/web_core.py`、
> `scripts/asset_picker.py`、`scripts/gate_panel.py`、`scripts/review_ui.py`（stdlib）、
> `scripts/web_api.py`（FastAPI 网关）、`scripts/onboarding.py`、`scripts/web/console.html`。

## 1. 定位

一个**仅绑 127.0.0.1** 的本地评审控制台：人在浏览器里看片、选素材（BGM / 角色 /
声线 / 镜头候选 / 场景 / 道具）、推进起步向导，并把选择以**单一真相**方式落回流水线既有
文件。浏览器是薄前端，**绝不发明生产状态**。

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
  （`asset_picker.select_asset`、`gate_panel.collect_gates`、`onboarding.*`）。
  网关测试（`tests/test_web_api.py`）与标准库测试（`tests/test_web_console.py`）
  验证**相同安全契约**。无 FastAPI 时网关测试自动跳过。
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
# 标准库服务器（零新增依赖）
aifilm review-ui serve --root <你的 film 根目录>
# 打开 http://127.0.0.1:<port>/console?token=<stdout token>

# FastAPI 网关（引入 Web 框架，共享同一安全内核）
python skills/ai-film-grok/scripts/web_api.py --root <film 根> --port 0
# stdout 打印 {"ok":true,"url":"http://127.0.0.1:<port>/console?token=...",...}
```

API 速查：`GET /api/gates` · `GET /api/assets?kind=` · `POST /api/select`
（body `{kind,asset_id,expected_revision,value?}`）· `GET /api/console-state`
（总览 + 多标签页同步）· `GET|POST /api/onboarding[/step|/go]`。

## 7. 测试 & 评审

- 控制台测试统一打 `pytest.mark.console`；本地跑：
  `pytest -m console`；CI 全量跑 `tests/`（含网关，fastapi 在 `requirements.lock` 内）。
- 改 `web_core.py` / `asset_picker.py` / `web_api.py` / `review_ui.py` /
  `gate_panel.py` / `console.html` 时，**必须**跑控制台测试 + `make doctor`，
  且 `ruff` 干净（见 `AGENTS.md` 迭代循环）。
- 门禁 / 冲突 / 跨域 / 越界 的安全契约由 `test_web_console.py` + `test_web_api.py` 双网关覆盖。
