# ai-film-grok 系统级重構優化計畫

> 目標：降低維護成本、消除重複代碼、改善安全性與 Git 倉庫健康度、提升可測試性。
> 優先級：P0（安全/倉理）→ P1（重複消除）→ P2（結構改善）→ P3（架構重構）

---

## P0 — Git 倉理與安全（立即執行）

### P0-1: 移除 Git 追蹤的無關檔案
**問題**：`.kilo/plans/` 和 `backups-skills/` 被 Git 追蹤，應該被忽略。
- `.kilo/` 包含 `node_modules/`（~15MB）和計畫草稿
- `backups-skills/` 包含多個 SKILL.md 副本（潛在敏感內容）
- **動作**：將 `.kilo/` 和 `backups-skills/` 加入 `.gitignore`，並從 Git 移除追蹤

### P0-2: 修復 `.githooks/` 硬编码絕對路徑
**問題**：`.githooks/pre-commit` 和 `.githooks/pre-push` 包含硬编码路徑 `/Users/dex/.agents/skills/gitea-publish/`，在其他機器上會失效。
- **動作**：改為相對路徑或使用 `git config` 動態偵測

### P0-3: 驗證 config.env.example 無真實密鑰
**問題**：`config.env` 包含真實 API 金鑰（MIMO_API_KEY, FISH_API_KEY），雖然已被 .gitignore 忽略，但存在風險。
- **動作**：確認 `config.env.example` 不含任何真實金鑰（已確認為佔位符）

---

## P1 — 代碼重複消除（高影響）

### P1-1: 移除 `slugify` 重複定義
**問題**：`slugify` 在三個地方定義：
- `util/validators.py:11`（典範版本）
- `aifilm_grok.py:93`（完全複製）
- `cli_media.py:94`（透過 `_ag().slugify()` 間接調用 aifilm_grok.py 的副本）
- **動作**：
  - 刪除 `aifilm_grok.py` 中的 `slugify`，改為 `from util.validators import slugify`
  - 刪除 `cli_media.py` 中的 `slugify`，改為 `from util.validators import slugify`

### P1-2: 移除 `atomic_write_text` 重複定義
**問題**：`atomic_write_text` 在兩個地方定義：
- `security_policy.py:216`（典範版本）
- `util/json_io.py:25`（功能相同但參數名不同，且 import 在函式內部）
- **動作**：刪除 `util/json_io.py` 中的 `atomic_write_text`，改為從 `security_policy` 匯入

### P1-3: 移除 `run`（subprocess）重複定義
**問題**：`run` 函式在 `aifilm_grok.py:114` 是 `util.subprocess.run` 的完整複製，但 `render_final.py` 的版本多了 `-nostdin`。
- **動作**：刪除 `aifilm_grok.py` 中的 `run`，改為 `from util.subprocess import run`

### P1-4: 移除 `read_json` 重複定義
**問題**：`aifilm_grok.py:86` 定義了 `read_json` 作為 `util.require_json` 的別名，但 `util/__init__.py` 已有軟版本 `read_json`。
- **動作**：刪除 `aifilm_grok.py` 中的 `read_json`，改為 `from util import require_json as read_json`（保持行為一致）

### P1-5: 移除 `aspect_dims` 重複定義
**問題**：`aspect_dims` 在 `aifilm_grok.py:101` 和 `util/validators.py:19` 完全重複。
- **動作**：刪除 `aifilm_grok.py` 中的 `aspect_dims`，改為 `from util.validators import aspect_dims`

### P1-6: 統一 `utc_now` 實現
**問題**：四個模組各有不同的 `utc_now` 實現，行為不一致（微秒保留、時區後綴）。
- **動作**：將所有模組導向 `util.time.utc_now` 作為唯一典範

---

## P2 — 結構改善（中高影響）

### P2-1: 為 `scripts/` 目錄添加 `__init__.py`
**問題**：`skills/ai-film-grok/scripts/` 缺少 `__init__.py`，不是完整的 Python package。
- **動作**：添加 `__init__.py` 使目錄成為 proper package

### P2-2: 提取 `aifilm_grok.py` 中的 CLI 子命令模組
**問題**：`aifilm_grok.py` 7,739 行，包含 95+ 個 `cmd_*` 函式，其中許多是薄封裝器。
- **動作**：將較大的內聏邏輯函式提取到 `cli_` 子模組：
  - `cli_init.py` — `cmd_init`, `_cmd_init_in_place`, `_infer_medium_from_theme`
  - `cli_write_spec.py` — `cmd_write_spec`, 五個 `_compatibility_*` 函式
  - `cli_graph.py` — `cmd_graph`, `_cmd_graph_legacy`
  - `cli_director.py` — `cmd_director`, `cmd_review_shot`, `cmd_review_contract`
  - `cli_audio.py` — 所有音頻相關 `cmd_*` 函式
  - `cli_heat.py` — `cmd_heat`, `cmd_preflight`, `cmd_cinematic_audit`
  - `cli_quality.py` — `cmd_quality`, `cmd_quality_closure`, `cmd_quality_ledger`
  - `cli_state_index.py` — `cmd_state_index`, `cmd_promotion_report`
  - `cli_assets.py` — `cmd_assets`
  - `cli_plan.py` — `cmd_plan`, `cmd_workshop`
  - `cli_dispatch.py` — `cmd_dispatch`, `cmd_advance`, `cmd_autopilot`
  - `cli_craft.py` — `cmd_craft`, `cmd_selects`

### P2-3: 提取 `render_final.py` 中的渲染階段
**問題**：`render_final.py` 4,350 行，`render_final()` 函式本身 2,250 行。
- **動作**：將渲染管線階段提取到子模組：
  - `subtitle_layout.py` — `split_units`, `_split_one_soft`, `_ensure_caption_density`, `unit_timings`
  - `subtitle_overlay.py` — `sub_png`, `mkcard_video`, `_wrap_title_lines`
  - `voice_policy.py` — `_locked_voice_role`, `validate_voice_language_locks`, `voice_for_shot`, 等
  - `narration_validation.py` — `validate_linear_narration`, `_legacy_validate_linear_narration`, `flatten_shots`
  - `media_concat.py` — `concat_videos`, `concat_audio_segments`（結構幾乎相同）
  - `audio_track_builder.py` — `build_native_track`, `build_vocal_color_track`

### P2-4: 拆分 `edit_policy_heat.py`
**問題**：`edit_policy_heat.py` 4,015 行，混合了熱度策略、編輯策略和鏡頭排序。
- **動作**：拆分为 `edit_policy.py`（已有）、`heat_policy.py`、`shot_sequencing.py`

---

## P3 — 架構重構（長期）

### P3-1: 統一錯誤處理
- 為 `FilmError` 添加 `code` 和 `details` 字段
- 統一所有模組的錯誤導入路徑

### P3-2: 型別提示補全
- 為缺少 `from __future__ import annotations` 的模組添加
- 統一 `utc_now` 返回類型

### P3-3: 測試基礎設施改善
- 根目錄 `tests/` 使用 proper package imports 而非 `sys.path.insert`
- 添加 `__init__.py` 到測試包

---

## 實施順序

```
P0-1 → P0-2 → P0-3 → P1-1 → P1-2 → P1-3 → P1-4 → P1-5 → P1-6 → P2-1 → P2-2 → P2-3 → P2-4 → P3-1 → P3-2 → P3-3
```

每個階段完成後運行 `make check-all` 驗證。
