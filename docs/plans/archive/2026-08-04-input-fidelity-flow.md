# Input Fidelity + Flow · 2026-08-04

**Status:** **F0–F3 + S SHIPPED** (v2.39.0)  

## Shipped

| Wave | Item |
|------|------|
| F0 | `input_fidelity.py` score · `fidelity status\|check` · receipt |
| F1 | `fidelity apply` source_quote / must_keep / protected dialogue |
| F2 | Story beat I2V prefix · still source overlap on register-still |
| F3 | closeout + ship-prep `input_fidelity` step · assert final optional hard |
| S | design-go · dispatch compact fidelity · next_actions · advance/autopilot allowlist |

## Commands

```bash
aifilm fidelity apply --root "<film>"
aifilm fidelity check --root "<film>"
aifilm design-go --root "<film>"
aifilm ship-prep --root "<film>"
aifilm closeout status --root "<film>"
```

## Env

- `AIFILM_FIDELITY_STRICT=1`
- `AIFILM_STILL_SOURCE_OVERLAP_STRICT=1`
- `AIFILM_SKIP_FIDELITY_FINAL_GATE=1`
