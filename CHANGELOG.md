# Changelog

All notable changes to **ai-film-grok** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/) · versioning: [SemVer](https://semver.org/) (mirrors `plugin.json`).

## [1.6.0] — 2026-07-22

### Added

- One Python 3.11+ resolver shared by the CLI launcher and Make targets; `make test` no longer falls back to macOS Python 3.9.
- Canonical Beat `director_board` contract: emotional turn, audience question, image/sound priorities, coverage, cut intent, and explicit approval are required before Beat lock.
- `aifilm review-shot`: deterministic first/middle/last contact sheet, motion/decode evidence, 1–5 director scorecard, timestamp evidence, and source-hash-bound review receipt.
- New film roots require shot-review evidence before an approved clip can enter delivery gates. `aifilm review-contract migrate` upgrades legacy roots without pretending old boolean approvals are new reviews.
- Final reviews for v1.6 roots record timestamped screening evidence. Open reshoot items remain open until explicitly resolved; a later pass cannot silently erase them.

### Changed

- Legacy `graph import` now writes a v2 migration receipt and seeds incomplete Beat contracts as authoring work rather than treating them as locked narrative truth.
- BGM documentation now accurately states that no shared licensed music is packaged; the procedural bed remains the safe default.

## [1.5.0] — 2026-07-22

### Added

- Integrated the vertical-drama upgrade through Phases 1–4: Drama Graph, Skill Registry, deterministic story planning, and asset/state registry.
- Added P0 continuity protections for state-photo/keyframe provenance, I2V first/last handoff, wardrobe no-redress, and keyframe geometry validation.
- Promoted the validated 1.4.3–1.4.8 work into the 1.5.0 plugin release.

## [1.4.8] — 2026-07-22

### Added

- **Phase 4 Asset Registry**: `aifilm assets sync|status|check`
  - `scripts/asset_registry.py` — structured Character / Location / Prop + CharacterState timeline
  - `assets-registry.json` + `receipts/assets-sync.json`
  - wardrobe_variants + cast_state_masters slots + `canonical/cast-states/<id>/`
  - Aligns with `state-index` (missing state photos + re-dress risks)
  - Patches `drama-graph.json` with `characterStates` / `assetRegistry`
  - `plan run` auto-syncs assets after film-spec seed
  - Registry skills: `character.state.update` · `location.bible.build` · `prop.track`
  - Schemas: style-bible locations/props objects · `assets-registry.schema.json`
  - Tests: `tests/test_asset_registry.py`

## [1.4.7] — 2026-07-22

### Added

- **Phase 3 Story Planning**: `aifilm plan normalize|run|project|status`
  - `scripts/story_plan.py` — story.normalize → episode → scene → beat → shot
  - Writes `drama-graph.json` (`mode=planned`) + seeds `film-spec.json` / timeline / bible / manifest skeleton
  - Vertical beat spine (hook→setup→escalate→peak→button); snappy `nar`≤28 + VO-safe `duration_sec`
  - Registry: story.normalize / episode.structure / scene.segment / beat.extract / shot.plan → implemented
  - Tests: `tests/test_story_plan.py` (one-liner DoD ≥3 beats)

### Notes

- Planner is deterministic (no LLM). Agent may refine nar/dsl after `plan run`, then `write-spec`.

## [1.4.6] — 2026-07-22

### Added

- **Phase 1 Vertical Drama Graph (v0)**: `aifilm graph derive|validate|status`
  - `schemas/drama-graph.schema.json` · `scripts/drama_graph.py`
  - Read-only projection from `film-spec.json` → `drama-graph.json` (Episode→Scene→Beat→Shot→Panel)
  - Asset hints (keyframe/clip/prompt presence) + `productionMode` inference
- **Phase 2 Skill Registry shell**: `aifilm skill list|show`
  - `registry/skills.json` (24 skills) · `registry/contracts/skill-envelope.*.json`
  - `scripts/skill_registry.py`
- **dispatch schema_version=2**: additive `graph` · `jobs_summary` · `execution_plan_digest` (HUD slim fields)
- Plan: `docs/plans/2026-07-21-vertical-drama-upgrade.md`
- Tests: `test_drama_graph.py` · `test_skill_registry.py` · dispatch packet asserts

### Notes

- film-spec remains executable source of truth; graph is derive-only (no dual-write yet).
- Skill runner still maps to existing CLI — contracts are envelopes, not full rewrite.

## [1.4.5] — 2026-07-21

### Added

- **状态照检查门（可补生成）**：`aifilm state-index check|plan` · `scripts/state_index_gate.py`
  - 查 missing state photos / undress-anchor / keyframes / continue promote
  - `generate_plan` = 本阶段可执行的补生成清单（目的：运镜转场流畅）
  - 写入 `receipts/state-index.json`；并入 `preflight` + `dispatch` next_actions

## [1.4.4] — 2026-07-21

### Added

- **Keyframe-first · 状态照索引**：`references/keyframe-first-state-index.md`  
  L0 style → L1 cast → L2 `cast-states/{full,partial,undressed,bare}` → L3 keyframe → L4 I2V；视频坏先改 keyframe/状态照。
- Bible field **`cast_state_masters`** + `resolve_state_photo()` in `visual_bible.py`
- Prompt injector emits **`State photo ref:`** + receipt `state_photo_paths` / `keyframe_first_note`
- Docs: SKILL hard gate #10 · hard-defaults · consistency 3b/W7 · style-bible · Agents.md

## [1.4.3] — 2026-07-21

### Added

- **P0 卸装后 still 源链（不回穿）**：片例 `xide-hardcore-thrust`。peak 后禁止 `image_edit(全装 cast)`；必须 `canonical/wardrobe/undress-anchor` 或已脱 still；I2V 锁 first-frame 衣着。
- New lesson: `references/lessons-2026-07-21-wardrobe-no-redress-still.md`
- Docs wired: `SKILL.md` hard gate #9 · `hard-defaults` · `consistency` §1e · `sex-undress-ladder` · `production-discipline` · `ecchi-story` · global `~/.grok/Agents.md`

### Changed

- Clarifies **pixel gate ≠ JSON gate**: `wardrobe_state=bare` with full-cast ref is still a re-dress accident.

## [1.4.2] — 2026-07-21

### Changed

- **卸装阶梯硬底强化**：`apply_wardrobe_continuity` 在 write-spec 继承前镜 `wardrobe_state`；rank 单调不降。
- 新码 **`HEAT_WARDROBE_RE_DRESS`**：后镜穿回更「整齐」的衣服 → `sex_wardrobe_strict` hard fail。
- Prompt 注入 `Costume continuity: NEVER re-dress` when state ≥ partial。
- Docs: sex-undress-ladder · hard-defaults · schema · SKILL。

## [1.4.1] — 2026-07-21

### Changed

- **声线默认**：成片以 **旁白 `nar` + BGM** 主导；`vocal_color`（娇喘语助独立 TTS）**默认关闭**（`voice_tracks.enabled=false` · `vocal_color_gain=0` · `auto_vocal_color=false`）。须显式 opt-in 才混入。
- `render_final` mix 默认 **3 输入**（nar/bgm/native）；无 color stem 时不再生成静音 `vocal_color_track.wav`。
- Docs: `SKILL.md` · `references/voice-tracks.md` · `references/hard-defaults.md` 与默认一致。

### Fixed

- `export_composition.py`: Remotion f-string JS ternaries; restore `build_title_sequence_html` / `build_end_roll_html` for HyperFrames export.
- `resolve_shot_vocal_color` gate: `enabled` default false (was true).

## [1.4.0] — 2026-07-21

### Added

- Root **README**: install paths (GitHub / local), usage logic (八环 + `dispatch`), architecture graph (PNG + SVG + Mermaid), and **pluggable model matrix** (image / I2V / TTS / BGM / lipsync / post / Grok OAuth).
- Shared `scripts/util.py` (`read_json` / `write_json`) required by the sex-floor / preflight path.
- Adult product hard floors (when `heat_scale=max`): sex duration ≥20%, undress ladder, spicy VO on every nar (prior commits on main).

### Fixed

- `preflight.py`: invalid `elif` after `for` (SyntaxError) when heat VO spice blocks run.
- Example `film-spec.example.json` nars now pass `sex_vo_strict` under `heat_scale=max`.
- `runtime-lock.json` refreshed for release fingerprints.

### Changed

- Default I2V season remains **`grok_primary`** (Grok `image_to_video`); Seedance opt-in via profile.
- Architecture diagram updated for grok_primary season.
- Skill-local README points to root docs as the public entry.

### Notes

- Local secrets stay in `skills/ai-film-grok/config.env` (gitignored).
- User skill path is a symlink into this plugin skill directory.
- Incomplete CLI package split kept in local stash (`wip-cli-refactor-pre-1.4-docs`); not part of this release.

## [1.0.0] — 2026-07-21

### Added

- Independent git root at `~/.grok/plugins/ai-film-grok` with GitHub remote.
- `AGENTS.md` absolute-path entry for coding agents.
- GitHub Actions CI: `plugin validate` + pytest.
- Grok plugin packaging: `plugin.json`, slash commands `/ai-film-grok` `/aifilm`.
- Full skill body under `skills/ai-film-grok` (dispatch eight-ring, Imagine I2V, edge TTS, HyperFrames/FFmpeg).

### CI

- GitHub Actions: `validate-core` + `test-full` both required (full suite green on main).
- Pinned deps via `skills/ai-film-grok/requirements.lock`.
