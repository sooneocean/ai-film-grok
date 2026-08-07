# Honesty-rail evidence · 2026-08-07

**Version:** 2.40.68  
**Plan:** [delivery-honesty-rail](../plans/2026-08-07-delivery-honesty-rail-todoplan.md)

## Units

| Wave | Unit | Evidence |
|------|------|----------|
| R1 | `core/skip_audit.py` | skip_flag / sync / verify / attach |
| R1 | closeout + official-final | `skips_used` · PARTIAL if iron unreasoned |
| R1 | tests | `pytest tests/test_skip_audit.py` |
| R2 | `core/attestation_audit.py` | ledger + pending_human_review |
| R2 | anatomy + register | require_anatomy_safe writes ledger |
| R2 | tests | `pytest tests/test_attestation_provenance.py` |
| R3 | `core/checkout_drift.py` | HEAD mismatch warn |
| R3 | doctor | `checkout_drift` field always |
| R3 | tests | `pytest tests/test_checkout_drift.py` |

## SURFACE (local)

```bash
export AIFILM_SKIP_CINEMATIC_GATE=1
# no reason → closeout skip_audit classification=PARTIAL
# with AIFILM_SKIP_REASON='demo' → SKIP_DOCUMENTED
aifilm doctor   # report.checkout_drift
```

## Residual

- R4 I5 ops canary / pgrep audit (OPEN_OPS without GPU)
- Touch-migrate remaining ~100 direct `os.environ AIFILM_SKIP_*` readers to `skip_flag` opportunistically
