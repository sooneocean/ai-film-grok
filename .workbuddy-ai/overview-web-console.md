# 验片 + 选素材 · localhost 互动控制台 — 本轮交付

> 资深开发落地记录（P0–P11，已全部交付并 push 至 origin 双远端）。零新增运行时依赖，复用现有安全内核。

## 已交付（可运行、已测试）

| 文件 | 作用 |
|---|---|
| `scripts/web_core.py` | 框架无关安全内核：token 生成、常量时间比对、loopback 跨域校验、安全媒体路径、哈希绑定、加锁写盘 |
| `scripts/gate_panel.py` | `collect_gates(root)` 聚合现有硬门禁（成人尺度/零旁白/声线中文锁 + i2v_motion/five_track/true_video/dramatic_meaning/anti_hijack/anatomy/cinematic），统一 `{code,status,detail}`；懒导入 + 优雅降级 |
| `scripts/asset_picker.py` | `list_assets` / `select_asset`：选素材落盘，调用现有模块（`bgm_library.get_approved_asset` 校验）、哈希绑定 `catalog+film-spec`、`expected_revision` 冲突 409、`exclusive_file_lock` 写 `selection-ledger.json`。**P5**：`kind=="shot"` 选择额外经 `core.film_io.save_manifest` 写入 `manifest.json` 的 `clips[shot_id]`（`status:"approved"`，缺失时 bootstrap 最小 manifest）；角色/声线/BGM 不写入 manifest（归属各自 canonical 文件） |
| `scripts/review_ui.py`（shim）+ `scripts/post/review_ui.py`（扩展） | `review_ui.py` 重构为 shim 委托 `post.review_ui`；控制台路由（`GET /api/gates`·`/api/assets`·`/api/console-state`·`/api/onboarding`·`/media-lib/...`·`/console` + `POST /api/select`·`/api/onboarding/step`·`/api/onboarding/go`）现位于 `post/review_ui.py`，保留原有 `/` 验片页与所有安全属性 |
| `scripts/web/console.html` | 互动控制台：选素材（BGM/角色/声线/镜头候选）+ 门禁面板 + 起步 Onboarding 向导（参考物→故事→角色→go），玻璃拟态、主题切换、磁吸、轻量粒子 hero，原生 JS 无构建。**P5 深化**：四类面板显示更丰富字段（角色定位/id、声线引擎、镜头候选 provider/model/status）+「已选入生产状态」徽章与按钮置灰；镜头批准按钮提示「写入 manifest.json (clips)」，选择成功后 toast 反馈 manifest 落盘 |
| `tests/test_web_console.py` | 6 个测试：门禁端点、资产端点、select 哈希绑定 + 冲突 409、坏 token 401、跨域 403、media-lib 越界 404、/console 页面 |
| `scripts/web_api.py`（P3 新增） | FastAPI 网关：复用 `web_core` 安全模型，`GET /`·`/console`·`/review`、`GET /media-lib/{path}`、`GET /api/gates`、`GET /api/assets?kind=`、`POST /api/select`、`GET/POST /api/onboarding[/step|/go]`（鉴权 + loopback 双重依赖，冲突 409） |
| `tests/test_web_api.py`（P3 新增） | 5 个网关测试：无 token 401、跨域 403、bad kind 400、onboarding step+go 200 + 规范文件落盘、go 未完成 400 |
| `scripts/onboarding.py`（P4 新增） | 起步向导域模块：`STEPS=("references","story","characters")`；`get_state`/`validate_step`/`submit_step`（哈希绑定 + `expected_revision` 冲突 409）/`go`（fail-closed，落盘规范文件 `references.json`·`intake/story/story.md`·`intake-manifest.json`·`style-bible.json` 后 fail-soft 调 `advance_local`） |
| `tests/test_onboarding.py`（P4 新增） | 7 个测试：空态、references 校验、三步提交 revision==3、stale 冲突 409、go 未完成拒、go 落盘规范文件、go 冲突 409 |
| `tests/test_asset_picker.py`（P5 新增） | 5 个测试：shot 选择绑定既有 manifest（保留 path/provider）、缺失时 bootstrap 最小 manifest、非 shot 不写 manifest、stale 冲突不改动 manifest、无 review_queue 仍软绑定 |

## 质量门

- `ruff check` 全绿（新增/改动文件：web_core / gate_panel / asset_picker / review_ui / web_api / onboarding / tests）
- `pytest -m console` → **41 passed**（stdlib + FastAPI 网关 + asset_picker + onboarding + web_core 共 41 个 console 标记测试；含 P6 门禁 403 / P7 canonical 绑定 / P9 console-state / P8 media-lib 越界 404 等）；未破坏既有验片 UI（完整 `not slow` 套件中 26 个无关失败为仓库既有依赖漂移，非本功能引入）
- `make lock-runtime`（刷新 `runtime-lock.json` 指纹）+ `make doctor` 全绿（`runtime_lock.ok=true`、`failed_checks=[]`）

## 如何运行

```bash
# 起服务（loopback-only，token 打印到 stdout）
aifilm review-ui serve --root <你的 film 根目录>
# 浏览器打开
http://127.0.0.1:<port>/console?token=<stdout 里的 token>
```
选素材面板试听 BGM 走 `/media-lib/`，选择写入 `receipts/*-selection.json`；门禁面板显示硬门禁彩色徽章，失败即拒绝批准/选择。

### 方式二 · FastAPI 网关（P3，引入 Web 框架）

> P3 把同一套安全内核（`web_core`）包进 FastAPI，是「传输换皮」而非行为变更——与 stdlib 服务器共享唯一安全/域真相。无 FastAPI 时 CI 自动跳过网关测试。

```bash
# 起服务（loopback-only，token 打印到 stdout JSON）
python skills/ai-film-grok/scripts/web_api.py --root <你的 film 根目录> --port 0
# stdout 打印 {"ok":true,"url":"http://127.0.0.1:<port>/console?token=...","root":"...","token":"..."}
# 浏览器打开 url 即可
```

FastAPI 网关路由：`GET /`·`/console`（控制台）、`GET /review`（验片页）、`GET /media-lib/{path}`（安全媒体流式）、`GET /api/gates`、`GET /api/assets?kind=`、`POST /api/select`（鉴权 + loopback 双重依赖，冲突 409）。

## 机制设计（门禁与机制）

1. **传输/鉴权**：只绑 127.0.0.1；token + 一次性 invite；跨域拦截；绝不回传密钥。
2. **单真相落盘**：Web 选择一律走现有 Python 模块，不新增状态。
3. **版本冲突**：每次选择带 `expected_revision`，stale → 409。
4. **门禁失败即拒**：硬门禁 fail 时服务端 403 + 前端置灰。

## 交付状态（P0–P11 全部 ✅，已 push 至 origin 双远端）

- ~~P3~~ ✅ FastAPI 网关（`web_api.py` + `test_web_api.py`，继承 `web_core` 安全模型）。
- ~~P4~~ ✅ 起步 Onboarding 向导（`onboarding.py` + `test_onboarding.py` + 路由 + `console.html`）。
- ~~P5~~ ✅ 镜头候选 approve 绑定 `manifest.json`（`asset_picker.py` 的 `clips[shot_id].status="approved"` 复用 `core.film_io.save_manifest`，缺失时 bootstrap 最小 manifest）+ 四类面板深化。
- ~~P6~~ ✅ 门禁 fail-closed 服务端强制 403：`web_core.WebConsoleForbidden`（独立类，**非** `WebConsoleError` 子类，→403）；`asset_picker.select_asset` 在 `collect_gates` 返回 `blocking`（仅 required gate `status=="fail"` 为真）时拒选/拒批准；stdlib（`post/review_ui.py`）与 FastAPI（`web_api.py`）双网关均映射 403。
- ~~P7~~ ✅ canonical 资产绑定：voice→`film-spec.json` `cast_voices`、character→`assets.json` `characters[].selected`、shot→`manifest.json` 精确候选（path/sha256/provider，非 `console` 占位）、scene/prop 只读；`_list_voices` 始终合并 fallback 池（`female_lead`/`male_lead`）避免钉一个藏另一个。
- ~~P8~~ ✅ 控制台体验加固：多标签页 `console_state` 同步轮询、ARIA tablist + 方向键导航、`:focus-visible` 焦点环、aria-live、prefers-reduced-motion 降级（关磁吸/hero 画布/过渡）、`preload="none"` 懒加载音频、窗口化渲染（PAGE=24 + 显示更多）。
- ~~P9~~ ✅ 状态聚合 `GET /api/console-state`（ledger revision/counts、gate blocking+hard_fail、approved manifest clips、onboarding 进度、recent selections）+ 总览 tab。
- ~~P10~~ ✅ 文档 `references/web-review-console.md` + `.github/PULL_REQUEST_TEMPLATE.md`（控制台自检清单）+ `console` pytest marker（`pytest.ini` + `tests/conftest.py`）。
- ~~P11~~ ✅ commit + push（双远端，fetch --all，非强推）：单提交 `cfcd93b`（版本 `2.40.64`），已推 GitHub `4ff33d8→cfcd93b` 与 Gitea `5ec189b→cfcd93b`。

> 注意（rebase 关键）：上游 `review_ui.py` 已重构为 shim（委托 `post.review_ui`），故 P6/P9 的控制台路由须落在 `post/review_ui.py`；`review_ui` 作为 shim经 `git rebase origin/main` 解决冲突时取 HEAD（shim），控制台逻辑并入 `post/review_ui.py`。后续若改控制台服务端逻辑，改 `post/review_ui.py`（与 `web_api.py` 保持一致）。
