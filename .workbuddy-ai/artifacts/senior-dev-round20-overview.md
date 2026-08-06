# Senior Dev — Round 20 Overview (2026-08-06)

**Context:** User said `go`. P3-1's zero-importer real migration is exhausted (Round 19 found 16 top-level files are intentional compat shims), so per last round's recommendation this turn **pivots to P4 (test-coverage gaps)**.

## What shipped — v2.40.36 (commit `c152b49`)
- **Added `tests/test_core_paths.py` — first tests for `scripts/core/paths.py`** (a security-boundary module, previously zero coverage). 11 deterministic, zero-dependency cases covering all 3 public contracts:
  - `valid_shot_id`: accepts `s01` / `Shot-1_a` / 64-char boundary; rejects `""`, `..`, `../x`, `/etc/passwd`, spaces, dots, 65-char → raises `FilmError`.
  - `film_output_path`: returns `root/out/<name>.mp4` with `.mp4` suffix; rejects bad suffix (`.exe`), path traversal (`../escape.mp4`), absolute (`/tmp/...`) → `FilmError`.
  - `record_file_matches`: `True` only when file exists AND sha256 matches; `False` on wrong/missing/empty sha, non-dict record, missing `path`.

## Verification
- `pytest`: **11 passed**. ruff clean.
- `make doctor`: `core_readiness.ok=true`, `failed_checks=[]`, `runtime_lock.ok=true` → gate fully green.
- Additive-only change (no `scripts/` module moved) → `runtime-lock.json` untouched, no regen needed.
- Dual-remote push via origin dual pushurl (Gitea + GitHub); `divergence(origin..github)=0`. No race this turn.

## Coverage survey (P4 candidates still untested, `util/core/node/final`)
`util.spine_helpers` · `core.emit` · `core.film_io` · `node.backend_probe` · `node.latentsync_adapter` · `node.musetalk_adapter` · `node.stable_audio_probe` · `final.bgm_spotting` · `final.caption_text` · `final.enhance` · `final.io` · `final.render_defaults` · `final.tts_tracks` · `final.voice_mix_config` · `final.watchdog` (skipped `core.constants` — 31 lines of constants, low ROI).

## Lesson
When testing wrappers over a security-policy module, check the **required keyword-only args** (e.g. `record_file_matches(..., field=...)`) — a missing kw fails at call time, not import time. Prefer deterministic, pure modules (path/identity helpers) for fast, high-value P4 unit tests.

## Next `go` suggestions
- P4: `core.emit` / `core.film_io` / `util.spine_helpers` / `final.render_defaults` (deterministic first).
- P5-1: expand `make type` mypy scan list (incremental, post cleanup of the 2315-error tree).
