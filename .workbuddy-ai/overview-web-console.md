# 验片 + 选素材 · localhost 互动控制台 — 本轮交付

> 资深开发落地记录（P0–P2）。零新增运行时依赖，复用现有安全内核。

## 已交付（可运行、已测试）

| 文件 | 作用 |
|---|---|
| `scripts/web_core.py` | 框架无关安全内核：token 生成、常量时间比对、loopback 跨域校验、安全媒体路径、哈希绑定、加锁写盘 |
| `scripts/gate_panel.py` | `collect_gates(root)` 聚合现有硬门禁（成人尺度/零旁白/声线中文锁 + i2v_motion/five_track/true_video/dramatic_meaning/anti_hijack/anatomy/cinematic），统一 `{code,status,detail}`；懒导入 + 优雅降级 |
| `scripts/asset_picker.py` | `list_assets` / `select_asset`：选素材落盘，调用现有模块（`bgm_library.get_approved_asset` 校验）、哈希绑定 `catalog+film-spec`、`expected_revision` 冲突 409、`exclusive_file_lock` 写 `selection-ledger.json`。**P5**：`kind=="shot"` 选择额外经 `core.film_io.save_manifest` 写入 `manifest.json` 的 `clips[shot_id]`（`status:"approved"`，缺失时 bootstrap 最小 manifest）；角色/声线/BGM 不写入 manifest（归属各自 canonical 文件） |
| `scripts/review_ui.py`（扩展） | 新增 `GET /api/gates`、`GET /api/assets?kind=`、`POST /api/select`、`GET /media-lib/...`、`GET /console`；保留原有 `/` 验片页与所有安全属性 |
| `scripts/web/console.html` | 互动控制台：选素材（BGM/角色/声线/镜头候选）+ 门禁面板 + 起步 Onboarding 向导（参考物→故事→角色→go），玻璃拟态、主题切换、磁吸、轻量粒子 hero，原生 JS 无构建。**P5 深化**：四类面板显示更丰富字段（角色定位/id、声线引擎、镜头候选 provider/model/status）+「已选入生产状态」徽章与按钮置灰；镜头批准按钮提示「写入 manifest.json (clips)」，选择成功后 toast 反馈 manifest 落盘 |
| `tests/test_web_console.py` | 6 个测试：门禁端点、资产端点、select 哈希绑定 + 冲突 409、坏 token 401、跨域 403、media-lib 越界 404、/console 页面 |
| `scripts/web_api.py`（P3 新增） | FastAPI 网关：复用 `web_core` 安全模型，`GET /`·`/console`·`/review`、`GET /media-lib/{path}`、`GET /api/gates`、`GET /api/assets?kind=`、`POST /api/select`、`GET/POST /api/onboarding[/step|/go]`（鉴权 + loopback 双重依赖，冲突 409） |
| `tests/test_web_api.py`（P3 新增） | 5 个网关测试：无 token 401、跨域 403、bad kind 400、onboarding step+go 200 + 规范文件落盘、go 未完成 400 |
| `scripts/onboarding.py`（P4 新增） | 起步向导域模块：`STEPS=("references","story","characters")`；`get_state`/`validate_step`/`submit_step`（哈希绑定 + `expected_revision` 冲突 409）/`go`（fail-closed，落盘规范文件 `references.json`·`intake/story/story.md`·`intake-manifest.json`·`style-bible.json` 后 fail-soft 调 `advance_local`） |
| `tests/test_onboarding.py`（P4 新增） | 7 个测试：空态、references 校验、三步提交 revision==3、stale 冲突 409、go 未完成拒、go 落盘规范文件、go 冲突 409 |
| `tests/test_asset_picker.py`（P5 新增） | 5 个测试：shot 选择绑定既有 manifest（保留 path/provider）、缺失时 bootstrap 最小 manifest、非 shot 不写 manifest、stale 冲突不改动 manifest、无 review_queue 仍软绑定 |

## 质量门

- `ruff check` 全绿（新增/改动文件：web_core / gate_panel / asset_picker / review_ui / web_api / onboarding / tests）
- `pytest tests/test_web_console.py tests/test_review_ui.py tests/test_web_api.py tests/test_onboarding.py tests/test_asset_picker.py` → **35 passed**（22 既有 + 7 onboarding + 5 asset_picker + 1 网关 shot 绑定；未破坏既有 验片 UI）
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

## 下一步（P5–P9）

- ~~P3~~ ✅ FastAPI 网关已落地（`web_api.py` + `test_web_api.py`，继承 `web_core` 安全模型），满足「引入 Web 框架」。
- ~~P4~~ ✅ 起步 Onboarding 向导已落地（`onboarding.py` + `test_onboarding.py` + `web_api`/`review_ui` 路由 + `console.html` 向导页）：引导用户从「参考物 → 故事 → 角色」逐步录入，`go` 落盘规范文件（`references.json`·`intake/story/story.md`·`intake-manifest.json`·`style-bible.json`）后 fail-soft 触发 `advance_local`，把用户推入流水线。原本计划的「四类面板深化」被此向导需求替换（用户新需求）。
- ~~P5~~ ✅ 镜头候选 approve 绑定 `manifest.json` 已落地（`asset_picker.py` 的 `clips[shot_id].status="approved"` 复用 `core.film_io.save_manifest`，缺失时 bootstrap 最小 manifest；`test_asset_picker.py` 5 测试 + 网关 shot 绑定测试）+ 四类面板深化（角色/声线/镜头显示更丰富字段 +「已选入生产状态」徽章与置灰，`console.html`）。注：场景/道具在控制台暂无对应 picker（pipeline 无对应 canonical 数据源已接好），故未新增面板，仅深化已有四类。
- P6：门禁 fail-closed 接入 approve / select 流程（服务端 403 + 代码；`console.html` 已显示 blocking banner，`asset_picker`/`web_api` 尚未服务端强制 403）。
- P7：打磨（主题 / 响应式 / 安全审查）。
- P8：文档（`references/web-review-console.md`）+ 团队 Code Review 指南 / PR 模板 + CI 纳入。
- P9：commit + push（双远端，`git fetch --all`，勿强推）。

> 决策说明：本轮先把**安全机制内核**与**可运行垂直切片**做实（stdlib，零新依赖），框架包装（FastAPI）作为 P3 在其上叠加——顺序上“先核心后框架”是更稳的资深做法，且不退化现有安全与单真相。
