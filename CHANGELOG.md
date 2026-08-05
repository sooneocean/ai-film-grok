# Changelog

## [2.39.27] - 2026-08-05

### Changed (CLI extract · W5d)
- **`cli_orchestrate.py`**: next / stage / dispatch / advance / autopilot / craft / selects.
- **`cli_oauth.py`**: grok-oauth / usage.
- **`cli_evidence.py`**: state-index / promotion-report / production-evidence / speech-preview.
- **`cli_bootstrap.py`**: lock-runtime / resume-manifest.
- **`aifilm_grok.py`**: ~5348 LOC (was ~6063); public subcommand strings unchanged.
- **Tests**: `tests/test_cli_w5d_extract.py`.
- **Docs**: `docs/plans/cli-extract-map.md`.

## [2.39.26] - 2026-08-05

### Fixed (version pointer · session closeout)
- Restore **plugin.json / docs** to the post P2 line after concurrent M5/M6 commits regressed the pointer to `2.39.23` while `2.39.24–25` already shipped post CLI + hotpath contracts.
- Confirm post modules remain: `post_route` · `caption_pixel_check` · `timeline_clock` · `post_doctor` · `mix_partial`.

## [2.39.25] - 2026-08-05

### Added (Post P2 · hotpath contracts)
- Expand `test_final_hotpath_contracts`: caption_path plate rules, SRT non-overlap clamp, mix PARTIAL v2, dual-clock rewrite, post-doctor double-burn, plate timeout floors, allow_burned_underlay ship path.
- Locks lesson-backed post P0/P1 invariants against CLI-extract churn.

## [2.39.24] - 2026-08-05

### Fixed (Post CLI restore + version hygiene)
- **CLI restore** on slim monolith: `caption-pixel-check`, `post-doctor`, `timeline-clock audit|rewrite`, `final --caption-path|--ship-hardburn` (dropped during CLI extract waves).
- **Pointers**: plugin / README / skill README / GRAPH → **2.39.24**.
- **Verify**: post P1 modules + hotpath tests green.

## [2.39.23] - 2026-08-05

### Added (Material Fidelity · M5 identity/FLF + M6 generation_ready)
- **M5** `identity_refs.py`: canonical/cast + face-lock first; legacy cast/refs soft-warn; media_pack `flf_ready`/`mode_hint`/`identity_warnings`.
- **M6** `generation_ready.py`: dispatch full+compact expose style/still/FLF readiness line.
- **Tests**: `tests/test_material_fidelity_m5m6.py`.

## [2.39.22] - 2026-08-05

### Changed (CLI extract · W5c)
- **`cli_audio.py`**: extract audio/TTS/BGM/SFX/lipsync cluster (~22 cmds) from monolith.
- **`aifilm_grok.py`**: ~5980 LOC (was ~7161 after write-spec extract).
- **Tests**: `tests/test_cli_audio_extract.py`.
- **Docs**: `docs/plans/cli-extract-map.md`.

## [2.39.21] - 2026-08-05

### Changed (CLI extract · W5b)
- **`cli_write_spec.py`**: extract `write-spec` + film-spec compatibility projectors from monolith.
- **`aifilm_grok.py`**: ~7161 LOC (was ~7539 after pilot extract).
- **Tests**: `tests/test_cli_write_spec_extract.py`.
- **Docs**: `docs/plans/cli-extract-map.md`.

## [2.39.20] - 2026-08-05

### Added (Post P1 · timeline clock + doctor + mix honesty)
- **`timeline_clock`**: single on-picture clock; `aifilm timeline-clock audit|rewrite`; final persists `receipts/film_timeline.json`.
- **`post-doctor`**: one-page post health (caption_path / double-burn / SRT / five-track / mix PARTIAL / pixel).
- **`mix_partial`**: PARTIAL receipt v2 with `reason_code` · `affected_tracks` · `honest_limits` · `error_type`.
- **preflight** hard: dual-clock · double-burn · SRT overlap · caption pixel red.
- **five-track** soft: FX likely inaudible · mix PARTIAL honesty.
- **Tests**: `tests/test_post_p1_timeline_doctor.py`.

## [2.39.20] - 2026-08-05

### Fixed (h3_primary + caption soft gates)
- **closeout caption_pixel**: soft-skip when no `final.srt` (no dialogue cues); hard only with SRT.
- **evidence_stale**: CAPTION_PIXEL_STALE only when SRT present.
- **tests**: isolate `AIFILM_I2V_PROFILE=grok_primary` for film-spec default + media-queue membership under machine h3_primary config.

## [2.39.19] - 2026-08-05

### Added (CLI extract + docs · W5)
- **`cli_pilot.py`**: extract `pilot pick|report|pack|score|approve` from monolith (`aifilm_grok` ~7.5k LOC).
- **Docs**: hard-defaults / skill README push **`h3_primary`** as 5090 default; `cli-extract-map` updated.
- **Tests**: `tests/test_cli_pilot_extract.py`.

## [2.39.18] - 2026-08-05

### Added (Material Fidelity · M3 registry + M4 evidence)
- **M3** `build_asset_prompt_hints`: location/prop locks into GenerationRequest (structure, lighting, palette, immutableRules, recurringObjects, prop condition/storyFunction).
- **M4** `shot_evidence.py`: evidence from mean sidecar + register-clip; `PRIOR_EVIDENCE` in next gen; next_actions still-challenge on weak mean; heavier pk identity L1 penalty.
- **Tests**: `tests/test_material_fidelity_m3m4.py`.
- **Docs**: material-fidelity-loop + plan tracker (M0–M4 shipped).

## [2.39.17] - 2026-08-05

### Added (Gate slim · W4)
- **Single machine next** after clips: ship-prep / gate-auto only; no duplicate `select-shortlist` in dispatch/next_actions (plate-less path returns early without stacking final/tts).
- **pilot-pack** `h3_mode_trio` + GO template for I2V/R2V/T2V smoke (`schema_version` 2); optional strict via `AIFILM_STRICT_H3_PILOT_MODES=1`.
- **ship-prep** writes `receipts/ship-prep-human.md` one-pager when multi-take / human PK.
- **Tests**: `tests/test_w4_gate_slim.py`.

## [2.39.16] - 2026-08-05

### Added (H3 overnight throughput · W3)
- **`aifilm h3 cycle --until-empty --execute`**: loop run-next until queue empty / capacity / fail (hard max cycles; never promote; not an OS daemon).
- **`aifilm h3 capacity-plan`**: backlog ETA by mode/priority → `receipts/h3-capacity-plan.json`.
- **Priority invariant**: `assert_priority_order` — P0 never starved by P2; queue exposes `priority_ok`.
- **dispatch**: `h3_primary` next prefers `h3-until-empty` + capacity-plan.
- **Tests**: `tests/test_h3_until_empty.py`.

### Docs (Material Fidelity Loop · index)
- **Plan + memory**: `docs/plans/2026-08-05-material-fidelity-loop.md` · `memory/2026-08-05-material-fidelity-loop.md`.
- **Runtime already on main** (`still_source` · `generation_request` · h3 plan receipt · queue sha gate · stages/visual「谁喂谁」).

## [2.39.15] - 2026-08-05

### Added (Post P0 · caption_path + pixel ink · Wave 2)
- **`caption_path`**: `master_hf` | `ship_hardburn` — one episode, one caption decision (`receipts/post-route.json`).
- **CLI**: `final --caption-path` / `--ship-hardburn`; `aifilm caption-pixel-check --root`.
- **closeout**: ladder steps `caption_pixel` + `evidence_fresh`; auto-run pixel check when final exists (soft-skip before plate).
- **Modules**: `post_route.py` · `caption_pixel_check.py` (bottom-band ink heuristic; escape `AIFILM_SKIP_CAPTION_PIXEL=1`).
- **Docs**: `docs/plans/2026-08-05-optimization-todoplan.md` · stages/post pointers.

### Changed (util · Wave 3 partial)
- **`util.run_ffmpeg` / `run_compose_env`**: canonical ffmpeg/compose runners; `render_final` / music / `compose_render` delegate.
- **`FilmError`**: optional `code` + `details`; `utc_now` unified in director_review / prompt_injector / visual_bible.

### Tests
- `tests/test_post_route.py` · `tests/test_caption_pixel_check.py`

## [2.39.14] - 2026-08-05

### Added (h3_primary · 5090 unlimited mainline · P0)
- **`AIFILM_I2V_PROFILE=h3_primary`**: film-wide local MiniMax H3 primary (`auto` → `comfy-h3`).
- **Router**: setup / safe dialogue / env under `h3_primary` lock to H3 (I2V or T2V); Grok not default bulk.
- **media-queue**: blocks cloud for all H3-locked shots on `h3_primary` (escape `AIFILM_ALLOW_CLOUD_RESTRICTED=1`).
- **dispatch / next_actions**: prefer `h3-run-next` when clips incomplete + H3 primary.
- **Docs**: `docs/plans/2026-08-05-h3-primary-capacity.md` · memory · weapon-lane · stages/visual · SKILL P0.
- **Tests**: `tests/test_h3_primary.py` (+ profile unit).

## [2.39.13] - 2026-08-05

### Changed (Machine-lane consolidation · single entry)
- **`ensure_machine_lane`**: one entry for ship-prep / closeout / export (fast if green).
- **`next_machine_lane_action`**: dispatch + next_actions share one post-clips next (gate-auto; ship-prep only for multi-take shortlist).
- **ship-prep**: skip re-run i2v when receipt already ok; end via ensure_machine_lane with `measure_i2v=False` if already graded.
- **export assert / closeout**: no dual gate-auto then cinematic auto_i2v thrash.
- Removed scattered ship-prep / i2v-motion / gate-auto triple next paths.

## [2.39.12] - 2026-08-05

### Changed (Orchestration timing + token efficiency)
- **state hash**: gate receipts (`gate-auto`/`cinematic`/`i2v-final`/…) hash only `ok`/`blocked_by` — timestamp thrash no longer busts dispatch cache.
- **advance**: `use_state_cache=True` in local loop (fewer full rebuilds per step).
- **gate-auto fast_path_reuse**: green+fast already written → no re-write (less I/O).
- **ship-prep**: skip gate-auto body when `machine_receipts_green`.
- **context-routing**: `max_refs` 3→2, `max_bytes` 8k→4k; `projection.verify` → deliver stage only.
- **compact_dispatch**: fidelity only on post/deliver/design; tighter 4.2kB trim budget.

## [2.39.11] - 2026-08-05

### Changed (Gate-auto optimize · fast_path + soft empty i2v)
- **fast_path**: when `gate-auto` + `i2v-final` + `cinematic` already ok, `run_gate_auto(force=False)` returns immediately (export/closeout/ship-prep thrash).
- **CLI** `gate-auto --force` to re-measure; advance allowlist includes `--force`.
- **i2v_motion** soft-skip when zero rows and no approved clips (empty pre-media root).
- **machine-ready.json** compact pointer; dispatch/next_actions skip re-push when green.
- export assert uses fast_path before full cinematic re-run.

## [2.39.10] - 2026-08-04

### Changed (Gate-auto deep wire · advance / dispatch / ship-prep / export)
- **advance** + **autopilot W8**: `gate-auto` and `cinematic-gate` on `ADVANCE_ACTIONS` + `LOCAL_THROUGHPUT_NEXT_IDS` so `aifilm advance` / autopilot can run the machine ladder without human click.
- **dispatch**: clips 齐后优先 `gate-auto`（机写 mean/i2v-final/cinematic）；`_COMMAND_POLICIES` local/none.
- **ship-prep** end stamp uses `run_gate_auto` (falls back to cinematic auto_i2v).
- **export-desktop** assert: missing/red cinematic → `gate-auto` once then re-check.
- Tests: advance argv + W8 allowlist cases. Escape unchanged (`AIFILM_SKIP_GATE_AUTO` / `AIFILM_SKIP_CINEMATIC_GATE`).

## [2.39.9] - 2026-08-04

### Added (Gate-auto machine verification · no human click-loop)
- **`gate_auto.py`** + CLI `aifilm gate-auto`: measure means → write i2v-final → inject sex_sfx → five_track → single-take promote → true_video → variety → cinematic → `receipts/gate-auto.json`.
- **closeout** auto-runs gate-auto when cinematic red; **next_actions** prefers gate-auto after clips complete.
- **cinematic-gate** default `auto_i2v=True` (measure+write when receipt missing/red).
- Human still required: pilot approval, multi-take PK, review-final, paid budget ack.
- Escape: `AIFILM_SKIP_GATE_AUTO=1`. Tests: `test_gate_auto.py`.
- Docs: hard-defaults · stages/deliver · SKILL · memory `2026-08-04-gate-auto.md`.
- Fix: register-clip true-video path uses getattr shot_id; TTS loop-risk fixture disables dramatic_meaning_strict.

## [2.39.8] - 2026-08-04

### Added (Cinema ship closeout · α–ε final)
- **closeout** ladder: hard `cinematic_gate` after i2v_motion; `closeout run` auto-refreshes gate.
- **SKILL** P0 #20 + command path: ship-prep → cinematic-gate → final → closeout.
- Memory: `2026-08-04-cinematic-ship-closeout.md` full-wave checklist.

## [2.39.7] - 2026-08-04

### Added (Cinematic-gate composite · Wave ε)
- **`cinematic_gate.py`**: one-shot true_video + inventory + i2v-final + variety + five_track + edit_rhythm → `receipts/cinematic-gate.json`.
- **CLI** `aifilm cinematic-gate [--ship-prep]`; ship-prep stamps gate; **export-desktop** requires ok.
- **dispatch/next**: after clips complete, push cinematic-gate before final.
- Escape: `AIFILM_SKIP_CINEMATIC_GATE=1`. Tests: `test_cinematic_gate.py`.

## [2.39.6] - 2026-08-04

### Added (5-Track cinema mix MVP · Wave δ)
- **`five_track.py`**: DX/FX/BG/MX/SUB contract mapped to final stems; auto-enable for dialogue_drama / heat max / premium.
- **LUFS**: default **lufs_strict** + **-16 ±1.5** (`-17.5…-14.5`) on cinema path; post-audit uses shared band.
- **CLI** `aifilm five-track plan|audit`; ship-prep step; film-spec ensure defaults + meat `sex_sfx` inventory.
- Docs: hard-defaults + 5track-audio-master MVP. Escape: `AIFILM_SKIP_FIVE_TRACK=1`.
- Tests: `test_five_track.py`.

## [2.39.5] - 2026-08-04

### Added / Changed (Edit rhythm VO-fit · Wave γ anti-PPT)
- **`dialogue_drama` default `visual_fit=vo`** via `edit_policy.default_visual_fit` / `resolve_shot_visual_fit` (spoken + mid_motion → vo).
- **Drive shots** auto `dsl.cut_on=mid_motion` when blank (hook/approach/action/act/climax).
- **Freeze pad** tightened: ≤0.15s (no-loop ≤0.20s) — no long still pad as fake length.
- **preflight** soft `EQUAL_SLOT_PPT_RISK`; film-spec writes `_edit_rhythm`.
- render_final / export-compose / preflight use shared defaults.
- Tests: `test_edit_rhythm_gamma.py`.

## [2.39.4] - 2026-08-04

### Added / Changed (Camera serves event · cinematic motion β)
- **No silent push-in pad** in `build_motion_prompt`; empty core fails `assert_motion_prompt_core`.
- **MOTION_CORE_CAMERA_ONLY**: hero I2V rejects camera filler without body/prop action or dialogue.
- **lint_meaningful_motion**: `CAMERA_WITHOUT_EVENT`; elevate `MOTION_NO_MEANING` / missing visible_change to error.
- **variety-precheck**: `ADJACENT_FRAMING_COLLISION` + `ADJACENT_TRIPLE_COLLISION` for meat neighbors.
- **H3 plan**: `mode_policy` follows list/plan command; run records `mode_cli_override` when CLI differs.
- Docs: hard-defaults + visual stage. Tests: `test_camera_serves_event.py`.

## [2.39.3] - 2026-08-04

### Added (True-video-only hero · ban still-as-camera)
- **`true_video_policy`**: hero timeline accepts **only generated video** (Grok I2V / H3 I2V|FLF|R2V / LTX). Stills never enter the cut.
- **register-clip / evaluate_clip / approved_clip_record**: reject png stills, Ken Burns endpoints, panel/shortform still-motion tags; `external` needs generative provenance tags.
- **preflight + final + ship-prep**: hard scan of approved clips; `PANEL_MOTION_NOT_HERO` on drama.
- **motion_plan**: Ken Burns / panel plans forbidden unless `production_mode=panel`.
- Docs: hard-defaults + stages visual/post. Escape: `AIFILM_SKIP_TRUE_VIDEO_POLICY=1`.
- Tests: `tests/test_true_video_policy.py`.

## [2.39.2] - 2026-08-04

### Changed (Chinese-only dialogue · Japanese retired)
- **Product**: `dialogue_spoken_lang=zh` hard lock; **reject** `ja` / `dialogue_ja` production path.
- **voice_cast_profiles**: ZH_POOL only; JA_POOL removed; `ja` language raises; strip legacy `ja-JP-*` voice ids.
- **film_spec / render_final / narrative_timeline / tts_rehearsal**: Chinese spoken/caption only; no JA voice defaults.
- **dialogue_screenplay**: ready = Chinese dialogue+subtitle; `DIALOGUE_JA_RETIRED` gate.
- **lipsync_challenge / lipsync_pilot**: approval binds **Chinese** final character dialogue.
- **hard-defaults / dispatch**: copy updated to 中文唯一.
- Tests: dialogue/voice/lipsync fixtures converted to zh.

## [2.39.1] - 2026-08-04

### Fixed / Changed (Chinese dialogue primary + TTS multi-provider + music import)
- **voice_cast_profiles**: default vocal language for dialogue/inner/media is **zh** (was ja); ja only via explicit `language` / `spoken_lang` / `dialogue_spoken_lang`.
- **audio_timeline**: carry authored `language` onto compiled vocal events so cast does not fall back to stale JA.
- **audio_tts_render**: honor locked provider from manifest (`edge` / `grok` / `mimo` / `fish` / `minimax` / `voicebox` / `qwen3` / `external`); no longer force `edge` only.
- **voice_cast_profiles**: locked profile always keeps `voice_id` (一角一声); normalize jp/cn aliases.
- **local_llm**: allow vision models `zai-org/glm-4.6v-flash` + `nvidia/nemotron-3-nano-omni` for omni / visual-text audit.
- **render_final_music**: local `SR` / `run` / `RenderError` to break circular import with `render_final`.
- Tests: event-language defaults + JA opt-in fixtures updated.

### Docs
- Root + skill **README** rewritten for **v2.39**: debrief / input fidelity / design-go / hybrid_h3 FLF / Fill-Idle / still-challenge; Gitea remotes; updated minimal path and I2V matrix.

## [2.39.0] - 2026-08-04

### Added (Input Fidelity full chain · F0–F3 + S)
- **`fidelity apply`**: stamp `source_quote` / must_keep / protected dialogue onto film-spec.
- **`design-go`**: debrief + fidelity + variety one-page (never signs pilot).
- **I2V**: `Story beat:` prefix via `motion_prompt_spine`.
- **register-still**: optional source overlap (strict via env/spec).
- **closeout / ship-prep**: `input_fidelity` ladder step + human summary.
- **dispatch compact** fidelity one-liner; **next_actions** fidelity-apply/design-go.
- **advance / autopilot** allowlist: fidelity-check|apply, design-go (no debrief/pilot sign).
- Tests: expanded `test_input_fidelity.py`.

## [2.38.9] - 2026-08-04

### Added (Input Fidelity · Wave F0)
- **`input_fidelity.py`**: aggregate score + codes (pollution, entity coverage, protected dialogue, must_keep map, debrief, source anchors) → `receipts/input-fidelity.json`.
- **`aifilm fidelity status|check --root`**: `--strict` / `--soft`; env `AIFILM_FIDELITY_STRICT`.
- Template + hard-defaults row + memory `2026-08-04-input-fidelity.md`; SKILL plan-chain hook.
- Tests: `test_input_fidelity.py`. Backlog F1–F3/S in `docs/plans/2026-08-04-input-fidelity-flow.md`.

### Changed (H3 I2V/R2V first+last primary · quality)
- **Policy `h3_max_effect_v2_first_last`**: first+last both present → **FLF primary** (including restricted dialogue-CU / high-motion); energy becomes `alt_mode=r2v`. `force_r2v` still R2V (last as pose ref).
- **Fill-Idle**: passes `has_last`; tracks `_flf_` as identity leg; dual prefer FLF; commands include `--last-frame`.
- **R2V first/last input**: last still is first multi-ref (pose land) + land prompt; plan/receipt/queue carry last for r2v.
- Docs: weapon-lane matrix · memory `2026-08-04-h3-flf-first-last.md`; SKILL P0 #7.
- Tests: energy+last→flf · force_r2v+last · 53 H3 tests green.

## [2.38.8] - 2026-08-04

### Added (script-value-debrief routing + smarter seed)
- **`next_actions`**: story intake → force `plan-debrief` / `plan-debrief-confirm` first (early return); pipeline stage flag `script_value_debrief_pending`; skip once pilot/media past planning.
- **`seed_from_reception`**: infer dramatic_function/rank; guarantee climax/ending; setup→climax pairs; `needs_agent_fill` only when state/visible incomplete.
- **Schema**: `schemas/script-value-debrief.schema.json` + soft stamp on write (`_schema_ok` / `_schema_validation`).
- **context-routing**: optional debrief ref on story/beats stages.
- Tests: next_actions debrief gate + richer seed/confirm coverage.

## [2.38.7] - 2026-08-04

### Added (H3 FLF + media-pack + multi-ref full chain)
- **Phase 2 media pack**: cast bible identity refs, state-master end still, still-challenge end candidates, `missing_last_hint` on plan.
- **Phase 3 R2V multi-ref**: armory injects LoadImage 21/22 → `ref_images.ref_image_1/2`; `<Picture n>` duty clause; `h3 run --ref` / pack refs.
- **Phase 4 end still**: `still-challenge promote --as end` → `stills/<id>_end.png` + manifest `*_end`.
- **Phase 0 scaffold**: `artifacts/5090-evaluation/h3-flf-ab-scaffold/` (GPU busy at ship; offline recipe).
- Tests: expanded `test_h3_flf_media_pack` (promote-as-end, multi-ref compile, identity refs).

## [2.38.6] - 2026-08-04

### Added (H3 FLF first+last frame · docs/tests closeout)
- **FLF mode** already in runtime (`h3_mode`/`h3_media_pack`/`--last-frame`); docs: weapon-lane + memory; tests: `test_h3_flf_media_pack`.

### Added (Script value debrief · presentation-value pre-lock)
- **`script_value_debrief.py`**: L0–L4 validate/score/seed/confirm/summary; soft missing / strict hard; pilot shortlist + beat→shot map.
- **`aifilm plan debrief`**: `--action status|seed|write|confirm|validate` (human confirm via `--user-phrase`).
- **`story_quality`**: folds promise_clarity / beat_value_coverage / setup_payoff / dead_air when debrief present.
- **`plan validate`**: attaches `script_value_debrief` + `story_quality`; `--strict` fails on missing/bad debrief.
- **`plan lock --scope story --strict`** / `AIFILM_DEBRIEF_STRICT=1`: block unconfirmed debrief.
- **`pilot pack`**: prefers debrief value_rank shortlist (`script_value_preference` on pilot-go receipt).
- Docs/templates/memory: `script-value-debrief.md`, example + adult-max JSON, agent/reception/SKILL hooks.
- Tests: `test_script_value_debrief.py` (15).

## [2.38.5] - 2026-08-04

### Added (FRW i2i still-material challenge · 30s rate limit)
- **`frw_rate_limit.py`**: shared image ≥30s / video ≥5min state (`~/.hermes/cache/ai-film-frw-frw-rate.json`); wired into `frw_dispatch`.
- **`still_challenge.py` + `aifilm still-challenge`**: plan/next/run/list/promote for FRW img2image candidate stills that improve I2V/R2V sources (unit=1, no silent promote, skip poison/continue).
- **H3**: `--still` override on plan/run; `still_challenge_candidates` on plan; `h3 next` may surface `still_challenge_hint`.
- Docs: hard-defaults · weapon-lane · memory `2026-08-04-frw-i2i-still-challenge.md`.
- Tests: `test_frw_rate_limit` · `test_still_challenge`.

## [2.38.4] - 2026-08-04

### Changed (C4 · status/doctor + giant module split + disk hygiene)
- **`cli_status`**: extract `cmd_doctor` + `_classify_doctor_readiness` (~350 LOC); re-export from `aifilm_grok`.
- **`edit_policy_heat.py`**: heat/wardrobe/sex/VO spice (~4k LOC) off `edit_policy`; public symbols re-exported.
- **`render_final_music.py`**: BGM/WAV/loudness helpers (~700 LOC) off `render_final`; re-exported.
- Monolith ~8070 → ~7720; `edit_policy` ~6360 → ~2470; `render_final` ~5020 → ~4340.
- **Disk (user OK):** remove repo-root duplicate `g2pW` (152M) and `.local-runtimes` (~4.5G offline TTS; edge remains default). Skill-side `g2pW` kept.
- **Tests:** fix `test_heat_arc_multi` `_spine` typos (`action_full` / `beat_motion` scope) so heat gates run again.

## [2.38.3] - 2026-08-04

### Changed (C3 · media CLI extract)
- **`cli_media.py`**: extract register-still/clip, style-lock, continuity, face-identity, assemble, reencode, shortform/ingest (~1.6k LOC).
- **`aifilm_grok`**: re-exports; helpers proxy through monolith for monkeypatch.
- Monolith ~9640 → ~8070 lines after C2+C3.

## [2.38.2] - 2026-08-04

### Fixed / Added (human-safe ship-prep + fill-idle cycle)
- **ship-prep**: multi-take **defers promote** by default (was mean-auto-promoting before human PK). Escape `AIFILM_SHIP_PROMOTE_FORCE=1`.
- **pk-compare**: writes `receipts/pk-dailies.md`.
- **`aifilm h3 cycle`**: evidence → run-next → evidence → pk peek (never promote).
- **next_actions**: Fill-Idle points at `h3 cycle --execute --max 5`.
- Tests: promote defer · cycle dry.

## [2.38.1] - 2026-08-04

### Changed (C1/C2 CLI post extract + hotpath + INDEX)
- **`cli_post.py`**: extract final/compose/closeout/export-desktop handlers (~1.5k LOC off `aifilm_grok`); public cmds unchanged.
- **`docs/plans/cli-extract-map.md`**, **`2026-08-04-project-refactor-active.md`**.
- INDEX Active P0 block; `@pytest.mark.hotpath` + `make test-hotpath`.

## [2.38.0] - 2026-08-04

### Added (Fill-Idle Wave αβγ · effect optimization)
- **α evidence**: `aifilm h3 evidence --root` → `receipts/fill-idle-evidence.json` + dailies metrics (no GPU).
- **β PK quality**: composite `pk_score` (motion − identity penalty); soft midframe L1; `dailies_md`; identity can demote recommended.
- **β shortlist**: multi-take rows attach `pk_advisory` (never auto-promote).
- **γ dual sticky**: dual second leg sorts ahead of other same-rank jobs.
- **γ enough-motion**: skip blind R2V when I2V strong (unless `h3_prefer: dual`); skip P2 when baseline ≥ floor+6.
- **γ free-memory**: `run-next` frees Comfy VRAM on mode switch (`--no-free-memory` escape).
- **γ Grok tag**: media-queue complete hardlinks `takes/<sid>/grok_*` when provider is Grok.
- Tests: pk composite · evidence; fill-idle threshold fixtures.

## [2.37.14] - 2026-08-04

### Changed (C1/C2 CLI post extract + hotpath marker + INDEX)
- **`cli_post.py`**: extract final / review-final / compose-* / register-final / closeout / export-desktop / post-plan / post-quality (~1.5k LOC); `aifilm_grok` re-exports (public cmds unchanged).
- **`docs/plans/cli-extract-map.md`** + **`2026-08-04-project-refactor-active.md`** active tracker.
- **INDEX**: Active P0 lessons block; archive rule pointer.
- **`@pytest.mark.hotpath`** + **`make test-hotpath`** for final/compose/gates fail-mode suite.
- Monolith `aifilm_grok.py` ~11200 → ~9650 lines.

## [2.37.13] - 2026-08-04

### Changed (P1a · util JSON hotpath)
- **`util.soft_json` / `require_json_as` / `require_json_fnv`**: single load path; domain modules stop re-implementing `json.loads`.
- **final_stages**: drop `_read_json`; use `soft_json`.
- **render_final / compose_render / export_composition / pilot_review / aifilm_grok**: thin aliases → util.
- **media_queue**: queue state + film-spec + capability canary via util read/write.
- Tests: `test_util_json_contract` covers soft/as/fnv + final_stages no local def.

## [2.37.12] - 2026-08-04

### Fixed / Added (Fill-Idle run-next production stage + batch)
- **`run-next`**: P2 soft challenges use **pilot** stage (was always production).
- **`run-next --max N`**: run up to N jobs per call (default 1, hard cap 20) — still not a daemon.
- Returns `jobs_ran` / `runs[]` / `pending_after`; stages/visual + memory updated.
- Tests: stage matrix in `test_fill_idle_run_next_ledger`.

## [2.37.11] - 2026-08-04

### Added (H2/H3 · hotpath gate matrix on fast suite)
- **`test_compose_hotpath_contracts`**: double-burn underlay/auto/multiclip + HF register caption fail-closed — **not** marked slow (was only under slow suite).
- **`test_gates_table_matrix`**: table-driven meaning_gate × genre/escape, zero_narration, motion ship export, heat final hard_fail.
- Complements Wave D / Delivery Truth without full render.

## [2.37.10] - 2026-08-04

### Added (ship-prep × Fill-Idle PK)
- **`ship-prep`**: advisory steps `pk_compare` + `fill_idle_pending` after shortlist (never auto-promote).
- Receipt `receipts/pk-compare-ship-prep.json` when multi-take exists; `human_pk_required` flag.
- CLI `--skip-pk` / env `AIFILM_SKIP_SHIP_PK=1`.
- Tests: `test_ship_prep_includes_pk_compare_advisory`.

## [2.37.9] - 2026-08-04

### Fixed / Added (Wave Z + H1 · maintainability)
- **`write_final_mix_partial_receipt`**: extract sidechain→amix PARTIAL receipt writer; closeout/agents can unit-test fail-mode without full final.
- **H1 tests** (`test_final_wave_d`): longform mode timeout floor 1800, cap 21600, on-disk partial receipt, plate `subs` burn|off fail-closed.
- **Disk hygiene inventory** (list only, no delete): `docs/reports/2026-08-04-disk-hygiene.md`.
- Greenline: check-all (2709+ passed); baseline refreshable via `make audit`.

## [2.37.8] - 2026-08-04

### Added (Speaker-frame + Fill-Idle run-next + PK ledger + dual-take)
- **`dialogue_speaker_frame_gate`**: on_camera speaker must match cue + dsl.subject/cast; heat-window beat flip gate; preflight soft/hard.
- **`aifilm h3 run-next`**: one-shot worker (capacity-aware); `--execute` runs next H3 job — not a daemon; never auto-promotes; returns `next_after` after run.
- **`aifilm h3 pk-ledger`**: advisory dailies ledger only (no cross-film auto win-rate; agree-all). CLI subparser complete.
- **Dual-take P0**: climax / dialogue-CU meat / `h3_prefer: dual` → after I2V, queue second leg **R2V** (and reverse) before marking done.
- Tests: `test_dialogue_speaker_frame_gate.py` · `test_fill_idle_run_next_ledger.py` · dual-leg in `test_h3_fill_idle.py`.

## [2.37.7] - 2026-08-04

### Fixed / Added (Fill-Idle production closed loop)
- **`list_shot_takes`**: discover baseline from **`manifest.clips`** (not only `takes/`) so Grok-only paths unlock P2.
- **`h3 next`**: soft **Comfy capacity** probe (`capacity_ready` / blockers; offline non-fatal).
- **`h3 run`**: best-effort **mean sidecar** on deliver path for PK/shortlist.
- **dispatch**: surfaces `h3 next` Fill-Idle while hybrid_h3 active.
- Tests: manifest baseline + capacity soft path.

## [2.37.6] - 2026-08-04

### Changed (Dramatic meaning default-on · every genre)
- **`meaning_gate_enabled`**: fail-closed for **every** genre pack by default (was heat=max / premium only).
- Escape: `dramatic_meaning_strict: false` (per film) or `AIFILM_SKIP_MEANING_GATE=1` (env; `strict:true` still wins).
- **shot/animatic stage-lock**: `director_cli.validate_native_stage_evidence` fail-closes when meaning gate applies.
- Isolation fixtures for other craft gates set `dramatic_meaning_strict: false`.
- Tests: `test_meaning_gate_default_on_every_genre` · director stage meaning lock tests.

## [2.37.5] - 2026-08-04

### Added (Fill-Idle machine queue · H3 next/pk)
- **`scripts/h3_fill_idle.py`**: P0a–P2 challenge queue (restricted primary first; P2 lowest mean); `next_fill_idle_job` + `pk_compare` (never auto-promote).
- **CLI**: `aifilm h3 list --challenge` · `aifilm h3 next` · `aifilm h3 pk-compare`.
- **next_actions**: surfaces `h3 next` Fill-Idle step when hybrid_h3.
- **SKILL.md** under 6k budget (P0 action line compact).
- Tests: `tests/test_h3_fill_idle.py` · `tests/test_fill_idle.py`; h3 list policy assert allows fill_idle suffix.

### Docs
- memory fill-idle checklist machine commands; weapon-lane pointer if needed.

## [2.37.4] - 2026-08-04

### Docs (Fill-Idle · Grok baseline + H3 challenge)
- **weapon-lane-matrix**: Fill-Idle section — P0→P1→P2 queue, energy-slot R2V, shortlist+human promote.
- **hard-defaults** / **AGENTS** 8c / **SKILL** P0 action: pointer to Fill-Idle policy.
- **memory** `2026-08-04-h3-fill-idle-challenge.md`; lesson h3-max-effect append operational table.
- **Agree-all locks**: P2 order = lowest mean first; ship allowed with P2 incomplete (hero challenge not mandatory); no auto cross-episode win-rate.
- No code path change (scheduling CLI E2+ deferred).

## [2.37.3] - 2026-08-04

### Added (H3 max-effect auto mode)
- **`scripts/h3_mode.py`**: `resolve_h3_mode` — explicit → continue I2V → env T2V → dialogue-CU/hard-flag R2V → default I2V (+ R2V alt).
- **`h3 plan` / `h3 list`**: `mode_resolve`, `effect_tips`, `command`/`command_alt`.
- Tests: `tests/test_h3_mode.py`. Docs: weapon-lane / h3-max lesson / hard-defaults.

## [2.37.2] - 2026-08-04

### Added (go4 continue Grok + go5 DP optics)
- **Shared continue handoff:** `scripts/continue_handoff.py` used by H3 + Grok. Write on `media-queue complete` (I2V/R2V), `register-clip`, and H3 run. Read in `plan_h3_shot` + `prompt_injector` I2V (CONTINUE clause; never overwrite approved stills).
- **DP focal inject:** `focal_clause` / extended `camera_clause` maps shot_size → 35/50/85/105mm phrase into motion spine (author `lens_mm` wins).

### Tests
- `tests/test_continue_and_dp_optics.py`

### Docs
- hard-defaults go4/go5 row

## [2.37.1] - 2026-08-04

### Notes
- Version pointer / notes; H3 auto-mode implemented in **2.37.3**.

## [2.37.0] - 2026-08-04

### Added (Throughput + Effect Loop)
- **`aifilm ship-prep --root`**: one-shot ladder means → variety → select-shortlist → i2v-motion-gate → film_core → single `next_cmd`. Receipt: `receipts/ship-prep.json`.
- **Auto mean_absdiff**: `measure_mean_absdiff` + `ensure_take_means` (ffmpeg fps=5 140×248 gray); writes take sidecars; `i2v-motion-gate --root` / collect rows measure missing means.
- **`select-shortlist --promote`**: highest-mean take → `manifest.clips[id]` (takes retained; marks below_floor vs DF floors).
- dispatch / next / advance / autopilot surface `ship-prep` after clips.

### Tests
- `tests/test_ship_prep_throughput.py`

### Docs
- hard-defaults Throughput 2.37 row

## [2.36.4] - 2026-08-04

### Added (Delivery Truth)
- **Zero-narration real gate:** `film_spec.zero_narration_gate` — `dialogue_drama` defaults `zero_narration_strict=true` (budget 0); raises `NAR_BUDGET_VIOLATION` on third-person nar ratio > 0. Schema fields + escape `false` / silent_scene+reason.
- **`assert_i2v_final_gate_for_export`:** `export-desktop` hard-blocks without `receipts/i2v-final-gate.json` ok=true. Escape: `AIFILM_SKIP_I2V_MOTION_GATE=1`.
- **closeout ladder:** `i2v_motion` step always hard; `film_core` hard for max/premium/dramatic_meaning_strict (never swallow exception as ok).
- **agent-review L0:** max/premium no longer provisional-pass missing motion receipt.

### Tests
- `tests/test_zero_narration_gate.py` now calls real `zero_narration_gate` (stand-in removed)
- `skills/ai-film-grok/tests/test_delivery_truth.py`

### Docs
- hard-defaults Delivery Truth + zero-nar true path; 5-Track marked target-arch where CLI not wired

## [2.36.3] - 2026-08-04

### Added (Temple-AV dramatic meaning stack · restore)
- Ship `scripts/dramatic_meaning.py` + wire into `cinematic_audit` / `film_spec` / `preflight` fail-closed production path.
- Tests: `tests/test_dramatic_meaning.py` (shot/motion/dialogue/arc good+bad).
- Schema `dramatic_meaning_strict`; fixtures motion semantics migrated for heat=max.

## [2.36.2] - 2026-08-04

### Added (Motion Core deep integration · Phase C)
- **Continue handoff read path:** `resolve_continue_handoff` + `plan_h3_shot` prefer previous `receipts/continue-handoff/<prev>_end.png` when `chain_mode=continue` or `parent_shot_id` set.
- **Never overwrite approved stills;** optional fill only if `stills/<id>.png` missing and `AIFILM_CONTINUE_COPY_STILL=1`.
- Plan surfaces `still_source` + `continue_handoff` packet for agents.

### Tests
- `ContinueHandoffReadTests` in `test_motion_core_p1.py`

## [2.36.1] - 2026-08-04

### Added (Temple-AV dramatic meaning stack)
- **`scripts/dramatic_meaning.py`**: pure gates for shot world-change, beat-serving motion, dialogue purpose (speaker+text+subtext/emotion), and `director_intent.emotional_arc` stacking (coverage + non-flat).
- Stable codes: `SHOT_MEANING_EMPTY`, `DIALOGUE_PURPOSE_EMPTY` / `DIALOGUE_SPEAKER_MISSING` / `DIALOGUE_TEXT_EMPTY`, `ARC_STACK_FLAT` / `ARC_NODE_ORPHAN` / `ARC_STACK_NO_MAPPING` (+ reuses `MOTION_NO_MEANING` / `BEAT_SEMANTICS_MISS`).
- Production path: `cinematic_audit` (write-spec) always fail-closes; `validate_film_spec` / `preflight` hard when `dramatic_meaning_strict` or `heat_scale=max` / `premium_vertical`.
- Schema flag `dramatic_meaning_strict`; hard-defaults + meaningful-motion lesson pointers.
- Tests: `tests/test_dramatic_meaning.py` (good pass / bad fail for all four outcomes + audit/preflight/API).

### Added (Motion Core deep integration · Phase B)
- **`i2v-motion-gate --root`**: auto-collect rows from film-spec (DF/wardrobe/heat) + takes/audit means; `--rows` optional; `--root` alone writes receipts.
- **Grok spine receipt**: `prompt_injector` I2V writes `receipts/prompts/<id>.grok.spine.txt`.
- **film_core dual spine**: closeout audit accepts `.motion` / `.h3` / `.grok.spine.txt`; missing hero spine → `CORE_SPINE_MISSING`.
- **dispatch / next / autopilot**: surface `i2v-motion-gate` and `film-core-closeout` when clips/final ready.

### Tests
- integrate_a: auto-gate soft DF mean=12; grok spine write; p1 grok-only closeout

## [2.36.0] - 2026-08-04

### Changed (Motion Core deep integration · Phase A)
- **Single tier resolver:** `motion_prompt_spine.motion_tier_resolve` is the only source for `prompt_tier` (soft|medium|high) and `optical_tier` (soft|medium|normal|meat|high). `motion_tier_for` + `i2v_motion_gate.motion_tier_for_shot` both delegate.
- **Grok I2V fail-closed:** `prompt_injector` asserts motion core after assemble (parity with H3 / media-queue). Escape: `AIFILM_SKIP_MOTION_CORE=1`.
- **No silent pass:** media_queue motion enrich + restricted routing re-raise as `QueueError`; H3 `--register` variety no longer swallows exceptions.
- **Audit floors** include soft/medium; CLI help documents DF/wardrobe fields.

### Tests
- `tests/test_motion_core_integrate_a.py` (table-driven tier parity + injector empty core)
- `test_media_queue` pilot unlock isolates variety via escape

### Docs
- hard-defaults Motion Core 整合 A · weapon-lane tier table

## [2.35.2] - 2026-08-04

### Added
- **Motion Core P1 — variety on bulk:** `bulk_preflight` and `h3 run --register` fail-closed on `variety-precheck` (`assert_variety_preflight`). Escape: `AIFILM_SKIP_VARIETY_PREFLIGHT=1`.
- **Motion Core P1 — DF-aware motion gate:** `motion_tier_for_shot` + floors soft≥10 / medium≥16 / normal≥18 / meat·high≥20; act/climax never demoted by soft DF; bare afterglow → medium.
- **Motion Core P2 min:** H3 `_write_continue_handoff` → `receipts/continue-handoff/`; closeout advisory `film_core` via `film_core_closeout_audit` → `receipts/film-core-closeout.json`.

### Tests
- `tests/test_motion_core_p1.py`

### Docs
- hard-defaults Motion Core P1/P2 row + high-motion DF floors

## [2.35.1] - 2026-08-04

### Added
- **Motion Prompt Spine (P0):** shared `scripts/motion_prompt_spine.py` carries film core into Grok + H3 motion — `dramatic_function` → `want_beat` → action → camera → dialogue/foley; `motion_tier` soft/medium/high.
- `build_shot_intent` emits `want_beat`, `motion_tier`, `spoken_text`, `has_action_core`, `action_summary`, `camera_prompt`.
- Fail-closed empty core on `aifilm h3 run` and `media-queue` (`MOTION_CORE_*`); H3 writes `receipts/prompts/<id>.h3.spine.txt`.
- `prompt_injector` I2V injects the same spine clauses (Grok parity).

### Tests
- `tests/test_motion_prompt_spine.py`

### Docs
- hard-defaults · weapon-lane-matrix · stages/visual · SKILL P0 #7 · h3-max-effect lesson

## [2.35.0] - 2026-08-04

### Added
- **Zero-Narration IRON (P0):** `dialogue_drama` now defaults to `zero_narration_strict:true`. Third-person narrator `nar` is hard-capped at 0% of runtime; `write-spec` raises `NAR_BUDGET_VIOLATION` if any narration ratio detected. Replacement paths: ① rewrite inner-monologue as character dialogue/subtext; ② background exposition as prop insert (`dramatic_function: sensory/insert`); ③ atmosphere as Foley SFX events. Escape: `{"silent_scene":true,"narration_reason":"…"}` or spec `zero_narration_strict:false` (reason required). Non-`dialogue_drama` genres retain legacy nar with ≤5% cap.
- **Hollywood DP Optics & Three-Phase Acting (P0):** Shot-size-to-focal-length auto-injection matrix (35mm wide → 50mm medium → 85mm CU → 105mm macro insert). Three-point lighting presets per scene tone (warm/tense/dramatic/afterglow/neutral) with Teal & Orange color grade default. Dialogue shots require three-phase acting prompt coverage: Pre-Speech (0.15–0.25s breath/eye shift) · Spoken Delivery (lip sync + eye contact) · Afterglow Breath (0.35–0.70s expression release). Lines >4.5s auto-split into speaker shot + listener reaction cutaway (DX audio continuous).
- **5-Track Cinematic Audio Master (P0):** Full-film default 5-track mix: DX (dialogue, center, -16 LUFS) · FX (Foley spot effects, L/R panned) · BG (Room Tone ambience bed, continuous, no silence >200ms) · MX (BGM Score, auto sidechain -4dB~-6dB on DX) · SUB (LFE pulse, drama beats only). Final loudness target: -16 LUFS ±1.5dB; peak ≤-1dBTP.

### Docs
- `references/hard-defaults.md`: two new P0 rows — 零旁白 IRON (2026-08-04) and 5-Track 影院级混音 (2026-08-04); header updated with Zero-Narration IRON note.
- `references/directors-lens.md`: narration constraint updated to Zero-Narration Strict; new sections — DP 电影焦段与光影矩阵 and 对白三相表演注入 (P0 · 2026-08-04).
- `references/hollywood-optics-prompts.md` [NEW]: focal length matrix, 3-point lighting matrix, Teal & Orange grade, three-phase acting prompt library, self-check checklist.
- `references/5track-audio-master.md` [NEW]: 5-track definition, mix order CLI, acceptance criteria, pipeline compatibility, zero_narration linkage.
- `SKILL.md`: P0 #18 (零旁白 IRON) and #19 (好莱坞 DP 光影+5-Track 混音) added; deep-dive links updated.

## [2.34.1] - 2026-08-04

### Fixed
- **H3 dialogue inject survives custom prompt files:** `h3_workflow._prompt_for_shot` no longer early-returns from `receipts/prompts/<id>.i2v.txt` without Mandarin inject. New `_merge_prompt_with_audio` appends lip-sync dialogue lines when `audio_cues` present (2026-08-04 stress canary regression).

### Docs
- **H3 max-effect playbook** from 5090 live matrix (quality A/B, high-motion, dialogue, e2e register, 7 framing angles + continuity endframe chain L1≈7.7).
- `references/lessons-2026-08-04-h3-max-effect.md` · `memory/2026-08-04-h3-max-effect.md`
- `references/weapon-lane-matrix.md` expanded: I2V/R2V/T2V selection, framing cheatsheet, free-memory ops, continue SOP
- hard-defaults P0 row · stages/visual · SKILL P0 #7/#8 · AGENTS 8b

### Tests
- `test_h3_prompt_file_still_injects_dialogue` · `test_h3_prompt_file_with_audio_block_still_gets_missing_line`

## [2.34.0] - 2026-08-03

### Added
- **Dialogue-first scene gate (P0):** `dialogue_drama` now rejects any scene with zero `on_camera`/`off_camera` dialogue shots. Scenes that are pure silence, pure `action_cover` coverage, or carry only third-person narrator VO are refused — every scene must put a visible speaking character in frame. Escapes: `scene {"silent_scene": true, "narration_reason": "..."}` for justified bridge gaps, or spec-level `allow_silent_scenes: true`. Spec audit surfaces `scenes_without_dialogue` and `allow_silent_scenes` in `_dialogue_drama`.
- **H3 dialogue-native prompt injection:** `h3_workflow._prompt_for_shot` inspects the shot's `audio_cues`. When a `dialogue` voice cue exists and `screen_mode == "on_camera"`/`"off_camera"`, the MiniMax H3 prompt now hard-injects the spoken Mandarin line with lip-sync priority — every v shot reads as the character actually talking. Non-dialogue shots keep the ambient/foley fallback.
- **Restricted dialogue → H3 lane:** `production_router.build_shot_intent` routes restricted (`heat_phase=act/climax`/`bare`/`undressed`) on-camera dialogue to `local_dialogue_h3` (`minimax-h3-i2v-pilot`; `r2v` when a reference state chain exists) instead of the `cloud_dialogue_ltx` lane, keeping meat+speech on the RTX 5090, `audio_policy=prefer_native`.

### Changed
- **Tool matrix pinned to four providers** — `grok i2v` (safe bulk) · `5090 H3 i2v/r2v` (restricted + restricted dialogue) · `FRW LTX 2.3` (safe dialogue棚) · `Qwen I2I` (state photos). SKILL P0 #7/#8 and `references/weapon-lane-matrix.md` updated to match.
- `SKILL.md` P0 #8 rewritten as **声线·对白优先**: scene-level dialogue hard gate, no narration as primary scene voice, dialogue shot face = speaker, restricted dialogue → H3.

### Docs
- `references/hard-defaults.md`: two new P0 rows — 对白优先·场景级拒旁白 v2.34 and 对白肉戏 → H3 本地对白路径.
- `references/dialogue-first-workflow.md`: scene-level gate summary; new **v2.34 对白车道补充** table.
- `references/weapon-lane-matrix.md`: new 对白优先 preamble; 对白近景 row split into sensitive (LTX) vs restricted (H3) lanes.

### Tests
- `tests/test_dialogue_scene_gate.py` (10 tests): scene gate rejects silence-only / action_cover-only / missing narration_reason; passes with dialogue; escapes via `silent_scene+narration_reason` and `allow_silent_scenes`; H3 prompt injection on / off-camera / r2v; ambient fallback when no dialogue cue.
- `tests/test_dialogue_primary_chain.py::test_dialogue_drama_rejects_storyteller_nar` updated to satisfy the new scene gate before reaching the storyteller rule.
- `tests/test_dialogue_contract.py::test_dialogue_drama_rejects_unbound_or_implicit_voice` updated to isolate the audio_cues check behind a valid scene dialogue gate.

## [2.33.2] - 2026-08-03

### Changed
- **Huangdao v3 caption + meat gates:** ship/PARTIAL path defaults to **PIL pixel hard-burn** captions (ban HF `opacity:0`+GSAP as sole subtitles); acceptance = frame-extract readable Chinese.
- **on_camera speaker = on-screen subject:** forbid climax line on wrong-character meat body.
- **Meat neighbor variety + afterglow:** no same-pose re-read across adjacent meat shots; afterglow must read as couple (ban solo stand-in).
- **Continue promote guard:** smash / cross-space / wardrobe jump must not blind-promote (beach→cave pollution).
- Dual-path captions documented in SKILL P0 #10, hard-defaults, stages post/visual/voice; lesson §G/H/I + memory short card.

### Docs
- `lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md` §G/H/I
- `memory/2026-08-03-huangdao-caption-hardburn-meat-variety.md`
- Agents.md pointer #8

## [2.33.1] - 2026-08-03

### Added
- **Huangdao rhythm/still/voice/silk lesson:** ban character-sheet keyframes, VO-fit dialogue pace, spoken_lang↔cast_voices lock, last-frame chain, HyperFrames silk ship path (PARTIAL).
- `media_qa.lint_still_not_character_sheet` hard-fails path tokens (sheet/turnaround/ortho…); soft multi-cell advisory.
- `register-still --status approved` raises `STILL_LOOKS_LIKE_CHARACTER_SHEET` before I2V.
- hard-defaults + stages visual/voice/post pointers; memory short card.

### Tests
- `tests/test_still_character_sheet_lint.py`

## [2.33.0] - 2026-08-03

### Changed
- **Chinese dialogue primary:** default `dialogue_spoken_lang=zh` (Edge 晓伊/云希); Japanese opt-in.
- **Dialogue primary chain:** default `vo_mode=dialogue_drama`; no third-person storyteller fill; narration gap hard cap 5%.
- **Interactive reverse-shot:** multi-sentence prose → alternating speakers + reverse/OTS reaction coverage.
- **Subtitles:** HyperFrames sole designed caption owner; prefer `caption_text`; plate `subs=off`.

### Tests
- `test_dialogue_primary_chain.py` and related voice/plan updates.

## [2.31.36] - 2026-08-03

### Added
- **Dual-lane weapon matrix (Grok Video 1.5 + 5090 MiniMax H3):** adult/heat-max films auto-enable H3 dual-lane; setup bulk stays Grok; restricted/meat/high-difficulty soft-lock `comfy-h3`.
- `production_router.classify_shot_content` + difficulty flags (`coitus_beat`, L4+contact, `force_local_h3`, …).
- `media-queue` hard-blocks cloud I2V for restricted_local (escape: `AIFILM_ALLOW_CLOUD_RESTRICTED=1`).
- `h3_workflow.ensure_h3_delivery_geometry` upscales H3 deliverables to ≥704×1280 before register.
- Docs: `references/weapon-lane-matrix.md` + visual stage card + hard-defaults pointers.

### Changed
- `shot-intent.schema.json` accepts difficulty/route/still-provider fields.
- Restricted route tests use `comfy-h3` (not retired wan22) under hybrid dual-lane.


## [2.31.35] - 2026-08-03

### Added
- **Wave W8 · autopilot local throughput allowlist:** `LOCAL_THROUGHPUT_NEXT_IDS` contract (closeout-run, bulk-preflight, variety-precheck, pilot-pack, select-shortlist, export-desktop, agent-review-final assist, …).
- Autopilot local path fail-closes when `next_id` is not on `ADVANCE_ACTIONS` (`local_not_allowlisted`).
- Dry-run never shells local advance (plans only).
- Tests: `tests/test_workflow_w8_autopilot.py` (allowlist ∩ advance, --apply reject, dry-run, local execute, human stop).

### Changed
- Local autopilot steps record `next_id` + `w8_throughput` on the receipt for audit.

## [2.31.34] - 2026-08-03

### Changed
- **MiniMax H3 film-lane open (打通):** `minimax-h3-{t2v,i2v,r2v}-pilot` → `status=verified` + `production_promoted=true`.
- Production armory select works without `--allow-experimental` (incl. adult-meat-motion-i2v).
- `aifilm h3 run` defaults to `--stage production`; weapon_router points motion demand to `aifilm h3`.
- **Bulk still requires user pilot approval** (auto_execute stays false for motion).

### Tests
- Armory/weapon_router tests updated for film-lane promotion.

## [2.31.33] - 2026-08-03

### Added
- **打通路径:** `aifilm agent-review-final --apply --reviewer … --user-phrase "可以"` rebuilds L0 assist and runs `review-final --review-file` in one step.
- Phrase gate reuses pilot whitelist (`可以`/`ok`/`做完`/`一路做完`); agent-forged phrases rejected.
- `--dry-run` validates without calling review-final; receipt `agent-review-final-apply.json`.

### Changed
- next/closeout point humans at `--apply` instead of hand-typing 16 score flags.
- Still fail-closed on review-final technical/editorial gates; never silent auto-approve.

## [2.31.32] - 2026-08-03

### Added
- **MiniMax H3 armory admission:** `registry/evidence/h3-canaries/minimax-h3-armory-intake-20260803.json`; T2V/I2V/R2V pilots marked `armory_admitted` (still experimental; not production-promoted); `film_workflow_cli=aifilm h3`; audio `prefer_native`.
- **P1 agent-review-final assist:** `aifilm agent-review-final --root` builds L0 scorecard + dim@sec evidence draft (`receipts/agent-review-final.json`).
- Optional `--reviewer` writes `receipts/final-review-input.assist.json` for one-command `review-final --review-file` (still human-gated).
- dispatch / next_actions / closeout / advance wire the assist step before human `review-final`.
- Tests: `tests/test_comfy_armory.py` armory-admitted H3; `tests/test_agent_review_final.py`.

### Changed
- comfy-weapon-armory docs point film H3 lane to `aifilm h3 plan|run|list`.
- Does **not** auto-approve `review-final` or set `final_complete`; pilot approve / paid spend unchanged; H3 bulk still pilot-gated.

## [2.31.31] - 2026-08-03

### Changed
- **P0 gate automation:** demote local no-spend delivery helpers from `human_required` → `none`:
  - `export-desktop`, `dailies`, skill `export.package`
  - `pilot pack` / `pilot-pack` GO evidence write (approve remains human)
- `advance` allowlists `export-desktop` (no `--force`); export name derived from film title (no `<中文名>` placeholder)
- `review-final` / `pilot approve` / paid+external spend stay human-gated

### Added
- Tests: `tests/test_workflow_p0_gates.py`

## [2.31.30] - 2026-08-03

### Added
- **H3 film workflow CLI**: `aifilm h3 plan|run|list` (plan → 5090 generate → audio decision → queue bookkeeping → register-clip).
- Dispatch / next-actions / visual stage pointers for hybrid_h3 dual-lane production.

### Changed
- H3 **native audio default is `prefer_native`**: keep usable diegetic stereo; strip only when unusable or explicit `strip_native_use_tts_bgm` / `mute_native`.
- H3 prompts ask for natural diegetic ambience/foley instead of silence.
- register-clip marks H3 clips with `use_clip_audio` from policy + QA `has_audio`.

### Tests
- `tests/test_h3_workflow.py` (CLI dispatch, plan/list, audio prefer/keep/strip decisions).

### Verified
- 5090 e2e: `aifilm h3 run` I2V + `prefer_native` → keep_native (mean_volume -19.1 dB, aac stereo), register candidate (`artifacts/…/h3-workflow-e2e/e2e-report.json`).

## [2.31.29] - 2026-08-03

### Added
- MiniMax H3 **R2V pilot verified** on private RTX 5090 (`minimax-h3-r2v-pilot` real_pilot + output hash).
- Canary under `skills/ai-film-grok/artifacts/5090-evaluation/minimax-h3-canary/` (352x608, ~5.2s, h264+aac).

## [2.31.28] - 2026-08-03

### Added
- Dual-lane **hybrid_h3** profile + MiniMax H3 local motion routing (restricted soft-lock, film-scoped).

### Fixed
- `runtime_policy` now resolves the skill's pinned runtime Python (via `runtime-python` script) instead of using `sys.executable` / `platform.python_version()` which reflected the host agent's Python, not the skill's. Fixes doctor `runtime_lock` false drift when run from inside Hermes.


## [2.31.27] - 2026-08-03

### Added
- **Dual-lane hybrid_h3 config**: `AIFILM_I2V_PROFILE=hybrid_h3` keeps Grok bulk auto while restricted/meat soft-locks to local MiniMax H3 (`comfy-h3`).
- Film-spec `h3` + `motion_lanes` defaults; shot-intent recommendations (`recommended_lane/provider/weapon`, H3 audio/duration).
- Example: `templates/film-spec.hybrid-h3.example.json`.
- Tests: `tests/test_hybrid_h3_lanes.py`.

### Changed
- Hybrid firepower docs + hard-defaults + weapon-lane matrix: Wan local → MiniMax H3.
- Shot-intent schema allows H3 routing fields and audio policies.

## [2.31.26] - 2026-08-03

### Added
- **Wave H:** green `bulk-preflight` receipt reuse when film-spec is not newer (faster multi-add enqueue).
- dispatch/next inject `select-shortlist` after clips when `takes/` has media; advance allowlist entry.
- Tests: `tests/test_workflow_wave_h.py`.

## [2.31.25] - 2026-08-03

### Added
- **Local MiniMax H3 (ComfyUI native) pilot lane** on the private RTX 5090:
  - Armory weapons: `minimax-h3-t2v-pilot`, `minimax-h3-i2v-pilot`, `minimax-h3-r2v-pilot`
  - API templates under `templates/comfy/minimax-h3-*-api.json`
  - Provider `comfy-h3` with endpoints `local_minimax_h3_{t2v,i2v,r2v}`
  - Weapon router maps unlocked motion demand to H3 experimental (pilot-gated, no silent bulk)
- Real T2V/I2V canaries under `artifacts/5090-evaluation/minimax-h3-canary/`
- Tests: armory H3 routing, weapon_router, provider registration

### Changed
- Local Wan 2.2 I2V stays retired; H3 is a new local path, not a Wan un-retire
- Comfy ops: default AIFILM_COMFY_DRIVER_VRAM_FALLBACK=0 so capacity uses ComfyUI metrics when SSH nvidia-smi probe is not fully wired
- Docs: comfy-weapon-armory + hard-defaults H3 pointers

## [2.31.24] - 2026-08-03

### Changed
- **Wave G bulk door hard by default:** after user pilot approval, `media-queue add` requires bulk-preflight ok (tunnel/lease not required at enqueue). Escape: `AIFILM_SKIP_BULK_PREFLIGHT=1` or `--allow-without-pilot`. Canary jobs skip. Force always: `--require-preflight`.

## [2.31.23] - 2026-08-03

### Added
- **Wave F agent-loop glue:** dispatch injects `variety-precheck` (design) and `bulk-preflight` (post-pilot bulk); `next_actions` surfaces bulk-preflight before queue.
- `advance` allowlist: `closeout-run`, `bulk-preflight`, `variety-precheck`, `pilot-pack` (local, approval none).
- closeout / pilot-pack / throughput CLIs marked local+none for advance (review-final still human).
- Tests: `tests/test_workflow_wave_f.py`.
- `runtime_policy.verify_runtime_lock` compares skill `runtime-python` version (not host agent).



## [2.31.22] - 2026-08-03

### Added
- **Workflow Wave D (final engineering):**
  - Plate timeout floors: short **1200s**; longform / ≥480s picture **1800s** (`estimate_plate_timeout`).
  - Timeout error on `aifilm final` now points to larger `--plate-timeout` or direct `render_final.py` + `AIFILM_FFMPEG_TIMEOUT`.
  - Sidechain mix failure/timeout → **simple amix fallback** with `receipts/final-mix-partial.json` (PARTIAL, not silent).
  - `stable_path_for_ffmpeg_filter`: mirror SRT to `/tmp` when film path has spaces; PIL caption burn uses it.
- Tests: `tests/test_final_wave_d.py`; longform timeout floor cases.
- stages/post + longform-workflow timeout / PARTIAL notes.
- Genre beat spines: `select_beat_spine` auto-discovers via `spine_exists` (not only GENRE_NAMES).
- Pre-plan structural keys (`story` / `episodes` / `story_resolution`) before writing drama-graph.
- `runtime_policy` resolves package/Python versions from skill `runtime-python` (not host agent interpreter).

## [2.31.21] - 2026-08-03

### Added
- **Workflow Wave B–C** (`workflow_pack` + `cli_workflow`):
  - `aifilm bulk-preflight` — single-door bulk readiness (pilot/heat/state/still/anatomy/tunnel/lease); optional `media-queue add --require-preflight` / `AIFILM_REQUIRE_BULK_PREFLIGHT=1`.
  - `aifilm variety-precheck` — design-time anti-boring matrix → `receipts/variety-precheck.json` + `variety-matrix.md`.
  - `aifilm select-shortlist` — multi-take preferred shortlist (advisory; never deletes takes).
  - `aifilm gpu-lease status|acquire|heartbeat|release` — 5090 one-owner lease (`~/.grok/run/gpu-lease.json`).
  - `aifilm tunnel-probe` — `18188/system_stats` Comfy JSON; `TUNNEL_WRONG_PORT` on 401/unauthorized.
  - `aifilm queue-progress` — honest progress = non-empty takes/clips only.
- `doctor` advisory field `comfy_tunnel` (does not fail core).
- `dispatch`: plate present → prefer `closeout-run`; skill maps for bulk-preflight / pilot-pack / variety.
- Tests: `tests/test_workflow_pack.py` (18 cases with Wave A).

### Changed
- SKILL commands list + stages/visual · stages/deliver pointers for new throughput cmds (SKILL ≤6kB).
- **Single closeout CLI path:** `aifilm closeout status|run` owns `closeout.py` receipts; `workflow_pack` re-exports without dual subparser registration. `pilot pack` primary; `pilot-pack` alias.

### Fixed
- Conflicting `closeout` argparse registration (`aifilm_grok` + `cli_workflow`) that blocked help/smoke.

## [2.31.20] - 2026-08-03

### Added
- **Workflow Wave A:** `aifilm closeout status|run` — heat → human review-final gate → post-audit → optional export next_cmd; receipt `receipts/closeout.json`.
- **`aifilm pilot pack`** — one-screen pilot GO pack (`receipts/pilot-go.json`: three-beat, media, score, heat, state-index, GO template).
- When `pilot-go.json` exists with `ok=false`, bulk `media-queue add` fails closed (`assert_pilot_go_allows_bulk`).
- `next_actions`: prefer `closeout-run` when a final/plate exists; surface `pilot-pack` in pilot window.
- Tests: `tests/test_workflow_wave_a.py`.


## [2.31.19] - 2026-08-03

### Changed
- **Optimization loop wired end-to-end:** `make check-all` / `make test-fast` / `make release-light` / `make lock-runtime` documented in Makefile + AGENTS.
- `util.require_json` strict read; soft `read_json` / atomic `write_json` remain the package API. Hot paths (`aifilm_grok`, `render_final`, `compose_render`, `export_composition`) delegate instead of local copies.
- `util.json_io` is a legacy strict facade over `require_json`/`write_json`.

### Added
- `tests/test_util_json_contract.py` locks soft vs strict JSON behavior.


## [2.31.18] - 2026-08-03

### Changed
- **pre-push light gate (default):** docs currency + doctor core only; full pytest suite no longer blocks every push.
- `AIFILM_RELEASE_GATE=full git push` or `python3 scripts/release_gate.py --mode full` keeps the previous heavy gate.
- Gate receipts are mode-aware (full satisfies light; light does not satisfy full).

### Fixed
- pre-push pins `core.fsmonitor=false` so gitea-publish secret scan is not blocked by local fsmonitor config.


## [2.31.17] - 2026-08-03

### Changed
- **Repo slim P4b:** untrack 27 canary media blobs under `artifacts/` (mp4/png/jpg/mp3); keep JSON/workflow/receipts tracked. Local media files remain on disk.
- Root `.gitignore` ignores `artifacts/**/*.{mp4,png,jpg,...}` so canary binaries do not re-enter the index.

### Docs
- Mark `docs/reports/2026-08-03-artifacts-inventory.md` as executed (untrack done).


## [2.31.16] - 2026-08-03

### Changed
- **Process slim Phase 2:** document single-truth layering (hard-defaults → stages → memory → lessons); voice pipeline context no longer requires full ep2 lesson.
- Slim plugin `AGENTS.md` hard-rules to pointers; global Agents film IRON → one-line pointers (host file; backup under `~/.grok/backups/*process-slim`).
- SKILL / INDEX / craft-spine / generative-film-craft: clarify 7-step user progress vs internal stages.

### Added
- `memory/README.md` short-card contract; process-slim plan session result; `docs/reports/2026-08-03-artifacts-inventory.md` (list-only).


## [2.31.15] - 2026-08-03

### Fixed
- **HEAD import break:** `story_plan` imported `story_contract.draft_story_contract` but the function was not yet in-tree — land full `draft_story_contract` + `_draft_story_contract` alias.
- Complete WIP from 2.31.13 notes that never made the prior commit: I2V default **`grok_primary`**, `final_stages` → `util.write_json`, story re-export contract tests.

### Changed
- I2V operating default: `film_spec` / `i2v_provider` / `capability_report` / `config_loader` / docs → grok-first (dialogue still FRW LTX when locked).
- Refresh `runtime-lock.json` after landing scripts.

### Added
- Contract tests: re-export identity (`story_plan` ↔ `beat_extraction` / `story_contract`) and seed override for draft contracts.
- Plans: ROI session closeout; `docs/plans/2026-08-03-process-slim-phase2.md` (proposed process slim).

## [2.31.14] - 2026-08-03

### Changed
- Extracted `plan_shots` + shot-planning helpers (`_camera_axis`, `_vertical_composition`, `_motion_text`, `_production_mode`, `_clip_nar`, `_duration_for_nar`) into `shot_planning.py`; `story_plan.py` imports from it.
- `DRAMATIC_FUNCS` now lives in `shot_planning.py` (re-exported via import).

### Fixed
- Fixed broken imports in `shot_planning.py` (was referencing non-existent `dialogue_screenplay` functions).
- Fixed zcode test assertions in `test_shot_planning.py` (`_camera_axis` idx math, `plan_shots` count for `shots_n=1`).
- Restored `grok` CLI symlink (was broken `/var/folders/…/grok-wrap-…` → `~/.grok/bin/grok`).


## [2.31.13] - 2026-08-03

### Changed
- I2V 默认运营 profile 从 `ltx23_primary` 切换到 `grok_primary`：bulk 动作主链 Grok `image_to_video`；对白讲话镜仍锁 FRW LTX 2.3 原生有声。
- `film_spec.resolve_i2v_profile()` / `default_i2v_provider()`、`i2v_provider.preferred()`、`capability_report` 默认/回退改为 grok-first；`ltx23_primary` 仅显式 opt-in。
- README / SKILL / hard-defaults / config.env.example 同步 grok-first 文档与默认值。
- **ROI 优化 · story 单一真相**：`story_plan` 删除与 `beat_extraction` 重复的 spine/extract/rebalance 实现，改为 re-export；`draft_story_contract` 收口到 `story_contract`（`story_plan` / `story_normalize` 薄别名）。
- `final_stages` 写 JSON 直接走 `util.write_json`（去掉薄包装）。
- 刷新 `runtime-lock.json` 脚本指纹（doctor `core_readiness` 绿）。

### Added
- `story_plan` 重新导出 `DRAMATIC_FUNCS`（自 `shot_planning`）恢复向后兼容 public API。
- `story_contract.draft_story_contract` 正式 API + 契约单测（re-export 同一性、seed 覆盖）。
- `test_shot_planning.py`：shot_planning 模块单测（相机轴 anti-boring 与实现一致）。

### Fixed
- `test_genre_beat_spines` 收集错误：`DRAMATIC_FUNCS` 迁移到 `shot_planning` 后补回 `story_plan` re-export。
- `test_shot_planning` 相机轴断言与 `idx % 3 == 1 → ecu_hold` 实现不一致导致的假红。

## [2.31.12] - 2026-08-03

### Changed
- Unified plain `logger.log` shim (stderr line, not JSON); structured logging stays on `get_logger`.
- `compose_render` / `compose_preview` / `render_final` / `aifilm_grok` now import shared `log` instead of local print copies.
- `final_stages` JSON I/O delegates to `util.write_json` / `util.read_json` (atomic writes).

### Added
- `plan_feedback` pattern helpers (shot-count / weight suggestions) + unit tests.
- Logger plain-compat tests.

### Fixed
- Pruned 13 prunable temporary git worktrees left from release/agent checkouts.


## [2.31.11] - 2026-08-03

### Added
- Final hot-path contract tests (`test_final_hotpath_contracts.py`): stages receipt plate `subs off` + HyperFrames ownership wording; HF caption gate fails closed when pixel probe is hard-false; heat final/media gates fail closed if `heat_check` cannot import; double-burn underlay plate guard on the fast path.

### Changed
- CHANGELOG backfill for the gap after 2.25.0: rollups for 2.25.1–2.25.6, 2.26.2, 2.27.0, 2.28.x (no pin), 2.29.0, 2.30.0, and 2.31.0–2.31.9.


## [2.31.10] - 2026-08-03

### Fixed
- Restored a clean `aifilm` runtime for package/version probes: strip host-agent `PYTHONPATH` in the launcher, Makefile, and check-all; query lock packages via a clean subprocess so Hermes/venv contamination cannot fail doctor.
- Recovered `story_plan` after a bad partial extraction: re-exported `DRAMATIC_FUNCS`, restored `AUTHORING_PLACEHOLDER=needs_authoring`, and kept `select_beat_spine` as a thin delegate to `beat_extraction` (single spine source of truth).
- Rebuilt `runtime-lock.json` fingerprints after script repairs.

### Added
- ROI optimization plan: `docs/plans/2026-08-03-roi-optimization-plan.md`.
- Unit coverage for story contract / quality / beat-spine / plan feedback (prior commits in this train).

### Changed
- Pinned skill requirements to the verified clean runtime: edge-tts==7.2.8, jsonschema==4.23.0 (with numpy/Pillow unchanged).


## [2.25.1–2.25.6] - 2026-07-30

_Rollup of patch releases after 2.25.0 (see git history for per-patch subjects)._

### Added

- Guarded offline Kokoro TTS route; InfiniteTalk pilot duration defaults.
- Expanded guarded audio/FRW controls and verified dialogue audio workflows.

### Changed

- Dialogue production evidence gates tightened across 2.25.x patches.

### Fixed

- Private semantic retrieval hardening.

## [2.26.2] - 2026-07-31

### Added

- Cinematic evidence requirements threaded through production gates.

### Changed

- Production paths fail closed when cinematic proof is missing.

## [2.27.0] - 2026-07-31

### Changed

- LTX native-audio I2V becomes the dialogue-primary motion route.

## [2.28.x] - 2026-07-31

_No distinct `plugin.json` pin found between 2.27 and 2.29 in this repo history._

## [2.29.0] - 2026-07-31

### Added

- Hardened cinematic audit controls and audio production guardrails.

## [2.30.0] - 2026-07-31

### Added

- Gated I2V provider chain with canary-bound routing (LTX/FRW/Grok lanes).

## [2.31.0–2.31.9] - 2026-08-03

_Summary of 2.31 train before 2.31.10 (detailed entry above). Missing intermediate patch numbers had no separate plugin.json pin._

### Added

- Production optimization + interactive production controls.
- Canonical delivery-contract hardening and HyperFrames caption ownership enforcement.
- Beat-spine system with genre JSON spines, story contract/quality, and plan feedback.
- Devops check-all target; story-plan unit tests and recovery after partial extraction damage.

### Changed

- Consolidated 2026-07-29 poison-shot / Comfy GPU / lipsync lessons into hard-defaults.

### Fixed

- Dialogue screenplay NameErrors and speaker-language P0 validation.
- Delivery-gate tests aligned to production chain contracts.
- Provider canary receipts for frw-api-i2v / frw-ltx23.


All notable changes to **ai-film-grok** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/) · versioning: [SemVer](https://semver.org/) (mirrors `plugin.json`).

## [2.25.0] - 2026-07-30

### Added

- Added a director-controlled ambience stem: formal ambience cues now render independently from scene effects and can be muted or gain-adjusted at final mix.
- Made `--export-stems` export narration, BGM, native, SFX, scene-sound, and ambience WAV stems with SHA-256 evidence in `mix_report.json`.

## [2.22.0] - 2026-07-29

### Added

- Added material-aware scene-sound defaults with explicit surface and environment evidence.
- Added the approval-gated ACE music editor, audio armory, exact-duration edits, motif development, and transition bridges.
- Added a local ComfyUI broker with bounded queue admission, ownership receipts, and fail-closed VRAM checks.

### Changed

- Final music rendering now requires approved edits or bridges instead of generating unreviewed replacements during delivery.

## [2.17.1] - 2026-07-29

### Added

- Added a hash-bound FantasyTalking pilot tuning control that permits only 6, 12, or 30 sampling steps; each choice remains experimental, pilot-only, and subject to human review.

### Fixed

- Refused unregistered FantasyTalking step counts before ComfyUI submission and preserved the production and template-mutation gates for every allowed step setting.

## [2.17.0] - 2026-07-29

### Added

- Added a private Stable Audio Open 1.0 ambience adapter and audio-node capability that remains candidate-only pending human and license review.
- Bound Stable Audio readiness to a local checkpoint SHA-256, adapter SHA-256, exact model identity, exact license, and cached executable probe instead of trusting arbitrary provenance text.

### Fixed

- Bounded RTX lip-sync health probes to 30 seconds while retaining enough time for a cold Windows/WSL fingerprint check.
- Rejected audio-node redirects, public/link-local targets, pre-auth body parsing, and pending ambience candidates entering formal timelines or stems.
- Preserved nested production-book department paths when migrating revision-zero projects and when running director checks.

## [2.16.0] - 2026-07-29

### Added

- Added pilot-only InfiniteTalk and FantasyTalking armory routes with versioned API workflows, exact model hashes, typed image/audio bindings, and evidence-bound source endpoints.
- Added registered custom-node validation: only the exact template node set and exact WanVideoWrapper/VideoHelperSuite module identities may execute.

### Fixed

- Added `local_wan22_i2v`, `local_infinite_talk`, and `local_fantasy_talking` to the explicit video registration contract.
- Comfy armory preparation and execution now preserve experimental, pilot-only, and human-approval gates instead of requiring the broad unknown-node bypass.

## [2.15.0] - 2026-07-28

### Added

- Added an authenticated MMAudio SFX canary with bounded video upload, pinned offline adapter provenance, hash-bound receipts, and pending-only human review.

### Security

- MMAudio checkpoints are restricted to explicit non-commercial research use; missing license acknowledgement, model fingerprint, clean commit, or offline weights fails closed.
- Formal audio timelines and scene-sound stems reject pending or CC BY-NC MMAudio candidates, and the adapter verifies the clean repository plus all required weight hashes.

## [2.14.4] - 2026-07-28

### Added

- Added `aifilm route plan`: explicit local, hash-bound planned receipts derived from a viable route; it never authorizes, queues, or submits media work.

## [2.14.3] - 2026-07-28

### Added

- Added `aifilm comfy capacity`, a bounded read-only admission report for the private RTX 5090 node.

### Fixed

- ComfyUI submissions now fail closed unless the queue is idle with at least 12 GiB free system memory and 24 GiB free GPU memory; missing resource telemetry also blocks submission.

## [2.14.2] - 2026-07-28

### Added

- Added fail-closed `aifilm route explain` for deterministic, read-only shot routing from versioned shot-intent, capability-snapshot, route-plan, and execution-plan contracts.

## [2.14.0] - 2026-07-28

### Added

- Added an authenticated, single-GPU Windows/WSL lip-sync node with measured LatentSync 1.6 provenance, atomic artifacts, bounded uploads, and hash-bound receipts.
- Added `aifilm lipsync-node health` plus remote LatentSync/MuseTalk routing for canary and final rendering.
- Bounded `bgm-library canary` generation for one configurable 10–600 second ACE-Step batch, with pending-only status and checksum, fingerprint, duration, and technical acceptance checks.
- Acceptance coverage for ten-cue within-film diversity, six-film rotation, and cropped or requantized near-duplicate rejection.

### Security

- Restricted plaintext node traffic to loopback through an SSH tunnel, rejected redirects, authenticated before multipart parsing, and fail-closed on input, backend, or receipt mismatch.

### Fixed

- Empty BGM libraries now expose a stable catalog checksum, and duplicate audio/fingerprints are rejected before a batch mutates the catalog.

## [2.13.0] - 2026-07-28

### Added

- Distilled the Professional Director 11-stage order into the single `/ai-film-grok` workflow, with new projects defaulting to professional control and legacy roots remaining compatible.
- Added a compact/full shared workflow status that projects existing narrative, pilot, clip, selects, rough-cut, post, review, and delivery evidence onto the internal director spine.
- Added `director lock-stage`, which records explicit human approval and hash-locks auto-resolved native evidence before advancing the professional stage.

### Fixed

- Deferred scene-sound work until its production stage so it cannot preempt story/spec routing.
- Replaced invalid generated `mimo` final commands with the supported bilingual Edge route.

## [2.12.0] - 2026-07-28

### Added

- Approval-gated shared ACE-Step BGM catalog, batch generation, local review packs, series motif lineage, duplicate clustering, and deterministic anti-repeat selection.
- `aifilm bgm-library` doctor, status, audit, generate, review, approval, planning, selection, and series-pack commands.
- `approved_library` final routing with fail-closed gap queues, catalog-bound mix receipts, and post-render usage accounting.

## [2.11.0] - 2026-07-28

### Added

- Explicit private-LAN `comfy-wan22` provider and `aifilm comfy` control plane for bounded inventory, input upload, typed workflow overrides, API-format submission, WebSocket/History completion, artifact download, targeted cancellation and memory release.
- Local-only workflow validation blocks ComfyUI external API nodes unless the submitted workflow receives an explicit approval flag.
- RTX 5090 capability reports bind installed Wan 2.2 model pairs, device VRAM and local output checksums without changing the `grok_primary` default.

## [2.8.0] - 2026-07-27

### Added

- Hash-bound `shot-quality-evidence` receipts join media decode/motion QA, human review, and clip uniqueness so replaced media cannot inherit approval.
- Queue-backed motion evidence, continuity-aware review packets, `aifilm quality-status`, and quality-closure blocking for missing per-shot evidence.

### Changed

- Release audit inventory now uses the same recursive shipped-surface definition as generated documentation; `make test` includes plugin-level contracts.

## [2.7.10] — 2026-07-27

### Added

- Character and pair motifs now carry instrumental palettes across the music timeline; procedural rendering makes every exported palette audibly distinct while keeping the motif and language tracks stable.

## [2.7.9] — 2026-07-27

### Fixed

- Pre-push rechecks the clean Git HEAD after the full release suite, so a commit or tracked edit made during validation cannot receive a stale success receipt.

## [2.7.8] — 2026-07-27

### Added

- Workshop packets now bind graph projections to a validated canonical packet, departments can prove immutable upstream handoff readiness, and dispatch packets retain accountable ownership.
- Music cues now carry semantic motifs, tempo, key, takes, transitions, and optional per-shot local-template routing into final render behavior.
- Review queues expose a bounded, schema-checked recent decision trail for the local approval UI.

## [2.7.7] — 2026-07-27

### Fixed

- Pre-push now fails closed on tracked worktree edits and reuses a local success receipt only for the exact clean Git HEAD, avoiding redundant full release checks during concurrent pushes.

## [2.7.6] — 2026-07-27

### Added

- Show packages select a validated deterministic motion preset for branded HyperFrames opening and ending cards.
- Audible native I2V stems receive a bounded per-shot gain plan before the final mix.
- The local review UI reports action success and failure through an accessible non-blocking status region.

## [2.7.5] — 2026-07-27

### Fixed

- Pre-push release checks now resolve their advisory lock through Git, so linked worktrees retain the same serialized release boundary.

## [2.7.4] — 2026-07-27

### Added — creative review and guarded delivery

- A local creative workshop compiles revision- and hash-bound briefs, diagnostics, shot decisions, and provider-neutral export packages without invoking paid providers.
- Review controls require explicit human approval and preserve native character dialogue, narration, music, and effects as separate delivery evidence.
- Final delivery resolves the reviewed artifact from its manifest path and SHA-256 instead of assuming a fixed filename.

### Fixed

- Post-audit is now a required, freshness-bound stage before Desktop export.
- The pre-push release gate serializes expensive checks and rejects stale generated project documentation.

## [2.7.2] — 2026-07-27

### Fixed — release evidence and shipped-surface verification

- Release baselines now require a clean working tree and bind plugin version, source fingerprint, and exact Git HEAD.
- CI collects the main skill tests, the shipped `ai-film-project` validator tests, and root-level plugin contracts.
- Generated status inventory covers every shipped skill instead of only the main skill directory.
- Current documentation consistently describes the eleven-dimension review gate and `grok_primary` I2V default.

## [2.6.0] — 2026-07-24

### Added — Adult max IRON（肉戏/脱衣/露点铁律）

- **肉戏时长硬底 50%**（`DEFAULT_SEX_DURATION_FLOOR=0.50`；hardcore 0.55）；亲密核 ≥60%、setup ≤20%（`heat_arc_strict`）。
- **能脱就脱 / 能露就露**：write-spec `apply_wardrobe_continuity` phase floor（act≥undressed、climax=bare）；新码 `HEAT_BARE_PEAK_MISSING`。
- **max 默认 spice=extreme**；plan 投影 `sex_min_duration_ratio=0.50` + `heat_arc_strict`。
- **持续挑战尺度最大**：`lint_heat_escalation_challenge` — phase 只升不降至 climax；禁 act 后 setup / 早 afterglow；禁 foreplay 长平台；必 climax 峰值。码 `HEAT_ESCALATION_*`；`challenge_max_scale` 默认 true。
- **prompt** Adult max IRON + continuous challenge 行；课 `lessons-2026-07-24-adult-max-iron.md`；测试 `test_adult_max_iron.py`。
- 逃生阀：显式 soft / `adult_max_iron:false` / `sex_*_strict:false`。

## [2.5.1] — 2026-07-24

### Fixed — ep2 声线分轨 + final SRT（P0 写回插件）

- **口白中文 / 角色日文 / 禁乒乓**：`is_character_speech_shot` 在显式 `storyteller|narrator` 时忽略残留 `nar_ja`，避免说书镜误跳日文。
- **SRT 硬失败**：`sub_lead` 默认改为 `0`；`build_subtitle_cues_for_shots` + `write_srt` 写盘前非重叠钳制。
- **阶段卡 / 路由 / 索引**：`stages/voice.md` · `stages/post.md` · `context-routing.json`（voice/rough/sound.design）· `INDEX.md` · `hard-defaults` · `SKILL.md` P0#8 · 全局 `Agents.md`。
- **课**：`references/lessons-2026-07-24-ep2-voice-heat-final.md` · `memory/2026-07-24-*`。

### Changed — Compact orchestration and bounded context

- `aifilm dispatch` now prints a compact, versioned packet by default while preserving the complete audit packet in `receipts/dispatch.json`; `--full`, `--format full`, and `AIFILM_DISPATCH_FORMAT=full` retain the legacy output contract.
- Dispatch separates state collection, full receipt construction, and compact presentation. State-hash and capability caches avoid unchanged recomputation while paid, external, and human-gated actions still force a live capability probe.
- Machine-readable context routing limits ordinary turns to three targeted stage or issue references, and the entry `SKILL.md` is reduced to the execution spine and P0 safety kernel.
- Orchestration bytes, estimated tokens, latency, cache state, and reference counts are recorded separately from provider generation usage and cost.

### Added

- `aifilm advance --root <film> --max-local <n>` safely advances only closed-allowlist local actions with state/transaction binding, fixed argument grammars, verification, and immediate stops at paid, external, pilot, human, duplicate, stale, or failed boundaries.
- Compact/full compatibility, cache invalidation, routing bounds, metrics separation, and safe-advance regression tests.

## [1.28.0] — 2026-07-24

### Added — Exact-first media generation usage accounting

- `aifilm usage status|list|summary|record` reports every T2I, image-edit, I2V/T2V and TTS request from the per-film `receipts/generation-usage.json` ledger.
- xAI OAuth image/video responses retain normalized token counters and exact `usage.cost_in_usd_ticks`; async video submit/poll shares one generation id while real retries remain separate requests.
- Native Grok Build calls can be recorded idempotently by provider request id or output hash. Missing provider usage remains explicitly `unknown` and is never inferred from quota deltas.
- Edge/Voicebox TTS records known local-zero cost; external backends without authoritative usage remain unknown. Dispatch and media-queue metrics expose actual request counts separately from planned budget units.

## [1.26.0] — 2026-07-24

### Added — Evidence-bound premium quality closure

- `aifilm quality-closure package|review|report` creates a no-spend, versioned premium benchmark package; records two independent blind reviews; and distinguishes contract, local-render, real-provider and human-review evidence.
- The report never upgrades contract-only evidence to an artistic-quality claim. Real provider media, current Master QC, delivery package, and two independent reviews remain required.
- Dailies now retain provider/model/cost, source keyframe, objective QA, director score, issue tags, reshoot decision, and selection rationale for each candidate.
- `aifilm next` returns only the highest-priority, receipt-backed repair when an independent review exposes a quality failure.
- Runtime locks now discover every shipped script/module; CI publishes a coverage JSON artifact as a non-blocking trend input.
- P2 boundary extraction: `dialogue_contracts.py` is now the shared pure aggregation used by both `film_spec` and `preflight`; `render_workspace.py` owns final-render path validation and its isolated work directory lifecycle.

## [1.25.0] — 2026-07-23

### Added — Gates & test hardening (audit P1)

- **CI `aifilm doctor` gate**: validate-core job now runs doctor and asserts schema + requirements.lock + script fingerprint integrity (version drift tolerated on CI, script fingerprint drift fails the build).
- **CI schema/commands coverage**: plugin validate now checks all `schemas/*.json` (was 2) and asserts `commands/*.md` launchers reference aifilm dispatch.
- **`tests/test_hard_defaults.py`**: contract-level regression locking the machine-readable rules in `hard-defaults.md` — sex-duration floor 0.30, wardrobe rank monotonicity (no re-dress), 11-dimension scorecard, keyframe 720×1280 9:16, pilot-gate default strict. 11 assertions.
- **`tests/conftest.py`**: shared pytest config auto-injects `scripts/` on sys.path + `film_root` fixture; new tests no longer need the boilerplate.

### Fixed — Architecture debt (audit P2/P3)

- **Broke util↔aifilm_grok circular import**: `FilmError` extracted to dependency-free `util/errors.py`; `util/json_io.py` + `util/validators.py` now top-level import (was 5 lazy `from aifilm_grok import FilmError`); `aifilm_grok.py` re-exports for backward compat. 65 lazy imports no longer needed for cycle avoidance.
- **sound_plan events enum synced**: `SPOT_EVENT_TYPES` expanded to match schema (added music_in/music_out/fade_in/fade_out); was stale at 3 values while schema had 7.
- **FRW host single source of truth**: `frw_lipsync.py` + `env_plate.py` now import `DEFAULT_HOST` from `frw_canary.py` (was 3× hardcoded duplicate).
- **config.env.example**: added 13 missing keys the code actually reads (FRW_API_KEY, FRWCLAW_ROOT, COSYVOICE_*, AIFILM_MUSIC_*, OPENAI_BASE_URL, XAI_BASE_URL, XAI_MODEL, AIFILM_SKIP_PILOT_GATE, SKIP_LOOP_RISK_GATE, AIFILM_STRICT_TTS_REHEARSAL); marked AIFILM_TTS_CMD/AIFILM_LIPSYNC_CMD as DEPRECATED (disabled, unsafe shell).
- **templates/film-spec.example.json**: added `grade` + `color_grade_strict` + `sound_plan.music_spotting` + `sound_plan.audio_tracks` + music_in/out events examples to match v1.22 schema.
- **lessons promotion labels**: 3 same-named lessons (character-stance/editorial-craft/directors-lens) now carry explicit "已晋升" headers pointing to their stable reference.
- **Deleted `grok_oauth.py.bak-pre-sdk-pack-*`** dead file (git retains history).

## [1.24.1] — 2026-07-23

### Added — Director methodology P3 close-out (release hygiene)

- **Scorecard 7→11 dimensions doc-sync**: `director_review.py` already enforced 11 dimensions (rhythm/emotion/theme/performance added to `--approve`), but all docs still said "seven dimensions". Aligned SKILL.md, README.md, and 12 reference files (principles, craft-spine, post-compose, grok-build-sdk, pipeline-methodology, director-self-scorecard, postproduction, auto-dispatch) + scripts (next_actions, craft_spine) to "eleven dimensions"; added the 4 new `--score-*` flags to the SKILL.md `review-final` example.
- **director-methodology.md registered**: the methodology master file existed but was unreachable from the spine/INDEX. Now listed in `references/INDEX.md` (professional-director section) and the SKILL.md on-demand-load table; file count 91→92.
- **Tests synced to 11 dimensions**: `test_delivery_gates.py` screening evidence + score flags expanded 7→11; added sidecar SRT to satisfy the `expect_subtitles` delivery quality gate. All delivery-gate slow tests green.

### Lessons written
- `lessons-2026-07-23-style-lock-from-ref.md` (full P0)
- `lessons-2026-07-23-face-identity-pixel.md` (full P0)
- `lessons-2026-07-23-photoreal-vs-manhua-stability.md` (medium routing)
- INDEX / SKILL / director-methodology cross-links

### Fixed — code hygiene
- ruff: removed unused imports (`math` in face_identity, `re` in style_lock); fixed f-string-without-placeholder; replaced dead `or True` / `False if strict else True` with `True` / `not strict`; `try/except:pass` → `contextlib.suppress` in render_final.
- runtime-lock.json regenerated after script fingerprint drift.

## [1.24.0] — 2026-07-23

### Pixel face-identity
- `scripts/face_identity.py`: aHash+dHash+hist on blurred face-region; multi-anchor enroll
- CLI `aifilm face-identity enroll|enroll-bible|verify|audit|status` → `receipts/face-identity.json`
- `lock-style --cast-master` auto-enrolls; `register-still --require-face-identity` optional hard gate
- `post_audit` uses real receipt (FACE_IDENTITY_DRIFT when not verified)
- tests/test_face_identity.py

## [1.23.0] — 2026-07-23

### Style lock from input ref (P0 stability)
- New `scripts/style_lock.py`: medium presets (anime/manhua/semi_real/photoreal), cast_locks, agent still/I2V prefixes
- CLI `aifilm style-lock plan|apply|check|prompt|recommend`
- `lock-style` gains `--medium` `--char-id` `--from-plan` `--strict-style-lock`
- `prompt_injector` emits MEDIUM LOCK from style_fingerprint
- Docs: lessons-2026-07-23-style-lock-from-ref.md + consistency §1a + SKILL open-film flow

## [1.22.0] — 2026-07-23

### Added — Director methodology injection (P3-1~P3-5: color grading + sound plan + scorecard)

- **film-spec schema**: `sound_plan` gained `music_spotting` (label/start/end/fade/emotion/beat_ref/intensity) and `audio_tracks` (dialogue/SFX/ambience/foley/music gain+ducking); `grade` field (lut/color_temperature/saturation/contrast/brightness/skin_tone_protection/gamma) + `color_grade_strict` gate.
- **Director review scorecard expanded 7→11 dimensions**: added `rhythm`, `emotion`, `theme`, `performance` to `SCORECARD_DIMENSIONS`; `--approve` now requires all 11 `--score-*` flags; `_DEFAULT_ACTION_FOR_DIM` maps each new dimension's fail→action.
- **director-methodology.md**: 40-year director methodology master file (pre-production/production/post-production three-phase + test matrix).
- Tests: `test_color_grading.py`, `test_sound_and_review.py`.

## [1.21.0] — 2026-07-23

### Improved — FFmpeg render safety

- FFmpeg execution is now non-interactive across final and designed-post rendering.
- Designed-post mux and stem outputs render to sibling temporary files, then publish atomically only after size and ffprobe validation.
- Failed or undersized encodes no longer overwrite an existing final output; media command failures retain actionable diagnostics.

## [1.20.0] — 2026-07-23

### Added — Director methodology injection (P1-5/P1-6: scene design + art direction)

- **Location schema expanded** (P1-5): `drama-graph.schema.json` Location upgraded from 2 fields (id/description) to full scene design sheet: `structure`, `timeOfDay`, `lighting`, `palette`, `immutableRules`, `recurringObjects`, `primaryAngles`, `atmosphere`, `color_temperature`, `set_dressing`, `lighting_plot`.
- **locationId filling** (P1-5): `derive_graph()` now populates `locationId` from scene or inferred from shot dsl.location (was hardcoded `None` at both scene + shot level).
- **SCENE_LOCATION_MISSING lint** (P1-5): new continuity lint code fires warning when shot has no locationId — scene continuity cannot be verified without location binding.
- **`art_direction` layer** (P1-6): style-bible.schema now defines structured `art_direction` object with `color_script` (per-scene color temperature + emotional motivation), `visual_motifs` (recurring symbols with narrative meaning), `texture_continuity` (texture elements that must be consistent). Replaces single-string palette/lighting for art direction.
- 9 new tests covering location filling, lint, and schema structure.

### Improved — FFmpeg/ffprobe reliability

- Added shared non-interactive FFmpeg/ffprobe execution and structured media probing.
- Unified timeout, missing-tool, invalid-output, and full-decode errors across media QA, duration checks, and master delivery.
- Kept encoding and filter behavior unchanged to avoid visual-quality regressions.

## [1.19.0] — 2026-07-23

### Added — Department evidence and take integrity

- Added hash-bound active-take history with superseded evidence preservation.
- Added `beat-evidence`, `editor-cut`, and `audio-visual` reports for action, edit, and sound-picture alignment.
- Added per-shot take comparison to `aifilm quality --shot-id`.

## [1.18.0] — 2026-07-23

### Added — Quality receipt observability

- Added read-only `aifilm quality --root <film>` reporting with optional `--shot-id` filtering.
- Dispatch now consumes the same shared quality summary, keeping operator output and orchestration gates consistent.

## [1.17.0] — 2026-07-23

### Added — Quality-first generation gates

- Added per-shot keyframe and clip quality receipts with stricter hero-shot promotion gates.
- Provider fallback now records routing evidence and requires a fresh hero pilot before bulk work.
- Dispatch now reports persisted quality blockers; hero quality evidence is required before promotion.
- Kept `grok_primary` as the reproducible hero default; Seedance requires canary and pilot evidence.

## [1.16.0] — 2026-07-23

### Added — Director methodology injection (P1-1/P1-2/P1-3: face-lock + hairstyle + makeup)

- **Structured `cast_locks`** (P1-1): style-bible.schema now defines `cast_locks` as a per-character structured object with `face_ref_path`, `identity_lock_tokens`, `never_tokens`, `hair_lock`, `makeup_lock`. prompt_injector prefers structured cast_locks over free-text identity_lock — locks are no longer a free-text blob.
- **`hair_swatches`** (P1-2): style-bible.schema now defines `hair_swatches` as structured per-character field `{color_name, hex, description}` — independent from identity_lock free text. prompt_injector auto-builds Hair lock line from swatches when cast_locks.hair_lock is absent.
- **`makeup`** (P1-3): style-bible.schema now defines `makeup` as structured per-character field `{name, ref_path, lock_tokens, cross_scene_consistency}` — from 0/10 to parameterized. prompt_injector injects Makeup line from cast_locks.makeup_lock or makeup field fallback.
- **Hair lock line injection** (consistency.md H4 compliance): prompt_injector now injects `Hair lock <char>: <color> (<NEVER tokens>)` — this was explicitly missing per consistency.md:148. Fallback chain: cast_locks.hair_lock → hair_swatches.color_name+description.
- **Makeup line injection**: prompt_injector injects `Makeup <char>: <lock_tokens>`. Fallback chain: cast_locks.makeup_lock → makeup[char].lock_tokens.
- Updated `references/style-bible.md` documentation for all three fields.
- **Backward compatibility**: no cast_locks/hair_swatches/makeup → behavior unchanged (identity_lock free text used, no Hair/Makeup lines injected).
- 9 new tests covering structured locks, fallback chains, precedence, and backward compat.

## [1.15.0] — 2026-07-23

### Added — Director methodology injection (P0-1: de-type-bias)

- **Multi-genre beat spines**: `dramatic_function` seven-value enum is now decoupled from the adult six-shot spine. New `genre` field (drama-graph + film-spec schemas) selects the beat spine template. Five genres supported: `adult` (default, backward-compat), `drama`, `mystery`, `arthouse`, `documentary` — each with its own beat spine (key/objective/weight/shots_n).

### Added — Director methodology injection (P0-2: three-act structure + pace chart)

- **Structured `act_structure`**: `director_intent.act_structure` upgraded from free-form to structured object with `setup`/`confrontation`/`resolution` text + optional ratio fields (`setup_ratio`/`confrontation_ratio`/`resolution_ratio`, classic 0.20/0.50/0.30, sum validated ≈1.0). `act_structure_strict: true` → write-spec hard-gates non-empty + all three acts present.
- **Structured `pace_chart`**: `director_intent.pace_chart` upgraded from string array to structured entries: `{label, start_ratio, end_ratio, cut_freq, intensity}` (≥3 segments). Validates ratio ranges, end>start, intensity 0-10. `pace_chart_strict: true` → write-spec hard-gates non-empty + ≥3 segments. Legacy string-array format still accepted (backward compat).
- `validate_director_intent()` in `film_spec.py` now validates both structures. `_draft_story_contract()` initializes act_structure defaults. `project_graph_to_film_spec()` projects act_structure + pace_chart into film-spec.
- Updated `film-spec.md` + `directors-lens.md` documentation.

### Added — Director methodology injection (P0-3: character bible)

- **Character schema expanded**: `drama-graph.schema.json` Character upgraded from 4 fields (id/identity/defaultWardrobe/castMaster) to full dramatic character bible: `name`, `age`, `personality`, `want`, `need`, `flaw`, `ghost_wound`, `arc_turning_points[]`, `relationships[]`, `psych_markers[]`, `dramatic_role` (protagonist/antagonist/mentor/ally/trickster/guardian/supporting). Visual identity fields preserved for backward compat.
- **Protagonist arc gate**: new `character_bible_strict: true` flag → write-spec hard-gates `director_intent.protagonist_want` / `protagonist_need` / `protagonist_arc` non-empty. New schema fields in film-spec + drama-graph.
- `_draft_story_contract()` initializes protagonist_want/need/arc fields. `project_graph_to_film_spec()` projects them into film-spec director_intent. Character generation in `story_plan.py` now populates dramatic role fields with authoring placeholders for leads.
- Legacy import path in `aifilm_grok.py` updated to project genre + protagonist fields + act_structure into drama-graph story.
- New `templates/character-bible.example.md` — full character bible template with dramatic arc, relationships, psych_markers, wardrobe table.
- `detect_genre()`: parallel to `detect_heat_signals()`, infers genre from brief text markers. Priority: explicit genre field > adult heat signals > genre text markers > default adult.
- `select_beat_spine()` accepts `genre` parameter; non-adult genres return `GENRE_SPINES[genre]` directly (ignores heat signals). Adult genre preserves existing heat-signal logic unchanged.
- `normalize_story()` now returns `genre` + `genre_evidence` fields.
- `project_graph_to_film_spec()` projects `genre` into film-spec top-level + `_plan` metadata.
- `extract_beats()` passes genre to `select_beat_spine()` + uses genre-specific authoring prompts.
- New `references/beat-spines.md` — 40-year director methodology: multi-genre spine definitions, selection logic, backward-compat guarantees, extensibility.
- Updated `directors-lens.md` + `film-spec.md`: `dramatic_function` table now shows generic semantics (de-ecchi-bound) per genre context.
- **Backward compatibility**: `dramatic_function` enum unchanged (write-spec gate unaffected). `genre` defaults to `adult`. Existing projects behave identically.

### Added — Professional director control plane

- Production Book, unified hash-bound human approvals, three rigor modes, precise stale propagation, and no-delete impact previews.
- Style Bible v3 plus Audio/Post Bible department nodes for cast, face, hair, makeup, wardrobe, art, camera, voice, dialogue, sound, music, edit, captions, mix, and Master.
- Agent-native `director`, `department`, and `skill run` CLI primitives with optimistic revisions, dry-run, atomic writes, structured receipts, and idempotent transaction recovery.
- Read-only Shot Packages, strict Style→Cast→State Photo→Keyframe→Clip→Promoted Tail provenance, exact shot-set comparison, Dailies/Selects, Picture Lock, and eleven professional stage gates.
- No-spend golden suite with genre isolation and continuity/audio/approval failure injection; Master delivery now requires real motion evidence, audio, visible captions, `ffprobe` read-back, and current full-film human approval.

## [1.14.4] — 2026-07-22

### Added

- Post-production P1b: `caption-frame-attest` binds explicit human readability approval to current sampled caption frames. Post-audit now fail-closes missing or stale caption-review evidence for v2 burned-subtitle deliveries.

## [1.14.3] — 2026-07-22

### Added

- Post-production P1a: `caption-frame-audit` extracts hash-bound final-MP4 frames during subtitle cues for human readability review. Post-audit now warns when burned-caption visual evidence is missing or stale.

## [1.14.2] — 2026-07-22

### Added

- Post-production P0: `final-delivery` v2 binds final output, subtitle, mix-report, and timeline provenance. Post-audit fail-closes incomplete v2 provenance while retaining a migration warning for legacy v1 sidecars.

## [1.14.1] — 2026-07-22

### Added

- `prompt-compression-attest` binds hash-matched candidate keyframes, clips, frame QA, an all-pass Pilot scorecard, and an existing human Pilot approval to a compression candidate. Evidence completion never promotes or rewrites a production rule.

## [1.14.0] — 2026-07-22

### Added

- `prompt-compression-pilot` writes an ai-film-grok hash-bound candidate ledger. It rejects removal of protected locks and requires same-condition candidate media, QA, scorecard, and human Pilot approval before any compression could be promoted.

## [1.13.9] — 2026-07-22

### Added

- Prompt-budget now supports a review-only token threshold and separates protected repeated locks from compression candidates. Candidates state their estimated saving but cannot be applied automatically; a director-approved Pilot equivalence check remains required.

## [1.13.8] — 2026-07-22

### Added

- `prompt-budget --root <film>` reads prompt-assembly receipts to estimate per-shot and episode input tokens, identify repeated provider-bound lines, and distinguish continuity locks from lines worth reviewing. It is read-only unless `--write` is explicit.

## [1.13.7] — 2026-07-22

### Changed

- Prompt assembly keeps local state-photo instructions in the traceability receipt instead of sending filesystem paths and executor guidance to image/video providers. It also de-duplicates negative constraints and records a local prompt-token estimate per shot.

## [1.13.6] — 2026-07-22

### Added

- Planning-answer dry-runs now return a canonical answer SHA-256 and transaction ID. A formal submission may require that exact ID with `--expected-transaction-id`, and records the binding in planning history.

## [1.13.5] — 2026-07-22

### Changed

- Planning-answer batches are now atomic: a formal write occurs only after the complete in-memory batch passes narrative validation; rejected batches leave graph and history untouched.

## [1.13.4] — 2026-07-22

### Added

- Planning history now packages diagnosis-specific answer templates as copyable planning-answer dry-run commands.

## [1.13.3] — 2026-07-22

### Added

- Planning history emits diagnosis-specific answer templates; unresolved core causality produces only the five-question story card.

## [1.13.2] — 2026-07-22

### Added

- Planning history now classifies stalled progress as no formal answers, unresolved core causality, or answers that did not reduce open fields.

## [1.13.1] — 2026-07-22

### Added

- `planning-history` provides local readiness progression, stalled-round count, and current high-priority authoring blockers.

## [1.13.0] — 2026-07-22

### Added

- Formal planning-answer writes append-only local planning-history entries with changed fields, graph revision, and readiness delta; dry-run remains non-mutating.

## [1.12.9] — 2026-07-22

### Added

- `planning-answer --dry-run` now reports readiness before/after, delta, and the remaining highest-priority authoring batch.

## [1.12.8] — 2026-07-22

### Added

- Planning autopilot now emits a minimal structured answer template and dry-run command for the next authoring batch.

## [1.12.7] — 2026-07-22

### Added

- Planning autopilot now reports a transparent weighted draft-readiness score and lock-review eligibility from unresolved authoring fields.

## [1.12.6] — 2026-07-22

### Added

- Planning autopilot now provides a minimal high-impact authoring batch before deferring lower-risk detail questions.

## [1.12.3] — 2026-07-22

### Added

- Planning autopilot now emits a priority-sorted director questionnaire from canonical `needs_authoring` fields, prioritizing story causality before tactic and coverage detail.

## [1.12.2] — 2026-07-22

### Added

- `planning-autopilot` exposes safe draft-automation steps separately from mandatory human story, lock, Pilot, and final-review checkpoints.

## [1.12.1] — 2026-07-22

### Added

- Director exception ledger now requires approver, approval time, and reviewed clip; historical approvals are visible as pending re-approval rather than silently trusted.

## [1.12.0] — 2026-07-22

### Added

- `director-ledger` centralizes human-approved subtitle carry-over exceptions and binds them to film-spec, drama graph, and final MP4 hashes; post-audit invalidates stale authorization.

## [1.11.9] — 2026-07-22

### Added

- Hard/Continue subtitle carry-over is permitted only by an exact, reasoned, range-bounded, human-approved `subtitle_carryovers` declaration.

## [1.11.8] — 2026-07-22

### Added

- `subtitle-cut-boundaries` blocks subtitle cues that cross authored hard cuts or strict Continue boundaries.

## [1.11.7] — 2026-07-22

### Added

- `subtitle-dialogue-alignment` blocks lipsync dialogue without a cue covering its human-observed delivery end, or without declared subtitle and subject safe areas.

## [1.11.6] — 2026-07-22

### Added

- `audio-provenance` binds canonical lipsync dialogue, local rehearsal-audio bytes, the rendered voice carrier, and the registered final MP4 with checksums.
- Final review and post-audit now reject a stale or missing dialogue-audio source chain, while explicitly distinguishing byte provenance from human sound and lip-sync judgment.

## [1.11.5] — 2026-07-22

### Added

- `speech-performance-timing` binds a measured dialogue rehearsal, its canonical text, the human-observed end-of-line delivery, and at least 0.2s of post-line reaction space.
- `review-final` now blocks lipsync dialogue that has no dialogue-kind TTS evidence, mismatched text, an impossible delivery end, or an immediate cut that removes the reaction beat.

## [1.11.4] — 2026-07-22

### Added

- `performance-timeline` compiles checksum-bound per-shot triggers, actions, reactions, delivery, and mouth-still observations into an ordered film timeline.
- Final approval now fails for content-channel projects when required performance receipts or their timestamp frames are absent, stale, or semantically out of order.

## [1.11.3] — 2026-07-22

### Added

- Performance-fact shot review: content-channel shots now bind human-observation timestamps for playable actions, visible triggers/reactions, dialogue delivery, and on-camera narration without mouth movement to the exact reviewed clip hash.
- Reactions cannot be approved before their declared trigger; the receipt explicitly records that this is human observation rather than automatic mouth, face, or acting recognition.

## [1.11.2] — 2026-07-22

### Changed

- Cleared the repository's ruff backlog with safe and reviewed mechanical fixes; CI now retains hard correctness checks while documenting intentional dynamic-import, compatibility, process-lifetime, and test-scope exceptions.
- Fixed real static defects in re-encode reporting and normalized formatting/imports across scripts and tests.

## [1.11.1] — 2026-07-22

### Added

- Content-channel contract: narration, dialogue, playable performance and motion now have separate fields and receipts.
- `content_channels_strict` rejects narration copied into visual action, on-camera dialogue with lipsync disabled, lipsync without dialogue, and reactions triggered by text rather than an in-scene event.

### Changed

- Prompt construction never falls back from `nar` to a motion/action instruction; narration is audio-only unless authored as a separate visible action.
- User-source fidelity runs only when `source_excerpt` exists, so stock/generated plans are no longer falsely judged as overwriting user text.

## [1.11.0] — 2026-07-22

### Added

- **CI hardening**: `validate-core` job now installs `ruff` and runs `ruff check` + `ruff format --check` on all scripts; `test-full` runs the complete test suite (including slow tests) as a hard gate.
- **`pyproject.toml`** for the skill: ruff configuration (line-length 100, target Python 3.11), pytest config with `slow` marker, and `tool.ruff.lint` rules (E, F, I, W, B, UP, SIM).
- **BGM cache**: 5 CC0-licensed R&B loops (`assets/bgm/rnb/`) with `index.json` and per-track license files, providing a safe default for `--music-mood rnb` without external dependencies.
- **Adapter smoke tests** (`tests/test_adapter_smoke.py`): parametrized tests verifying all I2V/TTS/BGM adapter modules import and expose their expected provider classes and methods.
- **I2V retry logic**: `grok_oauth_video.py` adapter now retries `video_generate` with exponential backoff (2s, 4s) on 429 rate-limit errors.

### Changed

- **`util.py` adoption**: 11 script files now use the shared `read_json`/`write_json` helpers instead of inline JSON I/O, reducing duplication and ensuring consistent error handling.
- **Subprocess timeouts**: all 16 script files with `subprocess.run`/`call`/`Popen` now specify `timeout=` (30s–300s depending on operation type), preventing indefinite hangs in CI and production.
- **Slow test markers**: 33 test files containing subprocess/FFmpeg/network calls are now marked `@pytest.mark.slow`, enabling fast CI (`pytest -m "not slow"`) and full CI (`pytest` without filter).
- **Version bump** to 1.11.0 (semver: minor — new features + hardening).

## [1.10.6] — 2026-07-22

### Changed

- Post-audit now requires complete passing final-review scorecard and seven-dimension screening evidence.
- Final review approval is invalidated when its bound MP4 hash differs from the current final.

## [1.10.5] — 2026-07-22

### Added

- Final-delivery sidecar hash consistency checks for final, subtitles, audio, and timeline.
- `export-desktop` now writes `项目状态/delivery-manifest.json` with exported file hashes and sizes.

## [1.10.4] — 2026-07-22

### Added

- Post-audit hard checks for subtitle double-burn risk and title plate duplication risk.
- Final delivery subtitle burn metadata and compose caption artifacts are now cross-checked.

## [1.10.3] — 2026-07-22

### Added

- Post-audit subtitle timecode/range validation.
- Audio mix loudness evidence reporting.
- Vertical safe-area audit with strict-vs-warning behavior.

## [1.10.2] — 2026-07-22

### Changed

- `export-desktop` now requires a current post-audit receipt with no hard failures or stale evidence.
- Internal preview/render paths remain available before formal delivery export.

## [1.10.1] — 2026-07-22

### Added

- Post-audit freshness binding for final, subtitle, audio mix, timeline, and final-review hashes.

### Changed

- Dispatch now treats stale post-audit receipts as delivery blockers.

## [1.9.1] — 2026-07-22

### Changed

- Connected `post-audit` freshness and hard-failure status to dispatch for post and verified stages.
- Dispatch now reports post-audit receipt presence, delivery readiness, hard failures, and warnings.

## [1.10.2] — 2026-07-22

### Added

- write-spec injects act/climax flesh `sound_plan` sfx accents from heat/sound_cues.
- Adult `pilot pick` prefers undress → union → rhythm.
- Dual-climax spine (`双高潮`/`两轮` or hardcore ≥90s); `templates/premises-adult.md`.

## [1.10.0] — 2026-07-22

### Added

- `spice_level` (suggestive/explicit/extreme) with `HEAT_VO_SPICE_TOO_MILD` for dual-entendre-only act VO.
- VO–motion alignment lint; sex_pose variety (`SEX_POSE_STALE`); montage craft lint + hardcore craft spine inject.
- Act auto flesh SFX (`impact/breath/leather`); hardcore/extreme vocal_color opt-in defaults.
- `aifilm heat vo-suggest` / `heat soften-log`; coitus review dimension; pose pack docs.
- Max sex duration floor raised to **30%** (hardcore still 40%).

### Changed

- Adult plan seeds denser nar + multi `sex_pose`; heat check reports spice/pose/sfx/montage.

## [1.9.0] — 2026-07-22

### Added

- Adult max planning spine (`ADULT_MAX` / `HARDCORE_MALE`) from brief heat signals — no silent pin without evidence.
- Coitus six-beat grammar lint + size-ladder lint in `_heat_arc` (`coitus_strict` / `size_ladder_strict` for hardcore).
- Sex I2V motion templates (`rhythm_hips`, `union_settle`, `finish_arch`, …) and heat-aware coverage.
- Prompt coitus readability HARD line for act/climax; `aifilm heat check`; adult-max film-spec template + playbook.

### Changed

- `plan run` projects `heat_phase` / `coitus_beat` / spicy `nar` seeds and `coitus_grammar.beats` when adult brief detected.
- Plugin minor **1.9.0** — adult production capability pack.

## [1.8.11] — 2026-07-22

### Added

- Unified `aifilm post-audit --root` post-production audit with JSON and Markdown receipts.
- Hard checks for final media presence/QA, final hash freshness, approved full-film review, open reshoots, and delivery sidecar.
- Evidence capture for final, review, subtitles, delivery, and open director notes.

## [1.8.10] — 2026-07-22

### Changed

- Connected the production evidence ledger to dispatch for media, rough, and verified stages.
- Dispatch now surfaces a hard production-evidence gate before bulk motion when canonical graph, current projection, or user-approved pilot evidence is missing.

## [1.8.9] — 2026-07-22

### Added

- Read-only `aifilm production-evidence --root` ledger for story, pilot, motion, audio, subtitle, and delivery evidence.
- Bulk readiness remains false until canonical story semantics, current projection, and user-approved pilot evidence exist.

### Changed

- Production QA evidence is now surfaced as one machine-readable report instead of scattered receipt inspection.

## [1.8.8] — 2026-07-22

### Changed

- Extracted the story idea → draft Drama Graph `plan run` route.
- Preserved authoring questions, draft state, optional film-spec seed, and force behavior.

### Added

- Regression coverage for missing sources and authoring-only one-liner plans.

## [1.8.7] — 2026-07-22

### Changed

- Extracted canonical `plan project` projection into a dedicated CLI route.
- Kept overwrite confirmation, graph readiness checks, validation summary, and output contract unchanged.

### Added

- Regression coverage for missing graph and overwrite protection.

## [1.8.6] — 2026-07-22

### Changed

- Extracted planning mutations into a dedicated transactional CLI route.
- Preserved revision receipts and explicit fail-closed confirmation for subtree replan operations.

### Added

- Regression coverage for missing graph and unconfirmed replan mutations.

## [1.8.5] — 2026-07-22

### Changed

- Extracted read-only Story Planning validation and status routes into a dedicated CLI module.
- Kept planning write operations in the main entry until their mutation receipts receive isolated route coverage.

## [1.8.4] — 2026-07-22

### Changed

- Extracted read-only Drama Graph validation and status routes into a dedicated CLI module.
- Kept legacy derive/import and canonical project flows in the main entry until their write contracts are separately covered.

## [1.8.3] — 2026-07-22

### Changed

- Extracted environment T2V and panel motion-plan routing into a dedicated media CLI module.
- Preserved existing provider arguments, prompt-file handling, error normalization, and JSON output.

## [1.8.2] — 2026-07-22

### Changed

- Extracted the Skill Registry CLI route into a dedicated module while preserving command names, arguments, and JSON output.
- Added subprocess-bounded CLI smoke coverage for help and registry listing.

## [1.8.1] — 2026-07-22

### Added

- CI smoke gates for the CLI launcher, shipped schemas, registry, and new production modules.
- Regression coverage proving stale execution nodes cannot be dispatched.

## [1.8.0] — 2026-07-22

### Added

- Execution job lifecycle metadata with input hashes, executable dependency gates, and production-mode routing.
- Deterministic `motion-plan` compiler for panel-animation shots.
- `aifilm skill validate` for runtime input/output envelope checks.

### Changed

- Environment plates can load prompts from files, avoiding shell-length and quoting failures.

## [1.7.0] — 2026-07-22

### Added

- Director-grade story planning fields for obstacle, tactic, turn, outcome, state delta, audience question, emotional turn, and actionable authoring questions.
- Hard narrative validation for observable shot state transitions and performance direction: playable action, expectation, subtext, gaze target, reaction trigger, and body state.
- Canonical Drama Graph v2 for derived roots, with explicit draft semantics and stale projection protection.
- Executable Skill Registry metadata, rhythm/coverage lint, and 9:16 platform safe-area lint.

### Changed

- VO rehearsal is now a dependency before motion generation in the execution graph.
- `plan run` remains an honest draft operation and no longer implies that a generated graph is production-ready.

## [1.6.0] — 2026-07-22

### Added

- One Python 3.11+ resolver shared by the CLI launcher and Make targets; `make test` no longer falls back to macOS Python 3.9.
- Canonical Beat `director_board` contract: emotional turn, audience question, image/sound priorities, coverage, cut intent, and explicit approval are required before Beat lock.
- `aifilm review-shot`: deterministic first/middle/last contact sheet, motion/decode evidence, 1–5 director scorecard, timestamp evidence, and source-hash-bound review receipt.
- New film roots require shot-review evidence before an approved clip can enter delivery gates. `aifilm review-contract migrate` upgrades legacy roots without pretending old boolean approvals are new reviews.
- Final reviews for v1.6 roots record timestamped screening evidence. Open reshoot items remain open until explicitly resolved; a later pass cannot silently erase them.

### Changed

- Legacy `graph import` now writes a v2 migration receipt and seeds incomplete Beat contracts as authoring work rather than treating them as locked narrative truth.
- BGM documentation now accurately states that no shared licensed music is packaged; the procedural bed remains the safe default.

## [1.5.0] — 2026-07-22

### Added

- Integrated the vertical-drama upgrade through Phases 1–4: Drama Graph, Skill Registry, deterministic story planning, and asset/state registry.
- Added P0 continuity protections for state-photo/keyframe provenance, I2V first/last handoff, wardrobe no-redress, and keyframe geometry validation.
- Promoted the validated 1.4.3–1.4.8 work into the 1.5.0 plugin release.

## [1.4.8] — 2026-07-22

### Added

- **Phase 4 Asset Registry**: `aifilm assets sync|status|check`
  - `scripts/asset_registry.py` — structured Character / Location / Prop + CharacterState timeline
  - `assets-registry.json` + `receipts/assets-sync.json`
  - wardrobe_variants + cast_state_masters slots + `canonical/cast-states/<id>/`
  - Aligns with `state-index` (missing state photos + re-dress risks)
  - Patches `drama-graph.json` with `characterStates` / `assetRegistry`
  - `plan run` auto-syncs assets after film-spec seed
  - Registry skills: `character.state.update` · `location.bible.build` · `prop.track`
  - Schemas: style-bible locations/props objects · `assets-registry.schema.json`
  - Tests: `tests/test_asset_registry.py`

## [1.4.7] — 2026-07-22

### Added

- **Phase 3 Story Planning**: `aifilm plan normalize|run|project|status`
  - `scripts/story_plan.py` — story.normalize → episode → scene → beat → shot
  - Writes `drama-graph.json` (`mode=planned`) + seeds `film-spec.json` / timeline / bible / manifest skeleton
  - Vertical beat spine (hook→setup→escalate→peak→button); snappy `nar`≤28 + VO-safe `duration_sec`
  - Registry: story.normalize / episode.structure / scene.segment / beat.extract / shot.plan → implemented
  - Tests: `tests/test_story_plan.py` (one-liner DoD ≥3 beats)

### Notes

- Planner is deterministic (no LLM). Agent may refine nar/dsl after `plan run`, then `write-spec`.

## [1.4.6] — 2026-07-22

### Added

- **Phase 1 Vertical Drama Graph (v0)**: `aifilm graph derive|validate|status`
  - `schemas/drama-graph.schema.json` · `scripts/drama_graph.py`
  - Read-only projection from `film-spec.json` → `drama-graph.json` (Episode→Scene→Beat→Shot→Panel)
  - Asset hints (keyframe/clip/prompt presence) + `productionMode` inference
- **Phase 2 Skill Registry shell**: `aifilm skill list|show`
  - `registry/skills.json` (24 skills) · `registry/contracts/skill-envelope.*.json`
  - `scripts/skill_registry.py`
- **dispatch schema_version=2**: additive `graph` · `jobs_summary` · `execution_plan_digest` (HUD slim fields)
- Plan: `docs/plans/2026-07-21-vertical-drama-upgrade.md`
- Tests: `test_drama_graph.py` · `test_skill_registry.py` · dispatch packet asserts

### Notes

- film-spec remains executable source of truth; graph is derive-only (no dual-write yet).
- Skill runner still maps to existing CLI — contracts are envelopes, not full rewrite.

## [1.4.5] — 2026-07-21

### Added

- **状态照检查门（可补生成）**：`aifilm state-index check|plan` · `scripts/state_index_gate.py`
  - 查 missing state photos / undress-anchor / keyframes / continue promote
  - `generate_plan` = 本阶段可执行的补生成清单（目的：运镜转场流畅）
  - 写入 `receipts/state-index.json`；并入 `preflight` + `dispatch` next_actions

## [1.4.4] — 2026-07-21

### Added

- **Keyframe-first · 状态照索引**：`references/keyframe-first-state-index.md`  
  L0 style → L1 cast → L2 `cast-states/{full,partial,undressed,bare}` → L3 keyframe → L4 I2V；视频坏先改 keyframe/状态照。
- Bible field **`cast_state_masters`** + `resolve_state_photo()` in `visual_bible.py`
- Prompt injector emits **`State photo ref:`** + receipt `state_photo_paths` / `keyframe_first_note`
- Docs: SKILL hard gate #10 · hard-defaults · consistency 3b/W7 · style-bible · Agents.md

## [1.4.3] — 2026-07-21

### Added

- **P0 卸装后 still 源链（不回穿）**：片例 `xide-hardcore-thrust`。peak 后禁止 `image_edit(全装 cast)`；必须 `canonical/wardrobe/undress-anchor` 或已脱 still；I2V 锁 first-frame 衣着。
- New lesson: `references/lessons-2026-07-21-wardrobe-no-redress-still.md`
- Docs wired: `SKILL.md` hard gate #9 · `hard-defaults` · `consistency` §1e · `sex-undress-ladder` · `production-discipline` · `ecchi-story` · global `~/.grok/Agents.md`

### Changed

- Clarifies **pixel gate ≠ JSON gate**: `wardrobe_state=bare` with full-cast ref is still a re-dress accident.

## [1.4.2] — 2026-07-21

### Changed

- **卸装阶梯硬底强化**：`apply_wardrobe_continuity` 在 write-spec 继承前镜 `wardrobe_state`；rank 单调不降。
- 新码 **`HEAT_WARDROBE_RE_DRESS`**：后镜穿回更「整齐」的衣服 → `sex_wardrobe_strict` hard fail。
- Prompt 注入 `Costume continuity: NEVER re-dress` when state ≥ partial。
- Docs: sex-undress-ladder · hard-defaults · schema · SKILL。

## [1.4.1] — 2026-07-21

### Changed

- **声线默认**：成片以 **旁白 `nar` + BGM** 主导；`vocal_color`（娇喘语助独立 TTS）**默认关闭**（`voice_tracks.enabled=false` · `vocal_color_gain=0` · `auto_vocal_color=false`）。须显式 opt-in 才混入。
- `render_final` mix 默认 **3 输入**（nar/bgm/native）；无 color stem 时不再生成静音 `vocal_color_track.wav`。
- Docs: `SKILL.md` · `references/voice-tracks.md` · `references/hard-defaults.md` 与默认一致。

### Fixed

- `export_composition.py`: Remotion f-string JS ternaries; restore `build_title_sequence_html` / `build_end_roll_html` for HyperFrames export.
- `resolve_shot_vocal_color` gate: `enabled` default false (was true).

## [1.4.0] — 2026-07-21

### Added

- Root **README**: install paths (GitHub / local), usage logic (八环 + `dispatch`), architecture graph (PNG + SVG + Mermaid), and **pluggable model matrix** (image / I2V / TTS / BGM / lipsync / post / Grok OAuth).
- Shared `scripts/util.py` (`read_json` / `write_json`) required by the sex-floor / preflight path.
- Adult product hard floors (when `heat_scale=max`): sex duration ≥20%, undress ladder, spicy VO on every nar (prior commits on main).

### Fixed

- `preflight.py`: invalid `elif` after `for` (SyntaxError) when heat VO spice blocks run.
- Example `film-spec.example.json` nars now pass `sex_vo_strict` under `heat_scale=max`.
- `runtime-lock.json` refreshed for release fingerprints.

### Changed

- Default I2V season remains **`grok_primary`** (Grok `image_to_video`); Seedance opt-in via profile.
- Architecture diagram updated for grok_primary season.
- Skill-local README points to root docs as the public entry.

### Notes

- Local secrets stay in `skills/ai-film-grok/config.env` (gitignored).
- User skill path is a symlink into this plugin skill directory.
- Incomplete CLI package split kept in local stash (`wip-cli-refactor-pre-1.4-docs`); not part of this release.

## [1.0.0] — 2026-07-21

### Added

- Independent git root at `~/.grok/plugins/ai-film-grok` with GitHub remote.
- `AGENTS.md` absolute-path entry for coding agents.
- GitHub Actions CI: `plugin validate` + pytest.
- Grok plugin packaging: `plugin.json`, slash commands `/ai-film-grok` `/aifilm`.
- Full skill body under `skills/ai-film-grok` (dispatch eight-ring, Imagine I2V, edge TTS, HyperFrames/FFmpeg).

### CI

- GitHub Actions: `validate-core` + `test-full` both required (full suite green on main).
- Pinned deps via `skills/ai-film-grok/requirements.lock`.
