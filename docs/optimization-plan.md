# Optimization Iteration Plan · ai-film-grok

> Generated 2026-08-05 from codebase analysis. Prioritized by impact × effort ratio.
> Each item is a todo-ready work package. Run `make check-all` after each batch.

---

## P0 — Critical Duplication (est. 40–60% code reduction in hot paths)

| # | Work Package | Files Affected | Impact | Effort |
|---|---|---|---|---|
| 1 | **Extract shared `_sha256_file` utility** — 18 files reimplement identical SHA-256 hashing | `still_challenge.py`, `lipsync_node_service.py`, `lipsync_node_client.py`, `mmaudio_adapter.py`, `sfx_library.py`, `bgm_candidates.py`, `audio_delivery_gate.py`, `backend_probe.py`, `stable_audio_probe.py`, `wardrobe_ladder.py`, `face_identity_hash.py`, `delivery_package.py`, `cinematic_audit.py`, `bgm_library.py` | HIGH — eliminates ~108 lines of duplicated crypto; ensures consistent hashing | LOW |
| 2 | **Extract shared `_load_spec()`, `_iter_shots()`, `_root()` utilities** | `h3_workflow.py`, `h3_fill_idle.py`, `still_challenge.py`, `generation_request.py` | HIGH — eliminates ~90 lines; fixes behavioral inconsistency (`_load_spec` returns `{}` vs raises) | LOW |
| 3 | **Extract shared HTTP/REST helper module** (`scripts/util/http_client.py`) | `grok_oauth.py`, `voicebox_tts.py`, `tts_backend.py`, `env_plate.py`, `frw_canary.py`, `frw_lipsync.py`, `music_external.py` | HIGH — eliminates ~200 lines of duplicated urllib boilerplate; centralizes retry/timeout policy | MEDIUM |
| 4 | **Extract shared `read_json` / `flatten_shots` / `narration_for_shot`** into a single utility | `render_final.py`, `export_composition.py`, `compose_render.py`, `caption_text.py`, `continuity_chain.py`, `i2v_motion_gate.py`, `pilot_review.py` | HIGH — 5 different `read_json` wrappers, 4 `flatten_shots` implementations, 2 `narration_for_shot` variants | MEDIUM |
| 5 | **Extract shared `_pilot_user_ok`, `_post_audit_current`, `_present`** from spine | `craft_spine.py`, `next_actions.py`, `workflow_spine.py`, `dispatch.py` | HIGH — inconsistency in pilot approval fallback causes different results depending on code path | MEDIUM |
| 6 | **Extract shared atomic output helper** (`_open_output_parent` + `_install_output`) | `piper_local_tts.py`, `chatterbox_local_tts.py` | MEDIUM-HIGH — byte-for-byte identical; ensures consistent atomic writes | LOW |
| 7 | **Extract shared WAV/MP3 ffmpeg conversion helper** | `voicebox_tts.py`, `cosyvoice_tts.py`, `kokoro_tts.py`, `chatterbox_local_tts.py`, `elevenlabs_tts.py`, `music_external.py` | MEDIUM — 6 implementations of identical ffmpeg command | LOW |

---

## P1 — Performance (I/O & CPU bottlenecks)

| # | Work Package | Files Affected | Impact | Effort |
|---|---|---|---|---|
| 8 | **Cache/incrementalize `compute_state_hash()`** | `dispatch_compact.py`, `dispatch.py`, `advance.py` | HIGH — full directory tree walk on every dispatch cycle; called 4× per autopilot invocation | MEDIUM |
| 9 | **Eliminate redundant file reads in dispatch chain** — pass pre-read project state through `build_dispatch()` → `build_next_actions()` → `build_workflow_status()` | `dispatch.py`, `next_actions.py`, `workflow_spine.py`, `craft_spine.py`, `project_state.py` | HIGH — same JSON files read 5–10× per dispatch cycle | MEDIUM |
| 10 | **Cache `read_json` within a single process** (LRU or module-level dict) | All gates files, especially `preflight.py` (15+ check blocks each reading `film-spec.json`, `manifest.json` independently) | HIGH — eliminates redundant disk I/O across 15+ check blocks | MEDIUM |
| 11 | **Extract `build_dispatch()` into focused sub-functions** | `dispatch.py` (1467 lines, monolithic) | MEDIUM — enables targeted testing and optimization of individual stages | MEDIUM |
| 12 | **Refactor `media_queue.py` `add_job()` (379 lines) and `comfy_video.py` `_driver_vr_probe()` (130 lines)** into smaller functions | `media_queue.py`, `comfy_video.py` | MEDIUM — reduces bug surface; improves testability | MEDIUM |
| 13 | **Remove dead code**: `FrwWanProvider`/`LocalComfyWan22Provider` registrations, `comfy_video.py` unreachable `generate()`, `export_composition.py` unreachable `build_title_sequence_html` lines 960–990 | `i2v_provider.py`, `comfy_video.py`, `export_composition.py` | MEDIUM — reduces cognitive load and import-time noise | LOW |
| 14 | **Break `preflight.py` `run_preflight()` (1721 lines) into composable `check_*()` functions** | `preflight.py` | MEDIUM — makes 15+ checks independently testable; eliminates bare `except Exception` swallowing | HIGH |

---

## P2 — Maintainability & Architecture

| # | Work Package | Files Affected | Impact | Effort |
|---|---|---|---|---|
| 15 | **Unify `_STAGE_OWNERS` (dispatch.py) and `_STAGE_RESPONSIBILITY` (next_actions.py)** into single shared constant | `dispatch.py`, `next_actions.py`, `project_state.py` | MEDIUM — overlapping data with different structures causes extra type-checking | LOW |
| 16 | **Consolidate `render_final.py` re-export layer** into proper module boundaries or dedicated compat shim | `render_final.py` (re-exports 50+ symbols) | MEDIUM — "god object" pattern masks module boundaries; causes test monkeypatching to target wrong module | MEDIUM |
| 17 | **Fix backward dependency**: move `_shot_visual_blob` / `_shot_visual_pose_blob` from `edit_policy_heat.py` to `edit_policy.py` | `edit_policy_heat.py`, `edit_policy.py` | MEDIUM — heat importing from base creates circular dependency risk | MEDIUM |
| 18 | **Replace raw `subprocess.run` with `util.subprocess.run`** across `node/` and `plan/` | `backend_probe.py`, `stable_audio_probe.py`, `latentsync_adapter.py`, `musetalk_adapter.py`, `narrative_evidence.py`, `shot_review.py`, `clip_uniqueness.py` | MEDIUM — bypasses security policy minimal-env wrapper; inconsistent timeout/error handling | MEDIUM |
| 19 | **Replace inline `_now()` / `datetime.now(UTC)` with `util.time.utc_now()`** | `narrative_evidence.py`, `shot_review.py`, `face_identity_hash.py`, `continuity_chain.py`, `bgm_library.py` | MEDIUM — ensures consistent timestamp format across codebase | LOW |
| 20 | **Consolidate `film_output_path` / `valid_shot_id`** — remove duplicates from `core/paths.py`, import from `util/validators.py` | `core/paths.py`, `util/validators.py` | MEDIUM — two definitions of same logic must be kept in sync | LOW |
| 21 | **Extract `_stable_hash` in `drama_graph.py` and `shot_package.py`** to use `util.json_io.canonical_json_sha256` | `drama_graph.py`, `shot_package.py` | LOW — ensures canonical hashing logic is single source of truth | LOW |
| 22 | **Replace bare `except Exception` / `except ImportError` with proper error handling** across `assets/`, `plan/`, `node/` | `asset_registry.py`, `drama_graph.py`, `story_plan.py`, `latentsync_adapter.py`, `musetalk_adapter.py`, `face_identity_hash.py`, `wardrobe_ladder.py` | MEDIUM — silent swallowing makes debugging extremely difficult | MEDIUM |

---

## P3 — Test Coverage & Quality

| # | Work Package | Files Affected | Impact | Effort |
|---|---|---|---|---|
| 23 | **Expand preflight test coverage** — currently only 4 of 15+ checks tested | `test_preflight.py`, `preflight.py` | HIGH — heat duration floor, character stance, VO drag, PPT risk, true-video policy, keyframe geometry, P4 fulfillment, continuity chain, etc. all untested | MEDIUM |
| 24 | **Add gates test coverage** for `delivery_artifact.py`, `delivery_package.py`, `cinematic_audit.py` | No dedicated test files exist | MEDIUM — these are critical export paths with no test safety net | MEDIUM |
| 25 | **Add `pytest.mark.slow` markers** to `test_release_gate.py` (creates real git repos with worktrees per test) and other slow tests | `test_release_gate.py`, `test_premium_pipeline_contracts.py` | LOW — enables `make test-fast` to skip truly slow integration tests | LOW |
| 26 | **Add `hotpath` marker to final/compose/gates fail-mode contract tests** and ensure they stay on fast suite | TBD | MEDIUM — protects the critical path from slow test pollution | LOW |
| 27 | **Test monkeypatch fix** — `render_final.py` re-exports cause tests to monkeypatch the wrong module | `render_final.py` + affected test files | MEDIUM — tests may be silently not exercising the real code path | MEDIUM |

---

## P4 — Debt Cleanup

| # | Work Package | Files Affected | Impact | Effort |
|---|---|---|---|---|
| 28 | **Remove retired provider registrations** (`FrwWanProvider`, `LocalComfyWan22Provider`) | `i2v_provider.py` | LOW — dead code at import time | VERY LOW |
| 29 | **Remove `# pragma: no cover` from ImportError branches** in `render_final.py` — either make them testable or document why they can't be | `render_final.py` | LOW | VERY LOW |
| 30 | **Add `AIFILM_RELEASE_GATE=full` CI step** to `.github/workflows/ci.yml` for release branches | `.github/workflows/ci.yml` | MEDIUM — current CI only runs light gate | MEDIUM |
| 31 | **Add `make audit` to CI** to catch drift between `project_audit.py` expectations and reality | `.github/workflows/ci.yml` | LOW | LOW |

---

## Execution Order (Recommended Sprints)

### Sprint 1 — Quick Wins (1–2 days)
Items 1, 2, 6, 7, 13, 15, 19, 20, 21, 28, 29

### Sprint 2 — Shared Utilities (2–3 days)
Items 3, 4, 5, 18, 16, 17

### Sprint 3 — Performance (2–3 days)
Items 8, 9, 10, 11, 12

### Sprint 4 — Architecture (2–3 days)
Items 14, 22

### Sprint 5 — Tests (1–2 days)
Items 23, 24, 25, 26, 27

### Sprint 6 — CI/CD (1 day)
Items 30, 31

---

## Key Metrics to Track

1. **Duplication score**: Count of `_sha256`, `_load_spec`, `_root`, `read_json`, `flatten_shots` definitions across codebase (target: reduce by 60%)
2. **`make check-all` runtime**: Baseline → target 30% faster after I/O caching
3. **Test coverage**: Gates + post + narrative modules (target: 80% line coverage)
4. **Largest file size**: `edit_policy_heat.py` (4026 lines), `film_spec.py` (3136 lines), `story_plan.py` (2858 lines) — target: decompose to <1500 lines each
5. **Bare `except Exception` count**: Target reduction by 50%

---

## Dependencies Between Items

```
Item 1 (sha256 util) ──┐
Item 2 (spec/shots util) ──┤
Item 6 (atomic output) ──┤
Item 7 (ffmpeg convert) ──┤
                        ├──→ Sprint 1 (all independent, can run in parallel)
Item 3 (http client) ──┤
Item 4 (film helpers) ──┤
Item 5 (pilot/post-audit) ──┤
                        ├──→ Sprint 2 (some share extraction patterns from Sprint 1)
Item 8 (state hash cache) ──┐
Item 9 (redundant I/O) ──────┤
Item 10 (read_json cache) ──┤
                           ├──→ Sprint 3 (I/O optimization batch)
Item 11 (dispatch decomposition) ──┐
Item 14 (preflight decomposition) ──┤
                                   ├──→ Sprint 4 (architecture batch)
Item 22 (bare except fix) ──────────┘
```

---

*Plan follows AGENTS.md conventions. Each item should be validated with `make check-all` and relevant pytest before marking done.*
