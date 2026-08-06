# Project-level refactor — active tracker (2026-08-04)

**Status:** ACTIVE  
**CLI map:** [cli-extract-map.md](cli-extract-map.md)

## Done: Z H1 H2/H3 P1a C1 C2 C3 C4 · disk hygiene (v2.37.9–2.38.4)

| Wave | Result |
|------|--------|
| C3 | `cli_media` extract · monolith ~8070 |
| C4 | doctor→`cli_status` · `edit_policy_heat` · `render_final_music` · monolith ~7720 |
| Disk | dropped repo-root `g2pW` (dup) + `.local-runtimes` (~4.65G); keep skill-side `g2pW` 152M |

## Next (optional)

- more CLI clusters (audio/bgm/lipsync) when touching those cmds
- further `render_final` text/plate split only if hotpath churn
