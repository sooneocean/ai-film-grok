---
title: ai-film-grok Codebase Optimization
type: refactor
status: active
date: 2026-07-21
origin: docs/brainstorms/2026-07-21-plugin-analysis-requirements.md
---

# ai-film-grok Codebase Optimization

## Summary

A historical refactor proposal. As of v1.6 the verified baseline is 462 passing tests plus 47 subtests; CI already has a full-suite job, while the CLI monolith has grown to 5,147 lines. Treat its old counts and CI diagnosis as superseded by the v1.6 release checks and director-review contract.

The plan proposes 5 waves over 3-5 working sessions, each independently shippable, prioritized by impact-to-effort ratio. No architectural rewrites — every wave respects the existing 4-layer architecture and 8-ring dispatch protocol.

---

## Problem Frame

The ai-film-grok plugin processes a user's text concept through a 4-layer pipeline (Agent → Visual → Voice → Design/Post) into a finished short film. Recent velocity (OAuth integration, CI setup, 75 commits) has left structural debt:

- **Monolith risk**: `aifilm_grok.py` at roughly 5,147 lines handles argument parsing AND all command group implementations. A single typo or import cycle in this file blocks the entire CLI.
- **I/O duplication**: `_read_json` / `_write_json` are copy-pasted across 10+ modules with minor variations. Changing JSON behavior (e.g., adding encoding validation) requires 10+ edits.
- **CI blind spot**: Only 4 of 58 test files run in CI (`test_doctor`, `test_dispatch`, `test_capability`, `test_delivery_gates`). The remaining `test_*` files — including all adapter tests (10 adapters, zero coverage) and edge-case tests — are not exercised on push.
- **No static analysis**: No ruff, isort, mypy, or pyright in CI. Style drift and type errors are discovered at runtime.
- **Hardening gaps**: Subprocess calls lack timeouts. I2V adapters lack retry logic despite known 429 rate limits from Grok Imagine. BGM assets directory is empty, forcing runtime API download in the hot path.
- **Slender core coverage**: Critical paths (dispatch layer routing, craft_spine, production_gates) are under-tested given their complexity.

This is not a broken codebase. It's a maturing one that needs systematic attention before debt slows the next feature cycle.

---

## Requirements

- R1. Reduce `aifilm_grok.py` below 1,500 lines by extracting cmd groups into focused modules — without changing any CLI flags or command behavior.
- R2. Eliminate I/O duplication: single `util.py` implementation of `_read_json` / `_write_json` consumed by all callers.
- R3. Full CI: all 58 test files run on push (pre-commit filter for >1s tests). Linting (ruff) and formatting (isort) as CI gates.
- R4. I2V pipeline hardening: configurable timeouts on subprocess calls, retry with backoff for Grok Imagine 429s, OAuth media-queue auto-chain.
- R5. Local BGM asset cache: populate `assets/bgm/rnb/` with license-safe low-bitrate files so runtime goes disk-first.
- R6. All changes pass existing 395 tests plus new tests for extracted modules. `doctor` gate green.

**Origin actors:** A1 (developing agent running dispatch), A2 (operator running `./aifilm doctor` or CLI commands)
**Origin flows:** F1 (text → pipeline → final MP4), F2 (`grok plugin validate` + CI), F3 (BGM/TTS resolution at render time)
**Origin acceptance examples:** AE1 (covers R1, R2 — extraction), AE2 (covers R3 — CI), AE3 (covers R4 — hardening), AE4 (covers R5 — BGM cache)

---

## Scope Boundaries

- No changes to the 4-layer architecture or 8-ring dispatch protocol.
- No migration to a different CLI framework (argparse stays).
- No workflow changes for the end user — all CLI flags, command names, and output formats remain identical.
- No I2V provider changes — Grok Imagine remains the default; no new provider abstractions.

### Deferred to Follow-Up Work

- Type checking (mypy/pyright) in CI: deferred to later wave due to the annotation effort across 29K lines.
- `aifilm_grok.py` complete elimination: goal is extraction to <1,500 lines, not zero. Full elimination would require a new CLI entry pattern.
- Adapter test expansion (10 adapters × smoke tests): scoped to 2-3 priority adapters in this plan; remainder are deferred.
- Performance benchmarking (before/after timing): noted as a future metric but not gated in this plan.

---

## Key Technical Decisions

### KTD-1: `scripts/util.py` as single I/O module
- Consolidate ALL `_read_json` / `_write_json` variants into one `util.py`.
- Always `encoding="utf-8"`, always `ensure_ascii=False` on write.
- Thin: no logging, no config — just read/write + basic file-not-found error wrapping.
- *Rejected alternative*: data-class wrappers or repository pattern — YAGNI for JSON persistence.

### KTD-2: Extraction by cmd group, not by layer
- `aifilm_grok.py` commands naturally cluster: `cmd_project_*`, `cmd_asset_*`, `cmd_audio_*`, `cmd_render_*`, `cmd_doctor_*`, `cmd_export_*`, `cmd_*_meta`
- Extract each cluster to `scripts/cli/<group>.py`. The main file imports and delegates.
- *Why not by 4-layer architecture*: cmd groups cross-cut the layers. Extracting by layer would create circular dependencies.

### KTD-3: CI wave runs ALL tests but allows per-file skip
- All `tests/test_*.py` files are discovered by pytest.
- Tests that genuinely take >1s (e.g., FFmpeg integration, I2V API calls) must opt out via `@pytest.mark.slow` and a `pytest -m "not slow"` as the fast path.
- Full suite runs nightly or on demand; the push CI runs the fast path.
- *Rejected alternative*: explicit allowlist — fragile, requires updating CI on every test add.

### KTD-4: Retry with exponential backoff for I2V
- Wrap Grok Imagine calls in `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2))`.
- Log each retry at `warning` level. After 3 failures, raise a clear `I2VRetryExhausted` error.
- Subprocess calls (`ffmpeg`, `ffprobe`, `grok`) get `timeout=` parameter matching typical operation duration × 2.

---

## Phased Execution

### Wave 0: I/O Consolidation + CI Fix (Session 1, ~45 min)
**Impact**: high. Effort: low. Clears the most duplicated tech debt.

1. Create `scripts/util.py` with `read_json(path)`, `write_json(path, data)`, and symmetrical helper `ensure_dir(path)`.
2. Replace all inline `_read_json` / `_write_json` across all modules (10+ files).
3. Fix `.gitignore` to include `*.bak` patterns.
4. Update CI config (`.github/workflows/ci.yml`) to run `pytest tests/ -q --tb=short` instead of the 4-file allowlist.
5. Add `slow` marker to tests that exceed 1s; make CI run `pytest tests/ -q --tb=short -m "not slow"`.
6. Add `ruff check .` and `ruff format --check .` steps to CI.

**Files changed**: ~15 (util.py new, 10+ modules edited, ci.yml, .gitignore)
**Verification**: `pytest tests/ -q --tb=short` green, `ruff check .` clean, `doctor` green.

### Wave 1: CLI Extraction (Session 1-2, ~90 min)
**Impact**: high. Effort: medium. Addresses the #1 maintainability concern.

1. Create `scripts/cli/` package with `__init__.py`.
2. Identify cmd group boundaries via `add_subparsers()` / `add_parser()` patterns in `aifilm_grok.py`.
3. Extract each group to `scripts/cli/<group>.py` — function takes the parsed args namespace + shared state, returns exit code.
4. Stitch: `aifilm_grok.py` imports all groups, registers parsers, delegates to group functions.
5. Keep argument parsing and `main()` in `aifilm_grok.py` — only the implementation moves.
6. Write smoke tests for each extracted group: does registering the parser succeed? Do known commands parse?

**Files changed**: ~8-12 (cli/ package new, aifilm_grok.py edited down, smoke tests new)
**Verification**: All existing commands work identically. `./aifilm doctor` green. `aifilm_grok.py` line count < 1,500.

### Wave 2: I2V Hardening (Session 2, ~45 min)
**Impact**: medium-high. Effort: low-medium. Prevents silent failures in production.

1. Add `tenacity` to dependencies (or vendored shell — check if already present).
2. Add retry wrapper for Grok Imagine `i2v` calls in adapter modules.
3. Add `subprocess.run(timeout=N)` to all FFmpeg and tool subprocess calls in `render_final.py` and `edit_policy.py`.
4. Add OAuth media-queue auto-chain: after OAuth video generation completes, auto-trigger the next media-queue step instead of requiring manual `queue process` call.
5. Logging: add structured logging (JSON lines) for I2V retries and subprocess timeouts.

**Files changed**: ~4-6 (adapter modules, render_final.py, edit_policy.py, oauth module)
**Verification**: I2V test with simulated 429 responds with retry. Subprocess timeout test raises clean error. OAuth media queue auto-chains in integration test.

### Wave 3: BGM Asset Cache + Test Coverage (Session 2-3, ~60 min)
**Impact**: medium. Effort: medium.

1. Seed `assets/bgm/rnb/` with 3-5 license-safe low-bitrate (96kbps MP3) ~30s loops.
2. Update BGM resolution in pipeline: check local cache first, fall back to API.
3. Expand test coverage for:
   - `test_craft_spine.py` — add edge cases (empty shot list, single shot, genre-specific routing)
   - `test_production_gates.py` — add more hard-gate combinations (pilot + VO budget, loop risk + stale credentials)
   - `test_adapter_smoke.py` — simple "does the adapter import and expose the expected interface" for 3 priority adapters
4. Add `@pytest.mark.slow` to the 2-3 longest tests (FFmpeg integration, full dispatch).

**Files changed**: ~6-8 (core modules for BGM path, test files new/edited, asset files)
**Verification**: BGM resolution hits local disk first. 400+ tests passing. Adapter smoke tests green.

### Wave 4: Polish (Session 3, ~30 min)
**Impact**: low. Effort: low.

1. Inline thin single-use modules: if `selects_report.py` and `evidence_status.py` are <50 lines each with one use site, inline them.
2. Add `config.env.example` schema — comment each variable with expected format, example, and required/optional label.
3. Deduplicate shell wrappers: extract `resolve_pyenv_python()` into `util.py` (appears in ~3 scripts).
4. Final `lsp_diagnostics` sweep on all changed files.

**Files changed**: ~4-6
**Verification**: `doctor` green, `pytest` green, `ruff check .` clean, all CLI commands work.

---

## Dependencies

```
Wave 0 (I/O + CI) ── no deps ── can ship standalone
Wave 1 (CLI extract) ── depends on Wave 0 util.py ── sequential
Wave 2 (I2V harden) ── no deps on Wave 0/1 ── can parallel with Wave 1
Wave 3 (BGM + tests) ── no deps on Wave 0/1/2 ── can parallel with Wave 1-2
Wave 4 (Polish) ── depends on Wave 0 util.py ── sequential
```

Waves 0 → 1 → 4 form a sequential spine (I/O consolidation enables clean extraction, polish is final). Waves 2 and 3 are fully parallel branches off Wave 0.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Extraction breaks CLI flags | Medium | High | Write parser smoke tests BEFORE extraction. Compare `--help` output before/after. |
| CI full suite takes too long (5min+) | Medium | Medium | `@pytest.mark.slow` marker + `-m "not slow"` for push CI. Full suite nightly. |
| I2V retry masks real failures | Low | Medium | Log every retry. Max 3 attempts. Exhaustion raises explicit error (not silent swallow). |
| OAuth auto-chain races media queue | Low | Medium | State machine: media-queue step waits for OAuth `status=completed` before triggering next step. |
| ruff new rules flag pre-existing code | High | Low | First `ruff check` pass may fail on old code. Per-rule baseline in `pyproject.toml`, only new violations block CI. |
| BGM license compliance | Low | Medium | Use only CC0 / royalty-free sources when seeding local cache. Document source in SKILL.md. |

---

## Verification

Each wave is independently shippable. Per-wave gate:

1. `pytest tests/ -q --tb=short -m "not slow"` — green
2. `ruff check .` — clean (or baseline-compliant per Risk row)
3. `ruff format --check .` — clean
4. `./aifilm doctor` — all systems green
5. `grok plugin validate /Users/dex/.grok/plugins/ai-film-grok` — pass

Final gate (all waves complete):
- All 400+ tests pass (fast + slow)
- `aifilm_grok.py` < 1,500 lines
- I/O duplication: zero (single `util.py` route)
- CI runs full test suite
- I2V retry + subprocess timeout documented and tested
- BGM cache populated and functional
- `lsp_diagnostics` clean on all changed files

---

## Sources & References

- [`aifilm_grok.py`](../../skills/ai-film-grok/scripts/aifilm_grok.py) — 4,246 line CLI monolith, target for extraction
- [`AGENTS.md`](../../AGENTS.md) — maintenance areas, pipeline methodology
- [`hard-defaults.md`](../../skills/ai-film-grok/references/hard-defaults.md) — hard gates that must be preserved
- [`pipeline-methodology.md`](../../skills/ai-film-grok/references/pipeline-methodology.md) — 4-layer architecture
- [`ci.yml`](../../.github/workflows/ci.yml) — current CI (4-test allowlist)
- [`config.env.example`](../../skills/ai-film-grok/config.env.example) — needs schema comments
