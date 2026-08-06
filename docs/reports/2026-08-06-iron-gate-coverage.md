# IRON / hard-gate coverage map (2026-08-06)

Short index: **rule → code → tests**. Doc-only rows are marked; prefer promoting them when they burn production.

| Rule (hard-defaults / memory) | Primary code | Tests / gates | Enforced? |
|-------------------------------|--------------|---------------|-----------|
| Adult MAX / heat sex duration floor | `narrative/edit_policy_heat.py`, `plan/film_spec_sex_floor.py` | `test_suse_final_iron`, heat tests | **code** fail-closed on silent 10s pad |
| Wardrobe no re-dress / scale fallback | `narrative/scale_fallback.py`, heat wardrobe codes | `test_suse_final_iron` (HEAT_WARDROBE_RE_DRESS) | **code** + receipts |
| Poison / anatomy stop | `anatomy_safety.py`, scale-fallback hard-on ban | heat / media_queue fail paths | **partial** (receipt stop; not full CV) |
| Composition anti-hijack (multi-seed) | `composition_anti_hijack.py` | anti-hijack tests if present; promote paths must call | **code** (+ escape env) |
| Native audio audible / not ASR | `core/media_ops.probe_native_audio_mean_volume`, `h3_ship_native` | `test_duration_target_ship_native` | **soft** honesty codes |
| Duration target honesty | `plan/duration_target.py` | `test_duration_target_ship_native` | **code** bulk-preflight |
| Official final plate ≠ master | `final/delivery_class`, render_final | `test_suse_final_iron` | **code** |
| VO window triangle tts≤cue≤slot | render_final / final helpers | `test_suse_final_iron`, final hotpath | **code** |
| Caption hard-burn ship | export / HF caption path | post caption / hotpath tests | **code** path-dependent |
| Multi-agent GPU no-hog | docs + ops discipline; fill-idle free-first | until-empty tests (behavior) | **process + code** free-first |
| Pilot GO human-only | dispatch / pilot | dispatch contract tests | **process** |

**Maintenance:** when adding an IRON row to `hard-defaults.md`, add a row here and a failing-mode test (prefer `@pytest.mark.hotpath` for ship-path fail-closed).
