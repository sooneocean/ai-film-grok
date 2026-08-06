# film-spec health evaluation (2026-08-05)

## Verdict

**In-repo contract is recoverable and green for all shipped `templates/film-spec*.json` under `validate_film_spec`.**  
Two H3 skeleton templates were incomplete (missing `director_intent` + scenes) and hard-failed; they were expanded onto the adult-max IRON shot arc while keeping H3 weapon-lane metadata.

**Historical Desktop / aifilm-work roots are largely content-stale**, not code-broken: retired `seedance-*` FRW models, older dramatic-meaning stacks, framing iron, missing `vo_mode`. Classified **deferred (external content)**.

**write-spec is stricter than validate**: cinematic audit fail-closes on incomplete creative contracts (`ARC_STACK_FLAT`, `FRAME_CHAIN_GAP`, `SIZE_FLAT`, `CREATIVE_CONTRACT_DIRECTOR_BOARD_MISSING`). Example / adult-max scaffolds pass **validate** but fail raw **write-spec** without director_board / arc_node progression / pose chain. The production path works when given a complete contract (see `tests/test_pipeline_validation.py` + double-run evidence under goal scratch).

## Method

1. Runtime: `skills/ai-film-grok/scripts/runtime-python` → CPython 3.11 (host `/usr/bin/python3` 3.9 cannot import `datetime.UTC`).
2. Real API: `from film_spec import validate_film_spec` (shipped).
3. Real CLI: `aifilm write-spec --root …` (shipped).
4. Evidence sources: shipped templates, in-repo H3 canary film-specs, Desktop historical roots, CHANGELOG (zero-narration / dramatic_meaning / write-spec extract / H3 templates).

## What works

| Target | Path | Result |
|--------|------|--------|
| `templates/film-spec.example.json` | `validate_film_spec` | OK (2 shots) |
| `templates/film-spec.adult-max.example.json` | `validate_film_spec` | OK (8 shots, heat max IRON) |
| `templates/film-spec.h3-primary.example.json` | `validate_film_spec` | OK after fix (8 shots + h3 block) |
| `templates/film-spec.hybrid-h3.example.json` | `validate_film_spec` | OK after fix (8 shots + motion_lanes) |
| Intentional bad fixtures (missing director_intent / bad dramatic_function / short logline) | `validate_film_spec` | Hard-fail as designed (`tests/test_director_intent.py`) |
| Complete write-spec contract (`valid_spec` shape + `aifilm init` tree) | `aifilm write-spec` | OK (pytest pipeline + scratch double-run) |
| Related unit suite (director intent, dramatic meaning, frame chain, write-spec extract) | pytest | Green |

## What failed (probe)

### A. In-repo shipped templates (fixed)

| File | Error | Root cause | Fix |
|------|-------|------------|-----|
| `film-spec.h3-primary.example.json` | `requires director_intent object` | Profile-only skeleton: title/h3 notes, **no** intent/scenes | Expanded to adult-max IRON arc + H3 metadata / notes |
| `film-spec.hybrid-h3.example.json` | same | Same class of skeleton | Expanded to adult-max IRON arc + `motion_lanes` / hybrid notes |

### B. In-repo canaries (deferred — not production templates)

| File | Observation | Classification |
|------|-------------|----------------|
| `artifacts/5090-evaluation/h3-*-*/film-spec.json` | Missing director_intent; with intent still hit `vo_pacing` / `vo_budget` | **Deferred**: evaluation stubs for H3 modes, not write-spec contracts |
| `artifacts/5090-vibevoice-asr-canary/film-spec.json` | `requires non-empty vo_mode` | **Deferred**: ASR canary fragment |

### C. Historical external roots (deferred content)

| Root | Hard fail | Classification |
|------|-----------|----------------|
| Desktop `e-virus-ch04-shelter` / `丝绒双姝` / `薇薇安夜啼…` / `E病毒第1章…` / aifilm-work `ximen-qing-ten-brothers` | `frw_video_model=seedance-2-fast-i2v is unavailable` | **Deferred**: retired FRW model stamped on old projects |
| Same after patching frw model → legacy-img2video | `dramatic meaning gate … ARC_NODE_ORPHAN` / `BEAT_SEMANTICS_MISS` | **Deferred**: pre-dramatic_meaning_strict content |
| `戏服玩心夜` | `framing iron lint … HEADROOM_MISS,HEAD_CROP` | **Deferred**: content framing |
| `便利店夜班_里番_Grok输出` | `requires non-empty vo_mode` | **Deferred**: incomplete export |

### D. write-spec vs validate gap (documented; not softened)

| Fixture | validate | write-spec cinematic audit |
|---------|----------|----------------------------|
| `film-spec.example.json` | OK | FAIL `ARC_STACK_FLAT` |
| `film-spec.adult-max.example.json` | OK | FAIL `FRAME_CHAIN_GAP`, `SIZE_FLAT` |
| Pipeline `valid_spec()` (+ director_board / performance / arc progression) | OK | OK |

This is intentional fail-closed production discipline, not a false hard-fail on still-supported fields. Scaffolds remain **validate-green authoring seeds**; agents must complete creative contract before write-spec.

## Historical / log context

- **CHANGELOG**: write-spec extracted to `cli_write_spec.py`; dramatic_meaning fail-closed; zero-narration IRON for `dialogue_drama`; hybrid-h3 template added as profile example; FRW seedance retired → LTX/legacy.
- **Memory / plans**: H3 primary capacity (2026-08-05), fill-idle challenge, adult-max IRON — film-spec remains executable source of truth.
- **Last known green path**: unit tests + adult-max / example under `validate_film_spec`; write-spec green only with full cinematic contract.

## Remediation done this session

1. **Templates**: `film-spec.h3-primary.example.json`, `film-spec.hybrid-h3.example.json` rewritten as adult-max-compatible production-valid specs retaining H3 fields.
2. **Tests**: `test_director_intent.py` asserts **all** `templates/film-spec*.json` pass real `validate_film_spec`, plus H3 lane field retention.
3. **No** softening of adult-max / dramatic-meaning / zero-narration / cinematic audit irons.
4. **No** bulk migration of Desktop roots (out of scope unless in-repo contract bug).

## Deferred (explicit)

- Bulk-rewrite historical Desktop film roots (seedance → legacy/ltx; dramatic_meaning arc nodes).
- Expand example/adult-max scaffolds into full write-spec cinematic contracts (optional future).
- Canary film-specs under `artifacts/5090-evaluation/*` (mode probes, not write-spec golden).

## How to re-verify

```bash
ROOT="$(git rev-parse --show-toplevel)"
SKILL="$ROOT/skills/ai-film-grok"
PY="$($SKILL/scripts/runtime-python)"
cd "$SKILL" && env -u PYTHONPATH "$PY" -m pytest tests/test_director_intent.py tests/test_cli_write_spec_extract.py tests/test_dramatic_meaning.py -q --tb=line
```

Commit: film-spec H3 templates + tests + this report (`Fix film-spec H3 templates so validate_film_spec accepts them`).

## Follow-up (same day · write-spec scaffolds)

1. Shipped templates write-spec green (pose chain, size variety, arc_node, performance/craft, director_board).
2. write-spec wardrobe hard-fail only when bible authored wardrobe_variants.
3. framing_lint _size_rank normalizes close-up / medium full / insert; medium-close before bare close.
4. Tests: all film-spec*.json through real write-spec; size-rank unit tests.
