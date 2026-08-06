# Code metabolism inventory — 2026-08-06

**Generated:** 2026-08-06T13:49:54Z
**Latest batch:** 2.40.44

## Summary

| Metric | Value |
|--------|------:|
| Top-level modules | 348 |
| Classified shims (incl. star-reexports) | 313 |
| Non-shim top-level residual | 35 |

## Four lanes

| Lane | Rule |
|------|------|
| A DELETE | empty for whole files |
| B TOMBSTONE | lipsync keep thin |
| C MIGRATE | package + hard-compat shim (**primary**) |
| D PEEL | pure leaves only on touch (done in prior batches) |

## Batch 2.40.44 — safe residual closeout (29 modules)

Moved with thin `sys.modules` shims (public `import name` preserved):

composition_anti_hijack, creative_pipeline, creative_quality, creative_workshop, department_cli, department_contracts, director_ledger, evidence_status, external_review, film_spec_profile, h3_timeline_prompt, master_delivery, mix_partial, optimization_program, performance_cue, plan_feedback, promotion_report, quality_check_video, quality_closure, quality_ledger, real_footage, review_ui, semantic_index, serial_quality, shortform_director, speech_performance_timing, transaction_receipt, transition_frame_audit, transition_ops

### Package targets
- `plan/`: composition_anti_hijack, creative_*, department_*, director_ledger, evidence_status, film_spec_profile, mix_partial, optimization_program, performance_cue, plan_feedback, promotion_report, quality_*, semantic_index, serial_quality, shortform_director, transition_ops
- `post/`: external_review, master_delivery, review_ui, transition_frame_audit
- `media/`: h3_timeline_prompt, real_footage
- `audio/`: speech_performance_timing
- `spine/`: transaction_receipt

## Residual non-shim (intentionally skipped)

Path-depth / high-importer / thrash giants (not safe residual queue):
`aifilm_grok` hub · `workflow_pack` · `input_fidelity` · `backend_lock` · `env_plate` · `config_loader` · `skill_runner` · `runtime_policy` · `security_policy` · high-imp director/quality hubs · etc.

## Iron

Public import names via shims · no heat/i2v/pilot retune · no giant orchestrator rewrite.
