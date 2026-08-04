# CLI extract map — aifilm_grok.py domain split

**Status:** ACTIVE · 2026-08-04 · v2.37.14+  
**Goal:** shrink `aifilm_grok.py` toward <2500 lines by extracting cmd handlers only.  
**Iron:** public subcommand strings never rename.

## Baseline

| Metric | Before C2 | After C2 |
|--------|-----------|----------|
| aifilm_grok.py LOC | ~11200 | ~9650 |
| Extracted | — | cli_post.py ~1685 |

## Domain map

| Domain | Module | cmds |
|--------|--------|------|
| post | cli_post.py DONE | final, review-final, compose-*, closeout, export-desktop |
| media | next | register-still/clip, style-lock, continuity |
| workflow | cli_workflow DONE | bulk-preflight, ship-prep |
| h3/comfy | cli_h3 / cli_comfy DONE | h3, comfy |
