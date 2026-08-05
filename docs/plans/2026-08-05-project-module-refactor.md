# Project module refactor — ACTIVE tracker (2026-08-05)

**Status:** ACTIVE · **W0–W6 package/docs SHIPPED** · **residual internal peels optional**  
**Evidence:** `scripts/{core,assets,spine,gates,plan,post,narrative,final,audio,media}/` · hub ≤2500 · shims · `tests/test_w3_package_shims.py`  
**Residual internal-peel todo:** [2026-08-05-residual-monolith-w4-todo.md](2026-08-05-residual-monolith-w4-todo.md)

## Waves

| Wave | Theme | Status |
|------|--------|--------|
| W0 | Tracker + baseline | **DONE** |
| W1 | `scripts/core/*` | **DONE** (~795 LOC) |
| W2 | CLI extract · hub ≤2500 | **DONE** (hub ~1462) |
| W3 | Package dirs + shims | **DONE** |
| W4 | Domain → packages (`post/render_final` · `narrative/edit_policy_heat`) | **DONE** package boundary (`ef9c4c70`) · **internal leaf peels residual** (bodies still ~2735 / ~4015 (R1c+R3a leaf rewire)) |
| W5 | Docs / AREA / shim audit | **DONE** |
| W6 | `audio/*` + `media/*` packages + shims | **DONE** (v2.39.54 boundary · v2.39.56 path-depth fix) |
| W7 | `cli/*` package boundary + expand post/plan/narrative | **IN PROGRESS** · B1 cli **DONE** (v2.39.61) · B2 post **DONE** (v2.39.62) · B3 plan **DONE** (v2.39.63) · B4 narrative **DONE** (v2.39.64) · package boundary complete |

## Residual peel order (risk × touch · not LOC vanity)

See [residual W4/internal plan](2026-08-05-residual-monolith-w4-todo.md):

1. `post/render_final` internal leaves (after `final/*` + music)  
2. `narrative/edit_policy_heat` packs (**bug-driven only**)  
3. `film_spec` projectors vs validate  
4. export / compose (harness first)  
5. `story_plan` only if dual-path residue  

**Do not** claim full internal peel DONE from package-boundary move alone.

## Iron
Public `aifilm` subcommand strings unchanged · shims hard-compat · no silent heat / `i2v_provider` / pilot policy change · no “everything <1500 LOC” vanity sprint.

## Related
- [2026-08-05-residual-monolith-w4-todo.md](2026-08-05-residual-monolith-w4-todo.md) — **single residual structure todo plan**
- [2026-08-05-strategy-director-engineer-upgrade.md](2026-08-05-strategy-director-engineer-upgrade.md) — R-struct pointer
- [cli-extract-map.md](cli-extract-map.md) — hub CLI extract (W2)

## W4–W5 closeout notes

- **W4 package boundary**: `render_final` → `scripts/post/render_final.py` + shim; `edit_policy_heat` → `scripts/narrative/edit_policy_heat.py` + shim.
- Internal leaf-split of multi-k bodies deferred (import graph / cycle risk); residual queue = residual plan R1–R5.
- **W5**: AGENTS AREA + this tracker.


## W6 audio/media (**DONE** · v2.39.54 + path fix v2.39.56)

- packages: `audio/` (45) · `media/` (32) + top-level `sys.modules` shims
- path fixes: skill root `parents[2]`; adapters/sibling via `parent.parent` (= `scripts/`); plugin root for `.local-runtimes` = `parents[4]` from `scripts/audio/*`
- public import/CLI names unchanged
- residual: optional internal peels only (see residual plan); not re-opened by W6
