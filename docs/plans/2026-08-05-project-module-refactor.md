# Project module refactor — ACTIVE tracker (2026-08-05)

**Status:** ACTIVE · **W0–W3 SHIPPED** · W4 leaf peel optional next  
**Evidence:** `scripts/{core,assets,spine,gates,plan}/` · `tests/test_w3_package_shims.py` · hub ≤2500

## Waves

| Wave | Theme | Status |
|------|--------|--------|
| W0 | Tracker + baseline | **DONE** |
| W1 | `scripts/core/*` · break cli↔hub IO cycle | **DONE** (on origin/main) |
| W2 | CLI parser/cmd extract · hub ≤2500 | **DONE** (hub 1455) |
| W3 | Package dirs + top-level shims | **DONE** (v2.39.44) |
| W4 | Domain monoliths → packages | **DONE** (post/render_final · narrative/edit_policy_heat) |
| W5 | Docs / AREA align / shim audit | **DONE** |

## Iron
Public `aifilm` subcommand strings unchanged · shims hard-compat · no silent heat/i2v_provider/pilot policy change.

## Related

- [2026-08-05-strategy-director-engineer-upgrade.md](2026-08-05-strategy-director-engineer-upgrade.md) — dual-lens residual queue (S3 = W3+, not re-do W1/W2)
- [cli-extract-map.md](cli-extract-map.md) — prior CLI domain extracts
- [REFACTORING_PLAN.md](../../REFACTORING_PLAN.md) — older P0–P3 (superseded by this tracker for structure)
- AGENTS.md AREA table — test map


## W3 batch (v2.39.44–45)

- packages: spine · assets · plan · gates (+ core)
- hard-compat shims via sys.modules
- path fixes: skill_scripts / advance / plan schemas
- verified: 43+ domain tests; main smoke import ok


## W4–W5 closeout

- **W4**: `render_final` → `scripts/post/render_final.py` + top-level shim; `edit_policy_heat` → `scripts/narrative/edit_policy_heat.py` + shim.
- Internal leaf-split of 4k-line monoliths deferred (import graph / cycle risk); package boundary is the ship gate.
- **W5**: AGENTS layout + AREA pointers; this tracker marked DONE for W3–W5.
- Iron: public imports and CLI strings unchanged (`sys.modules` shims).
