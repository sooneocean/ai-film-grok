# Code metabolism inventory — 2026-08-07

**Generated:** 2026-08-07T00:55:28Z
**Latest batch:** 2.40.47

## Summary

| Metric | Value |
|--------|------:|
| Top-level modules | 348 |
| Classified shims | 346 |
| Non-shim residual | 2 |

## Batch 2.40.47 (round 6 · path-depth residual)

| Package | Modules | Depth fix |
|---------|---------|-----------|
| `spine/` | automation_verify, route_catalog, skill_registry, skill_runner | parents[2] / scripts sibling launchers |
| `util/` | config_loader, runtime_policy, security_policy, structured_logger (shim `logger`) | config.env parents[3] |
| `plan/` | capability_report, motion_prompt_spine, optimization_metrics | skill_root parents[2]; metrics parent-walk OK |
| `media/` | backend_lock, env_plate, interactive_orchestration | skill root / scripts sibling paths |

## Still residual (intentionally)

`aifilm_grok` hub · `workflow_pack` giant thrash orchestrator

## Iron

Public import names via shims · path depth adjusted · no heat/i2v/pilot retune.
