# Honesty-rail evidence · 2026-08-07

**Version:** 2.40.71  
**Plan:** [delivery-honesty-rail](../plans/2026-08-07-delivery-honesty-rail-todoplan.md) · **R0–R4 CLOSED**

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
| R4.1 | soft-hog | `test_run_next_soft_hog` + `test_gpu_no_hog` |
| R4.2 | no pgrep -f invoke | `local_comfy_client_status` → ps; `test_pgrep_no_source_match` |
| R4.3 | OPEN_OPS | `attach_open_ops_status` · `test_openops_receipt` |

## SURFACE (local)

```bash
export AIFILM_SKIP_CINEMATIC_GATE=1
# no reason → closeout skip_audit classification=PARTIAL
aifilm doctor   # report.checkout_drift

# drain end: receipts/fill-idle-until-empty.json → open_ops_status
```

## Residual (non-blocking)

- Opportunistic migrate remaining direct `os.environ AIFILM_SKIP_*` readers
- True overnight GPU drain canary when user owns 5090 (OPEN_OPS without GPU is OK)
