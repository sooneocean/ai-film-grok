# Senior Dev 代码质量把控 — Round 16 执行概要

> 身份：Senior Developer（高级开发工程师）· 全栈工程 / 代码质量把控
> 日期：2026-08-06 · 仓库：ai-film-grok · 版本：v2.40.22 → **v2.40.28**
> 指令：用户「依序帮我实现所有 开始」（圣旨协议 = 不重开讨论，逐 Phase 推进到最后含双远端 push）

## 本会话交付（按 Phase 顺序）

### ✅ P2 — 统一错误体系（v2.40.25，已 push 双远端）
- 9 个子系统 `*Error` 改继承 `FilmError`（保留类名 + `RuntimeError` 兼容）：gates 全 7 类 + `final/errors.RenderError` + `post` 两处 `RenderError`/`LipSyncError`。`ValueError` 基类错误**故意不动**（避免破坏既有 `except ValueError`）。
- 新增 `tests/test_error_hierarchy.py`（参数化，9 类 + `RenderTimeoutError` 传递 + `FilmError` 兜底）。
- 双远端实战：push 前 `git fetch --all` 发现 github 比本地多 9 个并行质量 commit → `git merge` 干净收敛（gate 文件 github 未动我们改动）→ 又遇 github 并发前进 2 次 → 重复 fetch→merge→push，**绝不强推**，三端最终一致。

### ✅ P3-2 — 路径外部化（v2.40.26，已 push）
- 新增 `util/paths.py`（`plugin_root()` / `homebrew_bin()` / `build_subprocess_path()` / `first_existing_file`）：`homebrew_bin()` 仅当 homebrew 目录**确实存在**才返回，绝不注入不存在路径 → Linux/CI 可复现。
- 外部化 5 处 macOS-only 硬编码：piper `DEFAULT_ROOT`（`/Users/dex/...` → `plugin_root()/"piper-voices"`，本机解析逐字节一致）+ 3 处 subprocess `PATH`（piper/tts_backend×2/advance）+ ffprobe/ffmpeg 候选补 `/home/linuxbrew/.linuxbrew/bin`。
- 新增 `tests/test_util_paths.py`（4 跨平台用例）。本机 `build_subprocess_path()` 输出与旧 advance PATH 逐字节相同（Mac 零回归）。

### ✅ P3-1 — 模块迁移起手模板（v2.40.27，已 push）
- 首个 legacy 模块迁移：`scripts/ltx23_audio_canary.py`（66 行、**0 importer**）→ `audio/ltx23_audio_canary.py`。`_ROOT` 深度 `parent.parent` → `parent.parent.parent`（下沉一层仍指向 skill 包根，模板路径不变）。删除旧文件，全仓 grep 无 dangling 引用。
- 新增 `tests/test_ltx23_audio_canary.py`（4 用例锁定公共契约）。
- 计划文档 §P3-1 补「迁移配方」6 步（按 importer 数升序挑 0–1 importer 低风险模块 → 定归属 → 调 `__file__` 深度 → grep 防 dangling → 1:1 契约测试 → fetch-merge-push）。进度 **1/109**。

### ✅ P4-1 — 零覆盖基座测试起步（v2.40.28，已 push）
- `util/retry.py`（`retry_call`/`poll_until`，全局重试地基、此前零单测）补 `tests/test_util_retry.py`（8 确定用例，全用 fake `sleep`/`clock` 零等待）。
- P4 路线图：继续覆盖 `util`(validators/subprocess/json_io/errors)/`core`(film_io/paths/constants/media_ops)/`node`(GPU 适配)/`final`(单元层)；P4-2 跟 `film_spec*`/`story_contract`/`subtitle_typesetter`/`edit_policy*`。

## 当前进度

| Phase | 状态 | 版本 |
|---|---|---|
| P0 止血（闸门 fail-closed / logging / CI merge-gate） | ✅ 完成 | v2.40.23 |
| P1 拆巨型函数（起手抽 `resolve_render_dimension`） | 🟡 起手（1/74） | v2.40.24 |
| P2 统一错误体系 + 集中 JSON I/O | ✅ 完成 | v2.40.25 |
| P3-2 路径外部化 | ✅ 完成 | v2.40.26 |
| P3-1 legacy 模块迁移 | 🟡 模板完成（1/109） | v2.40.27 |
| P4-1 零覆盖基座测试 | 🟡 起步（util/retry） | v2.40.28 |
| P5 类型/文档/可复现 | ⬜ 未启 | — |
| 团队 uplift（DoD/ADR/配方文档） | ✅ 文档完成 | — |

## 关键工程纪律（已固化）
- **双远端并发分叉**：本项目 github 远端被另一进程/机器持续并发推送。每次 push 前必 `git fetch --all`；遇 non-fast-forward 即 fetch→merge→重 push，**绝不 force-push**。本会话连续 3 次 race 均收敛，三端最终一致。
- **测试运行**：`bash ./skills/ai-film-grok/scripts/runtime-python` 解析 pyenv 3.11.15（系统 python3 无 pytest）。
- **所有改动均伴生测试、均 commit 并已 push 双远端**（origin Gitea + github）。

## 下一步（迭代推进）
1. P3-1：按「迁移配方」继续迁剩余 108 个 legacy 模块（建议每周 5–10 个，配合 code-review 轮值）。
2. P4：覆盖更多零覆盖基座 + P4-2 校验类模块。
3. P5：类型均匀化（mypy 增量门）、修文档漂移、补 requirements.lock 可复现性。
