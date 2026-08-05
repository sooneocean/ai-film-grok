# Project module refactor — ACTIVE tracker (2026-08-05)

**Status:** ACTIVE · **W0–W3 SHIPPED** · W4 leaf peel optional next  
**Evidence:** `scripts/{core,assets,spine,gates,plan}/` · `tests/test_w3_package_shims.py` · hub ≤2500

## Waves

| Wave | Theme | Status |
|------|--------|--------|
| W0 | Tracker + baseline | **DONE** |
| W1 | `scripts/core/*` | **DONE** |
| W2 | CLI extract · hub ≤2500 | **DONE** |
| W3 | Package dirs + shims | **DONE** |
| W4 | Domain monoliths (render_final / heat) | **optional** (hotpath failure tests cover ship risk; partial peels may exist) |
| W5 | Docs / AREA / shim audit | **DONE** (AGENTS AREA package pointers) |

## Iron
Public `aifilm` subcommand strings unchanged · shims hard-compat · no silent heat/i2v_provider/pilot policy change.

## Related
- [2026-08-05-strategy-director-engineer-upgrade.md](2026-08-05-strategy-director-engineer-upgrade.md)
