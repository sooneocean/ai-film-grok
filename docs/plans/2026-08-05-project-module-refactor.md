# Project module refactor — ACTIVE tracker (2026-08-05)

**Status:** ACTIVE · W0–W2 done · hub ~1513 LOC · plugin 2.39.30  
**Selection:** Full A+B+C · hard compatibility (shims; public CLI strings never rename)  
**Session plan:** Grok plan mode `plan.md` (module blocks)

## Baseline (W0 · 2026-08-05)

| Metric | Value |
|--------|------:|
| plugin | 2.39.29 (pre-W1) |
| top-level `scripts/*.py` | 319 |
| `cli_*.py` modules | 36 |
| `aifilm_grok.py` LOC | 5028 |
| `render_final.py` | 4333 |
| `edit_policy_heat.py` | 4015 |
| `film_spec.py` | 3234 |
| `story_plan.py` | 2858 |
| `export_composition.py` | 2835 |

## Waves

| Wave | Theme | Status |
|------|--------|--------|
| W0 | Tracker + baseline | **DONE** |
| W1 | `scripts/core/*` · break cli↔hub IO cycle | **DONE** |
| W2 | CLI parser/cmd extract · hub ≤2500 | **DONE** (~1513 LOC) |
| W3 | Package dirs + top-level shims | pending |
| W4 | Domain monoliths (render_final / heat / …) | pending |
| W5 | Docs / AREA align / shim audit | pending |

## Iron

- Public `aifilm` subcommand strings unchanged
- Old imports keep working via re-export / shim
- Per-wave: `make check-all` + `make lock-runtime` when scripts fingerprints change
- No silent heat / i2v_provider / pilot policy changes

## Related

- [cli-extract-map.md](cli-extract-map.md) — prior CLI domain extracts
- [REFACTORING_PLAN.md](../../REFACTORING_PLAN.md) — older P0–P3 (superseded by this tracker for structure)
- AGENTS.md AREA table — test map
