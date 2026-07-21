# Changelog

All notable changes to **ai-film-grok** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/) · versioning: [SemVer](https://semver.org/) (mirrors `plugin.json`).

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
