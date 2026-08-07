# Code metabolism inventory — TERMINAL residual freeze

**Generated:** 2026-08-07  
**Latest batch:** 2.40.78 (C6.1 empty re-verify + C6.4 base contracts)  
**Structure status:** **SAFE QUEUE DONE** · only hub + thrash orchestrator left on purpose  
**Guard:** `tests/test_c6_migrate_queue_empty.py` fails if a new thick top-level appears outside IRON residual set.

## Summary (post 2.40.47)

| Metric | Value |
|--------|------:|
| Top-level modules | ~348 |
| Classified shims | ~346 |
| Non-shim residual (intentional) | **2** |

## Intentional residual (IRON · do not vanity-move)

| Module | Role | Rule |
|--------|------|------|
| `scripts/aifilm_grok.py` | **CLI hub / public entry** | **Keep top-level forever** as the control-plane entry. Further growth goes to `cli/*` packages (already extracted); do not bury hub under a package. Hub size budget remains ≤2500 LOC. |
| `scripts/workflow_pack.py` | **Ship-prep / closeout orchestrator** (~2k LOC thrash surface) | **No whole-file package move or vanity peel.** Peel pure leaves **only when a real bug forces multi-section edit** (bug-driven). Prefer harness tests over structure churn. |

### Explicit non-goals (still binding)

- “Everything under `scripts/` is a package path only”
- Deleting hard-compat shims wholesale
- Giant orchestrator rewrites without failure-mode tests
- Silent heat / `i2v_provider` / pilot policy changes in structure commits

## Completed waves (pointer)

| Batch | Theme |
|-------|--------|
| W0–W7 | packages + hub extract + shims |
| 2.40.38–46 | safe residual + expanded residual P3-1 |
| 2.40.47 | path-depth residual + depth fixes |
| **2.40.48** | **freeze documentation + structural guard tests** |

## Four lanes (unchanged)

| Lane | Status |
|------|--------|
| A DELETE | empty for whole files |
| B TOMBSTONE | lipsync thin |
| C MIGRATE | **safe queue emptied** |
| D PEEL | bug-driven only on remaining thick bodies (`workflow_pack`, `render_final`, …) |

## Iron

Public `aifilm` subcommand strings · hard-compat shims · dual-checkout discipline · no vanity LOC sprint.
