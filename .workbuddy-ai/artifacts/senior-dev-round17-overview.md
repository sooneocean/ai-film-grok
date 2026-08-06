# 资深开发代码质量把控 · Round 17 概览（P3-1 → P4 → P5 全落地）

> 圣旨协议："依序推进到p5" —— 不重开讨论，把 P3-1 续 → P4 续 → P5 全推进到最后含双远端 push。
> 仓库 `ai-film-grok` · 收尾版本 **v2.40.32** · 三端收敛于 `b9a8850`。

## 交付清单

| Phase | 版本 | Commit | 内容 |
|-------|------|--------|------|
| P3-1 续 | 2.40.30 | `166667d` | 再迁 2 个 legacy 模块（`wan_s2v_probe.py`→`media/`、`stable_audio_adapter.py`→`audio/`）+ 1:1 测试（6 passed）|
| P4 续 | 2.40.31 | `0f1f3cf` | `util/validators.py` 补 `tests/test_util_validators.py`（10 用例：slugify / aspect_dims 纯函数零依赖）|
| P5 | 2.40.32 | `44f5f1e` | P5-2 文档漂移 + P5-3 requirements.lock + P5-1 mypy 增量门禁 |
| merge | — | `b9a8850` | 合并 github/main（h3 8s cap, v2.40.29）并解决版本号冲突，以 2.40.32 为准 |

## P5 三项明细

### P5-2 修文档漂移 ✅
- `make sync-docs` 修 README/GRAPH 的 marker 块版本指针。
- **发现并修复两处 sync-docs 覆盖不到的硬编码指针**：README 顶部「版本」表（2.39.69→2.40.32）、「插件元数据/版本」表（2.39.56→2.40.32）；以及 `skills/ai-film-grok/README.md` 的 generated block。
- 建议：CI 加"README/GRAPH 全部版本指针 == plugin.json"校验（含非 marker 块）。

### P5-3 修可复现性 ✅
- 仓库根**此前无任何依赖清单**（无 requirements.txt / pyproject 依赖 / setup）。
- 生成 `requirements.lock`（479 行，运行时 Python 3.11.15 全环境冻结；已过滤 `-e` editable 本地路径如 `/Users/dex/YDEX/...`，避免破坏克隆复现）。
- `.gitignore` 的 `*.lock` 原忽略它 → 加 `!requirements.lock` 精确放行（注释说明是依赖锁非临时锁）。

### P5-1 类型均匀化（增量门禁已立）✅ 种子就绪，全量迭代中
- `skills/ai-film-grok/pyproject.toml` 加 `[tool.mypy]`：`mypy_path="scripts"` + `explicit_package_bases=true`（解决 `scripts/` 自带 `__init__.py` 引发的 `scripts.util.errors` vs `util.errors` 双映射）。
- Makefile 加 `type:` 目标 = mypy 增量门禁**种子**，首批只扫已干净的 `util/validators.py` + `util/errors.py` → `make type` 通过（Success 无错）。
- 全树扫描暴露 **2315 处类型错误（187 文件）**，集中在 `post/export_composition` / `core/gates` 巨型文件 —— 真多轮工程。按"每清一个模块即把文件名加进 `make type` 扫描列表"逐步推进，不一次性强开全树门禁（会红）。

## 关键纪律
- **双远端 race**：push 前 `git fetch --all`；github/main 已占 2.40.29，本地顺延到 2.40.30+ 避免 CHANGELOG/plugin.json 版本碰撞。三端最终收敛于 `b9a8850`，无强推。
- **runtime-python 契约**：该脚本只打印解释器路径、不转发参数 → 必须用 `RTP=$(bash .../runtime-python)` 捕获后 `$RTP -m pytest/mypy`（Makefile 用 `$$($(RUNTIME_PYTHON))` 同效）。

## 测试与质量门
- P3-1/P4 新增测试 16 passed（6 + 10），合并 github h3 改动后复测仍 16 passed。
- 每个 commit 经 pre-commit 目录校验（bgm-library catalog 契约）通过。
- 新代码 ruff 干净（`--fix` 清 I001）。

## 剩余迭代（非本轮阻塞）
- P3-1 剩 106 个 legacy 模块迁移（按 importer 升序、单 PR 单模块、配套 1:1 测试）。
- P4 继续覆盖 util(subprocess/errors) / core(film_io/paths/constants/media_ops) / node(GPU 适配) / final(单元层)；P4-2 跟进 film_spec*/story_contract/subtitle_typesetter/edit_policy*。
- P5-1 全量类型到 90% 是长期迭代；门禁随模块清理逐步扩展扫描列表。
