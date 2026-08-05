# Strategy · Director + Engineer Upgrade Plan (2026-08-05)

**Status:** ACTIVE · **strategy pointer for this pass**  
**Kind:** analysis-only (docs; no heat/i2v/pilot policy change)  
**Repo:** `/Users/dex/.grok/plugins/ai-film-grok` · evidence tree **`origin/main` @ 2.39.30** (hub 1455 · `scripts/core/` present)  
**Revision:** 2026-08-05f — S5.3 capacity-wait + hang-proof closeout ship
**Audience:** user (director intent) + coding agents (implementation sequencing)

> **一句话：** 规则与产线已够硬；下一层优化不是再叠 IRON，而是 **(导演) 把「门绿」变成「片好看/可交付」的可预期吞吐**，以及 **(工程) 按 ACTIVE 模块重构轨把热路径可测、可挂机、可维护**。

### Supersession / related trackers

| Doc | Role after this pass |
|-----|----------------------|
| **This file** | **Single strategy pointer** (dual-lens + ordered residual todos) |
| [2026-08-05-optimization-todoplan.md](2026-08-05-optimization-todoplan.md) | Ops throughput waves — Waves 0–2/4/5/M **SHIPPED**; residual pointed here |
| [2026-08-05-project-module-refactor.md](2026-08-05-project-module-refactor.md) | Structure owner — **W0–W5 package/docs SHIPPED** · residual **internal peels** |
| [2026-08-05-antifragility-todoplan.md](2026-08-05-antifragility-todoplan.md) | Fail-closed / hang / PARTIAL honesty residuals |
| [2026-08-05-h3-primary-capacity.md](2026-08-05-h3-primary-capacity.md) | h3_primary + until-empty — **code SHIPPED**; true overnight canary OPEN |
| [2026-08-05-material-fidelity-loop.md](2026-08-05-material-fidelity-loop.md) | M0–M4 SHIPPED; M5–M6 **code landed ~2.39.23** (doc backlog stale) |
| [2026-08-03-roi-optimization-plan.md](2026-08-03-roi-optimization-plan.md) | **CLOSED** A–E — do **not** re-open as greenfield |
| [2026-08-03-workflow-optimize-todo.md](2026-08-03-workflow-optimize-todo.md) | **SHIPPED** A–H+W8 — do **not** re-open |
| [cli-extract-map.md](cli-extract-map.md) | CLI domain extract map (public subcommand iron) |
| [REFACTORING_PLAN.md](../../REFACTORING_PLAN.md) | Older P0–P3 — **superseded for structure** by module-refactor tracker |

---

## 1. Current-state map (concrete repo evidence)

### 1.1 Inventory snapshot (evidence = `origin/main` @ 2.39.30 unless noted)

| Metric | Value | Source |
|--------|------:|--------|
| Plugin version | **2.39.30** | `plugin.json` on origin/main |
| Hub `aifilm_grok.py` | **1455 LOC** (was 5028 pre-W1) | `wc` on `git show origin/main:…` |
| `scripts/core/*` | **7 py · ~795 LOC** | present on origin (W1) |
| `cli_*.py` modules | **~41** | origin tree |
| Python scripts | **~360+** · **~150k+** LOC | project_audit / tree |
| Tests | **~380+** `test_*.py` | tree |
| Coverage (cached) | **~62%** overall | `skills/ai-film-grok/coverage.json` |
| References | **~165** md · **~78** lessons | tree |
| Memory cards | **~67** | tree |
| Stages | agent / visual / voice / post / deliver (+ approval) | `references/stages/` |
| Hard defaults | **211** lines (dense IRON table) | `references/hard-defaults.md` |
| Weapon matrix | **235** lines | `references/weapon-lane-matrix.md` |
| Hot CLI entry | `skills/ai-film-grok/scripts/aifilm` → `aifilm_grok.py` | SKILL.md |
| Gate-auto | `scripts/gate_auto.py` + `cinematic_gate.py` | hard-defaults P0 |
| H3 overnight | `cli_h3.py` · `h3_fill_idle.py` · `test_h3_until_empty` | plans |

### 1.2 Monolith / hot-path LOC (origin/main @ 2.39.30)

| Module | ~LOC | Why it matters |
|--------|-----:|----------------|
| `aifilm_grok.py` | **1455** | CLI hub after W1/W2 extract (≤2500 met) |
| `post/render_final.py` | **4333** | package-boundary SHIPPED; body still multi-k · **internal peel residual** — [residual plan](2026-08-05-residual-monolith-w4-todo.md) |
| `narrative/edit_policy_heat.py` | **4015** | package-boundary SHIPPED · **internal packs residual** (bug-driven) |
| `film_spec.py` | **3234** | write-spec / validate / projectors · **residual** |
| `story_plan.py` | **2858** | plan run / spines |
| `export_composition.py` | **2835** | compose / HF export surface |
| `edit_policy.py` | **2667** | visual_fit / stretch / cut silk |
| `h3_fill_idle.py` | **1700** | Fill-Idle + until-empty energy |
| `dispatch.py` | **~1450** | next_action brain · coverage **~81%** |
| `media_queue.py` | **1288** | bulk queue honesty |
| `core/*` | **~795** | **SHIPPED W1** — film_io / gates / media_ops / paths / emit |

**Coverage pain (audit cache, not vanity target):**  
`compose_render` **~19%** · `render_final` **~30%** · `production_gates` **~50%** · vs `dispatch` **~81%** · `story_plan` **~92%**.

### 1.3 Pipeline spine (product truth)

```text
story.receive → script-value-debrief → plan run → fidelity
  → write-spec / design-go → pilot (human GO) → bulk-preflight
  → bulk (h3_primary / queue) → gate-auto / ship-prep
  → final (render_final / HF) → review-final → closeout → export-desktop
```

| Stage | Stage card | Owning code (examples) | Canon rules |
|-------|------------|------------------------|-------------|
| Agent | `stages/agent.md` | `story_plan` · `film_spec` · `dramatic_meaning` | Director’s Lens · input fidelity · zero_narration |
| Visual | `stages/visual.md` | `still_source` · `generation_request` · `h3_*` · `media_queue` | Material fidelity · poison · true_video · h3 modes |
| Voice | `stages/voice.md` | `tts_backend` · `audio_*` · `five_track` | zh Edge · speaker-frame · 5-track −16 LUFS |
| Post | `stages/post.md` | `render_final` · `compose_*` · `caption_*` · `mix_partial` | caption_path · no double-burn · post-doctor |
| Deliver | `stages/deliver.md` | `gate_auto` · `cinematic_gate` · `closeout` · export | machine-lane green before ship |

### 1.4 Evidence discipline

- **SHIPPED structure claims** must match `origin/main` (`aifilm_grok.py` LOC + `scripts/core/` present), not a dirty worktree snapshot.
- Historical trap (e6844f01 era): tracker once said W1/W2 DONE while hub was still 5028 and `core/` absent — **fixed** when `0f355f60` landed code + this revision re-aligned docs.
- Local dirty trees may still fail doctor/ruff; that is hygiene, not permission to invent DONE waves.

---

## 2. SHIPPED vs OPEN / PARTIAL (do not re-greenfield)

### 2.1 Already SHIPPED (treat as foundation)

| Area | Evidence | Status |
|------|----------|--------|
| ROI A–E (runtime-lock, story dual-path, final contracts, util JSON, docs) | `2026-08-03-roi-optimization-plan.md` | **CLOSED** |
| Workflow A–H + W8 (closeout, pilot pack, bulk-preflight, lease, variety design, final packaging) | `2026-08-03-workflow-optimize-todo.md` | **SHIPPED** |
| Opt Wave 0 `h3_primary` | v2.39.14 · `test_h3_primary` · SKILL P0 | **DONE** |
| Opt Wave 1 `h3 cycle --until-empty` + capacity-plan | v2.39.16 · `test_h3_until_empty` | **DONE** (code) |
| Opt Wave 2 post_route / caption-pixel / soft SRT | v2.39.15–20 | **DONE** |
| Opt Wave 4 gate slim / pilot h3 modes | v2.39.17 · `test_w4_gate_slim` | **DONE** |
| Opt Wave 5 CLI pilot + domain extracts | cli_pilot · cli_post/media/audio/orchestrate… · cli-extract-map | **DONE** (ongoing residual) |
| **Module refactor W0–W2** (`core/*` + hub ≤2500) | v2.39.30 · hub **1455** · `scripts/core/` · `0f355f60` | **DONE on origin** |
| Material Fidelity M0–M4 (+ M5/M6 code ~2.39.23) | `still_source` · `generation_request` · CHANGELOG | **DONE** (tracker doc lag) |
| Gate-auto machine lane | `gate_auto.py` · hard-defaults · memory `2026-08-04-gate-auto` | **DONE** |
| Adult max / poison / variety / speaker / zero_narration IRON | hard-defaults + many tests | **DONE** as product law |
| Process slim / token budget / stages context | Phase2 plans · SKILL short spine | **DONE** enough for now |

### 2.2 OPEN / PARTIAL residuals (this strategy’s work queue)

| ID | Residual | Why still hurts / status |
|----|----------|-------------------------|
| **R-ops** | Full overnight drain to `queue_empty` | **PARTIAL** execute path proven; live stop=`capacity_not_ready` (pending_after=2, jobs_ran=0) on h3-angles canary — **not** queue_empty; multi-job drain OPEN until idle 5090 |
| **R-af1** | Hot-path subprocess timeouts | **PARTIAL→core SHIPPED** through 2.39.65 (adapters/node); compose_preview/speech_preview Popen residual open |
| **R-af2** | closeout ↔ post_doctor / caption-pixel | **SHIPPED** AF3/AF6 |
| **R-doc** | hard-defaults FRW-first bulk prose | **SHIPPED** AF8 → h3_primary |
| **R-mf-doc** | material-fidelity M5–M6 tracker | **SHIPPED** (M0–M6 landed) |
| **R-cov** | final/compose failure-mode tests | Still useful; not line vanity |
| **R-util** | Wave 3 util FilmError / run_ffmpeg | **PARTIAL** (hang-proof bulk through 2.39.65; full util.run_ffmpeg migration open) |
| **R-struct** | Module refactor leaf peels | **W0–W5 SHIPPED**; heat/film_spec intentional residual |
| **R-hygiene** | Local dirty trees / doc drift | Ongoing |

### 2.3 Explicit non-goals / iron (this strategy)

- No silent heat / `i2v_provider` / pilot self-approve policy change  
- No full re-open of **CLOSED** ROI or **SHIPPED** workflow waves as new greenfield  
- No rename of public `aifilm` subcommand strings  
- No bulk “split everything under 1500 LOC” for vanity  
- No full `references/` rewrite; no lesson deletion  
- No paid cloud burn / GPU overnight inside analysis commits  
- No force-push / config.env secrets  

---

## 3. 导演级优化（craft outcomes · story→deliver）

类比：现在仓库像 **已经装好消防规范与流水线的片厂**——再加规章收益小；收益在 **日产量、废片率、终审一次过**。

### D0 · North star metrics (measure, don’t vibes)

| Metric | Definition | Target posture |
|--------|------------|----------------|
| **First-pass ship** | closeout green without re-final | ↑ |
| **Still scrap rate** | approved still later poison / sheet / redress reject | ↓ |
| **I2V scrap rate** | mean/variety/identity fail after register | ↓ |
| **5090 busy useful %** | until-empty cycles that produce usable takes | ↑ |
| **Caption pixel truth** | ship frame OCR / caption-pixel-check ok | = hard |
| **Heat promise keep** | sex arc ≥ floors + impact ≥ bar without soft downgrade | hard |

Implement as **receipt counters** on real film roots (not new IRON paragraphs).

### D1 · Design-time “好看” before bulk (P0 craft)

**Pain:** gates green ≠ interesting picture (already canon in hard-defaults variety / anti-boring).  
**Upgrade:**

1. **Design GO one-pager** before pilot bulk: pose matrix (≥4 meat poses) · CU/L4 budget · adjacent camera plan · speaker map · sex_arc four beats on a timeline strip.  
2. Wire into existing surfaces only: `design-go` / pilot pack / `ship-prep` shortlist — **do not** invent a second bible.  
3. **Still challenge first** on weak meat stills (`still-challenge`) before overnight H3 burn (weapon-lane FRW i2i path).  
4. Acceptance: pilot GO package includes undress+union/rhythm evidence (already W2 iron) **plus** variety precheck soft→hard only after design GO signed.

**Depends on:** workflow W2/W4 (SHIPPED) — residual is **agent discipline + one-page receipt**, not new theory.

### D2 · h3_primary as default creative muscle (P0 capacity)

**Pain:** cloud quota vs free 5090 time — mostly solved in code; habit lag remains.  
**Upgrade:**

1. New films: default **`AIFILM_I2V_PROFILE=h3_primary`** when 5090 available (config.env.example + doctor advisory).  
2. Mode discipline from `h3_mode.py`: FLF when end still exists; R2V energy CU; T2V env-only; continue handoff endframe.  
3. Overnight: `h3 capacity-plan` → `h3 cycle --until-empty --execute` only after pilot GO + capacity idle.  
4. Grok remains pilot / soft escape — never silent bulk cloud under h3_primary.

**Open residual:** true execute canary (R-ops). Dry already logged.

### D3 · Material fidelity = “model eats correct pixels” (P0 scrap)

**Pain:** wrong still / prompt / cast master → whole I2V wasted.  
**Upgrade (mostly SHIPPED — enforce, don’t reimplement):**

1. Every restricted shot must have `receipts/prompts/<id>.request.json` + still sha match at queue.  
2. Peak meat: ban full cast master; undress-anchor / state masters only.  
3. Dispatch next should surface `generation_ready` / still-challenge hints (M6 intent).  
4. Fix tracker doc M5–M6 status (R-mf-doc).

### D4 · Voice + caption as ship surface (P0 delivery truth)

**Pain:** ledger has Chinese; pixel doesn’t — user sees “no subs.”  
**Upgrade:**

1. Ship path = **hardburn Chinese** proof via `caption-pixel-check` (SHIPPED modules).  
2. Master HF path keeps plate `subs=off` + single owner — no double-burn.  
3. Speaker-frame: on_camera speaker = frame subject (gate exists).  
4. Residual: **closeout fails closed** if final+srt but pixel check red (R-af2).  
5. TTS: Edge zh only; PARTIAL-honest if fallback — never silent ja voice (iron).

### D5 · Heat arc is product, not lint noise (P0 adult)

**Pain:** agents thrash on heat codes; users care about full arc + bare climax + variety.  
**Upgrade:**

1. Keep all max irons (no soften).  
2. Prefer **one heat boost pass at write-spec** over multi-round thrash at final.  
3. Afterglow / non-stand stills: enforce adjacent meat variety + afterglow not single stand (huangdao lesson).  
4. Impact S-bar stays on final; queue stays A-bar — already Wave 5–6.

### D6 · Gate-auto as director’s assistant, not thrash loop (P1)

**Pain:** historical mean→variety→ship thrash.  
**Upgrade (mostly SHIPPED):**

1. Default next after clips complete = **gate-auto** (machine lane).  
2. Human only for pilot / multi-take PK / review-final.  
3. `--force` only when intentionally remeasure.  
4. Residual hygiene: ensure dispatch compact always shows machine-lane reason codes (agent tax ↓).

### D7 · Continuity & true-video as non-negotiable craft (P1)

1. Still never on timeline; motion only in-model (true_video_policy).  
2. Continue hard cuts + endframe promote SOP; smash/cross-space no blind promote.  
3. Poison still: archive + repair; never I2V.

### D8 · Longform / serial (P2)

1. `plan run --production-mode longform` + serial validate already exist.  
2. Upgrade: per-episode cast/state reuse checklist as receipt (ai-film-project boundary stays project-level).  
3. Final timeout discipline: long films call `render_final` with ≥1800s mental model (hard-defaults / lessons).

---

## 4. 工程师级优化（structure · hot paths · ops）

类比：片厂建筑加固——**不拆舞台**（public CLI / heat iron），只修 **走线、防火门、夜班不挂死**。

### E0 · Sequencing iron

1. Structure work **follows** [project-module-refactor](2026-08-05-project-module-refactor.md) waves.  
2. Behavior changes **follow** fail-closed matrix in [antifragility](2026-08-05-antifragility-todoplan.md).  
3. Never mix “big move + policy change” in one commit.  
4. Per wave: `make check-all` + `make lock-runtime` when script fingerprints change + English commit + push.

### E1 · Module refactor residual = internal peels (W0–W5 package/docs SHIPPED)

**State:** hub **~1462** ≤2500; `scripts/core/*` (~795); packages include `post/` + `narrative/` (W4 boundary `ef9c4c70`); W5 docs DONE.  
**Do not re-do W0–W5 package/docs.** Residual:

1. **Internal leaf peels** of still multi-k bodies — **single plan:** [2026-08-05-residual-monolith-w4-todo.md](2026-08-05-residual-monolith-w4-todo.md).  
2. Package boundary ≠ full leaf peel DONE (`post/render_final` still ~4333; heat still ~4015).  
3. Any peel: `make check-all` + lock-runtime green before DONE.


### E2 · Domain monoliths — surgical, not heroic (P1)

Order by **ship risk × touch frequency**, not raw LOC:

| Priority | Module | Extract angle |
|----------|--------|---------------|
| 1 | `post/render_final.py` | stages already partial (`final_stages`, music, mix_partial) — peel leaf pure functions + failure-mode tests |
| 2 | `narrative/edit_policy_heat.py` | **4015** | package-boundary SHIPPED · **internal packs residual** (bug-driven) |
| 3 | `film_spec.py` | projectors vs validate vs CLI glue |
| 4 | `export_composition.py` / `compose_render.py` | coverage-starved; test harness first |
| 5 | `story_plan.py` | only if dual-path residue reappears |

**Anti-pattern:** 11k-line “move only” PR with no tests.

### E3 · Antifragility hot path (P0 eng / ops)

From antifragility residual list:

1. **AF1:** Migrate hang-risk ffmpeg/ffprobe to `util.run` / `util.run_ffmpeg` with timeouts — start `h3_fill_idle` identity midframe.  
2. **AF2:** closeout chains `post_doctor` + caption-pixel fail-closed when ship artifacts present.  
3. Replace silent `except: pass` on continue handoff / media_queue sidecars with PARTIAL receipts.  
4. until-empty tests: add `capacity_not_ready` / hang timeout paths (not only dry empty queue).

### E4 · Final hot-path testability (P0 quality)

1. Expand `test_final_hotpath_contracts` / compose fixtures for: caption_path dual-burn forbid · timeout · mix_partial · true_video plate.  
2. Prefer **fake ffmpeg** / recorded receipts over GPU.  
3. Target: every ship-blocking code path has one real entry-point test (no theater).

### E5 · Util / FilmError consistency (P1)

1. New code: `util.require_json` hard · `util.read_json` soft — ban new local `_read_json`.  
2. Continue mechanical migration only when touching a file.  
3. Logger: prefer shared logger when editing; no global reformat campaign.

### E6 · Doc / token / drift hygiene (P0 cheap)

1. **Fix hard-defaults L169** bulk ladder → h3_primary-aware wording (doc-only, matches weapon-lane).  
2. Refresh material-fidelity plan status M5–M6.  
3. Keep SKILL short; stages = turn context; lessons on demand.  
4. One strategy pointer (this file) — avoid a 4th parallel “full optimization” without supersession.

### E7 · Ops / doctor / lock (P1)

1. Status claims (Waves DONE) require origin evidence (LOC + paths), not worktree-only.  
2. `make doctor` core green on clean main after each wave.  
3. pre-push light remains default; full gate on release.  
4. Worktree prune discipline (already partially done).

### E8 · Security / credentials (standing)

1. config.env never commit.  
2. No token in receipts/logs.  
3. External spend never auto-retry.  
4. Any auth/crypto touch → `security-executor` (AGENTS.md).

---

## 5. Prioritized todo plan (checkable)

> Implementers: tick boxes in **this section** when executing. Analysis commit leaves them open.

### Wave S0 · Hygiene & truth (cheap · do first)

- [x] **S0.1** Fix `hard-defaults.md` 量产十条 #3 for `h3_primary` (AF8 · v2.39.34)  
- [x] **S0.2** Update material-fidelity plan: M5–M6 SHIPPED status + residual only if real  
- [x] **S0.3** Point optimization-todoplan “next” → this strategy residual table  
- [x] **S0.4** Structure tracker aligned to origin: W0–W2 SHIPPED (hub 1455 + `core/`); no fabricated DONE  

**Depends:** none · **Risk:** low · **Verify:** `rg` L169 · plan headers · origin LOC/`core/`

### Wave S1 · Hang-proof overnight (P0 eng+ops)

- [x] **S1.1** `h3_fill_idle` identity ffmpeg: timeout via `util.run` (AF1 · v2.39.34)  
- [x] **S1.2** scene_sound + local TTS adapter hang sites: explicit `timeout=` (v2.39.41)  
- [x] **S1.3** Tests: timeout → soft skip identity penalty + caution (AF1 + behavioral)  
- [x] **S1.4** until-empty unit: `capacity_not_ready` stop_reason path (AF5)  

**Depends:** util/subprocess SHIPPED · **Risk:** med · **Verify:** `pytest -k 'h3_until_empty or h3_fill_idle'` + manual dry cycle

### Wave S2 · Ship truth wire-up (P0 deliver)

- [x] **S2.1** closeout invokes post_doctor + caption-pixel when final present (AF3)  
- [x] **S2.2** Fail-closed ship if Chinese cues exist but pixel check fails / probe crash (AF6)  
- [x] **S2.3** Expand final hotpath contracts for caption_path / no double-burn (env force + spec route + master_hf ok)

**Depends:** caption-pixel / post_doctor modules SHIPPED · **Risk:** med · **Verify:** `test_final_hotpath_contracts` · closeout fixture film

### Wave S3 · Structure W3+ (W1/W2 SHIPPED — do not re-open)

- [x] **S3.1** W1 `scripts/core/*` on origin/main (v2.39.30)  
- [x] **S3.2** W2 hub ≤2500 on origin (**1455 LOC**) · public strings unchanged  
- [x] **S3.3** W3 package dirs + top-level shims (`assets/spine/gates/plan` · v2.39.44+)
- [x] **S3.4** W5 docs / AREA align / shim audit (AGENTS AREA package pointers)

**Depends:** W1/W2 already on origin · **Risk:** med · **Verify:** `test -d scripts/core` · `wc -l aifilm_grok.py` on origin · `make check-all` after W3

### Wave S4 · Domain peel (P1 eng · module-refactor W4)

- [x] **S4.1** failure-mode hotpath tests (timeout/mix_partial/double-burn); leaf extract deferred
- [x] **S4.2** heat internal packs — no forced peel (no bug-driven touch)
- [x] **S4.3** compose double-burn contracts in hotpath; full compose_render harness deferred


**Note:** S4 checkboxes = **risk cover / deferral**, not full internal leaf peels. Package boundary landed (`post/` · `narrative/`); residual peels = [residual plan](2026-08-05-residual-monolith-w4-todo.md).
**Depends:** S3 + W4 package boundary SHIPPED · **Risk:** high · **Verify:** targeted pytest + residual plan verify sets

### Wave S5 · Director throughput (P0 craft · mostly process)

- [x] **S5.1** design-go craft one-pager (poses/CU/L4/cameras/speakers + design-go-onepager.md)
- [x] **S5.2** doctor advisory when tunnel ok but profile not h3_primary/hybrid_h3
- [x] **S5.3** Execute until-empty canary **PARTIAL** — path proven; stop=`capacity_not_ready` (honest). Full `queue_empty` drain needs 5090 free · `artifacts/2026-08-05-s53-until-empty-canary.json`
- [x] **S5.3-ops** `h3 cycle --free-first` — idle+memory-floor → free once; **never** cancel foreign · live canary `artifacts/2026-08-05-s53-free-first-canary.json` (dry=queue_busy skip; exec race still capacity_not_ready)
- [x] **S5.3-ops deep** `--capacity-wait-sec` + `recover_capacity_contention` (2.39.66) — free-first again + poll; continue if ready; timeout still honest stop
- [x] **S5.4** generation_ready / still-challenge in dispatch compact

**Depends:** S1 for safe overnight · **Risk:** ops · **Verify:** canary JSON + dispatch screenshot/receipt

### Wave S6 · Coverage & util residual (P2)

- [x] **S6.1** util migration on touched paths (`input_fidelity` uses util json)
- [x] **S6.2** production_gates fail-closed covered in hotpath
- [x] **S6.3** coverage vanity chase forbidden (non-goal closed)

### Wave S7 · Longform / serial polish (P2)

- [x] **S7.1** serial validate remains product CLI (project-skill cast reuse boundary)
- [x] **S7.2** longform plate timeout floors tested (`estimate_plate_timeout`)

---

## 6. Dependency graph (impact × risk)

```text
S0 hygiene ──────────────────────────────┐
S1 hang-proof ─→ S5.3 overnight canary ──┤
S2 ship truth ───────────────────────────┤
S3 W3+ (W1/W2 already SHIPPED) ─→ S4 W4 domain peel
S5 design GO (can parallel after S0)
S6 / S7 last
```

**Impact order if capacity is scarce:**  
`S0` → `S1` → `S2` → `S5.3` → `S5.1` → `S3.3` → `S4` → `S6/S7`.  
(Do **not** schedule “finish W1/W2” — already on origin/main.)

---

## 7. Default “go” commands (ops residual)

```bash
export AIFILM_I2V_PROFILE=h3_primary
aifilm write-spec --root "<film>"
aifilm design-go --root "<film>"          # human craft page
aifilm pilot pack --root "<film>"         # human GO
aifilm bulk-preflight --root "<film>"
# after GO + 5090 idle:
aifilm h3 capacity-plan --root "<film>"
aifilm h3 cycle --root "<film>" --until-empty --execute
aifilm gate-auto --root "<film>"
aifilm final --root "<film>" --post-engine hyperframes --music-mood rnb --tts-backend edge
aifilm closeout run --root "<film>"
```

---

## 8. Success definition for this analysis pass

| Criterion | Met when |
|-----------|----------|
| Written dual-lens plan in-repo | **This file** |
| SHIPPED vs OPEN explicit | §2 |
| Director + engineer sections | §3–4 |
| Ordered checkable todos | §5 |
| Non-goals / irons | §2.3 |
| Cross-links / supersession | header table |
| Commit + push | follow-up git ops |

**Not** success: implementing all waves in one session.

---

## 9. Appendix · probe commands used

```bash
# inventory vs origin evidence
git show origin/main:plugin.json | python3 -c 'import sys,json; print(json.load(sys.stdin)["version"])'
git show origin/main:skills/ai-film-grok/scripts/aifilm_grok.py | wc -l   # expect ~1455
git ls-tree -r --name-only origin/main skills/ai-film-grok/scripts/core/  # expect 7 py
# anchors that must exist
test -f skills/ai-film-grok/scripts/aifilm_grok.py
test -f skills/ai-film-grok/scripts/render_final.py
test -f skills/ai-film-grok/scripts/gate_auto.py
test -f skills/ai-film-grok/references/hard-defaults.md
test -f skills/ai-film-grok/references/weapon-lane-matrix.md
test -f docs/plans/2026-08-05-optimization-todoplan.md
test -f docs/plans/2026-08-05-project-module-refactor.md
# tracker must NOT claim W1/W2 DONE without core/ + hub≤2500 on origin
```

---

*End of strategy pointer · 2026-08-05*
