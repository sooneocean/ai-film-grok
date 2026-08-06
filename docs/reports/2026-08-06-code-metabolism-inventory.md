# Code metabolism inventory — 2026-08-06

**Generated:** 2026-08-06T11:14:02Z
**Batch:** 2.40.38

## Summary

| Metric | Value |
|--------|------:|
| Top-level modules | 348 |
| Classified shims | 256 |
| Non-shim top-level | 92 |
| Functions ≥200 LOC | 74 |
| Max function | 2456 `post/render_final.py::render_final` |

## Four lanes

| Lane | Rule |
|------|------|
| A DELETE | 0 import ∧ 0 CLI ∧ 0 test (empty this scan) |
| B TOMBSTONE | frozen public API (lipsync) keep thin |
| C MIGRATE | low-importer → package + thin hard-compat shim |
| D PEEL | giant orchestrators → pure leaves |

## This batch (C + D)

| Module | Package | Shim |
|--------|---------|------|
| `vo_lint` | `narrative/` | top-level |
| `native_text_gate` | `gates/` | top-level |
| `seedance_bridge` | `media/` | top-level |
| `show_package` | `post/` | top-level |
| `gold_calibration` | `plan/` | top-level |
| `golden_suite` | `gates/` (prior) | shim added |
| `color_grade` | `post/` (prior) | shim added |
| `realesrgan_probe` | `media/` (prior a635a6fc) | already shimmed |

**Peel:** `post/render_final.resolve_plate_slot_sec`.

## Giant Top-12

| LOC | Path | Function |
|----:|------|----------|
| 2456 | `post/render_final.py` | `render_final` |
| 2322 | `plan/film_spec_validate.py` | `validate_film_spec` |
| 1937 | `gates/preflight.py` | `run_preflight` |
| 1189 | `spine/dispatch.py` | `build_dispatch` |
| 785 | `post/export_composition.py` | `write_hyperframes` |
| 765 | `post/post_audit.py` | `audit` |
| 745 | `cli/cli_post.py` | `cmd_final` |
| 734 | `post/closeout.py` | `closeout_status` |
| 681 | `plan/story_plan.py` | `project_graph_to_film_spec` |
| 653 | `cli/cli_post.py` | `add_post_parsers` |
| 648 | `spine/next_actions.py` | `build_next_actions` |
| 591 | `state_index_gate.py` | `run_state_index_check` |

## Iron

- Public CLI strings unchanged · hard-compat shims · no heat/i2v/pilot retune.

