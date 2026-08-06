# Residual 大石 / 大型模组拆分 Todo Plan — post-W4 (2026-08-05)

**Status:** ACTIVE · pure-helper peels **SHIPPED** (R1/R1b/R1c + R3a) · residual = orchestrator / heat packs / export harness only  
**Diagnosis + M-queue (2026-08-06):** [2026-08-06-monolith-relief-todoplan.md](2026-08-06-monolith-relief-todoplan.md) · M0 SHIPPED  
**Kind:** structure plan (docs + ordered implementer queue; not a vanity LOC sprint)  
**Owner tracker:** [2026-08-05-project-module-refactor.md](2026-08-05-project-module-refactor.md)  
**Strategy pointer:** [2026-08-05-strategy-director-engineer-upgrade.md](2026-08-05-strategy-director-engineer-upgrade.md) · R-struct  
**Baseline date:** 2026-08-05 worktree (plugin **2.39.51**) · LOC freeze `2026-08-05T03:49:08Z` · evidence commit `ef9c4c70` (W4 packages) · **LOC refresh 2.40.10**

> **一句话：** W0–W3（hub ≤2500 · `core/*` · package dirs）+ **W4 包边界**（`post/render_final` · `narrative/edit_policy_heat` + top-level shims）+ W5 docs **已 ship**；本档只排 **仍 4k 的内部叶拆** 与 next-tier 领域巨石——按 **出片风险 × 改动频率**，禁止「全员 <1500 行」冲刺，禁止把「搬进包」误报成「内部 peel DONE」。

---

## 0. What is already SHIPPED (do not re-open)

| Wave | Theme | Evidence |
|------|--------|----------|
| **W0** | Tracker + baseline | module-refactor lineage |
| **W1** | `scripts/core/*` | ~795 LOC · film_io / gates / media_ops / paths / emit |
| **W2** | CLI extract · hub ≤2500 | hub **1462** · `cli_*.py` · [cli-extract-map.md](cli-extract-map.md) |
| **W3** | Package dirs + hard-compat shims | `assets/spine/gates/plan` · `tests/test_w3_package_shims.py` |
| **W4 package boundary** | Domain → packages | `scripts/post/render_final.py` (**4333**) · `scripts/narrative/edit_policy_heat.py` (**4015**) · top-level **4-line** `sys.modules` shims · `ef9c4c70` |
| **W5** | Docs / AREA / shim audit | AGENTS AREA · tracker closeout |

**Partial leaves (not full internal peel DONE):**

| Peel | Path | ~LOC | Note |
|------|------|-----:|------|
| Music helpers | `render_final_music.py` | 743 | C4 re-export |
| Caption / voice / media / errors | `scripts/final/*` | ~1219 | leaf helpers; orchestrator still in `post/render_final` |
| Hotpath failure tests | `tests/test_final_hotpath_contracts.py` | — | S4 risk cover |
| Heat internal packs | — | — | **deferred** (import graph / cycle risk; no bug-driven force) |

**Honest status language:**  
- **W4 package boundary = DONE** (import path + package dirs).  
- **W4 internal leaf peels of 4k bodies = residual / optional** (tracker already says deferred).  
- Do **not** invent full domain peel DONE for heat packs / film_spec split / export harness.

---

## 1. Iron (binding)

1. **Public `aifilm` subcommand strings unchanged.**
2. **No silent heat / `i2v_provider` / pilot-policy change.**
3. **Shims / import hard-compat preserved** — top-level `import render_final` / `import edit_policy_heat` via `sys.modules` must keep working; package moves keep re-exports tested.
4. **No “split everything under 1500 LOC” vanity sprint.**
5. **One domain per wave commit**; never mix big move + policy change.
6. **DONE evidence = origin paths + LOC + tests**, not worktree-only claims.
7. Prefer **pure leaf extract first**; do not re-do package-boundary moves already on main.

---

## 2. Non-goals

- Re-doing W0–W3 hub extract or re-creating `scripts/core/*`
- Re-doing W4 **package boundary** move of render_final / heat (already SHIPPED)
- Full mechanical util / FilmError repo-wide migration
- Overnight true-GPU until-empty canary (ops residual)
- Product IRON rewrites (adult max, poison, h3_primary, caption hard-burn, pilot GO)
- Heroic multi-thousand-line move-only PRs without failure-mode tests
- Reviving `REFACTORING_PLAN.md` as primary structure owner

---

## 3. Residual monolith baseline (LOC)

> **Refresh:** 2026-08-06 worktree · plugin **2.40.10** · `wc -l` on package paths.  
> **Next structure queue owner:** [2026-08-06-next-optimization-todoplan.md](2026-08-06-next-optimization-todoplan.md) Wave 3 (bug-driven peel only).

| Priority | Module | ~LOC | Why residual (risk × touch) | Status |
|----------|--------|-----:|-------------------------------|--------|
| **P0** | `post/render_final.py` | **2985** | Ship path; orchestrator still thick after leaf peels | package SHIPPED · **internal leaf residual** |
| **P1** | `narrative/edit_policy_heat.py` | **4024** | Adult/heat IRON; high blast radius | package SHIPPED · **bug-driven packs only** |
| **P1** | `plan/film_spec.py` | **3147** | write-spec / validate / projectors; sex floor leaf exists | monolith · peel on touch |
| **P2** | `post/export_composition.py` | **2804** | HF/Remotion export; coverage-starved | harness first |
| **P2** | `post/compose_render.py` | **1579** | Compose path; double-burn contracts exist | harness residual |
| **P2** | `narrative/edit_policy.py` | **2584** | visual_fit / stretch / cut silk | peel if dual-owner pain |
| **P2** | `media/h3_fill_idle.py` | **2300** | capacity / until-empty | peel if logic thrash |
| **P3** | `plan/story_plan.py` | **2948** | High coverage; peel only if dual-path residue | watch |
| **CLI** | `cli/cli_post` / `cli_media` | 2476 / 2135 | Hub-extracted; further only if growing | optional |
| **SHIPPED** | hub `aifilm_grok.py` | **993** | ≤2500 | W2 DONE |
| **SHIPPED** | `scripts/core/*` | **~901** | shared I/O | W1 DONE |
| **SHIPPED** | top-level shims `render_final.py` / `edit_policy_heat.py` | thin + main guard | hard-compat | W4 boundary DONE |

**Ordering canon（风险 × 触达 · 与 monolith-relief M* 对齐）:**  
1. `film_spec` validate peel **on touch**（最高 ROI 预防边界 · M1）  
2. `post/render_final` stages **on final bug**（M2）  
3. export/compose **harness first**（M3）  
4. heat internal packs **bug-driven only**（M4 · 不预防性全拆）  
5. `story_plan` / cli / h3_fill_idle 仅双路径或 thrash（M5）

---

## 4. Checkable residual waves

### Wave R0 · Hygiene (always before any peel)

- [ ] Hub ≤2500 · `scripts/core/` present · shims import
- [ ] `pytest tests/test_w3_package_shims.py -q`
- [ ] Confirm package boundary: `post/render_final.py` + `narrative/edit_policy_heat.py` exist; top-level shims 4 lines

**Verify:**
```bash
ROOT="$(git rev-parse --show-toplevel)"
test -d "$ROOT/skills/ai-film-grok/scripts/core"
test -f "$ROOT/skills/ai-film-grok/scripts/post/render_final.py"
test -f "$ROOT/skills/ai-film-grok/scripts/narrative/edit_policy_heat.py"
test "$(wc -l < "$ROOT/skills/ai-film-grok/scripts/aifilm_grok.py")" -le 2500
cd "$ROOT/skills/ai-film-grok" && python -m pytest tests/test_w3_package_shims.py -q
```

---

### Wave R1 · `post/render_final` internal leaves (P0)

**Progress 2026-08-05 R1c+R3a:** `final/tts_tracks.py` + `film_spec_profile.py` (render_final ~2735; film_spec ~3136). Pure helper peels complete; residual = `render_final()` orchestrator body + heat packs (bug-driven) + export harness.

**Progress 2026-08-05:** re-wired AST-identical leaves via `final/*` (4333→~3271). **R1b (2.39.59–60):** peel native/cards/enhance → `final/*` (3271→~3006; missing files fixed in 2.39.60). Remaining: orchestrator body.

**Target:** `scripts/post/render_final.py` (~4333) — keep package + top-level shim.

**Already out / adjacent:** `final/*` · `render_final_music.py` (may still be partially inlined — re-wire not re-copy).

**Extract angle:**
1. Pure stage packs from orchestrator body: plate resolve, mix graph, subtitle burn selection, timeout helpers → `post/stages_*.py` or deepen `final/*`.
2. Deduplicate any remaining local copies of `final/*` helpers.
3. Keep `render_final(args)` entry + public re-exports via shim.

**Iron:** no caption_path / double-burn / mix_partial / timeout / VO-BGM gain policy change in move commits.

**Tests:** `test_final_hotpath_contracts` · `test_render_core_helpers` · `test_w3_package_shims` · touch-related final tests.

**Verify:**
```bash
cd skills/ai-film-grok
python -m pytest tests/test_final_hotpath_contracts.py tests/test_w3_package_shims.py tests/test_render_core_helpers.py -q
# make -C "$ROOT" check-all && make lock-runtime  # if fingerprints change
```

**DONE rule:** origin LOC delta on `post/render_final.py` + new module paths + hotpath still hits real entry. **Not** DONE because package boundary alone exists.

**Default:** defer unless final bug forces multi-section edit.

---

### Wave R2 · `narrative/edit_policy_heat` internal packs (P1 · bug-driven)

**Target:** `scripts/narrative/edit_policy_heat.py` (~4015).

**Extract angle (packs under `narrative/heat/` or sibling modules):**
phase/scale · wardrobe/undress · coitus/arc · spice/VO · impact/variety · multi-heroine · thin facade `lint_heat_arc` + re-exports.

**Iron:** public `heat check` schema unchanged; adult max / bare / undress **not** retuned in peel commits.

**Tests:** `test_heat_check` · `test_heat_arc_multi` · `test_adult_heat_upgrade`.

**Verify:**
```bash
python -m pytest tests/test_heat_check.py tests/test_heat_arc_multi.py -q
```

**DONE rule:** pack modules on origin + facade re-exports + heat tests green.  
**Default:** no forced peel (S4.2 / tracker deferred).

---

### Wave R3 · `film_spec` projectors vs validate (P1)

**Progress 2026-08-05 R3a:** provider/profile pure leaves → `film_spec_profile.py` (validate/projectors still residual).

**Target:** `film_spec.py` (~3234) — still root.

**Extract angle:**
1. Provider/profile resolve (`resolve_i2v_profile`, `default_i2v_provider`, `resolve_h3_config`) → pure leaf.
2. Validate/lint (`validate_film_spec`, director intent, zero_narration) → `film_spec_validate` or package.
3. Optional package boundary `plan/film_spec` or `narrative/film_spec` **only if** import graph stays acyclic; keep top-level shim if moved.
4. CLI stays at `cli_write_spec` (already extracted).

**Iron:** no silent `i2v_provider` / h3 default change; write-spec subcommand string unchanged.

**Tests:** `test_cli_write_spec_extract` + validate/story contract as touched.

**Verify:**
```bash
python -m pytest tests/test_cli_write_spec_extract.py -q
make -C "$ROOT" check-all   # if paths move
```

---

### Wave R4 · export / compose (P2 · harness-first)

**Targets:** `export_composition.py` (~2835) · `compose_render.py` (~1603).

**Extract angle:** harness first (`test_compose_hotpath_contracts` · `test_export_composition`); peel pure HTML/timeline builders only after churn.

**Iron:** caption_path dual-burn forbid; HF caption owner.

**Verify:**
```bash
python -m pytest tests/test_compose_hotpath_contracts.py tests/test_export_composition.py -q
```

---

### Wave R5 · `story_plan` dual-path only (P3 · optional)

**Target:** `story_plan.py` (~2858). Peel only if dual-path residue reappears.

**Verify:** `pytest tests/test_story_plan.py tests/test_story_contract_and_quality.py -q`  
**Default:** do not schedule.

---

### Wave R6 · CLI growth guard (optional)

`cli_post` / `cli_media` further split only if growing. **Iron:** no public subcommand renames.

---

## 5. Implementer checklist

1. [ ] **R0** hygiene (core + shims + package boundary present)
2. [ ] **R1** only if final hotpath is the touch target — one leaf pack per PR
3. [ ] **R2** heat packs — still deferred (bug-driven only)
4. [x] **R3a** profile leaves DONE; validate/projectors residual
5. [ ] **R4** harness first for export/compose
6. [ ] **R5** skip unless dual-path residue
7. [ ] After any script peel: `make check-all` · lock-runtime if needed · English commit · bump version + CHANGELOG

---

## 6. Verify command sets

### Docs-only / plan alignment
```bash
ROOT="$(git rev-parse --show-toplevel)"
test -f "$ROOT/docs/plans/2026-08-05-residual-monolith-w4-todo.md"
test -f "$ROOT/docs/plans/2026-08-05-project-module-refactor.md"
test -d "$ROOT/skills/ai-film-grok/scripts/core"
test -f "$ROOT/skills/ai-film-grok/scripts/post/render_final.py"
test -f "$ROOT/skills/ai-film-grok/scripts/narrative/edit_policy_heat.py"
test "$(wc -l < "$ROOT/skills/ai-film-grok/scripts/aifilm_grok.py")" -le 2500
# residual next-tier still present
for f in film_spec.py export_composition.py story_plan.py; do
  test -f "$ROOT/skills/ai-film-grok/scripts/$f"
done
make -C "$ROOT" doctor 2>/dev/null || true
```

### Structure code smoke
```bash
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT/skills/ai-film-grok"
python -m pytest tests/test_w3_package_shims.py tests/test_final_hotpath_contracts.py -q
# optional after peels: heat / write-spec / compose tests
make -C "$ROOT" check-all
```

---

## 7. Alignment map

| Doc | Expected language |
|-----|-------------------|
| **This file** | Single residual structure todo · internal peels after W4 package boundary |
| [project-module-refactor](2026-08-05-project-module-refactor.md) | W0–W5 package/docs **SHIPPED** · residual peels → this file (not falsely “internal peel DONE”) |
| [strategy](2026-08-05-strategy-director-engineer-upgrade.md) | R-struct = residual **internal** peels; W4 package boundary already on main |
| [optimization-todoplan](2026-08-05-optimization-todoplan.md) | Ops owner; structure residual pointed here |
| [cli-extract-map](cli-extract-map.md) | Hub extract DONE; further leaves → this plan |
| `REFACTORING_PLAN.md` | Superseded for structure |

---

## 8. Risks / anti-patterns

| Risk | Mitigation |
|------|------------|
| Claiming internal peel DONE because package move landed | Tracker + this plan: package boundary ≠ leaf peel |
| LOC vanity | Iron §4; order by risk × touch |
| Heat peel retunes adult max | Move-only commits |
| Import cycles when packing film_spec | Cycle check before package move; prefer pure leaf first |
| Fourth parallel optimization manifesto | One residual plan (this file) |

---

## 9. Related evidence

- Package boundary: `ef9c4c70` · `scripts/post/` · `scripts/narrative/` · 4-line shims
- Leaves: `scripts/final/*` · `render_final_music.py`
- Tests: `test_w3_package_shims` · `test_final_hotpath_contracts` · `test_heat_*`
- Tracker closeout notes: module-refactor “Internal leaf-split deferred”

---

## 10. Round closeout (2026-08-05 · pure-helper peels)

**SHIPPED this residual campaign:**

| Step | What | Evidence |
|------|------|----------|
| R1 | Re-export AST-identical caption/voice/media from `final/*` | 4333→3271 |
| R1b | `final/{native_audio,cards,enhance}.py` | ~3271→~3014 |
| R1c | `final/tts_tracks.py` (TTS + native/color tracks) | ~3014→~2745 |
| R3a | `film_spec_profile.py` + re-export via `plan/film_spec` (W7) | profile pure leaves |
| Package | W4/W7 package dirs + shims | `post/` · `plan/` · `narrative/` |

**Explicitly still residual (optional / bug-driven — not vanity LOC):**

1. `post/render_final.render_final()` orchestrator body (~2k lines) — peel stages only when final bugs force multi-section edit  
2. `narrative/edit_policy_heat` internal packs — **bug-driven only** (S4.2)  
3. `plan/film_spec` validate/projectors split — when write-spec churn demands  
4. export/compose harness-first (R4) — not heroic rewrite  
5. `story_plan` — only dual-path residue  

**Iron still binding:** public subcommand strings · no silent heat/i2v/pilot · shim hard-compat · no 1500-LOC vanity sprint.

**Verify (regression set for leaf peels):**
```bash
cd skills/ai-film-grok
python -m pytest tests/test_i2v_profile.py tests/test_safe_sidecars.py \
  tests/test_native_audio_mix.py tests/test_render_core_helpers.py \
  tests/test_final_hotpath_contracts.py tests/test_w3_package_shims.py -q
```

