# CLI extract map — aifilm_grok.py domain split

**Status:** ACTIVE · 2026-08-05 · v2.39.18  
**Goal:** shrink `aifilm_grok.py` toward <2500 lines by extracting cmd handlers only.  
**Iron:** public subcommand strings never rename.

## Baseline

| Metric | Before C2 | After C2 | After C3 | After C4 | After W5 (pilot) |
|--------|-----------|----------|----------|----------|------------------|
| aifilm_grok.py LOC | ~11200 | ~9650 | ~8070 | ~7720 | ~7650 (pilot out) |
| Extracted | — | cli_post | +cli_media | +doctor→cli_status | +**cli_pilot** |

## Domain map

| Domain | Module | cmds |
|--------|--------|------|
| post | cli_post.py DONE | final, review-final, compose-*, closeout, export-desktop |
| media | cli_media.py DONE | register-still/clip, style-lock, continuity, face-identity, assemble |
| status/doctor | cli_status.py DONE | status, doctor |
| workflow | cli_workflow DONE | bulk-preflight, ship-prep, pilot-pack alias |
| h3/comfy | cli_h3 / cli_comfy DONE | h3, comfy |
| **pilot** | **cli_pilot.py DONE (W5)** | pilot pick/report/pack/score/approve |

## Next candidates

- audio / bgm / lipsync cmd cluster still in monolith (~handlers + build_parser)
- `cmd_write_spec` (~470 LOC)
- further render_final leaf splits if needed
- do **not** rename public subcommands

## Profile docs (W5)

- Runtime default for 5090 owners: **`h3_primary`**
- Dual-lane compatibility: `hybrid_h3`
- Cloud-only: `grok_primary`
