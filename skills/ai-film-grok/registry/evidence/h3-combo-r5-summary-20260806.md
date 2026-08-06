# H3 Combo R5 · 2026-08-06 · family/system prompt revalidation

**Root**: `artifacts/5090-evaluation/h3-combo-r5-family-20260806`  
**Still**: r4 soft portrait still (same seed 20260805, steps 20)  
**Matrix**: round-4 order (7 combos), post family-apply + system-clause code

## Results (all ok)

| combo | mode | family | motion | start_L1 | mouth |
|-------|------|--------|--------|----------|-------|
| r4_high_tl_i2v | i2v | high_motion_max | **18.1** | 19.6 | 26.1 |
| r4_high_tl_r2v | r2v | high_motion_max | **25.4** | 20.6 | 46.1 |
| r4_high_flat_r2v | r2v | high_motion_flat | 20.8 | 20.7 | 55.0 |
| r4_dlg_flat_i2v | i2v | dialogue_mouth_flat | 18.2 | 19.4 | **48.4** |
| r4_dlg_tl_i2v | i2v | dialogue_mouth_max | 11.9 | 19.5 | 30.5 |
| r4_dlg_tl_r2v | r2v | dialogue_mouth_max | 12.4 | **66.0** (id weak) | 24.8 |
| r4_soft_tl_i2v | i2v | soft_portrait_alive | **5.5** | 19.4 | 22.9 |

## Lane winners → registry

| lane | mode | family | note |
|------|------|--------|------|
| hero_identity_lock | i2v | soft_portrait_alive | identity≈74; micro-life still soft mean~5.5 |
| high_motion_energy | r2v | high_motion_max | mean **≥20** confirmed (25.4 > flat 20.8) |
| dialogue_mouth_energy | i2v | dialogue_mouth_flat | mouth metric win; mid L1≈77 drift — see runner_up max |
| faceless_env | t2v | env_no_face | policy-only |

## Ops lesson
After each H3 job, VRAM often sits ~9–10 GiB free with idle queue → capacity floor blocks next job. **free-memory every job**, not only mode switch (code fixed in same release).

## Receipts
- `compare/verdict.json` · `compare/winners-merged.json` · `receipts/combo-eval-r5.json`
