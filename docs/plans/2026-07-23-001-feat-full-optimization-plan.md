# feat: Full ai-film-grok optimization — 4 technical modules + 16 infrastructure upgrades

**Created:** 2026-07-23
**Status:** active
**Target repo:** ai-film-grok (plugin root: `/Users/dex/.grok/plugins/ai-film-grok`)
**Total work units:** 20 (U1–U20)

---

## Problem Frame

The ai-film-grok short-video pipeline has strong foundations (dispatch → craft → audio-plan → final → compose) but lacks:

1. **Visual fidelity** — no micro-expression tracking, no optical depth-of-field simulation, no frame interpolation
2. **Audio realism** — no spatial distance attenuation, no wall occlusion modeling
3. **Infrastructure maturity** — duplicated configuration loading across 6+ modules, `print()`-based logging throughout, `SystemExit` used as error control flow in adapters, no caching, no checkpoint/resume, no parallel I2V generation
4. **Developer experience** — weak CLI validation, no dev watch mode, no automated lessons auditing
5. **Quality gates** — low test coverage in key modules (`compose_render.py`, `render_final.py`, adapters), no structured test baselines

---

## Scope Boundaries

### In scope
- All 4 technical modules (facial micro-expression graph, optical DOF/bokeh, spatial audio physics, optical-flow frame interpolation)
- All 16 infrastructure optimization items from the audit
- Python scripts under `skills/ai-film-grok/scripts/`
- Tests under `skills/ai-film-grok/tests/`
- References under `skills/ai-film-grok/references/`
- Config files (`config.env`, `config.env.example`)
- CI workflow (`.github/workflows/ci.yml`)
- CLI commands (`aifilm_grok.py` argument parsing)

### Deferred to Follow-Up Work
- CLI rewrite in a framework (click/typer) — keep argparse for now, only add validators
- Full async migration of the subprocess layer — use `concurrent.futures` instead
- Plugin packaging for non-Grok environments — keep `aifilm` CLI as entry point
- Migration of inline `film-spec.json` store to SQLite — keep JSON files

### Out of scope
- Changes to the Remotion/HyperFrames rendering backends (just add frame interpolation passthrough)
- New AI model training or fine-tuning
- Pipeline DSL grammar changes beyond the 4 modules
- Performance benchmarking suite (add metrics hooks but no dashboard)

---

## Key Technical Decisions

| Decision | Rationale |
|---|---|
| **Phase 0 first** — config, logging, utilities | Every later unit depends on these; pays off compounding |
| **Parallel background subagents for implementation** | 20 units × sequential = weeks; parallel = days |
| **Keep argparse, add validators** | Minimal diff, no framework migration cost |
| **Config loader: single `config_loader.py` with pydantic schema** | Existing `_load_config_env()` duplication in 6 files must stop |
| **Logger: structured JSON to stderr, optional file** | Compatible with existing `log()` callers via adapter; no silent breakage |
| **Cache: content-hash keyed, `cache/` directory under project root** | Simple, no external dependency, survives across sessions |
| **Checkpoint: shot-level `.done` markers in receipts** | Lightweight; enables `--resume` without full spec re-parse |
| **Testing: pytest baseline + per-module coverage target** | Prioritize `compose_render.py`, `render_final.py`, adapters |

---

## Implementation Units

### Phase 0: Foundation (U1–U3)

These must land first — every other unit consumes them.

---

#### U1. Centralized config loader

**Goal:** Single `config_loader.py` with pydantic schema that replaces all 6+ duplicate `_load_config_env()` implementations.

**Dependencies:** None

**Files:**
- `skills/ai-film-grok/scripts/config_loader.py` — create
- `skills/ai-film-grok/scripts/adapters/voicebox_tts.py` — modify
- `skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py` — modify
- `skills/ai-film-grok/scripts/adapters/elevenlabs_tts.py` — modify
- `skills/ai-film-grok/scripts/adapters/music_external.py` — modify
- `skills/ai-film-grok/scripts/aifilm_grok.py` — modify
- `skills/ai-film-grok/scripts/env_plate.py` — modify
- `skills/ai-film-grok/tests/test_config_loader.py` — create
- `skills/ai-film-grok/references/config-schema.md` — create

**Approach:**
- `ConfigSchema` pydantic model with all known env vars, defaults, and validators
- `load_config()` function: reads `config.env` from canonical path once, caches in module global
- `env_config(key)` for ad-hoc access from old-style code during migration
- Each adapter migrates from inline `_load_config_env()` → `from config_loader import load_config`
- Generate exhaustive `config.env.example` by scanning all `os.environ.get()` calls in the codebase

**Patterns to follow:** Existing `_load_config_env()` callers throughout adapters.

**Test scenarios:**
1. Happy: `config_loader.load_config()` reads from existing `config.env` and returns validated schema
2. Missing file: no `.env` file — returns defaults without error
3. Typo key: unknown env var is warned but not fatal
4. Type coercion: `AIFILM_MUSIC_TIMEOUT=abc` raises validation error
5. Cache behavior: second call returns cached instance without re-reading file
6. Generated example: `generate_example()` output matches actual `os.environ.get()` keys found in codebase

**Verification:** `ruff check`, `pytest test_config_loader.py -q`, all adapters still pass their `doctor()` calls.

---

#### U2. Structured logger

**Goal:** Unified `logger.py` replacing all `def log(msg): print(msg, file=sys.stderr, flush=True)` copies.

**Dependencies:** None (can parallel U1)

**Files:**
- `skills/ai-film-grok/scripts/logger.py` — create
- `skills/ai-film-grok/scripts/aifilm_grok.py` — modify (replace `log()` with import)
- `skills/ai-film-grok/scripts/compose_render.py` — modify
- `skills/ai-film-grok/scripts/compose_preview.py` — modify
- `skills/ai-film-grok/scripts/render_final.py` — modify
- `skills/ai-film-grok/scripts/media_qa.py` — modify
- `skills/ai-film-grok/scripts/lipsync_backend.py` — modify
- `skills/ai-film-grok/tests/test_logger.py` — create

**Approach:**
- `LogRecord` dataclass: timestamp, level, module, message, optional `extra` dict
- `Logger` class with `.info()`, `.warn()`, `.error()`, `.debug()` methods
- JSON output to stderr by default, human-readable fallback via env flag
- Backward-compatible `log(msg)` function that delegates to `Logger.info()`
- Metrics counter API: `logger.count("i2v.gen.shot", tags={"model":"minimax"})` stored in memory, flushed to JSON on pipeline completion

**Patterns to follow:** Existing `log()` signature (`str`) → no caller changes needed.

**Test scenarios:**
1. Happy: `logger.info("test")` outputs valid JSON to stderr
2. Levels: debug lines suppressed at default INFO, visible at DEBUG
3. Extra fields: structured `extra` dict appears in JSON output
4. Backward compat: existing `log("msg")` import still works
5. Counter: `logger.count("shots", 1)` increments, `logger.counts()` returns accumulated

**Verification:** `pytest test_logger.py -q`, grep for `def log(msg)` in codebase to confirm no copies remain.

---

#### U3. Shared utility extraction

**Goal:** Extract duplicated `utc_now()`, `write_json()`, `read_json()`, `run()` into shared util package.

**Dependencies:** None (can parallel U1, U2)

**Files:**
- `skills/ai-film-grok/scripts/util/__init__.py` — create
- `skills/ai-film-grok/scripts/util/time.py` — create
- `skills/ai-film-grok/scripts/util/json_io.py` — create
- `skills/ai-film-grok/scripts/util/subprocess.py` — create
- `skills/ai-film-grok/scripts/util/validators.py` — create
- `skills/ai-film-grok/tests/test_util.py` — create

**Approach:**
- `util/time.py`: `utc_now()` from shared source
- `util/json_io.py`: `write_json(path, data)`, `read_json(path)`, `atomic_write_text(path, content)`
- `util/subprocess.py`: `run(cmd, ...)` wrapper with `minimal_subprocess_env()` already in `security_policy.py`
- `util/validators.py`: `valid_shot_id()`, `film_output_path()`, `slugify()` from `aifilm_grok.py`
- Each old function becomes a thin wrapper calling the util version, then callers migrate one at a time

**Patterns to follow:** Existing function signatures — wrappers are API-compatible.

**Test scenarios:**
1. `utc_now()` returns ISO 8601 string without microseconds
2. `write_json()` creates parent dirs atomically
3. `read_json()` raises `FilmError` on missing file
4. `valid_shot_id()` rejects `../escape`, empty string, `/../`

**Verification:** `pytest test_util.py -q`, existing tests for `aifilm_grok.py` still pass after wrapper migration.

---

### Phase 1: Core Technical Modules (U4–U7)

These are the 4 modules from the original request. Implemented in parallel after Phase 0 lands.

---

#### U4. Facial micro-expression graph

**Goal:** Track micro-expression shifts per-character across consecutive shots and validate perceptual continuity.

**Dependencies:** U1 (config), U3 (util)

**Files:**
- `skills/ai-film-grok/scripts/micro_expression.py` — create
- `skills/ai-film-grok/scripts/expression_graph.py` — create
- `skills/ai-film-grok/scripts/continuity.py` — modify (add `CODE_EXPRESSION_DISCONTINUITY`)
- `skills/ai-film-grok/scripts/asset_registry.py` — modify (add expression state registration)
- `skills/ai-film-grok/tests/test_micro_expression.py` — create

**Approach:**
- `ExpressionGraph` class: per-shot → per-shot-edge → per-character timeline
- Expression states: `neutral`, `smile`, `surprise`, `furrow`, `pout`, `grimace`, `blank` + intensity float `[0,1]`
- Edge rules: consecutive shots of same character with same expression = stable; jump from `smile(0.8)` → `furrow(0.7)` in ≤1 shot = discontinuity flag
- `CODE_EXPRESSION_DISCONTINUITY` gate in `continuity.py`: soft warning at doctor time
- `asset_registry.py`: character expression state registered alongside location/prop state

**Patterns to follow:** Existing `CharacterState` in `asset_registry.py`, `ContinuityCode` enum in `continuity.py`.

**Test scenarios:**
1. Happy: 3 consecutive shots with same expression → no discontinuity
2. Edge: expression jump with bridge shot (neutral in between) → no discontinuity
3. Error: character enters a shot with no expression data → `UNKNOWN` state logged
4. Gate: `CODE_EXPRESSION_DISCONTINUITY` fires when adjacent shots differ by ≥2 intensity tiers

**Verification:** `pytest test_micro_expression.py -q`, integration: `aifilm lint-continuity --root <test-fixture>` reports expression gates.

---

#### U5. Optical depth-of-field & bokeh simulation

**Goal:** DSL-level controls for shallow depth-of-field (`shallow_dof_f1_4`, `anamorphic_bokeh`) and post-process simulation via FFmpeg lens blur.

**Dependencies:** U1 (config), U3 (util)

**Files:**
- `skills/ai-film-grok/scripts/optical_dof.py` — create
- `skills/ai-film-grok/scripts/story.py` — modify (add `focal_depth` DSL attributes)
- `skills/ai-film-grok/scripts/render_final.py` — modify (add `--optical-dof` ffmpeg filter chain)
- `skills/ai-film-grok/scripts/film_spec.py` — modify (validate focal_depth values)
- `skills/ai-film-grok/tests/test_optical_dof.py` — create

**Approach:**
- DSL attributes per-shot: `focal_depth` enum (`deep_focus`, `medium`, `shallow_dof_f1_4`, `anamorphic_bokeh`), `focus_distance_m` float
- Post-process: FFmpeg `lensfun` filter for optical DOF + `gblur` for bokeh fallback
- `optical_dof.py`: renders the FFmpeg filter graph from shot DSL values
- `render_final.py`: `--optical-dof` flag appends the filter chain before final encode
- DSL validation in `film_spec.py`: `anamorphic_bokeh` requires `aspect_ratio == "9:16"` soft warning

**Patterns to follow:** Existing `dsl` dict in `story.py` shot definitions (e.g., `motion`, `action`).

**Test scenarios:**
1. Happy: DSL with `shallow_dof_f1_4` produces correct FFmpeg `lensfun` filter args
2. Fallback: no lensfun available → uses `gblur=sigma=2:enable='between(t,0,5)'` fallback
3. Edge: `focus_distance_m=0` treated as "auto" (use center-weighted detection)
4. Validation: `anamorphic_bokeh` + non-9:16 → soft warning in doctor

**Verification:** `pytest test_optical_dof.py -q`, manual: `ffmpeg -filters | grep lensfun` to confirm available.

---

#### U6. Distance attenuation & wall occlusion for spatial audio

**Goal:** Spatially-aware audio mixing: amplitude attenuation by shot distance, low-pass filter when subject is behind a wall.

**Dependencies:** U1 (config), U3 (util)

**Files:**
- `skills/ai-film-grok/scripts/spatial_audio.py` — create
- `skills/ai-film-grok/scripts/make_sfx_bed.py` — modify (add distance/occlusion to SFX bus)
- `skills/ai-film-grok/scripts/sound_plan.py` — modify (add `spatial` audio plan section)
- `skills/ai-film-grok/scripts/film_spec.py` — modify (validate spatial audio params)
- `skills/ai-film-grok/tests/test_spatial_audio.py` — create

**Approach:**
- Per-shot DSL attributes: `distance_from_camera_m` (float), `behind_wall` (bool), `environment` (indoor/outdoor/hall)
- Amplitude model: `dB = -6 * log2(distance / 1.0)` — doubles distance = -6dB
- Wall occlusion: when `behind_wall=true`, apply low-pass FFmpeg filter `lowpass=f=1000` + gain -3dB
- `make_sfx_bed.py`: reads spatial params from shot spec, applies per-track before mixing
- `sound_plan.py`: `spatial` section documents attenuation curves for doctor

**Patterns to follow:** Existing `make_sfx_bed.py` per-shot SFX generation, `sound_plan.py` plan dictionary.

**Test scenarios:**
1. Happy: `distance=2m, behind_wall=false` → -6dB amplitude, no filter
2. Occlusion: `behind_wall=true` → lowpass 1000Hz + -3dB
3. Distance curve: `distance=4m` → -12dB; `distance=0.5m` → +6dB
4. Edge: `distance=0` → clamp to 0.1m, no infinite dB
5. Environment: `environment=hall` → early reflection reverb tail (predelay 20ms)

**Verification:** `pytest test_spatial_audio.py -q`, integration: `make_sfx_bed.py` produces wav with measurable amplitude differences.

---

#### U7. Optical-flow frame interpolation

**Goal:** Frame interpolation via FFmpeg `minterpolate` filter for slow-motion and frame-rate upsampling.

**Dependencies:** U1 (config), U3 (util)

**Files:**
- `skills/ai-film-grok/scripts/frame_interpolate.py` — create
- `skills/ai-film-grok/scripts/render_final.py` — modify (add `--interpolate` flag)
- `skills/ai-film-grok/scripts/story.py` — modify (add `frame_rate_multiplier` DSL attribute)
- `skills/ai-film-grok/tests/test_frame_interpolate.py` — create

**Approach:**
- DSL: `frame_rate_multiplier: 2|3|4` per-shot, defaults to 1 (off)
- FFmpeg filter: `minterpolate='mi_mode=mci:mc_mode=aobmc:vsbmc=1:fps=60'`
- Multiplier 2 → 24fps → 48fps (smooth motion); multiplier 4 → 24fps → 96fps (dramatic slow-mo ready)
- `render_final.py --interpolate auto|N`: auto reads from shot DSL, N forces global multiplier
- Duration compensation: interpolated shot duration changes → sync VO cut list accordingly

**Patterns to follow:** Existing `render_final.py` filter chain construction for subtitles and hardcodes.

**Test scenarios:**
1. Happy: multiplier=2 on 24fps source → 48fps output, duration halved
2. Duration: after interpolation, VO cut timestamps are remapped
3. Edge: multiplier=1 → passthrough, no filter appended
4. Fallback: ffmpeg without `minterpolate` → clear error, not silent failure

**Verification:** `pytest test_frame_interpolate.py -q`, integration: `ffmpeg -filters | grep minterpolate` confirms availability.

---

### Phase 2: Reliability (U8–U12)

---

#### U8. Testing baseline & coverage gates

**Goal:** Establish test infrastructure: baseline coverage measurement, targeted tests for uncovered modules, CI coverage gate.

**Dependencies:** U3 (util — tests need stable imports)

**Files:**
- `skills/ai-film-grok/tests/test_compose_render.py` — create
- `skills/ai-film-grok/tests/test_render_final.py` — create
- `skills/ai-film-grok/tests/test_adapters.py` — create (smoke tests for all adapter `doctor()` functions)
- `skills/ai-film-grok/tests/test_cmd_final.py` — create
- `.github/workflows/ci.yml` — modify (add coverage step)
- `skills/ai-film-grok/pyproject.toml` — modify (add pytest-cov config)
- `skills/ai-film-grok/tests/conftest.py` — create (shared fixtures)

**Approach:**
- `conftest.py`: shared `minimal_root` fixture (tmpdir + minimal manifest), `mock_ffprobe` fixture
- `test_compose_render.py`: mock subprocess, test `ensure_audio_mux`, `register_final_film`, `assert_underlay_not_double_burn` with varied inputs
- `test_render_final.py`: mock ffmpeg, test `split_units`, `pdur`, `resolve_font`, filter chain assembly
- `test_adapters.py`: smoke-test each adapter's `doctor()` with mock HTTP, test TTS synthesis with fake response
- CI: `pytest --cov=scripts --cov-fail-under=60` (baseline), with `--cov-report=term-missing`
- Coverage target: 60% baseline in Phase 2, 75% target by Phase 5

**Patterns to follow:** Existing test style in `test_security_policy.py` (unittest + pytest marks).

**Test scenarios:** Tests themselves — see each unit's test scenarios.

**Verification:** `pytest --cov=scripts --cov-report=term`, CI passes with ≥60% coverage.

---

#### U9. SystemExit cleanup → custom exception hierarchy

**Goal:** Replace all `raise SystemExit(...)` in adapter code with typed exceptions.

**Dependencies:** U1 (config_loader — adapters touched)

**Files:**
- `skills/ai-film-grok/scripts/adapters/voicebox_tts.py` — modify
- `skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py` — modify
- `skills/ai-film-grok/scripts/adapters/elevenlabs_tts.py` — modify
- `skills/ai-film-grok/scripts/adapters/music_external.py` — modify
- `skills/ai-film-grok/tests/test_adapters.py` — extend (verify exception types)

**Approach:**
- Add `TTSBackendError(RuntimeError)`, `MusicGenError(RuntimeError)` to new `errors.py` module
- Each adapter's `synthesize()` / `generate()` raises typed errors instead of `SystemExit`
- CLI entry points (`main()`) catch the typed errors and convert to exit code at the boundary
- No behavior change for callers — `FilmError` is the top-level user-facing type

**Patterns to follow:** Existing `FilmError(RuntimeError)`, `ComposeRenderError(RuntimeError)`, `RenderError(RuntimeError)`.

**Test scenarios:**
1. `voicebox_tts.synthesize()` with unreachable server → raises `TTSBackendError`, not SystemExit
2. `music_external._http_generate()` with 500 response → raises `MusicGenError` with detail
3. `cosyvoice_tts.synthesize()` with empty text → raises `TTSBackendError`, not SystemExit

**Verification:** `pytest test_adapters.py -q`, grep for `raise SystemExit` in adapters — zero remaining.

---

#### U10. CLI input validation

**Goal:** Centralized `validators.py` with input sanitizers for all public CLI parameters.

**Dependencies:** U3 (util package)

**Files:**
- `skills/ai-film-grok/scripts/util/validators.py` — extend
- `skills/ai-film-grok/scripts/aifilm_grok.py` — modify (add validation calls)
- `skills/ai-film-grok/tests/test_validators.py` — create

**Approach:**
- `validate_shot_id(value)` — existing, keep
- `validate_tone(value)` — must match known tones in `director_intent.tone`
- `validate_post_engine(value)` — `ffmpeg|hyperframes|remotion|auto`
- `validate_root(path)` — must be directory, must contain `manifest.json` or `film-spec.json`
- `validate_tts_backend(value)` — `edge|minimax|voicebox|cosyvoice|elevenlabs`
- Each validator returns `str` on success, raises `SecurityPolicyError` or `FilmError` on failure
- `build_parser()` adds `type=` lambda wrapping each validator

**Patterns to follow:** Existing `valid_shot_id()` in `aifilm_grok.py`.

**Test scenarios:**
1. Valid: `validate_post_engine("hyperframes")` returns `"hyperframes"`
2. Invalid: `validate_post_engine("hyper")` raises `FilmError`
3. Root: `validate_root("/nonexistent")` raises `FilmError`
4. Shot ID: `validate_shot_id("../escape")` raises `SecurityPolicyError`

**Verification:** `pytest test_validators.py -q`, `aifilm final --root /nonexistent` shows clear error.

---

#### U11. Content-addressable cache

**Goal:** Disk cache for expensive operations: ffprobe probes, I2V results (optionally), LLM prompt results.

**Dependencies:** U3 (util), U2 (logger)

**Files:**
- `skills/ai-film-grok/scripts/cache.py` — create
- `skills/ai-film-grok/scripts/media_duration.py` — modify (check cache first)
- `skills/ai-film-grok/scripts/render_final.py` — modify (probe cache)
- `skills/ai-film-grok/tests/test_cache.py` — create

**Approach:**
- `ContentCache` class: `cache/` directory under project root
- `cache_key(data: bytes) → str`: SHA256 hex digest
- `get(key) → Path | None`: return cached file path or None
- `put(key, data: bytes) → Path`: write to cache, return path
- `put_file(key, source_path: Path)`: copy file into cache
- `max_size`: LRU eviction, default 1GB, configurable env var
- ffprobe probe result cached by file inode+size+mtime hash
- Optional I2V result cache: keyed by prompt hash + seed + model

**Patterns to follow:** No existing cache — fresh design.

**Test scenarios:**
1. Happy: `cache.put("abc", b"data")`, `cache.get("abc")` returns path
2. Miss: `cache.get("nonexistent")` returns None
3. Eviction: cache over `max_size` → oldest entries removed
4. ffprobe: second call with same file returns cached duration without subprocess

**Verification:** `pytest test_cache.py -q`, integration: two `pdur()` calls on same file show single ffprobe invocation.

---

#### U12. Checkpoint / resume system

**Goal:** If `final` fails at shot 37/50, `final --resume` starts at shot 37 instead of shot 1.

**Dependencies:** U11 (cache), U3 (util)

**Files:**
- `skills/ai-film-grok/scripts/checkpoint.py` — create
- `skills/ai-film-grok/scripts/render_final.py` — modify (checkpoint after each shot)
- `skills/ai-film-grok/scripts/dispatch.py` — modify (shot-level checkpoint markers)
- `skills/ai-film-grok/tests/test_checkpoint.py` — create

**Approach:**
- Shot-level `.shot_done` marker files in `receipts/checkpoints/`
- `CheckpointManager(root)`: `.is_done(shot_id) → bool`, `.mark_done(shot_id)`, `.clear()`
- `final --resume`: skips shots where `.is_done()` is true
- `final --force`: clears all checkpoints before starting
- Written atomically (write to temp, rename)

**Patterns to follow:** Existing receipt pattern in `compose_preview.py` (`receipts/compose-preview.json`).

**Test scenarios:**
1. Happy: 3 shots marked done, resume → only generates shots 4+
2. Partial: shot 2 failed (no marker), resume → re-generates shots 2+
3. Clear: `--force` removes all markers before start
4. Isolation: different project roots don't interfere

**Verification:** `pytest test_checkpoint.py -q`, integration: start `final`, kill at shot N, `final --resume` picks up correctly.

---

### Phase 3: Performance & DX (U13–U15)

---

#### U13. Parallel I2V generation

**Goal:** Use `concurrent.futures.ThreadPoolExecutor` to generate multiple shots simultaneously.

**Dependencies:** U2 (logger), U12 (checkpoint — needs shot-level markers)

**Files:**
- `skills/ai-film-grok/scripts/dispatch.py` — modify (add `--parallel N` flag)
- `skills/ai-film-grok/scripts/media_queue.py` — modify (thread-safe queue)
- `skills/ai-film-grok/tests/test_parallel_dispatch.py` — create

**Approach:**
- `dispatch.py --parallel N`: N = number of parallel workers (default 1 for backward compat)
- Worker pool via `ThreadPoolExecutor` for I2V API calls (I/O bound, not CPU)
- Each worker: pick next shot from queue → generate → mark checkpoint → log progress
- `media_queue.py`: add thread-safe `Queue` wrapper
- Rate limiting: optional `--rate N/min` for API quota compliance

**Patterns to follow:** Existing sequential `dispatch.py` shot loop — wrap with executor.

**Test scenarios:**
1. Happy: 3 mock shots, N=3 → all complete in ~same time as 1 shot
2. Rate limit: `--rate 2/min` → sleeps between shots
3. Error in one worker → other workers complete, partial checkpoint saved
4. Backward compat: N=1 (default) → identical behavior to current sequential

**Verification:** `pytest test_parallel_dispatch.py -q`, benchmark: `aifilm dispatch --parallel 4 --root <fixture>` completes faster than sequential.

---

#### U14. Dev watch mode

**Goal:** `aifilm watch` — file watcher that re-runs doctor/lint/status on changes.

**Dependencies:** U2 (logger)

**Files:**
- `skills/ai-film-grok/scripts/watch_mode.py` — create
- `skills/ai-film-grok/scripts/aifilm_grok.py` — modify (add `cmd_watch`)
- `skills/ai-film-grok/tests/test_watch_mode.py` — create

**Approach:**
- Uses `watchdog` (or `inotify`-style polling on macOS via `kqueue`)
- Default watch paths: `film-spec.json`, `style-bible.json`, `manifest.json`, `assets/characters/*.json`
- On change: sequential run of `doctor → lint-continuity → status` commands
- `--exec CMD`: run arbitrary command on change

**Patterns to follow:** File-watching design only — no existing watch mode.

**Test scenarios:**
1. Touch `film-spec.json` → watch triggers doctor
2. `aifilm watch --exec "echo changed"` runs command
3. Debounce: rapid changes within 500ms trigger once

**Verification:** `pytest test_watch_mode.py -q`, manual: `aifilm watch --root <fixture>` and touch `film-spec.json`.

---

#### U15. Media prune & cleanup

**Goal:** `aifilm prune` — policy-based cleanup of intermediate clip artifacts.

**Dependencies:** None

**Files:**
- `skills/ai-film-grok/scripts/prune.py` — create
- `skills/ai-film-grok/scripts/aifilm_grok.py` — modify (add `cmd_prune`)
- `skills/ai-film-grok/tests/test_prune.py` — create

**Approach:**
- Dry-run by default: `aifilm prune --dry-run` lists what would be deleted
- `--keep N`: keep N most recent clip sets
- `--older-than DAYS`: remove clips older than N days
- `--project ID`: prune only specific project's artifacts
- Cleanup targets: `clips/`, `audio/` (intermediate mixes), `out/_final_work/`
- Safe: never touches `out/film_final.mp4`, `canonical/`, `receipts/`

**Patterns to follow:** No existing prune command.

**Test scenarios:**
1. Dry run: lists files but deletes nothing
2. `--keep 2`: removes all but 2 newest clip directories
3. `--older-than 7`: removes clips with mtime > 7 days ago
4. Safety: never deletes anything in `out/` or `canonical/`

**Verification:** `pytest test_prune.py -q`, manual: `aifilm prune --root <fixture> --dry-run` shows planned deletions.

---

### Phase 4: Polish (U16–U20)

---

#### U16. MediaQA per-style profiles

**Goal:** Configurable QA thresholds per style-bible profile instead of hardcoded values.

**Dependencies:** U1 (config_loader), U8 (test infrastructure)

**Files:**
- `skills/ai-film-grok/scripts/media_qa_profiles.json` — create
- `skills/ai-film-grok/scripts/media_qa.py` — modify (load profile, use thresholds)
- `skills/ai-film-grok/scripts/style_bible.py` — modify (allow `qa_profile` field)
- `skills/ai-film-grok/tests/test_media_qa_profiles.py` — create

**Approach:**
- `media_qa_profiles.json`: per-profile threshold maps
  - `default`: `min_motion_score=0.05`, `min_resolution="720x1280"`, `max_black_frames_pct=5`
  - `lo-fi`: `min_motion_score=0.01`, `min_resolution="480x854"`
  - `cinematic`: `min_motion_score=0.1`, `min_resolution="1080x1920"`, `max_black_frames_pct=1`
- `style-bible.json` `qa_profile` field selects which profile to use
- `media_qa.py` `analyze_media()` reads profile, falls back to `default`

**Patterns to follow:** Existing `analyze_media()` function signature — add optional `profile` parameter.

**Test scenarios:**
1. Default: existing callers with no profile → same behavior as today
2. Lo-fi profile: reduced motion threshold accepts lower-motion clip
3. Missing profile key: falls back to `default` with warning

**Verification:** `pytest test_media_qa_profiles.py -q`, integration: `--qa-profile lo-fi` on test fixture passes.

---

#### U17. Lessons auditing & promotion

**Goal:** Review all ~49 lessons files, promote validated ones to stable references, retire duplicates.

**Dependencies:** None

**Files:**
- `skills/ai-film-grok/scripts/audit_lessons.py` — create
- `skills/ai-film-grok/scripts/aifilm_grok.py` — modify (add `cmd_audit_lessons`)
- Multiple `references/lessons-*.md` — modify (promote or deprecate)

**Approach:**
- `audit_lessons.py` scans all `references/lessons-*.md` files
- For each, checks: is it referenced by any stable doc? Is it >14 days old with no updates?
- Classification: `promote` (merge into stable ref), `deprecate` (add `deprecated: YYYY-MM-DD` header), `keep` (still active lesson)
- Output: report with per-file classification and merge targets
- Promote step: append content to target `references/*.md` and add `source: lessons-*.md` note

**Patterns to follow:** Existing stable references in `references/` (markdown files).

**Test scenarios:**
1. Report: lists all lessons with classification, no side effects with `--dry-run`
2. Promote: `--promote` flag merges file content into stable reference, adds deprecation header
3. Stale: >30 days with 0 cross-references → flagged as deprecated candidate

**Verification:** `python3 audit_lessons.py --dry-run` produces correct report. No lessons data loss.

---

#### U18. CI doctor step

**Goal:** Add `aifilm doctor --offline` to CI pipeline to catch config drift.

**Dependencies:** U1 (config_loader)

**Files:**
- `.github/workflows/ci.yml` — modify
- `skills/ai-film-grok/scripts/aifilm_grok.py` — modify (add `--offline` flag to doctor)

**Approach:**
- `doctor --offline`: checks file structure, import health, config presence, no external API calls
- CI step runs after `grok plugin validate` and before pytest
- Fail on: missing required files, import errors, `config.env.example` drift

**Patterns to follow:** Existing CI structure in `.github/workflows/ci.yml`.

**Test scenarios:** CI-only — manual trigger to verify.

**Verification:** CI run shows green `doctor --offline` step.

---

#### U19. Automated config.env.example generation

**Goal:** Single source of truth for all env vars, auto-generated from codebase scan.

**Dependencies:** U1 (config_loader)

**Files:**
- `skills/ai-film-grok/scripts/config_loader.py` — modify (add `generate_example()`)
- `skills/ai-film-grok/config.env.example` — regenerate
- `skills/ai-film-grok/tests/test_config_loader.py` — extend

**Approach:**
- `ConfigSchema` pydantic model carries metadata: `env_name, default, description, source_file`
- `generate_example()`: walks `@field()` metadata, produces complete `.env.example` with comments
- Static scan: AST-parses all `.py` files for `os.environ.get(...)` calls, cross-references against schema

**Patterns to follow:** Existing `config.env.example` structure.

**Test scenarios:**
1. Generated example contains all env vars found by static scan
2. Every `os.environ.get()` call in codebase has a corresponding line in example
3. Generated file passes `python3 -c "exec(open('config.env.example').read())"` (syntax-valid)

**Verification:** `pytest test_config_loader.py -q`, regenerate: `config_loader.generate_example()` produces file, diff shows current state.

---

#### U20. i18n framework

**Goal:** Add `language` field to `film-spec.json` that propagates to TTS, subtitle, and BGM style selection.

**Dependencies:** U1 (config_loader), U2 (logger)

**Files:**
- `skills/ai-film-grok/scripts/localization.py` — create
- `skills/ai-film-grok/scripts/film_spec.py` — modify (add `language` validation)
- `skills/ai-film-grok/scripts/tts_backend.py` — modify (pass language to adapter)
- `skills/ai-film-grok/scripts/render_final.py` — modify (subtitle split by language rules)
- `skills/ai-film-grok/scripts/sound_plan.py` — modify (BGM mood by locale)
- `skills/ai-film-grok/tests/test_localization.py` — create

**Approach:**
- `Language = Literal["zh", "en", "ja", "auto"]` in `localization.py`
- `film-spec.json` `language` field at root level
- TTS dispatch: maps `zh → edge-zh-CN-Xiaoxiao`, `en → edge-en-US-Jenny`, `ja → edge-ja-JP-Nanami`
- Subtitle split: Chinese uses character-boundary logic (existing), English uses word-boundary, Japanese uses morpheme-boundary
- BGM: locale influences mood selection (zh → C-pop leaning, en → RnB leaning)
- Fallback: `auto` detects from narration text via heuristic

**Patterns to follow:** Existing `tts_backend` voice routing, `split_units()` in `render_final.py`.

**Test scenarios:**
1. zh: TTS routes to zh-CN voice, subtitles split by character
2. en: TTS routes to en-US voice, subtitles split by word
3. auto: detects Chinese text → uses zh pipeline
4. BGM: `language=en` selects different procedural BGM preset
5. Validation: unsupported language `fr` raises validation error with supported list

**Verification:** `pytest test_localization.py -q`, integration: `aifilm write-spec --language en` produces English-flagged spec.

---

## Dependency Graph

```
U1 (config loader)    ─┬─→ U4 (micro-expr) ──→ U8 (test baseline)
                        ├─→ U5 (optical DOF) ─→ U8
U2 (logger)  ──────────┼─→ U6 (spatial audio) ─→ U8
                        ├─→ U7 (frame interp) ─→ U8
U3 (util)    ──────────┤
                        ├─→ U9 (SystemExit) ─→ U8
                        ├─→ U10 (CLI validate) ─→ U8
                        ├─→ U11 (cache) ─→ U12 (checkpoint) ─→ U13 (parallel)
                        └─→ U16 (mediaQA profiles)
                              U14 (watch) ─ independent ─
                              U15 (prune) ─ independent ─
                              U17 (lessons) ─ independent ─
                              U18 (CI) ─ after U1 ─
                              U19 (env example) ─ after U1 ─
                              U20 (i18n) ─ after U1, U2 ─
```

**Parallel execution plan:**

| Batch | Units | Rationale |
|---|---|---|
| Batch 0 | U1, U2, U3 | Foundation — parallelizable (no deps) |
| Batch 1 | U4, U5, U6, U7 | 4 core modules — all depend on Batch 0 only, parallel among themselves |
| Batch 2 | U8, U9, U10, U11, U20 | Reliability — U8 tests need U4–U7 modules, others need only Batch 0 |
| Batch 3 | U12, U14, U15, U16, U17, U18, U19 | Performance+Polish — most depend on Batch 0 only |
| Batch 4 | U13 | Parallel I2V — needs U12 (checkpoint) |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Backward compat break from config_loader | Low | High | Keep old `_load_config_env()` as thin wrapper; add migration guide in docstring |
| FFmpeg lensfun filter not available | Medium | Medium | Add `gblur` fallback; doctor reports lensfun availability |
| FFmpeg minterpolate not compiled in | Medium | Medium | Check at doctor time; clear error in render |
| Parallel I2V hits API rate limits | Medium | High | Add `--rate N/min` flag; default N=2 conservative |
| Watch mode polling on macOS misses events | Low | Low | Use watchdog native kqueue; fall back to 1s poll |
| i18n TTS voice quality differs across languages | Medium | Low | Document known-quality voices; `auto` detects and warns |

---

## Verification Strategy

### Per-unit verification
Each unit includes its own `pytest test_*.py` file. Minimum bar:
- `lsp_diagnostics` clean
- `ruff check` clean on changed files
- Unit tests pass

### Integration verification (end-to-end)
After each batch:
1. `aifilm doctor --offline` — green
2. `grok plugin validate /path/to/plugin` — green
3. `ruff check scripts/ && ruff format --check scripts/` — clean
4. `pytest tests/ -q --tb=line -m "not slow"` — green

### System verification (all batches complete)
1. Full test suite: `pytest tests/ -q --tb=line` — green
2. CI dry run: `act` or push to CI — green
3. Manual: generate a real project with `aifilm init → write-spec → dispatch → final` — no regressions

---

## Effort Estimate

| Phase | Units | Est. person-days | Parallelizable |
|---|---|---|---|
| Phase 0: Foundation | 3 | 2 | Yes (3 agents) |
| Phase 1: Core modules | 4 | 4 | Yes (4 agents) |
| Phase 2: Reliability | 5 | 3 | Yes (per-unit agents) |
| Phase 3: Performance/DX | 3 | 2 | Yes (per-unit agents) |
| Phase 4: Polish | 5 | 2 | Yes (per-unit agents) |
| **Total** | **20** | **13** | **~4-5 days wall clock** |

---

## Future Considerations

- **Metri** dashboard: once structured logging and counters are in place, a simple web dashboard could render pipeline performance over time
- **Plugin SDK**: if the pattern stabilizes, extract `config_loader`, `logger`, `cache`, `checkpoint` into a shared `ai-film-sdk` package
- **Distributed dispatch**: parallel I2V workers could spawn on separate machines via Redis queue when scale demands it
