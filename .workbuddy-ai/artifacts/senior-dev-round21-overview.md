# Round 21 · P4-2 测试缺口补漏 — `core/film_io` 首测 + 迁移 import 修复

> 角色：Senior Developer（高级开发工程师）｜驱动：圣旨协议 "go"（续 P4 测试覆盖）
> 提交：`a8a8eb4` → 双远端（Gitea + GitHub）同步，divergence 0

## 交付内容

1. **新增 `tests/test_core_film_io.py`（9 用例）** — 覆盖 `core/film_io.py` 全部 8 个对外契约：
   - `empty_manifest`：结构形态（title/theme/aspect）、portrait 9:16 维度（width>0 且 height>width）、必需键齐备；`gates` 恰有一个 `True`（键 `brief`）；`created_at`/`updated_at` 为含 `T` 的 ISO 字符串。
   - `film_dirs` / `ensure_tree`：7 个子目录（prompts/canonical/keyframes/clips/audio/out/receipts）均创建且位于 root 下。
   - `save_manifest` / `load_manifest`：往返保留 title/aspect；缺失文件抛 `FilmError`。
   - 导演笔记：`director_notes_path` → `director_notes.json`；`save`/`load` 往返一致；缺失时回退空 `dict`。
   - 纯函数、`tmp_path` 隔离、零网络/ffmpeg 依赖；ruff 干净。

2. **顺带修复 Round 18/19 迁移遗留的测试 import 断点**（恢复整套 `tests/` 可收集）：
   - `tests/test_closed_loop.py`：`from color_grade` → `from post.color_grade`（R18 把 `color_grade` 迁到 `post/`）。
   - `tests/test_professional_golden.py`：`from golden_suite` → `from gates.golden_suite`（R19 把 `golden_suite` 迁到 `gates/`）。
   - 修复前这 2 处 `ModuleNotFoundError` 会让整套 `pytest tests/` 在收集期直接中断（CI `Core pytest` 步此前 abort、0 用例运行）；修复后收集恢复零错误。

3. **版本 `2.40.38`**（plugin.json + CHANGELOG 条目）。

## 验证结果

| 门禁 | 结果 |
|------|------|
| `make doctor` | ✅ 全绿（`core_readiness.ok=true`、`runtime_lock.ok=true`、`film_spec_schema.ok=true`） |
| 新测试 `test_core_film_io.py` | ✅ 9 passed，ruff 干净 |
| 完整 `tests/`（CI 等价 `-m "not slow"`） | ✅ 收集零错误，**3435 passed** |
| 双远端推送 | ✅ `a8a8eb4` 已到 Gitea + GitHub，divergence 0 |

## 关键决策与注意

- **竞态处理**：推送前 `git fetch --all` 发现 GitHub `main` 已被另一 agent 的 Real-ESRGAN 提交 `1f33058` 抢先合入（占 `2.40.37`，同样改了 CHANGELOG/plugin.json）。本地 rebase 到 `github/main`，解决 2 处冲突 → 我的 film_io 工作升到 **`2.40.38`**（条目置顶于 `2.40.37` 之上），保持线性历史、无 force-push。
- **23 个既有失败（非本轮引入）**：散落 `test_comfy_recovery` / `test_h3_flf_media_pack` / `test_production_*` / `test_dispatch_compact` / `test_next_actions` 等无关文件。与本轮改动零关系（我的 `test_core_film_io.py` 9 用例全过、2 个修过的文件也通过），属独立的测试稳定化工作流。
- **本地 `make check-all` 的 ruff 步有 75 个 `scripts/` 既有违规**（F405/SIM105 等）：CI 钉死 `RUFF_VERSION=0.15.10` 但 ruff 步只扫 `scripts/`、**不扫 `tests/`**；我的新增文件在 `tests/` 下，与这些既有基线无关，不构成门禁阻塞。

## 下一步 P4 候选（确定性优先）

- `core.emit`、`util.spine_helpers`、`final.render_defaults` / `voice_mix_config` / `caption_text`。
- `node.*` / `final.bgm_spotting` / `enhance` / `io` / `tts_tracks` / `watchdog` 可能依赖运行时/外部，需先确认可模拟。
- 另可立项：① 23 个既有测试失败的稳定化；② `scripts/` 75 个 ruff 违规清理（独立 phase）。
