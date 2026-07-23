# Changelog

All notable changes to **ai-film-grok** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/) · versioning: [SemVer](https://semver.org/) (mirrors `plugin.json`).

## [1.15.0] — 2026-07-23

### Added — Director methodology injection (P0-1: de-type-bias)

- **Multi-genre beat spines**: `dramatic_function` seven-value enum is now decoupled from the adult six-shot spine. New `genre` field (drama-graph + film-spec schemas) selects the beat spine template. Five genres supported: `adult` (default, backward-compat), `drama`, `mystery`, `arthouse`, `documentary` — each with its own beat spine (key/objective/weight/shots_n).
- `detect_genre()`: parallel to `detect_heat_signals()`, infers genre from brief text markers. Priority: explicit genre field > adult heat signals > genre text markers > default adult.
- `select_beat_spine()` accepts `genre` parameter; non-adult genres return `GENRE_SPINES[genre]` directly (ignores heat signals). Adult genre preserves existing heat-signal logic unchanged.
- `normalize_story()` now returns `genre` + `genre_evidence` fields.
- `project_graph_to_film_spec()` projects `genre` into film-spec top-level + `_plan` metadata.
- `extract_beats()` passes genre to `select_beat_spine()` + uses genre-specific authoring prompts.
- New `references/beat-spines.md` — 40-year director methodology: multi-genre spine definitions, selection logic, backward-compat guarantees, extensibility.
- Updated `directors-lens.md` + `film-spec.md`: `dramatic_function` table now shows generic semantics (de-ecchi-bound) per genre context.
- **Backward compatibility**: `dramatic_function` enum unchanged (write-spec gate unaffected). `genre` defaults to `adult`. Existing projects behave identically.

### Added — Professional director control plane

- Production Book, unified hash-bound human approvals, three rigor modes, precise stale propagation, and no-delete impact previews.
- Style Bible v3 plus Audio/Post Bible department nodes for cast, face, hair, makeup, wardrobe, art, camera, voice, dialogue, sound, music, edit, captions, mix, and Master.
- Agent-native `director`, `department`, and `skill run` CLI primitives with optimistic revisions, dry-run, atomic writes, structured receipts, and idempotent transaction recovery.
- Read-only Shot Packages, strict Style→Cast→State Photo→Keyframe→Clip→Promoted Tail provenance, exact shot-set comparison, Dailies/Selects, Picture Lock, and eleven professional stage gates.
- No-spend golden suite with genre isolation and continuity/audio/approval failure injection; Master delivery now requires real motion evidence, audio, visible captions, `ffprobe` read-back, and current full-film human approval.

## [1.14.4] — 2026-07-22

### Added

- Post-production P1b: `caption-frame-attest` binds explicit human readability approval to current sampled caption frames. Post-audit now fail-closes missing or stale caption-review evidence for v2 burned-subtitle deliveries.

## [1.14.3] — 2026-07-22

### Added

- Post-production P1a: `caption-frame-audit` extracts hash-bound final-MP4 frames during subtitle cues for human readability review. Post-audit now warns when burned-caption visual evidence is missing or stale.

## [1.14.2] — 2026-07-22

### Added

- Post-production P0: `final-delivery` v2 binds final output, subtitle, mix-report, and timeline provenance. Post-audit fail-closes incomplete v2 provenance while retaining a migration warning for legacy v1 sidecars.

## [1.14.1] — 2026-07-22

### Added

- `prompt-compression-attest` binds hash-matched candidate keyframes, clips, frame QA, an all-pass Pilot scorecard, and an existing human Pilot approval to a compression candidate. Evidence completion never promotes or rewrites a production rule.

## [1.14.0] — 2026-07-22

### Added

- `prompt-compression-pilot` writes an ai-film-grok hash-bound candidate ledger. It rejects removal of protected locks and requires same-condition candidate media, QA, scorecard, and human Pilot approval before any compression could be promoted.

## [1.13.9] — 2026-07-22

### Added

- Prompt-budget now supports a review-only token threshold and separates protected repeated locks from compression candidates. Candidates state their estimated saving but cannot be applied automatically; a director-approved Pilot equivalence check remains required.

## [1.13.8] — 2026-07-22

### Added

- `prompt-budget --root <film>` reads prompt-assembly receipts to estimate per-shot and episode input tokens, identify repeated provider-bound lines, and distinguish continuity locks from lines worth reviewing. It is read-only unless `--write` is explicit.

## [1.13.7] — 2026-07-22

### Changed

- Prompt assembly keeps local state-photo instructions in the traceability receipt instead of sending filesystem paths and executor guidance to image/video providers. It also de-duplicates negative constraints and records a local prompt-token estimate per shot.

## [1.13.6] — 2026-07-22

### Added

- Planning-answer dry-runs now return a canonical answer SHA-256 and transaction ID. A formal submission may require that exact ID with `--expected-transaction-id`, and records the binding in planning history.

## [1.13.5] — 2026-07-22

### Changed

- Planning-answer batches are now atomic: a formal write occurs only after the complete in-memory batch passes narrative validation; rejected batches leave graph and history untouched.

## [1.13.4] — 2026-07-22

### Added

- Planning history now packages diagnosis-specific answer templates as copyable planning-answer dry-run commands.

## [1.13.3] — 2026-07-22

### Added

- Planning history emits diagnosis-specific answer templates; unresolved core causality produces only the five-question story card.

## [1.13.2] — 2026-07-22

### Added

- Planning history now classifies stalled progress as no formal answers, unresolved core causality, or answers that did not reduce open fields.

## [1.13.1] — 2026-07-22

### Added

- `planning-history` provides local readiness progression, stalled-round count, and current high-priority authoring blockers.

## [1.13.0] — 2026-07-22

### Added

- Formal planning-answer writes append-only local planning-history entries with changed fields, graph revision, and readiness delta; dry-run remains non-mutating.

## [1.12.9] — 2026-07-22

### Added

- `planning-answer --dry-run` now reports readiness before/after, delta, and the remaining highest-priority authoring batch.

## [1.12.8] — 2026-07-22

### Added

- Planning autopilot now emits a minimal structured answer template and dry-run command for the next authoring batch.

## [1.12.7] — 2026-07-22

### Added

- Planning autopilot now reports a transparent weighted draft-readiness score and lock-review eligibility from unresolved authoring fields.

## [1.12.6] — 2026-07-22

### Added

- Planning autopilot now provides a minimal high-impact authoring batch before deferring lower-risk detail questions.

## [1.12.3] — 2026-07-22

### Added

- Planning autopilot now emits a priority-sorted director questionnaire from canonical `needs_authoring` fields, prioritizing story causality before tactic and coverage detail.

## [1.12.2] — 2026-07-22

### Added

- `planning-autopilot` exposes safe draft-automation steps separately from mandatory human story, lock, Pilot, and final-review checkpoints.

## [1.12.1] — 2026-07-22

### Added

- Director exception ledger now requires approver, approval time, and reviewed clip; historical approvals are visible as pending re-approval rather than silently trusted.

## [1.12.0] — 2026-07-22

### Added

- `director-ledger` centralizes human-approved subtitle carry-over exceptions and binds them to film-spec, drama graph, and final MP4 hashes; post-audit invalidates stale authorization.

## [1.11.9] — 2026-07-22

### Added

- Hard/Continue subtitle carry-over is permitted only by an exact, reasoned, range-bounded, human-approved `subtitle_carryovers` declaration.

## [1.11.8] — 2026-07-22

### Added

- `subtitle-cut-boundaries` blocks subtitle cues that cross authored hard cuts or strict Continue boundaries.

## [1.11.7] — 2026-07-22

### Added

- `subtitle-dialogue-alignment` blocks lipsync dialogue without a cue covering its human-observed delivery end, or without declared subtitle and subject safe areas.

## [1.11.6] — 2026-07-22

### Added

- `audio-provenance` binds canonical lipsync dialogue, local rehearsal-audio bytes, the rendered voice carrier, and the registered final MP4 with checksums.
- Final review and post-audit now reject a stale or missing dialogue-audio source chain, while explicitly distinguishing byte provenance from human sound and lip-sync judgment.

## [1.11.5] — 2026-07-22

### Added

- `speech-performance-timing` binds a measured dialogue rehearsal, its canonical text, the human-observed end-of-line delivery, and at least 0.2s of post-line reaction space.
- `review-final` now blocks lipsync dialogue that has no dialogue-kind TTS evidence, mismatched text, an impossible delivery end, or an immediate cut that removes the reaction beat.

## [1.11.4] — 2026-07-22

### Added

- `performance-timeline` compiles checksum-bound per-shot triggers, actions, reactions, delivery, and mouth-still observations into an ordered film timeline.
- Final approval now fails for content-channel projects when required performance receipts or their timestamp frames are absent, stale, or semantically out of order.

## [1.11.3] — 2026-07-22

### Added

- Performance-fact shot review: content-channel shots now bind human-observation timestamps for playable actions, visible triggers/reactions, dialogue delivery, and on-camera narration without mouth movement to the exact reviewed clip hash.
- Reactions cannot be approved before their declared trigger; the receipt explicitly records that this is human observation rather than automatic mouth, face, or acting recognition.

## [1.11.2] — 2026-07-22

### Changed

- Cleared the repository's ruff backlog with safe and reviewed mechanical fixes; CI now retains hard correctness checks while documenting intentional dynamic-import, compatibility, process-lifetime, and test-scope exceptions.
- Fixed real static defects in re-encode reporting and normalized formatting/imports across scripts and tests.

## [1.11.1] — 2026-07-22

### Added

- Content-channel contract: narration, dialogue, playable performance and motion now have separate fields and receipts.
- `content_channels_strict` rejects narration copied into visual action, on-camera dialogue with lipsync disabled, lipsync without dialogue, and reactions triggered by text rather than an in-scene event.

### Changed

- Prompt construction never falls back from `nar` to a motion/action instruction; narration is audio-only unless authored as a separate visible action.
- User-source fidelity runs only when `source_excerpt` exists, so stock/generated plans are no longer falsely judged as overwriting user text.

## [1.11.0] — 2026-07-22

### Added

- **CI hardening**: `validate-core` job now installs `ruff` and runs `ruff check` + `ruff format --check` on all scripts; `test-full` runs the complete test suite (including slow tests) as a hard gate.
- **`pyproject.toml`** for the skill: ruff configuration (line-length 100, target Python 3.11), pytest config with `slow` marker, and `tool.ruff.lint` rules (E, F, I, W, B, UP, SIM).
- **BGM cache**: 5 CC0-licensed R&B loops (`assets/bgm/rnb/`) with `index.json` and per-track license files, providing a safe default for `--music-mood rnb` without external dependencies.
- **Adapter smoke tests** (`tests/test_adapter_smoke.py`): parametrized tests verifying all I2V/TTS/BGM adapter modules import and expose their expected provider classes and methods.
- **I2V retry logic**: `grok_oauth_video.py` adapter now retries `video_generate` with exponential backoff (2s, 4s) on 429 rate-limit errors.

### Changed

- **`util.py` adoption**: 11 script files now use the shared `read_json`/`write_json` helpers instead of inline JSON I/O, reducing duplication and ensuring consistent error handling.
- **Subprocess timeouts**: all 16 script files with `subprocess.run`/`call`/`Popen` now specify `timeout=` (30s–300s depending on operation type), preventing indefinite hangs in CI and production.
- **Slow test markers**: 33 test files containing subprocess/FFmpeg/network calls are now marked `@pytest.mark.slow`, enabling fast CI (`pytest -m "not slow"`) and full CI (`pytest` without filter).
- **Version bump** to 1.11.0 (semver: minor — new features + hardening).

## [1.10.6] — 2026-07-22

### Changed

- Post-audit now requires complete passing final-review scorecard and seven-dimension screening evidence.
- Final review approval is invalidated when its bound MP4 hash differs from the current final.

## [1.10.5] — 2026-07-22

### Added

- Final-delivery sidecar hash consistency checks for final, subtitles, audio, and timeline.
- `export-desktop` now writes `项目状态/delivery-manifest.json` with exported file hashes and sizes.

## [1.10.4] — 2026-07-22

### Added

- Post-audit hard checks for subtitle double-burn risk and title plate duplication risk.
- Final delivery subtitle burn metadata and compose caption artifacts are now cross-checked.

## [1.10.3] — 2026-07-22

### Added

- Post-audit subtitle timecode/range validation.
- Audio mix loudness evidence reporting.
- Vertical safe-area audit with strict-vs-warning behavior.

## [1.10.2] — 2026-07-22

### Changed

- `export-desktop` now requires a current post-audit receipt with no hard failures or stale evidence.
- Internal preview/render paths remain available before formal delivery export.

## [1.10.1] — 2026-07-22

### Added

- Post-audit freshness binding for final, subtitle, audio mix, timeline, and final-review hashes.

### Changed

- Dispatch now treats stale post-audit receipts as delivery blockers.

## [1.9.1] — 2026-07-22

### Changed

- Connected `post-audit` freshness and hard-failure status to dispatch for post and verified stages.
- Dispatch now reports post-audit receipt presence, delivery readiness, hard failures, and warnings.

## [1.10.2] — 2026-07-22

### Added

- write-spec injects act/climax flesh `sound_plan` sfx accents from heat/sound_cues.
- Adult `pilot pick` prefers undress → union → rhythm.
- Dual-climax spine (`双高潮`/`两轮` or hardcore ≥90s); `templates/premises-adult.md`.

## [1.10.0] — 2026-07-22

### Added

- `spice_level` (suggestive/explicit/extreme) with `HEAT_VO_SPICE_TOO_MILD` for dual-entendre-only act VO.
- VO–motion alignment lint; sex_pose variety (`SEX_POSE_STALE`); montage craft lint + hardcore craft spine inject.
- Act auto flesh SFX (`impact/breath/leather`); hardcore/extreme vocal_color opt-in defaults.
- `aifilm heat vo-suggest` / `heat soften-log`; coitus review dimension; pose pack docs.
- Max sex duration floor raised to **30%** (hardcore still 40%).

### Changed

- Adult plan seeds denser nar + multi `sex_pose`; heat check reports spice/pose/sfx/montage.

## [1.9.0] — 2026-07-22

### Added

- Adult max planning spine (`ADULT_MAX` / `HARDCORE_MALE`) from brief heat signals — no silent pin without evidence.
- Coitus six-beat grammar lint + size-ladder lint in `_heat_arc` (`coitus_strict` / `size_ladder_strict` for hardcore).
- Sex I2V motion templates (`rhythm_hips`, `union_settle`, `finish_arch`, …) and heat-aware coverage.
- Prompt coitus readability HARD line for act/climax; `aifilm heat check`; adult-max film-spec template + playbook.

### Changed

- `plan run` projects `heat_phase` / `coitus_beat` / spicy `nar` seeds and `coitus_grammar.beats` when adult brief detected.
- Plugin minor **1.9.0** — adult production capability pack.

## [1.8.11] — 2026-07-22

### Added

- Unified `aifilm post-audit --root` post-production audit with JSON and Markdown receipts.
- Hard checks for final media presence/QA, final hash freshness, approved full-film review, open reshoots, and delivery sidecar.
- Evidence capture for final, review, subtitles, delivery, and open director notes.

## [1.8.10] — 2026-07-22

### Changed

- Connected the production evidence ledger to dispatch for media, rough, and verified stages.
- Dispatch now surfaces a hard production-evidence gate before bulk motion when canonical graph, current projection, or user-approved pilot evidence is missing.

## [1.8.9] — 2026-07-22

### Added

- Read-only `aifilm production-evidence --root` ledger for story, pilot, motion, audio, subtitle, and delivery evidence.
- Bulk readiness remains false until canonical story semantics, current projection, and user-approved pilot evidence exist.

### Changed

- Production QA evidence is now surfaced as one machine-readable report instead of scattered receipt inspection.

## [1.8.8] — 2026-07-22

### Changed

- Extracted the story idea → draft Drama Graph `plan run` route.
- Preserved authoring questions, draft state, optional film-spec seed, and force behavior.

### Added

- Regression coverage for missing sources and authoring-only one-liner plans.

## [1.8.7] — 2026-07-22

### Changed

- Extracted canonical `plan project` projection into a dedicated CLI route.
- Kept overwrite confirmation, graph readiness checks, validation summary, and output contract unchanged.

### Added

- Regression coverage for missing graph and overwrite protection.

## [1.8.6] — 2026-07-22

### Changed

- Extracted planning mutations into a dedicated transactional CLI route.
- Preserved revision receipts and explicit fail-closed confirmation for subtree replan operations.

### Added

- Regression coverage for missing graph and unconfirmed replan mutations.

## [1.8.5] — 2026-07-22

### Changed

- Extracted read-only Story Planning validation and status routes into a dedicated CLI module.
- Kept planning write operations in the main entry until their mutation receipts receive isolated route coverage.

## [1.8.4] — 2026-07-22

### Changed

- Extracted read-only Drama Graph validation and status routes into a dedicated CLI module.
- Kept legacy derive/import and canonical project flows in the main entry until their write contracts are separately covered.

## [1.8.3] — 2026-07-22

### Changed

- Extracted environment T2V and panel motion-plan routing into a dedicated media CLI module.
- Preserved existing provider arguments, prompt-file handling, error normalization, and JSON output.

## [1.8.2] — 2026-07-22

### Changed

- Extracted the Skill Registry CLI route into a dedicated module while preserving command names, arguments, and JSON output.
- Added subprocess-bounded CLI smoke coverage for help and registry listing.

## [1.8.1] — 2026-07-22

### Added

- CI smoke gates for the CLI launcher, shipped schemas, registry, and new production modules.
- Regression coverage proving stale execution nodes cannot be dispatched.

## [1.8.0] — 2026-07-22

### Added

- Execution job lifecycle metadata with input hashes, executable dependency gates, and production-mode routing.
- Deterministic `motion-plan` compiler for panel-animation shots.
- `aifilm skill validate` for runtime input/output envelope checks.

### Changed

- Environment plates can load prompts from files, avoiding shell-length and quoting failures.

## [1.7.0] — 2026-07-22

### Added

- Director-grade story planning fields for obstacle, tactic, turn, outcome, state delta, audience question, emotional turn, and actionable authoring questions.
- Hard narrative validation for observable shot state transitions and performance direction: playable action, expectation, subtext, gaze target, reaction trigger, and body state.
- Canonical Drama Graph v2 for derived roots, with explicit draft semantics and stale projection protection.
- Executable Skill Registry metadata, rhythm/coverage lint, and 9:16 platform safe-area lint.

### Changed

- VO rehearsal is now a dependency before motion generation in the execution graph.
- `plan run` remains an honest draft operation and no longer implies that a generated graph is production-ready.

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
