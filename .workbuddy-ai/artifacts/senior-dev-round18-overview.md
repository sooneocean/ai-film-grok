# Senior Dev — Round 18 Overview (2026-08-06)

**Context:** User said `go` (圣旨协议 = drive the next open quality item to completion, including dual-remote push, no re-opened discussion). Continuation of P3-1 legacy-module decomposition.

## What shipped

### P3-1 batch 2 — v2.40.33 (commit `806bb99`)
- Migrated 3 media probe modules into `media/` via `git mv` (history preserved):
  `seedvr2_probe`, `wan_dancer_probe`, `wan_fun_control_probe` (all 0-importer).
- Updated 3× 1:1 contract tests (imports + `@patch` targets to `media.X._json_request`; `probe_command` assertion path).
- Synced `registry/comfy-weapons.json` 3 `probe_command` paths to `scripts/media/<name>.py`.
- 12 tests pass, ruff clean. **Committed + pushed dual-remote** (left uncommitted from prior summary).

### P3-1 batch 3 — v2.40.34 (commit `e4f7fca`)
- Migrated 3 zero-importer business modules into existing packages:
  - `color_grade.py` → `scripts/post/`
  - `dailies_selects.py` → `scripts/post/`
  - `source_chain.py` → `scripts/assets/`
- Updated 3× 1:1 tests (`from post.X` / `from assets.X`); 17 tests pass; ruff clean.

### 🔴 Critical fix — `runtime-lock.json` fingerprint drift
- v2.40.33 had **missed `runtime-lock.json`** when migrating the 4 probes (only `registry` was synced) → `make doctor` `runtime_lock.ok` went `false`, `core_readiness.failed_checks=["runtime_lock"]`.
- This round ran `make lock-runtime`, regenerating the lock. It fixed:
  1. The 4 probe path drifts missed in v2.40.33.
  2. Pre-existing **content** drift from the concurrent `h3 8s cap` merge (`adapters/`, `audio/tts_backend`, `gates/*`, `final/errors`, `media/h3_workflow`, `spine/advance`, `stable_audio_adapter`, …).
- After regen: `make doctor` fully green (`runtime_lock.ok=true`, `failed_checks=[]`). Lock diff = 56 insertions / 52 deletions (expected).

## Verification
- `pytest` on migrated modules: 12 (batch 2) + 17 (batch 3) = 29 passed.
- `ruff` clean on all touched files.
- `make doctor` → `core_readiness.ok=true`, `runtime_lock.ok=true`.
- Dual-remote push: origin dual pushurl covers Gitea + GitHub; `divergence(origin..github)=0`. No race this turn.

## Reusable lesson (P3-1 migration checklist)
When migrating a module, you MUST run `make lock-runtime` to regenerate `runtime-lock.json` — not just sync `registry/comfy-weapons.json`. Runtime-lock drift is also triggered by any content change to `scripts/` (incl. concurrent merges), so regenerating before commit is good hygiene.

⚠️ Zero-importer ≠ zero-risk: `backend_lock`, `burn_srt_pil` (pathed via `final_stages.py`), `comfy_broker_service` (`.ps1`), `lipsync_*` (`runtime_policy.py` allow-list), `mmaudio_*`, `seedance_bridge` carry shell-wrapper / policy / cross-script path references — grep & handle those before moving (or skip).

## P3-1 progress
- Cumulative migrated: **9 / 109+** legacy top-level modules.
- Remaining zero-importer candidates: ~19 (e.g. `cli_hub_residual`, `film_spec_lints`, `golden_suite`, `story_normalize`; some show stale dual paths in lock — vet carefully).
- P4 / P5-1 continue in subsequent rounds.

## Commits
- `806bb99` v2.40.33 — 3 media probes → media/ (batch 2 closeout)
- `e4f7fca` v2.40.34 — color_grade/dailies_selects/source_chain → packages + runtime-lock regen
