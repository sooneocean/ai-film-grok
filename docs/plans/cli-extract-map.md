# CLI extract map — aifilm_grok.py domain split

**Status:** ACTIVE · 2026-08-04 · v2.38.4  
**Goal:** shrink `aifilm_grok.py` toward <2500 lines by extracting cmd handlers only.  
**Iron:** public subcommand strings never rename.

## Baseline

| Metric | Before C2 | After C2 | After C3 | After C4 |
|--------|-----------|----------|----------|----------|
| aifilm_grok.py LOC | ~11200 | ~9650 | ~8070 | ~7720 |
| Extracted | — | cli_post ~1685 | +cli_media ~1700 | +doctor→cli_status |

## Domain map

| Domain | Module | cmds |
|--------|--------|------|
| post | cli_post.py DONE | final, review-final, compose-*, closeout, export-desktop |
| media | cli_media.py DONE | register-still/clip, style-lock, continuity, face-identity, assemble |
| status/doctor | cli_status.py DONE (C4) | status, doctor |
| workflow | cli_workflow DONE | bulk-preflight, ship-prep |
| h3/comfy | cli_h3 / cli_comfy DONE | h3, comfy |

## Giant modules (not CLI cmds · same C4 wave)

| Module | After split | Leaf |
|--------|-------------|------|
| edit_policy.py | ~2470 | edit_policy_heat.py ~4015 (re-export facade) |
| render_final.py | ~4340 | render_final_music.py ~725 (re-export facade) |

## Next candidates

- audio / bgm / lipsync cmd cluster still in monolith
- further render_final (text/subtitle / plate) if needed
- do **not** rename public subcommands
