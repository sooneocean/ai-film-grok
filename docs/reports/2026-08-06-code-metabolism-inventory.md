# Code metabolism inventory — 2026-08-06

**Generated:** 2026-08-06T11:34:48Z
**Latest batch:** 2.40.39

## Summary

| Metric | Value |
|--------|------:|
| Top-level modules | 348 |
| Classified shims | 255 |
| Non-shim top-level | 93 |
| Functions ≥200 LOC | 74 |
| Max function LOC | 2450 |

## Four lanes

| Lane | Rule |
|------|------|
| A DELETE | 0 import ∧ 0 CLI ∧ 0 test (empty) |
| B TOMBSTONE | frozen lipsync keep thin |
| C MIGRATE | package + thin hard-compat shim |
| D PEEL | pure leaves from giant orchestrators |

## Batch 2.40.39 (this round)

| Module | Package |
|--------|---------|
| `render_workspace` | `post/` |
| `vo_atempo` | `audio/` |
| `context_routing` | `spine/` (+ SKILL_ROOT parents[2]) |
| `benchmark` | `plan/` |
| `provider_canary` | `media/` |
| `product_brief` | `plan/` |
| `planning_autopilot` | `plan/` |
| `elevenlabs_canary` | `audio/` |

**Peel:** more `resolve_plate_slot_sec` call sites (cue triangle + visual slot).  
**P4:** `tests/test_core_emit.py` for `core.emit`.

## Prior batch 2.40.38

vo_lint, native_text_gate, seedance_bridge, show_package, gold_calibration + golden_suite/color_grade shims + first plate-slot peel.

## Iron

Public import names via shims · no heat/i2v/pilot retune in structure commits.
