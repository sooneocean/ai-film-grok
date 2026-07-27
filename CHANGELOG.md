# Changelog

All notable changes to **ai-film-grok** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/) · versioning: [SemVer](https://semver.org/) (mirrors `plugin.json`).

## [2.7.4] — 2026-07-27

### Added — creative review and guarded delivery

- A local creative workshop compiles revision- and hash-bound briefs, diagnostics, shot decisions, and provider-neutral export packages without invoking paid providers.
- Review controls require explicit human approval and preserve native character dialogue, narration, music, and effects as separate delivery evidence.
- Final delivery resolves the reviewed artifact from its manifest path and SHA-256 instead of assuming a fixed filename.

### Fixed

- Post-audit is now a required, freshness-bound stage before Desktop export.
- The pre-push release gate serializes expensive checks and rejects stale generated project documentation.

## [2.7.2] — 2026-07-27

### Fixed — release evidence and shipped-surface verification

- Release baselines now require a clean working tree and bind plugin version, source fingerprint, and exact Git HEAD.
- CI collects the main skill tests, the shipped `ai-film-project` validator tests, and root-level plugin contracts.
- Generated status inventory covers every shipped skill instead of only the main skill directory.
- Current documentation consistently describes the eleven-dimension review gate and `grok_primary` I2V default.

## [2.6.0] — 2026-07-24

### Added — Adult max IRON（肉戏/脱衣/露点铁律）

- **肉戏时长硬底 50%**（`DEFAULT_SEX_DURATION_FLOOR=0.50`；hardcore 0.55）；亲密核 ≥60%、setup ≤20%（`heat_arc_strict`）。
- **能脱就脱 / 能露就露**：write-spec `apply_wardrobe_continuity` phase floor（act≥undressed、climax=bare）；新码 `HEAT_BARE_PEAK_MISSING`。
- **max 默认 spice=extreme**；plan 投影 `sex_min_duration_ratio=0.50` + `heat_arc_strict`。
- **持续挑战尺度最大**：`lint_heat_escalation_challenge` — phase 只升不降至 climax；禁 act 后 setup / 早 afterglow；禁 foreplay 长平台；必 climax 峰值。码 `HEAT_ESCALATION_*`；`challenge_max_scale` 默认 true。
- **prompt** Adult max IRON + continuous challenge 行；课 `lessons-2026-07-24-adult-max-iron.md`；测试 `test_adult_max_iron.py`。
- 逃生阀：显式 soft / `adult_max_iron:false` / `sex_*_strict:false`。

## [2.5.1] — 2026-07-24

### Fixed — ep2 声线分轨 + final SRT（P0 写回插件）

- **口白中文 / 角色日文 / 禁乒乓**：`is_character_speech_shot` 在显式 `storyteller|narrator` 时忽略残留 `nar_ja`，避免说书镜误跳日文。
- **SRT 硬失败**：`sub_lead` 默认改为 `0`；`build_subtitle_cues_for_shots` + `write_srt` 写盘前非重叠钳制。
- **阶段卡 / 路由 / 索引**：`stages/voice.md` · `stages/post.md` · `context-routing.json`（voice/rough/sound.design）· `INDEX.md` · `hard-defaults` · `SKILL.md` P0#8 · 全局 `Agents.md`。
- **课**：`references/lessons-2026-07-24-ep2-voice-heat-final.md` · `memory/2026-07-24-*`。

### Changed — Compact orchestration and bounded context

- `aifilm dispatch` now prints a compact, versioned packet by default while preserving the complete audit packet in `receipts/dispatch.json`; `--full`, `--format full`, and `AIFILM_DISPATCH_FORMAT=full` retain the legacy output contract.
- Dispatch separates state collection, full receipt construction, and compact presentation. State-hash and capability caches avoid unchanged recomputation while paid, external, and human-gated actions still force a live capability probe.
- Machine-readable context routing limits ordinary turns to three targeted stage or issue references, and the entry `SKILL.md` is reduced to the execution spine and P0 safety kernel.
- Orchestration bytes, estimated tokens, latency, cache state, and reference counts are recorded separately from provider generation usage and cost.

### Added

- `aifilm advance --root <film> --max-local <n>` safely advances only closed-allowlist local actions with state/transaction binding, fixed argument grammars, verification, and immediate stops at paid, external, pilot, human, duplicate, stale, or failed boundaries.
- Compact/full compatibility, cache invalidation, routing bounds, metrics separation, and safe-advance regression tests.

## [1.28.0] — 2026-07-24

### Added — Exact-first media generation usage accounting

- `aifilm usage status|list|summary|record` reports every T2I, image-edit, I2V/T2V and TTS request from the per-film `receipts/generation-usage.json` ledger.
- xAI OAuth image/video responses retain normalized token counters and exact `usage.cost_in_usd_ticks`; async video submit/poll shares one generation id while real retries remain separate requests.
- Native Grok Build calls can be recorded idempotently by provider request id or output hash. Missing provider usage remains explicitly `unknown` and is never inferred from quota deltas.
- Edge/Voicebox TTS records known local-zero cost; external backends without authoritative usage remain unknown. Dispatch and media-queue metrics expose actual request counts separately from planned budget units.

## [1.26.0] — 2026-07-24

### Added — Evidence-bound premium quality closure

- `aifilm quality-closure package|review|report` creates a no-spend, versioned premium benchmark package; records two independent blind reviews; and distinguishes contract, local-render, real-provider and human-review evidence.
- The report never upgrades contract-only evidence to an artistic-quality claim. Real provider media, current Master QC, delivery package, and two independent reviews remain required.
- Dailies now retain provider/model/cost, source keyframe, objective QA, director score, issue tags, reshoot decision, and selection rationale for each candidate.
- `aifilm next` returns only the highest-priority, receipt-backed repair when an independent review exposes a quality failure.
- Runtime locks now discover every shipped script/module; CI publishes a coverage JSON artifact as a non-blocking trend input.
- P2 boundary extraction: `dialogue_contracts.py` is now the shared pure aggregation used by both `film_spec` and `preflight`; `render_workspace.py` owns final-render path validation and its isolated work directory lifecycle.

## [1.25.0] — 2026-07-23

### Added — Gates & test hardening (audit P1)

- **CI `aifilm doctor` gate**: validate-core job now runs doctor and asserts schema + requirements.lock + script fingerprint integrity (version drift tolerated on CI, script fingerprint drift fails the build).
- **CI schema/commands coverage**: plugin validate now checks all `schemas/*.json` (was 2) and asserts `commands/*.md` launchers reference aifilm dispatch.
- **`tests/test_hard_defaults.py`**: contract-level regression locking the machine-readable rules in `hard-defaults.md` — sex-duration floor 0.30, wardrobe rank monotonicity (no re-dress), 11-dimension scorecard, keyframe 720×1280 9:16, pilot-gate default strict. 11 assertions.
- **`tests/conftest.py`**: shared pytest config auto-injects `scripts/` on sys.path + `film_root` fixture; new tests no longer need the boilerplate.

### Fixed — Architecture debt (audit P2/P3)

- **Broke util↔aifilm_grok circular import**: `FilmError` extracted to dependency-free `util/errors.py`; `util/json_io.py` + `util/validators.py` now top-level import (was 5 lazy `from aifilm_grok import FilmError`); `aifilm_grok.py` re-exports for backward compat. 65 lazy imports no longer needed for cycle avoidance.
- **sound_plan events enum synced**: `SPOT_EVENT_TYPES` expanded to match schema (added music_in/music_out/fade_in/fade_out); was stale at 3 values while schema had 7.
- **FRW host single source of truth**: `frw_lipsync.py` + `env_plate.py` now import `DEFAULT_HOST` from `frw_canary.py` (was 3× hardcoded duplicate).
- **config.env.example**: added 13 missing keys the code actually reads (FRW_API_KEY, FRWCLAW_ROOT, COSYVOICE_*, AIFILM_MUSIC_*, OPENAI_BASE_URL, XAI_BASE_URL, XAI_MODEL, AIFILM_SKIP_PILOT_GATE, SKIP_LOOP_RISK_GATE, AIFILM_STRICT_TTS_REHEARSAL); marked AIFILM_TTS_CMD/AIFILM_LIPSYNC_CMD as DEPRECATED (disabled, unsafe shell).
- **templates/film-spec.example.json**: added `grade` + `color_grade_strict` + `sound_plan.music_spotting` + `sound_plan.audio_tracks` + music_in/out events examples to match v1.22 schema.
- **lessons promotion labels**: 3 same-named lessons (character-stance/editorial-craft/directors-lens) now carry explicit "已晋升" headers pointing to their stable reference.
- **Deleted `grok_oauth.py.bak-pre-sdk-pack-*`** dead file (git retains history).

## [1.24.1] — 2026-07-23

### Added — Director methodology P3 close-out (release hygiene)

- **Scorecard 7→11 dimensions doc-sync**: `director_review.py` already enforced 11 dimensions (rhythm/emotion/theme/performance added to `--approve`), but all docs still said "seven dimensions". Aligned SKILL.md, README.md, and 12 reference files (principles, craft-spine, post-compose, grok-build-sdk, pipeline-methodology, director-self-scorecard, postproduction, auto-dispatch) + scripts (next_actions, craft_spine) to "eleven dimensions"; added the 4 new `--score-*` flags to the SKILL.md `review-final` example.
- **director-methodology.md registered**: the methodology master file existed but was unreachable from the spine/INDEX. Now listed in `references/INDEX.md` (professional-director section) and the SKILL.md on-demand-load table; file count 91→92.
- **Tests synced to 11 dimensions**: `test_delivery_gates.py` screening evidence + score flags expanded 7→11; added sidecar SRT to satisfy the `expect_subtitles` delivery quality gate. All delivery-gate slow tests green.

### Lessons written
- `lessons-2026-07-23-style-lock-from-ref.md` (full P0)
- `lessons-2026-07-23-face-identity-pixel.md` (full P0)
- `lessons-2026-07-23-photoreal-vs-manhua-stability.md` (medium routing)
- INDEX / SKILL / director-methodology cross-links

### Fixed — code hygiene
- ruff: removed unused imports (`math` in face_identity, `re` in style_lock); fixed f-string-without-placeholder; replaced dead `or True` / `False if strict else True` with `True` / `not strict`; `try/except:pass` → `contextlib.suppress` in render_final.
- runtime-lock.json regenerated after script fingerprint drift.

## [1.24.0] — 2026-07-23

### Pixel face-identity
- `scripts/face_identity.py`: aHash+dHash+hist on blurred face-region; multi-anchor enroll
- CLI `aifilm face-identity enroll|enroll-bible|verify|audit|status` → `receipts/face-identity.json`
- `lock-style --cast-master` auto-enrolls; `register-still --require-face-identity` optional hard gate
- `post_audit` uses real receipt (FACE_IDENTITY_DRIFT when not verified)
- tests/test_face_identity.py

## [1.23.0] — 2026-07-23

### Style lock from input ref (P0 stability)
- New `scripts/style_lock.py`: medium presets (anime/manhua/semi_real/photoreal), cast_locks, agent still/I2V prefixes
- CLI `aifilm style-lock plan|apply|check|prompt|recommend`
- `lock-style` gains `--medium` `--char-id` `--from-plan` `--strict-style-lock`
- `prompt_injector` emits MEDIUM LOCK from style_fingerprint
- Docs: lessons-2026-07-23-style-lock-from-ref.md + consistency §1a + SKILL open-film flow

## [1.22.0] — 2026-07-23

### Added — Director methodology injection (P3-1~P3-5: color grading + sound plan + scorecard)

- **film-spec schema**: `sound_plan` gained `music_spotting` (label/start/end/fade/emotion/beat_ref/intensity) and `audio_tracks` (dialogue/SFX/ambience/foley/music gain+ducking); `grade` field (lut/color_temperature/saturation/contrast/brightness/skin_tone_protection/gamma) + `color_grade_strict` gate.
- **Director review scorecard expanded 7→11 dimensions**: added `rhythm`, `emotion`, `theme`, `performance` to `SCORECARD_DIMENSIONS`; `--approve` now requires all 11 `--score-*` flags; `_DEFAULT_ACTION_FOR_DIM` maps each new dimension's fail→action.
- **director-methodology.md**: 40-year director methodology master file (pre-production/production/post-production three-phase + test matrix).
- Tests: `test_color_grading.py`, `test_sound_and_review.py`.

## [1.21.0] — 2026-07-23

### Improved — FFmpeg render safety

- FFmpeg execution is now non-interactive across final and designed-post rendering.
- Designed-post mux and stem outputs render to sibling temporary files, then publish atomically only after size and ffprobe validation.
- Failed or undersized encodes no longer overwrite an existing final output; media command failures retain actionable diagnostics.

## [1.20.0] — 2026-07-23

### Added — Director methodology injection (P1-5/P1-6: scene design + art direction)

- **Location schema expanded** (P1-5): `drama-graph.schema.json` Location upgraded from 2 fields (id/description) to full scene design sheet: `structure`, `timeOfDay`, `lighting`, `palette`, `immutableRules`, `recurringObjects`, `primaryAngles`, `atmosphere`, `color_temperature`, `set_dressing`, `lighting_plot`.
- **locationId filling** (P1-5): `derive_graph()` now populates `locationId` from scene or inferred from shot dsl.location (was hardcoded `None` at both scene + shot level).
- **SCENE_LOCATION_MISSING lint** (P1-5): new continuity lint code fires warning when shot has no locationId — scene continuity cannot be verified without location binding.
- **`art_direction` layer** (P1-6): style-bible.schema now defines structured `art_direction` object with `color_script` (per-scene color temperature + emotional motivation), `visual_motifs` (recurring symbols with narrative meaning), `texture_continuity` (texture elements that must be consistent). Replaces single-string palette/lighting for art direction.
- 9 new tests covering location filling, lint, and schema structure.

### Improved — FFmpeg/ffprobe reliability

- Added shared non-interactive FFmpeg/ffprobe execution and structured media probing.
- Unified timeout, missing-tool, invalid-output, and full-decode errors across media QA, duration checks, and master delivery.
- Kept encoding and filter behavior unchanged to avoid visual-quality regressions.

## [1.19.0] — 2026-07-23

### Added — Department evidence and take integrity

- Added hash-bound active-take history with superseded evidence preservation.
- Added `beat-evidence`, `editor-cut`, and `audio-visual` reports for action, edit, and sound-picture alignment.
- Added per-shot take comparison to `aifilm quality --shot-id`.

## [1.18.0] — 2026-07-23

### Added — Quality receipt observability

- Added read-only `aifilm quality --root <film>` reporting with optional `--shot-id` filtering.
- Dispatch now consumes the same shared quality summary, keeping operator output and orchestration gates consistent.

## [1.17.0] — 2026-07-23

### Added — Quality-first generation gates

- Added per-shot keyframe and clip quality receipts with stricter hero-shot promotion gates.
- Provider fallback now records routing evidence and requires a fresh hero pilot before bulk work.
- Dispatch now reports persisted quality blockers; hero quality evidence is required before promotion.
- Kept `grok_primary` as the reproducible hero default; Seedance requires canary and pilot evidence.

## [1.16.0] — 2026-07-23

### Added — Director methodology injection (P1-1/P1-2/P1-3: face-lock + hairstyle + makeup)

- **Structured `cast_locks`** (P1-1): style-bible.schema now defines `cast_locks` as a per-character structured object with `face_ref_path`, `identity_lock_tokens`, `never_tokens`, `hair_lock`, `makeup_lock`. prompt_injector prefers structured cast_locks over free-text identity_lock — locks are no longer a free-text blob.
- **`hair_swatches`** (P1-2): style-bible.schema now defines `hair_swatches` as structured per-character field `{color_name, hex, description}` — independent from identity_lock free text. prompt_injector auto-builds Hair lock line from swatches when cast_locks.hair_lock is absent.
- **`makeup`** (P1-3): style-bible.schema now defines `makeup` as structured per-character field `{name, ref_path, lock_tokens, cross_scene_consistency}` — from 0/10 to parameterized. prompt_injector injects Makeup line from cast_locks.makeup_lock or makeup field fallback.
- **Hair lock line injection** (consistency.md H4 compliance): prompt_injector now injects `Hair lock <char>: <color> (<NEVER tokens>)` — this was explicitly missing per consistency.md:148. Fallback chain: cast_locks.hair_lock → hair_swatches.color_name+description.
- **Makeup line injection**: prompt_injector injects `Makeup <char>: <lock_tokens>`. Fallback chain: cast_locks.makeup_lock → makeup[char].lock_tokens.
- Updated `references/style-bible.md` documentation for all three fields.
- **Backward compatibility**: no cast_locks/hair_swatches/makeup → behavior unchanged (identity_lock free text used, no Hair/Makeup lines injected).
- 9 new tests covering structured locks, fallback chains, precedence, and backward compat.

## [1.15.0] — 2026-07-23

### Added — Director methodology injection (P0-1: de-type-bias)

- **Multi-genre beat spines**: `dramatic_function` seven-value enum is now decoupled from the adult six-shot spine. New `genre` field (drama-graph + film-spec schemas) selects the beat spine template. Five genres supported: `adult` (default, backward-compat), `drama`, `mystery`, `arthouse`, `documentary` — each with its own beat spine (key/objective/weight/shots_n).

### Added — Director methodology injection (P0-2: three-act structure + pace chart)

- **Structured `act_structure`**: `director_intent.act_structure` upgraded from free-form to structured object with `setup`/`confrontation`/`resolution` text + optional ratio fields (`setup_ratio`/`confrontation_ratio`/`resolution_ratio`, classic 0.20/0.50/0.30, sum validated ≈1.0). `act_structure_strict: true` → write-spec hard-gates non-empty + all three acts present.
- **Structured `pace_chart`**: `director_intent.pace_chart` upgraded from string array to structured entries: `{label, start_ratio, end_ratio, cut_freq, intensity}` (≥3 segments). Validates ratio ranges, end>start, intensity 0-10. `pace_chart_strict: true` → write-spec hard-gates non-empty + ≥3 segments. Legacy string-array format still accepted (backward compat).
- `validate_director_intent()` in `film_spec.py` now validates both structures. `_draft_story_contract()` initializes act_structure defaults. `project_graph_to_film_spec()` projects act_structure + pace_chart into film-spec.
- Updated `film-spec.md` + `directors-lens.md` documentation.

### Added — Director methodology injection (P0-3: character bible)

- **Character schema expanded**: `drama-graph.schema.json` Character upgraded from 4 fields (id/identity/defaultWardrobe/castMaster) to full dramatic character bible: `name`, `age`, `personality`, `want`, `need`, `flaw`, `ghost_wound`, `arc_turning_points[]`, `relationships[]`, `psych_markers[]`, `dramatic_role` (protagonist/antagonist/mentor/ally/trickster/guardian/supporting). Visual identity fields preserved for backward compat.
- **Protagonist arc gate**: new `character_bible_strict: true` flag → write-spec hard-gates `director_intent.protagonist_want` / `protagonist_need` / `protagonist_arc` non-empty. New schema fields in film-spec + drama-graph.
- `_draft_story_contract()` initializes protagonist_want/need/arc fields. `project_graph_to_film_spec()` projects them into film-spec director_intent. Character generation in `story_plan.py` now populates dramatic role fields with authoring placeholders for leads.
- Legacy import path in `aifilm_grok.py` updated to project genre + protagonist fields + act_structure into drama-graph story.
- New `templates/character-bible.example.md` — full character bible template with dramatic arc, relationships, psych_markers, wardrobe table.
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
