# Monolith closeout status (2026-08-06 · v2.40.17)

**Branch:** current checkout (`codex/next-optimization-round` or equivalent)  
**Verdict:** **heat structure DONE** · final/export/film_spec **leaves shipped** · orchestrator bodies residual by design

## Shipped structure

| Area | Before | After | Notes |
|------|-------:|------:|-------|
| `edit_policy_heat` | ~3788–4024 | **~90 facade** | 7 packs re-export |
| heat packs | — | phase/wardrobe/coitus/spice/impact/multi/arc_lint | cycle-safe leaves |
| `render_final` | ~2985 | **~2887** | leaves: defaults/io/manifest/voice_mix/spotting/watchdog |
| `export_composition` | ~2804 | **~2575** | cues + helpers peeled |
| `film_spec_validate` | ~3033 | **~2420** + lints **~717** | pure lints peeled |

## Residual (honest — not vanity LOC)

1. **`render_final()` body** (~2.3k): TTS loop · stretch · concat · music bed · dual mix · subs · mux — high coupling; next peels need stage context object + harness per stage.
2. **`export_composition` writers:** `write_hyperframes` / `write_remotion` / `build_timeline_package` still thick.
3. **`validate_film_spec` body** still one large procedure after pure lints out.
4. **export integration tests** on this branch may fail on `dramatic_meaning_strict` fixtures — product gate, not peel regression (ParseSrt + peel suite green).

## Iron preserved

Public CLI strings · shim hard-compat · no silent heat/i2v/pilot retune.

## Verify

```bash
cd skills/ai-film-grok
python3 -m pytest tests/test_w3_package_shims.py tests/test_final_hotpath_contracts.py \
  tests/test_heat_check.py tests/test_heat_arc_multi.py tests/test_cli_write_spec_extract.py \
  tests/test_director_intent.py tests/test_export_hotpath_contracts.py \
  tests/test_compose_hotpath_contracts.py tests/test_export_composition.py::ParseSrtTests \
  tests/test_suse_final_iron.py tests/test_render_core_helpers.py -q
```
