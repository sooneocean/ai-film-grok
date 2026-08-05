# Project module refactor — ACTIVE tracker (2026-08-05)

**Status:** ACTIVE · W0–W4 partial SHIPPED (v2.39.47) · heat/export residual · W5 docs
**Selection:** Full A+B+C · hard compatibility (shims; public CLI strings never rename)  
**Evidence tree:** `origin/main` @ plugin **2.39.30** · hub **`aifilm_grok.py` = 1455 LOC** · `scripts/core/*` present  
**Do not claim DONE from dirty worktree alone** — only origin (or green main after push).

## Baseline → after W1+W2 (measured on origin/main)

| Metric | Pre (≤2.39.29 / W0) | After W1+W2 (2.39.30) |
|--------|--------------------:|----------------------:|
| plugin | 2.39.29 | **2.39.30** |
| `aifilm_grok.py` LOC | 5028 | **1455** (≤2500 met) |
| `scripts/core/*` | absent | **7 modules · ~795 LOC** |
| `cli_*.py` modules | ~36 | **~41** (+ quality/director/motion/review/misc ops) |
| `render_final.py` | 4333 | 4333 (W4 later) |
| `edit_policy_heat.py` | 4015 | 4015 |
| `film_spec.py` | 3234 | 3234 |
| `story_plan.py` | 2858 | 2858 |
| `export_composition.py` | 2835 | 2835 |

### core package (W1 · on origin)

```text
skills/ai-film-grok/scripts/core/
  __init__.py · constants.py · emit.py · film_io.py
  gates.py · media_ops.py · paths.py
```

Landing commits (structure): `0f355f60` refactor W1+W2 · follow-ups `071a3113` / `e9ea5b91` / `2df9e7c9` lock + hard-compat.

## Waves

| Wave | Theme | Status |
|------|--------|--------|
| W0 | Tracker + baseline | **DONE** |
| W1 | `scripts/core/*` · break cli↔hub IO cycle | **DONE** (on origin/main) |
| W2 | CLI parser/cmd extract · hub ≤2500 | **DONE** (hub 1455) |
| W3 | Package dirs + top-level shims | **DONE** (v2.39.44) |
| W4 | Domain monoliths (render_final peel first) | **DONE** partial v2.39.47 (render_final ~3305) |
| W5 | Docs / AREA align / shim audit | pending |

## Iron

- Public `aifilm` subcommand strings unchanged
- Old imports keep working via re-export / shim
- Per-wave: `make check-all` + `make lock-runtime` when scripts fingerprints change
- No silent heat / i2v_provider / pilot policy changes
- Tracker status must match **origin** LOC/`core/` presence (no fabricated DONE)

## Related

- [2026-08-05-strategy-director-engineer-upgrade.md](2026-08-05-strategy-director-engineer-upgrade.md) — dual-lens residual queue (S3 = W3+, not re-do W1/W2)
- [cli-extract-map.md](cli-extract-map.md) — prior CLI domain extracts
- [REFACTORING_PLAN.md](../../REFACTORING_PLAN.md) — older P0–P3 (superseded by this tracker for structure)
- AGENTS.md AREA table — test map


## W3 batch (v2.39.44–45)

- packages: spine · assets · plan · gates (+ core)
- hard-compat shims via sys.modules
- path fixes: skill_scripts / advance / plan schemas
- verified: 43+ domain tests; main smoke import ok
