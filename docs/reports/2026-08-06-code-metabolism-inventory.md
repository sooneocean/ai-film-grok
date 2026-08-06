# Code metabolism inventory — 2026-08-06

**Generated:** 2026-08-06T11:41:14Z
**Latest batch:** 2.40.41

## Summary

| Metric | Value |
|--------|------:|
| Top-level modules | 348 |
| Classified shims | 265 |
| Non-shim top-level | 83 |

## Four lanes

| Lane | Rule |
|------|------|
| A DELETE | empty for whole files |
| B TOMBSTONE | lipsync keep thin |
| C MIGRATE | package + hard-compat shim |
| D PEEL | pure leaves from orchestrators |

## Batch 2.40.41

| Module | Package |
|--------|---------|
| `review_pack` / `picture_lock` / `auto_cut` / `local_omni_review` | `post/` |
| `speech_preview` | `audio/` |
| `reference_audit` | `media/` |
| `shortform_motion` / `prompt_compression_pilot` / `optimization_experiments` / `motion_plan` | `plan/` |

**Peel:** `coerce_optional_float` for optional `in_point_sec`.  
**P4:** `tests/test_core_constants.py`.

## Prior

- 2.40.39: 8 modules + plate-slot sites + core.emit  
- 2.40.38: 5 modules + plate-slot intro + golden/color shims  

## Iron

Public import names via shims · no heat/i2v/pilot retune.
