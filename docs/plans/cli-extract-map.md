# CLI extract map — aifilm_grok.py domain split

**Status:** ACTIVE · 2026-08-05 · v2.39.28
**Goal:** shrink `aifilm_grok.py` toward <2500 lines by extracting cmd handlers only.  
**Iron:** public subcommand strings never rename.

## Baseline

| Metric | After W5b write-spec | After W5c audio |
|--------|----------------------|-----------------|
| aifilm_grok.py LOC | ~5980 (W5c) | **~5348 (W5d)** |
| Extracted | cli_write_spec | +**cli_audio** (~1235 LOC, 22 cmds) |

## Domain map

| Domain | Module | cmds |
|--------|--------|------|
| post | cli_post.py DONE | final, review-final, compose-*, closeout, export-desktop |
| media | cli_media.py DONE | register-still/clip, style-lock, continuity, face-identity, assemble |
| status/doctor | cli_status.py DONE | status, doctor |
| workflow | cli_workflow DONE | bulk-preflight, ship-prep, pilot-pack alias |
| h3/comfy | cli_h3 / cli_comfy DONE | h3, comfy |
| pilot | cli_pilot.py DONE | pilot pick/report/pack/score/approve |
| write-spec | cli_write_spec.py DONE | write-spec + compatibility projectors |
| **audio** | **cli_audio.py DONE (W5c)** | audio-* · tts-* · bgm/sfx/lipsync · capability · verify |
| **orchestrate** | **cli_orchestrate.py DONE (W5d)** | next · stage · dispatch · advance · autopilot · craft · selects |
| **oauth** | **cli_oauth.py DONE (W5d)** | grok-oauth · usage |
| **evidence** | **cli_evidence.py DONE (W5d)** | state-index · promotion-report · production-evidence · speech-preview |
| **bootstrap** | **cli_bootstrap.py DONE (W5d)** | lock-runtime · resume-manifest |

## Next candidates

- remaining `build_parser` bulk still large inside aifilm_grok
- further render_final leaf splits if needed
- do **not** rename public subcommands

## W5d2 parsers (v2.39.28)

- add_*_parsers for orchestrate/oauth/evidence/bootstrap moved out of build_parser.
