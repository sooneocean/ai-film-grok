# Honesty-rail evidence · 2026-08-07

**Version:** 2.40.75  
**Plan:** [delivery-honesty-rail](../plans/2026-08-07-delivery-honesty-rail-todoplan.md) · **R0–R5 CLOSED**

## Units

| Wave | Unit | Evidence |
|------|------|----------|
| R1 | `core/skip_audit.py` | skip_flag / sync / verify / attach |
| R1–R4 | closeout · attestation · checkout · I5 | prior ship 2.40.68–71 |
| **R5** | 板间账实 | CTO/iron/honesty headers ↔ plugin **2.40.75** |
| **R5+** | skip 触达 wave | anti-hijack · generation · scale · fill · five_track · variety · fidelity · dialogue package · motion core · meaning · rebind · continuity · pilot-go · bulk preflight · ship-prep · render_final |

## Tests

```bash
pytest skills/ai-film-grok/tests/test_skip_audit.py  # includes test_round2_hotpath_skips_ledger
```

## Residual (non-blocking)

- 少量 CLI 直读 `AIFILM_SKIP_*`（face identity / motion mean / write_spec duration）可继续触达
- closeout `sync_armed_env_skips` 仍兜底扫 env
