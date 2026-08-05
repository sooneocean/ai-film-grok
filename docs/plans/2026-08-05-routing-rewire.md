# Routing rewire — semantic single source (2026-08-05)

**Status:** ACTIVE · R0–R7 **SHIPPED** (R5 = contract/layer labels only; no silent lane change)  
**Scope:** CLI hub · spine dispatch · skill registry · production/weapon routers · context routing  
**Not:** HTTP · residual render_final/heat leaf peels (see residual monolith plan)

## Iron

- Public `aifilm` subcommand strings never rename
- No silent change to pilot / `i2v_provider` / adult MAX / native-audio dialogue policy
- Green = `make check-all` (or targeted pytest + doctor) after each wave

## Diagnosis (one line)

Packages split (W0–W7) finished; **semantic routing** still has 6 parallel tables, 3 stage taxonomies, 3 ID spaces hand-stitched.

## Layers

| # | Role | Owner |
|---|------|--------|
| 1 | CLI surface (~131 cmds) | `aifilm_grok.py` + `cli/*` |
| 2 | Agent orchestration | `spine/dispatch.py` → `receipts/dispatch.json` |
| 3 | Next-step suggestions | `spine/next_actions.py` |
| 4 | Local auto-exec | `spine/advance.py` · `autopilot.py` |
| 5 | Skill list + argv bridge | `registry/skills.json` · `skill_runner.py` |
| 6 | Per-shot capability rank | `plan/production_router.py` (`aifilm route`) |
| 7 | Armory / provider lock | `media/weapon_router.py` |
| 8 | Domain branches | `post/post_route` · `dialogue_i2i_route` · `frw_dispatch` |
| 9 | Doc budget | `registry/context-routing.json` |

## Target

`registry/route-catalog.json` = single machine source for action id ↔ cli ↔ skill ↔ stage ↔ policy ↔ advance_eligible.  
Legacy tables become validators or thin readers. Agent surface stays: **dispatch only**.

## Waves

| Wave | Theme | Risk |
|------|--------|------|
| R0 | Inventory + routing-map.md | none |
| R1 | route-catalog + consistency tests | low |
| R2 | stage_model projection | medium |
| R3 | Hub if-ladder → table | low |
| R4 | Dispatch peel (policy/packet) | medium |
| R5 | production_router ↔ weapon_router contract | **high** — confirm first |
| R6 | Agent compact + context-routing | low |
| R7 | CI / changelog / orphans | low |

**Default go pack:** R0 → R1 → R3.  
**R5 needs explicit user confirm.**

## Default stage model

- Public craft: `agent | visual | voice | post | deliver`
- `design` = internal alias of `post`
- workflow_spine 11-stage kept; project via `stage_model` only

## Related

- [project-module-refactor](2026-08-05-project-module-refactor.md)
- [cli-extract-map](cli-extract-map.md)
- [residual monolith](2026-08-05-residual-monolith-w4-todo.md)
- Human map: `skills/ai-film-grok/references/routing-map.md`
- Inventory: `python skills/ai-film-grok/scripts/tools/route_inventory.py`
