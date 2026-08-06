# Session wrap · structure merge closeout · 2026-08-05

## Shipped (on origin/main)
- **W7 package boundary DONE**: `cli/` · expanded `post/` · `plan/` · `narrative/` + thin hard-compat shims (v2.39.61–64)
- **R1/R1b/R1c peels**: render_final leaves via `final/*` (voice normalize wired to orchestrator)
- **R3a**: film_spec profile leaf (partial)
- **S5.3 capacity-wait**: `h3 cycle --capacity-wait-sec` + free-first poll (v2.39.66)
- **Hang-proof** audio/adapters/node timeouts (v2.39.58–65)
- Tip: `752ad1a` / plugin **2.39.66**

## Verified
- structure-smoke: `test_w3_package_shims` + final hotpath + voice normalize + heat + h3 until-empty + dispatch → **65–69 passed** (`{SCRATCH}/structure-smoke.log`)
- `make release-light` → exit 0 (`{SCRATCH}/release-light.log`)
- `git push origin main` → up-to-date / accepted (`{SCRATCH}/push-main.log`)
- Working tree clean; main == origin/main

## Residual (NOT claimed DONE)
- C3: export/compose deeper internal peels
- C4: `edit_policy_heat` ~4k internal packs
- seedvr2-armory 4 research commits intentionally not merged
- Historical codex/* branches behind main (ahead=0) not force-deleted

## Honest language
Package boundary ≠ full heat/export internal peel DONE.
