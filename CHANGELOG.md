# Changelog

## [2.41.31] - 2026-08-07

### Added (edit-director · Round 3)
- **apply ↔ post-plan sync**: design → post_owner (hyperframes|remotion|ffmpeg); create/realign `post-plan.json`.
- **editorial**: EDL path, source_types, optional trims from `edit/edl.json` (A-roll).
- **`edit-director checklist`**: dry-run → `receipts/edit-director-checklist.{md,json}`.
- **Tests:** sync · EDL/trims fail-closed · checklist (18 cases).

## [2.41.30] - 2026-08-07

### Added (Phase D · review_mode)
- `review_mode_policy`: async_dailies (default) | gate_each.
- gate_each blocks advance on multi-take picks; picture_lock/final hard-clear take backlog.
- CLI: `director-center set-mode|blockers`; final/review-final gate hooks.

## [2.41.29] - 2026-08-07

### Added (edit-director · Round 2 production loop)
- **ship-prep**: auto-draft `post/edit-director-plan.json` when missing (advisory step).
- **final**: `resolve_final_defaults` — plan supplies `--post-engine` / caption when CLI does not pin.
- **post-doctor**: EDIT_DIRECTOR_* health; hard fail on plan vs post-route caption mismatch.
- **closeout**: plate next_cmd prefers plan `final_cmd` when plan exists.
- **Tests:** resolve defaults · post-doctor mismatch · closeout cmd.

## [2.41.28] - 2026-08-07

### Added (director-center · Phase A–C)
- **`aifilm director-center open|status|stop|wait`**: loopback 指挥中心 + 等人审。
- **`GET /api/live` · `/api/events` · `/api/takes` · `POST /api/takes/review`**: 人审收件箱、活动流、多 take 选片（双网关）。
- **console**: 指挥中心 KPI/收件箱/活动流 + **选 Take** tab（并排 Select/Reject，anti-hijack 提示）。
- **`aifilm takes select|reject`**: CLI 与 Web 同学 take_registry。
- **dispatch** `console_url` / `console_hint` 连动。
- **Tests:** `test_director_center.py`。

## [2.41.27] - 2026-08-07

### Added (edit director · full desk)
- **`aifilm edit-director`**: draft / normalize / status / set / apply / run / audit / snapshot / cuts / activate.
- Plan truth: `post/edit-director-plan.json` · schema · hard-defaults / stages/post 快卡 · memory · todoplan.
- **`run --execute`**: apply → shell existing `aifilm final` (injectable runner / `AIFILM_EDIT_DIRECTOR_EXECUTE_STUB=1`).
- **Dispatch hooks**: next_actions + professional selects_rough_cut/post_locks prefer edit-director before bare final thrash.
- **Tests:** `test_edit_director.py`.

## [2.41.26] - 2026-08-07

### Added (Web 控制台 · 导演总控台 / 多片工作室视图)
- **导演总控台（studio mode）：** `aifilm review-ui serve --studio <dir>` 启动工作室模式，扫描目录下所有影片根目录并构建跨片注册表；`/studio` 页面别名保持不变（API 命名空间为 `/api/studio*` 无冲突）。
- **总控台 tab：** 控制台新增「总控台」页（仅 studio 模式可见，启动即默认进入）——展示全部已制作 / 制作中的 AI Film 卡片，支持按分类（题材）与状态筛选、关键词搜索；每张卡含进度条、状态 pill 与「打开此片」。
- **多片监控：** `GET /api/studio` 列出工作室全部影片（分类、状态计数、进度），`GET /api/studio/<id>` 取单片详情，`POST /api/studio/select` 切换当前活跃影片（服务端 `active_film` 持久化、跨接口生效），含路径穿越防护（非法 id → 400、缺失 → 404）。
- **已发布作品：** 总控台合并 `video-library/catalog.json`（`aifilm-video-library-v1`，`assets` 键）中已发布的影片元数据，与本地在制影片同屏管理监控。
- **注册表模块：** 新增纯函数、可测的 `scripts/studio.py`——`discover_films` / `summarize_film` / `build_studio` / `load_released`。
- **测试 & e2e：** 新增 `tests/test_web_studio.py`；`web/smoke_console.py` 扩展 studio 阶段。

### Changed
- `review_ui.py` 服务端支持 studio 模式：`film_root` 经 `self.server.active_film` 动态绑定；`/api/console-state` 注入 `studio_mode` / `studio_dir` / `active_film_id`。
- `runtime-lock.json`：刷新 studio 相关指纹。

## [2.41.25] - 2026-08-07

### Fixed
- **platform package collect:** re-export `build_platform_opening_html` from `export_composition` (W4 peel left it importable only via `export_html`).
- **export_html:** restore missing stdlib imports (`html`, `math`, `os`, `struct`, `tempfile`, `wave`) after peel — end-roll/opening/suspense stings no longer `NameError`.

### Changed
- INDEX / frw-lipsync / seedance-camera-vocab: archived · 非生产 wording for lipsync/Seedance legacy docs (mind clear).

## [2.41.24] - 2026-08-07

### Changed (retired-weapon clear · mind surface round 4)
- **route-catalog:** `status=tombstone` valid; post-lipsync CLIs (`frw-lipsync`, `lipsync-*`) marked tombstone; `list_routes()` hides tombstone/deprecated by default; `get_route` still resolves hidden ids.
- **doctor:** `weapon_inventory` slim payload = primary `line` + `retired_count`/`experimental_count` + `mind.retired_do_not_plan` (no retired name thrash).
- **comfy_armory:** `select_weapon` never picks `research_weapons` (hard error on research id).
- **Tests:** route tombstone hide/lookup; research weapon not selectable.

## [2.41.23] - 2026-08-07

### Changed (retired weapon clear mind)
- **Default mind:** `aifilm weapon inventory` defaults to **primary only**; `--tier all|retired|experimental` + `--research` expand; report carries `retired_count` / `mind.retired_do_not_plan`.
- **Seedance unregister:** `SeedanceProvider` **not** in default registry; escape `AIFILM_ALLOW_SEEDANCE=1` re-registers; `get("seedance")` points to H3 / frw-api-i2v.
- **Docs:** hard-defaults「已退役勿规划」; weapon-inventory retired table; weapon-lane 退役折叠; memory `2026-08-07-retired-weapon-clear-mind`; plan `docs/plans/2026-08-07-retired-weapon-clear-todoplan.md`.
- **seedance_bridge:** docstring rebrand as Chinese motion prompt pack (not live Seedance spine).
- **wan_*_probe:** first-line 非生产 research-only.
- **Tests:** primary-only listing · retired not in demand_primary_index · seedance not registered · closed_loop expects comfy-h3/frw-api-i2v.
- **Web path fix / hard-compat:** `web_api` sibling console.html; dual_mix `primary_native_shot_ids` import; `extract_native_audio` stub; input_fidelity list cues speaker.

## [2.41.22] - 2026-08-07

### Changed (code slim round 2)
- **`comfy_video` Wan dead path:** `select_wan22_weapon` / `resolve_wan22_profile` / `build_wan22_i2v_prompt` fail-closed; graph body removed (~260 LOC).
- **`probe`:** connectivity-only (`schema_version` 2, `wan22_retired`); no longer gates H3 on missing Wan weights.
- **Web console package path fix:** `web_api._console_html` reads sibling `console.html` (not `web/web/`).
- **Web console package:** `web_core`/`web_api`/`asset_picker`/`gate_panel`/`onboarding`/`onboarding_planner`/`smoke_console` → `scripts/web/` + thin top-level shims.
- **C6 residual:** intentional top-level only hub + `workflow_pack` (matches metabolism freeze).
- **Tests:** Wan routing/graph retired assertions; websocket unit test no longer needs real `websocket-client`.

## [2.41.21] - 2026-08-07

### Changed (code slim · dead-logic consolidation)
- **Wan22 / FRW Wan:** `LocalComfyWan22Provider` + `FrwWanProvider` collapsed to construction tombstones (dead probe/generate bodies removed; still not registered).
- **Seedance mild gate:** `seedance` `generate()` requires `AIFILM_ALLOW_SEEDANCE=1`; subclasses `frw-api-i2v` / `frw-ltx23` unchanged.
- **composition_fill_gate:** implementation → `gates/composition_fill_gate.py` + thin top-level shim + `main()`.
- **Docs tax:** active slim board `docs/plans/2026-08-07-code-slim-consolidation-todoplan.md`; superseded pointers on major plans; `artifacts/README.md` + gitignore ops noise patterns.
- **Tests:** tombstone + Seedance allow gate; C6 residual no longer lists fill_gate as thick top-level.

## [2.41.20] - 2026-08-07

### Changed (monolith orchestrator relief · go next 到最后 · closeout)
- **W2 residual:** `plan/film_spec_validate_body.py` — BGM + shot loop + edit craft (~941 LOC allowlist).
- **`validate_film_spec` orchestrator ~136 LOC** (provider → body → soft → heat); drop from mega allowlist.
- **W3:** `preflight_premium` soft-read production-book (no hard crash on standard roots); harness `test_preflight_harness_w3`.
- **W4:** export builders already each <800 — file residual frozen bug-driven.
- **W5–W6:** deferred frozen; W7 board CLOSED — no third monolith plan.
- **Guard:** mega-fn allowlist tracks body + preflight + closeout + dispatch only.

### Fixed
- Premium preflight used `require_json` for optional production-book → bare roots raised FilmError.

## [2.41.19] - 2026-08-07

### Added (effect ROI · E1–E5 default muscle)
- **`gates/effect_roi.py`:** still-feed veto · soft-still lint · effect scorecard · weak-take reburn · face-lock promote assert.
- **dispatch:** fill/face/source red → **no** `h3-run-next` primary; still-challenge / ensure_fill first.
- **select-shortlist:** ban below-floor promote; face-lock triple hard legs block promote.
- **ship-prep:** writes `receipts/effect-scorecard.json` + `weak-take-reburn.json`; prefer_native auto `music-director draft`.
- **H3:** CLI `--mode` override requires `AIFILM_H3_MODE_OVERRIDE_REASON` or `AIFILM_ALLOW_H3_MODE_OVERRIDE=1`.
- **prompt:** dialogue/soft densify mouth + micro-life energy (family blend).
- **Docs:** hard-defaults row · stages/visual · plan · memory · iron-status gates.
- **Tests:** `tests/test_effect_roi_e1_e5.py`.

## [2.41.18] - 2026-08-07

### Added / Closed (H3 native chain · go to end)
- **True-film:** e-virus-ch06 `ship-native --light-process` → `film_native_stable.mp4` (19 clips, ~16MB, mean≈−19.6 dB, light ok). Evidence: `docs/reports/2026-08-07-h3-native-ship-light-evidence.md`.
- **Music Director:** re-exports `NATIVE_LIGHT_AF_FILTER` (same IRON as final.native_audio).
- **Orchestrator plan:** core SHIPPED; residual mega-fn bug-driven only.

## [2.41.17] - 2026-08-07

### Changed (monolith orchestrator relief · W2 validate sections)
- **`film_spec_validate_provider.py`:** I2V/H3/still/transition defaults (pre-shot).
- **`film_spec_validate_soft_gates.py`:** continuity/stance/performance/meaning/composition soft gates (uses existing lints only).
- **`validate_film_spec`:** ~1727 → ~1057 LOC; heat/provider/soft leaves assemble.
- **Tests:** write-spec + story_plan + heat paths green.

## [2.41.16] - 2026-08-07

### Added (H3 native light re-encode)
- **`apply_native_light_af_filter`**: post-concat optional audio re-encode with `NATIVE_LIGHT_AF_FILTER` (video copy); forbids agate/arnndn.
- **CLI** `aifilm h3 ship-native --light-process` · env `AIFILM_H3_SHIP_LIGHT_PROCESS=1`.
- Default remains concat `-c copy` for speed; light path is opt-in.

## [2.41.15] - 2026-08-07

### Merged
- Merge gitea/main (console command-center) with H3-native + final stage peels.

## [2.41.14] - 2026-08-07

### Changed (monolith orchestrator relief · W1.8 orchestration)
- **`render_final` ~456 lines** stage sequence (was 1155+): voice timeline · audio prep · dual mix · delivery report leaves.
- **Leaves:** `stages_voice_timeline` · `stages_audio_prep` · `stages_dual_mix.run_dual_track_mix_stage` · `stages_delivery_report`.
- **Guard:** mega-fn allowlist drops `render_final` (under 800).
- **Tests:** `tests/test_stages_w18_orchestration.py`.

## [2.41.13] - 2026-08-07

### Changed (H3 native chain close-the-loop)
- **h3 ship-native:** default out `film_native_stable.mp4`; receipt carries `NATIVE_LIGHT_AF_FILTER` + forbid agate/arnndn; legacy `film_native_h3.mp4` alias.
- **closeout:** accepts stable + legacy native plate paths.
- **music_director:** light numpy path documents FFmpeg counterpart constant.
- Tests: ship-native receipt + native light filter.

## [2.41.12] - 2026-08-07

### Changed (monolith orchestrator relief · W1.6 picture)
- **`final/stages_picture_concat.py`:** stretch plates · title/end cards · join intents/styles concat.
- **`render_final`:** stages 2–4 delegate to leaf (structure-only; lipsync stays off).
- **Tests:** `tests/test_stages_picture_concat.py`.

## [2.41.11] - 2026-08-07

### Added (Music Director R3 · batch + checklist)
- **`music-director batch --file`**: JSON/JSONL multi-shot mute/duck/peak edits.
- **`music-director checklist`**: export `receipts/music-director-checklist.{md,json}` prioritized listen list.
- **`audit --apply-peak-auto`**: stamp `peak_fix=auto` on hot stems.
- Tests for batch/checklist/peak suggestions.

## [2.41.10] - 2026-08-07

### Added (Music Director R2 · production harden)
- **ffmpeg decode** for non-wav native sources (mp3/m4a/mp4/clips) via `load_audio_samples`.
- **discover** expands to `clips/` + manifest clip paths.
- **light process** on apply (DC + ~80Hz highpass; no agate).
- **CLI** `music-director set` (mute window/entire, duck, peak) · `audit` (hot peak probe).
- Tests extended in `test_music_director_plan.py`.

### Fixed (Web 控制台 · 指挥台 · gitea/main)
- **起步 tab 复活：** `activateTab` 对 `onboarding` 调用 `loadOnboarding()`.
- **工作台指挥台：** 仪表盘指挥面板 + `/api/onboarding/go` · `/api/advance`.
- **致命错误浮条：** 全局 error/unhandledrejection.
- **e2e：** `smoke_console.py` 指挥台 DOM 断言.

## [2.41.9] - 2026-08-07

### Changed (monolith W2–W4 peels)
- heat validate tail · preflight_premium · export_html

## [2.41.8] - 2026-08-07

### Changed (monolith orchestrator relief · W1.4 subs)
- **`final/stages_subs.py`:** cue clock · SRT write/mirror · PIL burn or copy (`subs=off` default).
- **`render_final`:** stage 8 delegates to leaf (structure-only; HF caption owner / no double-burn policy unchanged).
- **Tests:** `tests/test_stages_subs.py`.

## [2.41.7] - 2026-08-07

### Changed (monolith orchestrator relief · W2)
- **film_spec_validate heat tail** → `plan/film_spec_validate_heat.py` (`apply_heat_cast_and_adult_tail`, ~650 LOC) structure-only.
- validate_film_spec body ~2360→~1727 span.

## [2.41.6] - 2026-08-07

### Changed (monolith orchestrator relief · follow-through)
- **W1.1:** `final/render_context.py` / `load_render_context` (shipped in prior commit on 2.41.5 line; documented here).
- **Tests:** `tests/test_final_stages_peel.py` (helpers, dual-mix, mux, context exports).
- **Docs:** `docs/plans/2026-08-07-dispatch-stage-map.md` · orchestrator relief W1.1 full.

## [2.41.6] - 2026-08-07

### Added (Music Director · H3 native desk)
- **`audio/music_director.py`**: draft / normalize / merge / apply / review for BGM + native voice (mute windows, mute_entire, peak_fix).
- **CLI** `aifilm music-director draft|apply|review` — plan at `audio/music-director-plan.json`; stems at `audio/native_directed/`.
- **final**: prefer directed native stems when apply receipt matches; overlay plan BGM duck on music_cue path.
- **Stages/memory/hard-defaults** pointers; tests `test_music_director_plan.py`.
- Wrong-line v1 = **audio mute** (picture unchanged).


## [2.41.5] - 2026-08-07

### Changed (monolith orchestrator relief · W1 peels)
- **`render_final` leaves:** `final/render_helpers.py` · `final/stages_dual_mix.py` · `final/stages_mux_manifest.py` · `final/stages_official_finalize.py` (structure-only; A5/PARTIAL/XOR semantics unchanged).
- **Guard:** `tests/test_mega_fn_budget.py` · dual-mix unit tests.
- **Plan:** `docs/plans/2026-08-07-monolith-orchestrator-relief-todoplan.md`.

## [2.41.4] - 2026-08-07

### Added (Film Production OS · W7 full cross-cut · plan CLOSED)
- **Performance direction:** `plan/performance_direction.py` · `aifilm plan performance-direction` — objective/subtext/body/eye/breath; emotion-only hard under `--strict`.
- **SoundCue model:** `plan/sound_cue_model.py` · `aifilm plan sound-cues` — typed cues + bridge flags.
- **Cinematography rules:** `plan/cinematography_rules.py` · `aifilm plan cine-rules list|resolve` (alongside `cine-lookup`).
- **Asset version chain:** `plan/asset_version.py` · `aifilm plan asset-version register|approved`.
- **Tests:** `test_film_production_os_w7.py` (7). Plan **W0–W7 CLOSED**.

## [2.41.3] - 2026-08-07

### Added / Changed (closeout · ROI gates + OS W7 + plan CLOSED)
- **Gates:** still face-lock resolve errors fail-closed (`STILL_SOURCE_RESOLVE_FAILED`); still provenance manifest read fail-closed (no silent empty).
- **Doctor F5:** `aifilm doctor --root` probes face-identity enroll / verified=false with `next_cmd`; red when gap.
- **W7 Performance:** optional acting layer on `performance_cue` — objective · subtext · eye · breath · tempo.
- **W7 Cine rules:** `plan/cine_rules.py` · `aifilm plan cine-lookup` · prompt compiler auto-suggests framing when empty.
- **Stages T8:** `stages/post.md` transition knife-edge three-liner.
- **Film Production OS plan:** W0–W7 MVP **CLOSED** (console Shot Card / full version chain deferred).
- **Tests:** `test_roi_gates_face_doctor.py` + W7 cases in `test_film_production_os_w5_w6.py`.

## [2.41.2] - 2026-08-07

### Added (Film Production OS · W5–W6 closeout)
- **W5 Prompt Compiler:** `plan/prompt_compiler.py` · `aifilm plan compile-prompt --shot-id --adapter h3|grok|generic` — execution artifact only; no project mutation; provider-leak lint.
- **W5 Take review:** `take_registry.set_take_review` + `aifilm takes compare|review` (performance/continuity/camera/artifacts + director_status).
- **W6 Revise plan:** `plan/revise_plan.py` · `aifilm plan revise --defect face|…` — minimal unit; never default whole-scene regen.
- **W6 Assembly gate:** `plan/assembly_gate.py` · `aifilm plan assembly-gate` — draft/rejected takes blocked from rough cut.
- **W3 composite:** `aifilm plan production-ready` (coverage + storyboard + animatic).
- **Tests:** `test_film_production_os_w5_w6.py`.

## [2.41.1] - 2026-08-07

### Added (Film Production OS · W3–W4 slice)
- **W3 Coverage Checker:** `plan/coverage_check.py` · `aifilm plan coverage-check` · receipt `coverage-check.json`; roles establish/CU/reaction/…; strict blocks `production_allowed`.
- **W3 Storyboard status:** `plan/storyboard_status.py` · `aifilm plan storyboard --action set|gate|status`; approve needs `--user-phrase`.
- **W4 Scene drama:** `plan/scene_drama.py` · `aifilm plan scene-drama` (dramatic_goal/conflict/turn/arc).
- **W4 Continuity audit:** `plan/continuity_audit.py` · `aifilm plan continuity-audit` (In→Out wardrobe/prop breaks).
- **Shims** + tests: `test_film_production_os_w3_w4.py`.

## [2.41.0] - 2026-08-07

### Changed (Heat plot-driven · highest ROI)
- **Policy:** `genre=adult` no longer silent-pins `heat_scale=max`. Default is **`hot` + `pinned_by=plot_driven`**. Full max IRON only on **explicit** pull (办事/尺度拉满/hardcore/dual/`heat_scale=max`).
- **Plan:** `derive_heat_scale` three-state; `detect_heat_signals` splits `_EXPLICIT_MAX_MARKERS` vs `_ADULT_INTENSITY_MARKERS`; target lift only for explicit_max (H3-nominal multiples).
- **Project:** plot-driven skips `challenge_max_scale` / sex_floor hard; keeps wardrobe no-redress product hard.
- **Gates:** `heat_check` / `heat_agent_status` hard-fail only when `heat_pinned_by=explicit_max` (or legacy max without plot_driven pin).
- **Onboarding:** heuristic adult → `hot`; default persist scale `hot`.
- **Docs:** hard-defaults adult pin row updated (covers 2026-07-29 silent-max).
- **Tests:** `test_heat_plot_driven.py` + adult heat / onboarding expectations.

## [2.40.112] - 2026-08-07

### Added (Film Production OS · W0–W2)
- **W0 docs:** `docs/plans/2026-08-07-film-production-os-todoplan.md` · `references/production-state-map.md` · hard-defaults / INDEX / CTO pointers; freeze anti-patterns (no second DirectorAgent, no screenplay→model).
- **W1 CreativeIntent:** `director_intent` fields theme/audience_emotion/protagonist_pov/genre/visual_language/pacing (+ nested `creative_intent`); `creative_intent_strict` gate.
- **W1 story structure:** `plan/story_structure.py` · `aifilm plan validate-structure` · receipt `receipts/story-structure.json`.
- **W2 Shot Cards:** `plan/shot_card.py` · purpose enum + aesthetic-only reject · `aifilm plan shot-cards`.
- **W2 Director Interpretation:** `plan/director_interpretation.py` · `aifilm director interpret-scene`.
- **Meaning gate:** `lint_shot_meaning` merges `SHOT_PURPOSE_AESTHETIC_ONLY`.
- **Tests:** `test_film_production_os_w1_w2.py` (18).

## [2.40.111] - 2026-08-07

### Added (Error Internalization & Web Console Integration)
- **Error Internalization Gates:** `gates/identity_generation_lock.py`, `gates/partner_cast_gate.py`, `gates/still_provenance.py` & `core/skip_audit.py`.
- **Web Console Deep Integration:** Integrated Onboarding Auto-Decompose, 5090 H3 Pipeline Queue Dashboard, and Delivery Honesty Rail into `console.html` and `review_ui.py`.
- **Tests:** `test_error_internalization_e1_e4.py`, `test_skip_audit.py`, `test_hard_defaults_memory_links.py`.

## [2.40.110] - 2026-08-07

### Changed (Web console UI · 电影工作室美学收尾 T3+T6–T12)
- **字体：** 引入 JetBrains Mono 作 `--font-mono`，asset/引擎 id 等机器串用等宽体提升扫读性（Space Grotesk + Sora 已就位）。
- **富化素材卡（仅真实 API 字段）：** 装饰性合成波形条（明确标注非真实音频，由 id 派生稳定高度）+ energy/duration/bpm/mood 指标 chip；主按钮「选入生产」+ 次按钮「跳过」（客户端 skipped 标记，重渲染不回弹）；API 无 peak/RMS/stem/waveform，绝不伪造音频指标。
- **筛选栏：** 文本搜索 + bgm 的 mood/energy 下拉（列表去重），客户端 180ms 防抖过滤 + 实时计数 + 空结果引导。
- **对比模式：** 每卡「对比」切换（上限 3），底部托盘 + 模态框按字段并排；切换 kind 清空对比集。
- **空/加载/错误态：** 骨架屏 shimmer、API 失败「重试」、空列表引导态。
- **响应式 + 动效：** 640px 表头横滚/网格单列/KPI 两列→单列；统一 `--ease` 缓动 token，保留 reduced-motion 降级。
- **工作台整合远端 workbench：** 保留电影工作室暖墨底+琥珀单强调美学（覆盖远端一度回退的 AI 味紫青渐变旧版），并吸纳远端「验片」iframe 内嵌 tab（data-tab=review）+ 仪表 tab（data-tab=overview）以通过 B1 single-shell 测试。后端契约零修改，`console` 门禁持续绿。

## [2.40.109] - 2026-08-07

### Changed (T5 edit_transition peel)
- **Peel** join craft + xfade graphs from `narrative/edit_policy.py` → `narrative/edit_transition.py` (~963 LOC).
- **Hard-compat:** `edit_policy` re-exports public + private craft symbols (`_CRAFT_WHY` etc.); top-level shim `edit_transition.py`.
- **edit_policy** residual ~1695 LOC (stretch / stance / motion / heat hooks).
- **Tests:** edit_policy + smooth_flow + transition suites green (106).

## [2.40.108] - 2026-08-07

### Added (F3 still face-lock bind · T4 plate transition_ops align)
- **`gates/still_face_lock_bind.py`**: archive still path hard-ban; cast enroll required before H3; pixel drift soft unless strict/max heat. Wired into `assert_still_source_safe` + `generation_request` + `generation_ready`.
- **`plan/plate_transition_align.py`**: align plate xfade styles to `transition_ops.picture`; continue ops must hard_cut; hard fail on missing style / continue-not-hard. Wired into `render_final` concat.
- **Tests:** `test_still_face_lock_bind_f3.py` (bind + plate align).
- **Docs:** hard-defaults F3/T4 · face-transition plan progress.

## [2.40.107] - 2026-08-07

### Changed (WebUI/router closeout · C3/C4/D1)
- **C3 stage single source:** `craft_spine.CRAFT_STAGES` re-exports `stage_model.CRAFT_EIGHT` (+ test).
- **C4 dispatch hot path:** `build_dispatch` caches film-spec + manifest reads (no triple re-read).
- **D1 web package:** `scripts/web/{routes,projection}.py` + `__init__`; top-level `web_routes` / `console_projection` shims.
- **Docs:** web-review-console package note.

## [2.40.106] - 2026-08-07

### Changed (route-catalog C1 orphan governance)
- **Reclass:** 36 hub-primary CLI (`dispatch`/`doctor`/`advance`/…) orphan → **canonical**; 60 other CLI-surface orphans → **partial** (`cli_only_not_spine`).
- **Orphan soft-cap tests:** count &lt;40 and ratio &lt;20%; hub primaries must not be orphan.
- **Docs:** CONTRIBUTING new-CLI must add catalog row; routing-map C1 note.
- **meta.c1_orphan_governance** recorded on catalog.

## [2.40.105] - 2026-08-07

### Added (F2 face-lock triple · T3 transition-frame closeout)
- **`gates/face_lock_triple.py`**: AND of face_identity · identity_generation · partner_cast; `master_eligible=false` on hard fail or IDENTITY_PARTIAL; `receipts/face-lock-triple.json`.
- **Official-final honesty**: annotate forces `OFFICIAL_FINAL_PLATE` when triple not master-eligible.
- **Closeout + ship-prep steps**: `face_lock_triple` · `transition_frame_audit`.
- **T3** `transition_frame_audit_closeout_status`: final+delivery → missing/stale audit hard (`transition_policy_soft` / `AIFILM_SKIP_TRANSITION_FRAME_AUDIT` escape).
- **Tests:** `test_face_lock_triple_f2.py` · `test_transition_frame_closeout_t3.py`.
- **Docs:** hard-defaults F2/T3 rows · face-transition plan progress.

## [2.40.104] - 2026-08-07

### Added / Changed (WebUI workbench · Wave B1 single shell)
- **Single shell nav:** 起步 · 选素材 · **验片** · 门禁 · **仪表** in `console.html` (no split external link as primary).
- **验片 tab:** lazy iframe → `/review` (token via sessionStorage); ↗ pop-out to dedicated page.
- **stdlib pages:** `/` and `/console` serve shell; `/review` serves review `_PAGE`; invite 303 → `/console`; serve URL → `/console?token=…`.
- **FastAPI serve URL** aligned to `/console?token=…`.
- **Tests / smoke:** shell tabs + `/review` page checks.
- **Docs:** `web-review-console.md` B1 page map.

## [2.40.103] - 2026-08-07

### Added (WebUI workbench · Wave B2 dispatch projection)
- **`console_projection.py`:** read-only `project_dispatch_for_console` (from `receipts/dispatch.json`, never rebuilds dispatch on GET) + `project_queue_snapshot` (media-queue + takes count).
- **`console_state`:** embeds `dispatch_projection` + `queue_snapshot` (fail-soft).
- **`console.html` overview:** production meter, next_cmd/why/weapon/blocked, **copy next CLI** button (clipboard only).
- **Tests:** `tests/test_console_projection.py`.
- **Docs:** `web-review-console.md` B2 fields.

## [2.40.102] - 2026-08-07

### Added / Changed (WebUI workbench · Wave A contract + FastAPI review parity)
- **`scripts/web_routes.py`:** single route table for stdlib + FastAPI (`handler_id`, domain, loopback flags); unified `error_body` → `{error, detail}`.
- **FastAPI `web_api` review parity:** `/api/status|action|settings|advance|final-review-*` + `/media/*`; exception handler emits dual error keys.
- **VALID_KINDS single source:** gateway no longer hardcodes a subset; `asset_picker.list_assets` owns kinds (incl. scene/prop).
- **stdlib `review_ui`:** error JSON also fills `detail` for parity.
- **Tests:** `tests/test_web_routes.py` (contract + openapi coverage + error body + status).
- **Docs:** `references/web-review-console.md` full route table; onboarding plan status → 主体已落地.

## [2.40.101] - 2026-08-07

### Changed (lock-face + edit transitions · default HARD)
- **Face identity default hard:** with `cast_masters`, missing enroll/audit receipt and enroll gaps raise at preflight (`assert_face_identity_passed`). Proven drift remains always hard. Legacy soft: `face_identity_soft: true` or `AIFILM_SKIP_FACE_IDENTITY_GATE=1`.
- **Transition policy / export read-back default hard:** continue soft-intent always hard; scene flashy / paragraph bad / soft-soup hard by default. Legacy soft: `transition_policy_soft: true` (continue still hard). Soft-style soup: `HF_TRANSITION_SOFT_SOUP` (punchy max run 2, auto/silk max 3).
- **Preflight** severity aligned with the above.
- **Tests:** FaceIdentityGateTests + transition policy/assert/readback + soft-soup cases.
- **Docs:** `docs/plans/2026-08-07-codebase-opt-face-transition-todoplan.md` · hard-defaults rows.

## [2.40.100] - 2026-08-07

### Added / Changed (H3 official P3.5 real-burn canary)
- **P3.5 densify A/B reburn** seed `202608074` · 6/6 takes at `artifacts/5090-evaluation/h3-official-ab-20260807/`.
- **Score (raw mean):** high official **28.92 >** legacy 26.92 (Δ+2); dialogue/soft mean still favor legacy.
- **Policy:** high auto → **official** densify (escape `AIFILM_H3_HIGH_MOTION_OFFICIAL=0`); dialogue stays official for `<d>` structure.
- **Evidence:** `artifacts/2026-08-07-h3-official-p35-canary.json` · `run_p35_reburn.py`.
- **Harden:** dialogue gate import soft-path; canary register=False + skip existing + inter-burn free.

## [2.40.99] - 2026-08-07

### Added / Changed (error internalization · E5 + E6.3 + F5)
- **E5 H3 mode override receipt:** `record_h3_mode_override` → `receipts/h3-mode-override.json` when CLI `--mode` ≠ plan resolve (no silent full-film i2v cover).
- **E6.3 SKIP iron set expand:** identity/partner/still/bulk/crop/pilot-go/caption-pixel/… in `IRON_SKIP_FLAGS` (hotpaths already on `skip_flag`; fallbacks remain).
- **F5 memory slim:** active cards **≤40** (archived 21 L4/session/canary cards); README refresh; hard-defaults/AGENTS archive pointers; soft-cap pytest.
- **Tests:** `test_h3_mode_override_e5.py` · F5 cap in `test_error_internalization_e1_e4`.

## [2.40.98] - 2026-08-07

### Added (error internalization · E1/E2/E4 + F4 flywheel)
- **E1 identity generation lock:** `gates/identity_generation_lock.py` — archive-path mix hard-fail; `face-identity.verified≠true` → `IDENTITY_PARTIAL`; closeout step + `receipts/cast-generation.json`; escape `AIFILM_SKIP_IDENTITY_GEN`.
- **E2 partner cast gate:** `gates/partner_cast_gate.py` — cast_master+face_lock paths; `style.locked` false-green when multi-cast incomplete; escape `AIFILM_SKIP_PARTNER_CAST`.
- **E4 still provenance:** `gates/still_provenance.py` — ban `midframe_paste`/composite provenance + `_archive_poison_*` paths on H3 I2V; escape `AIFILM_SKIP_STILL_PROVENANCE`.
- **E3 dual-truth fix:** hard-defaults native-speech row → light-process default (aligned with no-midframe card).
- **F4 dead-link test:** hard-defaults `memory/*` links must resolve; fixed archive pointers for input-fidelity / frw-i2i.
- **iron-status:** register composition_fill · identity_generation · partner_cast · still_provenance · skip_audit.
- **Tests:** `tests/test_error_internalization_e1_e4.py`.
- **Docs:** MEMORY_GOVERNANCE F0 flywheel · nutrient-matrix §2b.

## [2.40.97] - 2026-08-07

### Changed (H3 official · soft densify live canary DONE)
- **Live burn DONE:** `s_soft_portrait_official` seed `202608074` ~70s; mean **1.28** vs legacy **4.13** (−2.84) vs O3 official **1.47**.
- **Auto soft → legacy** (micro-life energy; densify did not close mean gap). High stays official densify; dialogue stays official.
- **Evidence:** `skills/ai-film-grok/artifacts/2026-08-07-h3-official-soft-live-canary.json`.
- **Escape:** force soft official via `AIFILM_H3_PROMPT_DIALECT=official`.

## [2.40.96] - 2026-08-07

### Added / Changed (Onboarding v2 · 闭环 + 启发式增强)
- **后端闭环（go 真正落盘）：** `voice_suggestions` → `film-spec.json["cast_voices"]`（按角色 id 合并，不覆盖既有）；`bgm_mood` 写入 `film-spec.json`；`scenes` → 新 canonical `intake/scenes.json`；`shot_hints` → 新 canonical `intake/shot-hints.json`。
- **启发式增强（无本地 LLM 兜底更聪明）：** 真实 `shot_hints`（按场景派生 action/camera）；`theme` / `tone` 推断（受氛围偏好 hint 覆盖）；多角色检测新增对白冒号前缀「名：」+ 更多言语动词；无名时也按 她/他 代词合成 女主/男主（或单 主角）占位卡司。
- **前端：** 拆解方案中「镜头提示」渲染为卡片（动作 + 机位）；新增「基调」可编辑字段。
- **测试：** 扩展 planner 启发式用例；新增 `_persist_canonical_v2` 落盘闭环测试（cast_voices / bgm / scenes / shot-hints / 合并既有）。

## [2.40.95] - 2026-08-07

### Changed (H3 official · live densify canary DONE → auto high official)
- **Live burn DONE:** `s_high_motion_official` seed `202608073` LocalComfyH3Provider after unload_models free; mean **24.86** vs legacy **20.67** (+4.19) vs O3 official **18.58** (+6.28); ~68s.
- **Auto high:** default official densify (`AIFILM_H3_HIGH_MOTION_OFFICIAL` default **1**); escape `=0` for legacy timeline.
- **Evidence:** `skills/ai-film-grok/artifacts/2026-08-07-h3-official-live-canary.json`.
- **Note:** soft-portrait not reburned (O3 soft official mean still low); human look still final.

## [2.40.94] - 2026-08-07

### Changed (H3 official prompt · R5 upgrade iteration)
- **Combo families:** `dialogue_mouth_official` / `high_motion_official` / `soft_portrait_official` + `R5_OFFICIAL_COMBO_ORDER` (`build_combo_matrix(round=5)`); `compile_family_author_prompt` routes `prompt_format=official` through `h3_official_prompt`.
- **Auto dialect:** R2V / multi-ref → official; high-motion stays legacy unless `AIFILM_H3_HIGH_MOTION_OFFICIAL=1`.
- **GUIDE gaps:** on-screen text (`onscreen_text` → `"…"`); multi-cue `<scenetrans>` continuity.
- **Plan dry-run:** `preview_official_h3_prompt` + `plan_h3_shot.prompt_preview` + `*.h3.preview.txt` receipt (no GPU).
- **Tests:** official scenetrans/opt-in/preview + combo R5 compile (40 green with combo suite).

## [2.40.93] - 2026-08-07

### Fixed / Changed (C6.5 core package imports + CI coverage floors real impl)
- **core/** imports real packages for mypy: `util.security_policy`/`runtime_policy`, `plan.director_review`/`film_spec_validate`, `media.*`, `assets.*`, `gates.*` (no top-level shim attr-defined).
- **`core/media_ops.parse_volume_stats`:** return type includes `raw_text: str`.
- **`make type` seed:** full core package (**21 modules** incl. film_io/media_ops/skip_audit/attestation/checkout_drift/gates).
- **CI coverage floors:** point at real impls `media/media_qa.py` · `gates/quality_evidence.py` · `assets/continuity.py` (not 100% shims); guard tests in `test_ci_roi_contract`.

## [2.40.92] - 2026-08-07

### Changed (H3 official prompt · densify P2.5 + receipt P3)
- **Base densify:** `_densify_base_action_tail` (half-second pose/fabric life on I2VA path).
- **Ref2VA densify:** `detailed_description` soft 350–500 words; `official_prompt_word_count`.
- **Receipt:** `run_h3_shot` writes `*.h3.meta.json` (+ `*.h3.official.txt` when official structure).
- **P3 reburn:** OPEN_OPS when Comfy queue busy (zero submit); compile progress in `artifacts/2026-08-07-h3-official-p25-p3-progress.json`.
- **Tests:** densify word-band + base half-second golden.

## [2.40.91] - 2026-08-07

### Changed (H3 official prompt · densify P2.5 + receipt P3)
- **Base densify:** `_densify_base_action_tail` (half-second pose/fabric life on I2VA path).
- **Ref2VA densify:** `detailed_description` toward GUIDE 350–500 words; `official_prompt_word_count`.
- **Receipt:** `run_h3_shot` writes `*.h3.meta.json` (+ `*.h3.official.txt` when official structure).
- **Tests:** densify word-band + base half-second golden.

### Fixed / Changed (C6.5 mypy dual-module unblock + core seed)
- **style_lock dual-module:** import real packages (`from assets import style_lock|face_identity`) in `core/gates` + `cli_media` (no `from scripts import …` / top-level shim).
- **mypy config:** `follow_imports=silent`; exclude top-level hard-compat shims `style_lock.py` / `face_identity.py` (package impls under `assets/` remain typed when listed).
- **`core/paths`:** import `util.security_policy` / `util.runtime_policy` (same pattern as C6.5 util fix).
- **`make type` seed:** + `core/constants` · `core/emit` · `core/paths` (**15 modules**, zero errors).

## [2.40.90] - 2026-08-07

### Fixed (C6.1 residual guard · eng closeout honesty)
- **`test_c6_migrate_queue_empty`:** allowlist `onboarding_planner.py` (Onboarding v2 auto-decompose; console entry, not vanity migrate).

## [2.40.89] - 2026-08-07

### Changed (H3 official prompt · GUIDE optimize P2)
- **Ref2VA multi-ref:** `_merge_official_refs` deep-merges `media_pack` / last / identity refs; duties land in `subject_definitions` / `retention_analysis` (absorbs legacy `r2v_ref_prompt_clause` dump).
- **Dense detailed_description:** Ref2VA path densifies env/light/wardrobe/half-second motion (soft ≥80 words unit floor).
- **Workflow:** official compile passes packed refs; legacy FLF/R2V free-text append still skipped on official prompts.
- **Tests:** `test_ref2va_multi_ref_duties_and_density` · `test_merge_refs_from_shot_last_path`.
- **Docs:** optimize plan P2 ✅.

## [2.40.88] - 2026-08-07

### Added / Changed (Onboarding v2 · 贴故事+图 → 出方案)
- **Onboarding 重做（agent 规划感）：** 从"填空格 3 步表单"改为「贴故事 + 主角图 → ✨让AI拆解 → 可编辑方案 → 确认启动」。故事为唯一必填项，主角图可选（仅存本地，不上云）。
- **启发式兜底：** 无本地 LLM（`AIFILM_LOCAL_LLM_BASE_URL` 未设）时 `onboarding_planner.deterministic_decompose` 自动拆解（识别主角/配角、推断类型/热度、规划分镜、建议声线+BGM 氛围），确保 onboarding 永不阻塞；配 LLM 时走私有 `local_llm.decompose`（fail-soft 回退启发式）。
- **新端点（双网关 FastAPI + stdlib 一致）：** `POST /api/upload`（字节校验 PNG/JPEG/WEBP，magic-byte 校验，0o600）、`POST /api/onboarding/brief`、`POST /api/onboarding/decompose`、`POST /api/onboarding/plan`、`GET /api/file`（只读工作区图片，path-escape 安全）。
- **首写 genre/heat_scale：** `go` 现经 `_persist_canonical_v2` 写入 `film-spec.json` 的 genre/heat_scale，解除"门禁立刻 403"的体验痛点；并落 `style-bible.json` / `intake-manifest.json` + 尝试 `drama_graph.derive_graph`。
- **控制台前端（console.html）：** Brief → thinking 步骤流（reduced-motion 友好）→ 可编辑角色/分镜/声线/BGM 方案卡片（llm/heuristic 来源徽章）→ 确认启动；保留「手动录入（高级）」折叠区向后兼容。
- **测试：** 新增 `test_onboarding_planner.py`（启发式分解单测）；`test_web_api` / `test_review_ui` 扩 onboarding 上传/拆解/plan/go、409 冲突、跨域 403、坏 token 401、file path-escape 404。
- **修复：** `review_ui.do_POST` 缩进错位（try 块越级）；`onboarding.handle_upload` 缺 `import os`；`onboarding` 多余 `import re`；`onboarding_planner` 未用 `LocalLLMError` 导入。刷新 `runtime-lock.json`。

## [2.40.87] - 2026-08-07

### Changed (CTO C6.5 mypy expand wave-2 + C6.3 Lane A guard)
- **`make type`:** + `util/config_loader` · `util/film_spec` · `util/structured_logger` (12-module seed, zero errors).
- **C6.3 guard:** `tests/test_c6_lane_a_delete_scan.py` freezes intentional zero-import residuals (examples/probes/tools); new dead whole-files fail closed.
- CI `typecheck` continues to run `make type` (list growth is automatic).

## [2.40.86] - 2026-08-07

### Added (C6.3 Lane A machine guard)
- **`tests/test_c6_lane_a_delete_scan.py`:** freezes 4 intentional 0-import residuals (examples / backend_probe / route_inventory); new dead modules fail closed.

### Changed (H3 official prompt · GUIDE optimize P0+P1)
- **`h3_official_prompt`:** align T2VA/I2VA/FL2VA/L2VA/Ref2VA with MiniMax HF guides — T2VA no Picture1; camera type+amplitude+speed; multi-speaker `(Sx)` + `<d>[Mandarin|English]`; FL/L duration align; optional music from bgm intent; stronger `validate_official_prompt`.
- **`h3_workflow`:** official path fail-closed validate; skip legacy FLF/R2V free-text append on official prompts; 2V stage remains legacy-only.
- **Docs:** `docs/plans/2026-08-07-h3-official-prompt-optimize-todoplan.md` · memory/hard-defaults/h3-core-day pointers.
- **Tests:** `test_h3_official_prompt` golden modes (12).

## [2.40.85] - 2026-08-07

### Added (CTO eng closeout · D7.2 + C6.3 empty + B3 OPEN_OPS)
- **D7.2 CI typecheck:** new `typecheck` job runs `make type` (scoped util mypy seed); included in `merge-gate` AND of required jobs.
- **C6.3 Lane A:** re-scan top-level non-shim modules → **0** safe-delete candidates (queue already drained; hard-compat shims retained).
- **B3 closeout canary:** `artifacts/2026-08-07-b3-ops-canary-closeout.json` — Comfy 18188 up; eng-day no exclusive drain → **OPEN_OPS** (honest partial success).
- **OPEN reconcile:** C5 full · C6.1/3/4/5 · D7.2/4 · B3 OPEN_OPS closed for eng-day; C4 remains **bug-driven only**; content P8 / B3.4 deferred.

## [2.40.84] - 2026-08-07

### Added (H3 official prompt dialect · O3 canary → auto)
- **`h3_official_prompt`:** MiniMax `h3-prompt-writing` serializer (`integrated_multimodal_description` / soundscape / music; Ref2VA six-section; `<d>[Lang]` dialogue).
- **Default dialect `auto`:** dialogue → official; high-motion → legacy timeline (canary mean); else official. Force via `AIFILM_H3_PROMPT_DIALECT=official|legacy`.
- **Round-2 high-motion densify** in official path (half-second pose thrash + strong camera + energetic soundscape).
- **Wiring:** `h3_workflow._prompt_for_shot` dialect switch; vendor pin `references/vendor/minimax-h3/`; hard-defaults + h3-core-day.
- **Evidence:** `skills/ai-film-grok/artifacts/2026-08-07-h3-official-ab-canary.json` (6/6 seed 20260807).
- **Tests:** `tests/test_h3_official_prompt.py`.

## [2.40.83] - 2026-08-07

### Fixed / Changed (CTO C6.5 mypy incremental expand)
- **Import path:** `util/{validators,subprocess,json_io,runtime_policy}` import `util.security_policy` (not hard-compat shim) so mypy sees real attributes.
- **`make type` list expanded:** errors · validators · time · paths · logger · json_io · subprocess · retry · security_policy (zero errors).
- Restores green `make type` seed after shim static-analysis breakage.

## [2.40.81] - 2026-08-07

### Changed (CTO C5.6 path externalization)
- **`util.paths.resolve_tool`:** portable tool lookup via `shutil.which` + existing brew/system bindirs.
- **Migrated:** `dialogue_scene_package` · `piper_local_tts` off hardcoded brew tool paths.
- **Docs:** `cosyvoice_local_tts` examples use `$HOME/...` (no `/Users/dex`).
- **Contract tests:** `test_c5_path_externalization` + `resolve_tool` units.

## [2.40.80] - 2026-08-07

### Added (CTO C6.4 base contracts · config_loader + core.gates)
- **`util.config_loader`:** env/bool/int resolve, fingerprint cache invalidate, `load_config` dict shape, `generate_example` safety header.
- **`core.gates.recompute_gates`:** empty film all-closed keys; brief+spec flip; invalid spec stays closed.
- CTO C6.4 mark expanded.

## [2.40.79] - 2026-08-07

### Fixed (CTO C5.5 subprocess timeout)
- **Hang protection:** `util.subprocess.run` / `run_compose_env` treat `timeout=None` as **60s** (thin facades can no longer disable timeouts by forwarding unset kwargs).
- **compose_render.run** default timeout **60s** (long renders still pass explicit 600/3600).
- **Contract tests:** `tests/test_c5_subprocess_timeout.py`.

## [2.40.78] - 2026-08-07

### Added / Fixed (CTO C6.1 empty verify + C6.4 base contracts)
- **C6.1 honesty:** re-scan confirms safe migrate queue empty; IRON residuals only. Guard test `test_c6_migrate_queue_empty` fails on new thick top-level outside residual set.
- **C6.4 `core.media_ops`:** contract tests for volumedetect parsers + `run_fn`-injected probe path.
- **C6.4 `util.film_spec`:** strict/soft/shot-iter contracts; **fix** `soft_load_spec` used strict `util.json_io.read_json` → now `util.soft_json` (missing/invalid → `{}`).
- Inventory pointer + CTO C6.1/C6.4 marks.

## [2.40.77] - 2026-08-07

### Added / Changed (CTO C5.3 JSON I/O single entry)
- **Facades only:** `compose_render` / `export_composition` / `final.io` thin `read_json` → `util.require_json_as` / `require_json_fnv`; `pilot_review.read_json = soft_json`; drop shadow `render_final` local def (re-export `final.io`).
- **Kill reimplementation:** `i2v_motion_gate` nested `json.loads` fallback removed; `elevenlabs_canary._write_json` → `util.write_json`.
- **Call-site soft/strict wave:** face_identity · tts_rehearsal · cli_graph_mutation · i2v_provider · auto_cut · compose_preview · context_routing · dispatch_compact → `soft_json` / `require_json_fnv` / `read_json`.
- **Contract tests:** `tests/test_c5_json_io_single_entry.py` (whitelist facades, no nested reimpl, no local `_write_json` dump).

## [2.40.76] - 2026-08-07

### Added (CTO eng-day · C5.2 FilmError + CLI skip residual + C5.1 expand)
- **FilmError inheritance wave (RuntimeError-safe):** `CloseoutError`, `QueueError`, `InputFidelityError`, `ComposeRenderError`, `ComposeExportError`, `H3WorkflowError`, `H3ShipNativeError`, `MediaQAError`, `RenderWorkspaceError` now inherit `util.errors.FilmError` (still `RuntimeError` via MRO).
- **CLI skip_flag residual:** face identity · motion mean · duration target · cinematic → ledger when film root known.
- **IRON_SKIP_FLAGS:** FACE_IDENTITY · MOTION_MEAN · DURATION_TARGET · CINEMATIC · CANONICAL_TRUTH.
- **C5.1 logger expand:** bulk_preflight variety skip + media_queue bulk_preflight skip → WARNING stderr.
- **B3 OPEN_OPS canary:** `artifacts/2026-08-07-b3-ops-canary-round2.json` (eng-day, no drain).
- **Tests:** `test_error_hierarchy` expanded · `test_cli_residual_skips_ledger`.
- **C5.4:** `docs/REVIEW_CHECKLIST.md` — `except Exception` must log+re-raise or explicit partial; new `*Error` must inherit FilmError.
- ValueError-based subsystem errors left for touch-migrate (no `except ValueError` break).

## [2.40.75] - 2026-08-07

### Added (honesty-rail R5 + skip touch-migrate wave)
- **R5 board reconcile:** honesty + CTO headers aligned to **2.40.75**; evidence report closed R0–R5.
- **skip_flag touch wave:** anti-hijack · generation_request · scale_promote · endframe · composition_fill · five_track · fidelity final · variety (cinematic/ship/bulk) · variety_pixel · dialogue package · motion core · meaning · narrative rebind · continuity prog · pilot-go · bulk preflight · crop-master · ship PK · h3 ship-native · caption pixel · render_final package skip.
- **IRON_SKIP_FLAGS** expanded: fidelity / composition_fill / motion_core / dialogue_package / meaning.
- **Tests:** `test_round2_hotpath_skips_ledger` in `test_skip_audit`.

## [2.40.74] - 2026-08-07

### Added (CTO C5.1 logging pilot)
- **util.logger** pilot wired into honesty hot path: `core/skip_audit` (skip armed WARNING + ledger write fail), `production_gates._env_skip_armed` fallback DEBUG, `core/checkout_drift` git fail DEBUG + drift INFO.
- **util package export:** `from util import log, set_level`.
- **Tests:** `tests/test_util_logger.py` (stderr routing / set_level / skip_flag log).
- Library logs stay on **stderr** (CLI JSON stdout contract intact). Env: `AIFILM_LOG_LEVEL`.

## [2.40.73] - 2026-08-07

### Fixed / Added (go-all · A1 residual + G0.4/D7.4 + A2.1 + B3 canary)
- **production_gates:** remaining env SKIP (anti-boring / headroom / transition×2 / style-bible / face / continuity) → `_env_skip_armed` + IRON ledger.
- **G0.4 / D7.4:** CI `validate-core` asserts `plugin.json` version in `docs/GRAPH.md` + README project-status.
- **A2.1:** `stages/deliver.md` ship-prep rows 15–17 (skip_usage / attestation / plate≠master).
- **B3 OPEN_OPS canary:** `artifacts/2026-08-07-b3-ops-canary.json` — Comfy 18188 up; eng-day no film drain → OPEN_OPS.
- **C6 scan:** low-importer thick top-level queue empty (terminal residual freeze).
- **Tests:** skip_audit anti-boring ledger + IRON secondary flags.

## [2.40.72] - 2026-08-07

### Added (web review console · local live smoke + PR gate)
- **`scripts/smoke_console.py`:** repo-relative live smoke harness that spawns the real `aifilm review-ui serve` on a loopback socket and drives the full console flow end-to-end (console page, gates panel, asset listing + bad-kind 400, console-state + recent_selections, onboarding, hash-bound select 200/409, blocking gate 403, cross-origin 403, bad token 401, media-lib path-escape 404). Stdlib-only driver; exits non-zero on first failure.
- **`make smoke-console`:** one-click local regression target mirroring the CI `console` job.
- **PR template:** added a "console 门禁须绿" checkbox (CI `console` job / `make smoke-console`) under 控制台改动自查.

## [2.40.71] - 2026-08-07

### Added (delivery honesty-rail R4 I5 ops · named contracts)
- **R4.1:** `test_run_next_soft_hog` — unowned `run-next` soft-cap max_jobs=5; until-empty requires ownership; OPEN_OPS receipt when refused.
- **R4.2:** `test_pgrep_no_source_match` — forbid `pgrep -f` invocations in scripts; `local_comfy_client_status` remains `ps` token method.
- **R4.3:** `test_openops_receipt` — drain end `open_ops_status=queue_empty|OPEN_OPS` (+ reason); isolates live GPU lease via mock.
- Board honesty-rail **R0–R4 CLOSED**; evidence report updated.

## [2.40.70] - 2026-08-07

### Fixed (honesty-rail R1 expand · more skip_flag wires)
- **skip_flag wired:** `gate_auto.skip_enabled(root)` · `i2v_motion_gate_skip_enabled(root)` · pilot / heat-queue / loop-risk via `production_gates._env_skip_armed` · `true_video_policy.policy_skip_enabled(root)`.
- **call sites:** closeout + cinematic pass film root into i2v skip.
- **Tests:** `test_skip_audit` pilot/gate_auto/i2v ledger scenarios.

## [2.40.69] - 2026-08-07

### Added (delivery honesty-rail R1 complete + R2 + R3)
- **R1 SKIP audit complete:** `sync_armed_env_skips` closeout pre-pass; `attach_skips_to_report` → `official-final-report.skips_used`; plate-boring + anatomy escape via `skip_flag`.
- **R2 attestation provenance:** `core/attestation_audit.py` ledger `receipts/attestation-ledger.json`; `require_anatomy_safe` / register-still·clip write provenance; missing reviewer/session → `pending_human_review`; closeout advisory step.
- **R3 checkout drift:** `core/checkout_drift.py`; `aifilm doctor` always records `checkout_drift` (HEAD mismatch → environment warning; dirty-only silent); `--checkout-drift` opt-in verbose.
- **Law:** hard-defaults row + memory `2026-08-07-delivery-honesty-rail.md`.
- **Tests:** `test_skip_audit` · `test_attestation_provenance` · `test_checkout_drift`.

## [2.40.68] - 2026-08-07

### Added (CI · web review console permanent gate)
- **Isolated `console` CI job:** `.github/workflows/ci.yml` now runs `pytest tests/ -m console` as a dedicated, isolated job (parallel to `hotpath`/`test-full`) so web-console regressions are caught independently of the broader suites. Wired into `merge-gate` `needs` so it is a required merge check.
- Covers stdlib + FastAPI gateways, `asset_picker` hash-bound select (200/409), fail-closed gate 403 (`WebConsoleForbidden`), canonical bindings, onboarding, and `console-state` aggregator.

## [2.40.67] - 2026-08-07

### Fixed / Added (A1 heat-final receipt + honesty-rail R0/R1 partial)
- **heat final receipt:** `assert_heat_allows_final` write failure → **ProductionGateError** (no silent `except pass` after final_ok).
- **skip_audit (R1 pilot):** `core/skip_audit.py` — `skip_flag` / `record_skip_usage` / `verify_skip_usage`; ledger `receipts/skip-usage.json`.
- **Wired:** heat-final env skip + cinematic `skip_enabled(root)` + closeout `skip_audit` step (IRON skip无 reason → PARTIAL).
- **Hotpath tests:** QueueHonesty also mocks foreign GPU lease (no live `lease_held_foreign` flake).
- **Plan:** delivery-honesty-rail Active; R0 + R1 partial ship.
- **Tests:** `test_opt_round_a1_heat_final_receipt.py`.

## [2.40.66] - 2026-08-07

### Fixed (CTO G0.2 dual-checkout + A1 state_index)
- **G0.2:** synced `~/.grok/ai-film-grok` → plugins tip via **git ff-only** (no hand copy); local `.workbuddy-ai` dirty left uncommitted.
- **state_index_gate:** `wardrobe_ladder` ImportError no longer silent-skip — hard `WARDROBE_LADDER_MODULE_MISSING` when non-full wardrobe / exact ids / heat max|hot; soft otherwise. Fallback `needs_ladder` for later missing-state checks.
- **keyframe probe:** `pick_best_keyframe` failures surface as soft `KEYFRAME_PROBE_ERROR` (keyframes/ fallback kept).
- **Tests:** `tests/test_opt_round_a1_state_index.py`.

## [2.40.65] - 2026-08-07

### Fixed (CTO A1 · measured VO map silent empty)
- **production_gates `_measured_map_for_root`:** when `receipts/tts-rehearsal.json` exists, corrupt/unreadable parse or module ImportError → **ProductionGateError** (no silent `{}` → est_vo hide measured loop-risk).
- Missing receipt still returns `{}` (est_vo path).
- **Tests:** `LoopRiskGateTests` corrupt / missing / valid receipt.

## [2.40.64] - 2026-08-07

### Added (localhost review console · P6–P11)
- **Fail-closed gate gate (P6):** `WebConsoleForbidden` (→403) distinct from `WebConsoleError`; `asset_picker.select_asset` refuses any selection/approval while a required gate `status=="fail"` (`blocking`). Wired into both the stdlib gateway (`post/review_ui.py`) and the FastAPI gateway (`web_api.py`).
- **Canonical asset bindings (P7):** `voice` selections pin `cast_voices` in `film-spec.json`; `character` selections set `characters[].selected` in `assets.json`; `shot` selections bind the precise candidate (`path`/`sha256`/`provider`) into `manifest.json` instead of a console placeholder. `scene`/`prop` are read-only. `_list_voices` always merges the fallback pool so pinning one never hides the other.
- **UX hardening (P8):** multi-tab `console-state` sync polling, ARIA tablist + arrow-key nav, `:focus-visible` ring, `aria-live` status, `prefers-reduced-motion` degrade (no magnetic/hero canvas/transitions), `preload="none"` lazy audio, windowed rendering (`PAGE=24` + "显示更多").
- **Console-state aggregator (P9):** `GET /api/console-state` returns ledger revision/counts, gate blocking + hard_fail, approved manifest clips, onboarding progress, and recent selections; powers the overview tab.
- **Docs & CI (P10):** `references/web-review-console.md` (architecture/security/data-contract/gate-semantics), `.github/PULL_REQUEST_TEMPLATE.md` with console self-check, and a `console` pytest marker registered in `pytest.ini` + `tests/conftest.py`.
- **Security core (`web_core.py`):** framework-agnostic shared by both gateways — token auth (URL param + `X-Review-Token` + HttpOnly/SameSite=Strict cookie), one-time invite, cross-origin rejection, path-escape protection, Range/Content-Range media streaming.

## [2.40.63] - 2026-08-07

### Added (iron I5 GPU/ops · multi-agent + dual-film)
- **run-next soft-hog honesty:** busy hold → `partial=true` + `halt_reason_code=RUN_NO_HOG_BUSY_HOLD` + open_ops (no bare ok without machine reason).
- **Unowned batch cap:** execute without ownership soft-caps `--max` to **5**.
- **Dual-film lease:** foreign `LEASE_HELD` blocks `run-next --execute` and `until-empty --execute` (`lease_held_foreign` / `RUN_LEASE_HELD_FOREIGN`) even with `--i-own-the-gpu` (must acquire/release).
- **CLI:** `h3 run-next --i-own-the-gpu`; iron-status lists `gpu_no_hog` gate.
- **Canary:** `artifacts/2026-08-07-i5-ops-canary.json` — CODE_CLOSED_OPS_PARTIAL (Comfy up but queue_busy + foreign lease; no overnight drain).
- **Tests:** `test_gpu_no_hog` + `test_h3_until_empty` foreign-lease / soft-cap.
- **Plan:** iron I5 code path closed; true exclusive overnight drain remains user-named OPEN_OPS.

## [2.40.62] - 2026-08-07

### Fixed (CTO A1.4 / hotpath · queue honesty isolation)
- **test_final_hotpath_contracts QueueHonesty:** mock `probe_comfy_capacity_soft` idle so live 5090 `COMFY_QUEUE_BUSY` cannot flaky-flip expected `queue_empty` / `capacity_not_ready` into `no_hog_busy_hold`.
- no_hog IRON still covered by `test_gpu_no_hog` (busy hold / idle pass / ownership override).

## [2.40.61] - 2026-08-07

### Fixed (CTO A1 silent-green · round 4)
- **cinematic_gate edit_rhythm:** probe exception was `ok=True skipped` → now **ok=False** (hard on heat max/hot/extreme).
- **iron_status:** plate_boring floor import fail → `plate_boring_meat_floor_error` (no silent omit).
- **post_audit premium:** audio/post bible probe exceptions → hard `*_BIBLE_PROBE_ERROR`.
- **final_stages caption:** SRT cue probe fail marks pixel_probe ok=false + `cue_probe_error`.
- **Tests:** `tests/test_opt_round_a1_cinematic_post.py`.

## [2.40.60] - 2026-08-07

### Added (shot generation · Wave 6 canary closeout)
- **Synthetic canary:** `artifacts/2026-08-07-shot-lane-canary.json` — 8 lanes + continue redress + no-speech lint (**ok=true**).
- **Regression:** `tests/test_shot_lane_canary_wave6.py`.
- **Plan CLOSED:** [shot-generation-lane](docs/plans/2026-08-07-shot-generation-lane-todoplan.md) Wave 0–6 DONE; H3 day board T3 still-prior CODE CLOSED cross-link.

## [2.40.59] - 2026-08-07

### Fixed (CTO A1 preflight bare except:pass · round 3)
- **preflight:** bare `except: pass` on VO drag / equal-slot PPT / heat arc+erotic / stance / loop_risk / vml·fch·mm / locations / P4 / continuity / voice_lang / compose-preview → **soft issue** (no silent green).
- **heat_arc_probe_error:** **hard** when `heat_scale` max|hot|extreme and `adult_max_iron` (default); meaningful_motion / P4 strict flags also hard on probe fail.
- Helpers: `_append_probe_error` · `_is_heat_max_iron`.
- **Tests:** `tests/test_opt_round_a1_preflight_pass.py`.

## [2.40.58] - 2026-08-07

### Added (shot generation · Wave 5 continue + env)
- **Continue handoff safety:** write/resolve mark `safe_for_continue=false` on poison source still, `ENDFRAME_REDRESS_RISK`, or composition-fill fail; next shot will not seed I2V from unsafe endframe.
- **H3 plan:** only passes continue endframe when resolve ok + safe.
- **Fill-Idle:** P0c reason `continue_handoff_blocked_need_safe_still` when parent endframe blocked.
- **Env heuristic:** missing `shot_role` + establishing/bridge DF (or faceless wide setup) → T2V/env lane.
- **Tests:** `tests/test_wave5_continue_env.py`.

## [2.40.57] - 2026-08-07

### Fixed (CTO A1 gates silent-green round 2)
- **cinematic_gate:** variety probe exception → hard red (no silent ok); adds **variety_pixel** step; five_track probe fail hard on heat max/hot/extreme.
- **preflight:** speaker_frame / dialogue_audio_lane / style_bible probe errors → **hard** when max dialogue_drama / heat max (was soft swallow).
- **Tests:** `tests/test_opt_round_a1_gates2.py`.

## [2.40.56] - 2026-08-07

### Added (shot generation · Wave 0–4 lanes)
- **Wave 0–1:** `shot_lane` + `aifilm shot-lane` + poison queue skip (`anatomy_safe=false`).
- **Wave 2:** dialogue still recipe / no-speech prompt / `dialogue_audio_lane` / VO-fit cut_on.
- **Wave 3:** `assert_still_path_ready_for_i2v` on h3 run + media-queue; pilot three_look fill+lane.
- **Wave 4:** bulk variety hard floors surfaced; **restricted insert without still → no silent T2V** (`INSERT_NEEDS_DETAIL_STILL`).
- **Tests:** `test_shot_lane` · `test_dialogue_wave2` · `test_composition_fill_wave3` · `test_wave4_variety_insert`.
- **Plan:** [shot-generation-lane](docs/plans/2026-08-07-shot-generation-lane-todoplan.md).

## [2.40.55] - 2026-08-07

### Added (shot generation · Wave 3 composition fill closed-loop)
- **`assert_still_path_ready_for_i2v`:** any I2V first-frame path + optional auto-remedy (stills/keyframes/handoff).
- **H3 run hard-block** postage-stamp / tiny subject after anatomy; plan advisory `composition_fill` + `generation_lane`.
- **media-queue** I2V/R2V first input same fill gate.
- **pilot pack** three_look machine prefill: composition_fill + per-shot generation_lane.
- **Tests:** `tests/test_composition_fill_wave3.py` · plan [shot-generation-lane](docs/plans/2026-08-07-shot-generation-lane-todoplan.md).

## [2.40.54] - 2026-08-07

### Fixed / Added (CTO A1 + iron residual optimization)
- **A1 gate-auto silent green:** `auto_promote_single_takes` respects shortlist `ok`/`promote_blocked`; variety probe exception no longer soft-greens; gate-auto runs **variety_pixel** hard when meat≥2.
- **I1.5 scale promote_ban:** shared `assert_scale_promote_allowed` on **register-still + register-clip** (root + nested decision).
- **I4.2 iron-status CLI:** `aifilm iron-status [--root] [--strict]` lists IRON gates + armed `AIFILM_SKIP_*` + floors.
- **Tests:** `tests/test_opt_round_a1_iron.py`.

## [2.40.53] - 2026-08-07

### Added (shot generation · Wave 2 dialogue chain)
- **Still recipe:** `lint_dialogue_still_recipe` / `assert_dialogue_still_for_register` — on_camera 台词镜须 speaker + 禁 WS/fullbody still；挂 `register-still approved` + preflight。
- **Prompt:** H3 `_prompt_for_shot` 对白镜禁 `no speech` / 禁开口类自定义句（`DIALOGUE_PROMPT_NO_SPEECH`）。
- **Audio lane:** write-spec `apply_film_dialogue_audio_lanes` 默认 `native`；preflight lint missing/invalid；`resolve_dialogue_audio_lane` 认显式字段。
- **VO-fit:** 对白镜自动 `cut_on=mid_motion` + `visual_fit=vo`（可无 dsl 时创建）。
- **Tests:** `tests/test_dialogue_wave2.py`。

## [2.40.52] - 2026-08-07

### Added (shot generation lane · Wave 0–1)
- **`shot_lane` projection:** `scripts/media/shot_lane.py` → lane ∈ setup/dialogue_*/meat/insert/env/continue/poison_blocked/reaction + H3 mode + gates + still/audio recipe.
- **CLI:** `aifilm shot-lane --root [--shot-id] [--write]`.
- **Fill-Idle:** `generation_lane` on rows; `anatomy_safe=false` → poison queue skip (aligned with `assert_still_anatomy_for_i2v`).
- **Docs:** visual 分型表 + 毒镜 5 行 SOP；weapon-lane-matrix **lane id** 列；plan [shot-generation-lane](docs/plans/2026-08-07-shot-generation-lane-todoplan.md).
- **Tests:** `tests/test_shot_lane.py`.

## [2.40.51] - 2026-08-07

### Added (iron internalization closeout · I2.2/I2.4/I1.4/I3/I4)
- **I2.4 generation request hard:** `assert_generation_request_for_i2v` for restricted/adult; media-queue fail-closed; H3 auto-build if missing. Escape `AIFILM_SKIP_GENERATION_REQUEST=1`.
- **I2.2 endframe no-redress:** `endframe_wardrobe` heuristic on `register-clip approved` (skin ratio drop → `ENDFRAME_REDRESS_RISK`). Escape `AIFILM_SKIP_ENDFRAME_WARDROBE=1`.
- **I1.4 mix default broadband:** `render_final` no longer defaults to acrossover multiband; opt-in `AIFILM_ALLOW_ACROSSOVER_MIX=1`.
- **I3 context:** slim `stages/visual.md` + `post.md`; routing adds `h3-core-day` + issue codes (wardrobe/plate-boring/shortlist/variety).
- **I4.1 contract:** `test_hard_defaults` locks plate-boring floor = meat mean 20 + anti-hijack gate smoke.
- **Plan:** iron internalization I0–I4 product path **SHIPPED** (I5 ops still OPEN_OPS).

## [2.40.50] - 2026-08-07

### Added (iron internalization I2 · anatomy + speaker-frame fail-closed)
- **I2.1 anatomy attestation:** `assert_still_anatomy_for_i2v` shared gate; **H3 run** + media-queue use it; poison still always blocks; restricted meat/undress shots require attestation even without film heat=max; genre=adult film-level require; bulk-preflight anatomy hard; escape `AIFILM_SKIP_ANATOMY_SAFETY=1`.
- **I2.3 speaker-frame hard unify:** `speaker_frame_hard_enabled` (dialogue_drama + max/hot/extreme|adult|genre adult); preflight + `assert_*` + **write-spec validate** fail-closed; escape `speaker_frame_strict:false`.
- **Tests:** `tests/test_iron_i2_anatomy_speaker.py`.

## [2.40.49] - 2026-08-07

### Added (iron internalization I1 · fail-closed anti-fake-green)
- **I1.1 multi-seed anti-hijack:** `composition_anti_hijack.multi_seed_anti_hijack_gate`; `select_shortlist` multi-seed without AH → `ok=false` (unless `AIFILM_SKIP_ANTI_HIJACK`); `pk_compare` multi-seed marks `not_promotable` + `PK_MULTI_SEED_NO_ANTI_HIJACK`.
- **I1.2 variety pixel bind:** `workflow_pack.variety_pixel_bind` → `receipts/variety-pixel.json`; ship-prep hard step `variety_pixel` (`VARIETY_FIELD_ONLY_STALE` / `ADJACENT_MEAN_CLONE` / missing meat clip|mean). Escape `AIFILM_SKIP_VARIETY_PIXEL=1`.
- **I1.3 plate-boring meat mean:** `final.delivery_class.assess_plate_boring_meat_mean` (meat avg&lt;20 or ≥50% weak) → force `OFFICIAL_FINAL_PLATE` + PARTIAL; closeout/export honesty; receipt `plate-boring-mean.json`. Escape `AIFILM_SKIP_PLATE_BORING=1`.
- **Tests:** `tests/test_iron_i1_fail_closed.py` + shortlist promote test uses intentional AH skip for dummy bytes.
- **Plan:** [iron-internalization](docs/plans/2026-08-07-iron-internalization-todoplan.md) I1 SHIPPED.

## [2.40.48] - 2026-08-07

### Changed (code metabolism terminal residual freeze)
- **Document freeze:** [inventory](docs/reports/2026-08-06-code-metabolism-inventory.md) marks safe migrate queue **DONE**. Intentional non-shim residual:
  - `aifilm_grok.py` — **CLI hub stays top-level** (growth via `cli/*` only; hub ≤2500).
  - `workflow_pack.py` — **no vanity package move**; peel pure leaves **only bug-driven**.
- **Guard tests:** `tests/test_metabolism_terminal_residual.py` (layout + inventory text).
- **SHIM_POLICY / module-refactor tracker** updated with the same iron.
- No product/behavior change.

## [2.40.47] - 2026-08-07

### Changed (code metabolism round 6 · path-depth residual P3-1×14)
- **Path-depth modules moved + depth fixed:** `config_loader`/`runtime_policy`/`security_policy`/`structured_logger`(import `logger`)→`util/`; `skill_registry`/`skill_runner`/`route_catalog`/`automation_verify`→`spine/`; `capability_report`/`motion_prompt_spine`/`optimization_metrics`→`plan/`; `backend_lock`/`env_plate`/`interactive_orchestration`→`media/`.
- **Depth rules:** skill-root `parents[1]`→`parents[2]` under packages; `config.env` via `parents[3]`; script siblings via `parent.parent / name`.
- **Inventory** refreshed (non-shim residual ~2, mainly hub + workflow_pack).
- **Verify:** path-depth suite 105 passed / 30 subtests; shim identity 10/10.
- Iron: public `import name` preserved; no heat/i2v/pilot retune.

## [2.40.46] - 2026-08-06

### Changed (code metabolism round 5 · P3-1×19 expanded residual)
- **19 domain modules** (no `__file__` depth risk) moved with hard-compat shims into `gates/` / `plan/` / `media/` / `post/` / `narrative/` / `spine/` (incl. `input_fidelity`, `state_index_gate`, `director_cli`/`review`, `true_video_policy`, `dailies`, `rhythm`, `pipeline_events`, …).
- **Inventory** refreshed (non-shim residual ~17).
- **Verify:** related suite 146 passed (+8 subtests).
- Iron: public `import name` preserved; path-depth hubs still residual.

## [2.40.45] - 2026-08-06

### Fixed (metabolism follow-up · antifragility source-path tests)
- **AF tests read real impl after P3-1 shims:** `test_antifragility_af` `shortform_director` / `optimization_program` / `elevenlabs_canary` now use `_impl_source(...)` instead of top-level shim files (shim has no `timeout=` bodies).
- **elevenlabs_canary metrics assertion** aligned with shipped path: 2×`subprocess.run` + `probe_native_audio_mean_volume(..., timeout=60.0)`.
- **Verify:** `tests/test_antifragility_af.py` 27 passed.

## [2.40.44] - 2026-08-06

### Changed (code metabolism residual closeout · P3-1×29 + inventory)
- **Safe residual queue emptied:** 29 low-importer domain modules relocated with hard-compat top-level shims: `semantic_index`, `transaction_receipt`, `creative_pipeline`/`quality`/`workshop`, `department_cli`/`contracts`, `external_review`, `master_delivery`, `real_footage`, `serial_quality`, `promotion_report`, `transition_frame_audit`/`transition_ops`, `shortform_director`, `optimization_program`, `plan_feedback`, `h3_timeline_prompt`, `speech_performance_timing`, `composition_anti_hijack`, quality/performance/evidence leaves, etc.
- **Inventory:** `docs/reports/2026-08-06-code-metabolism-inventory.md` (non-shim residual ~35 after star-reexport classification).
- **Verify:** targeted suite 320 passed / 1 skipped; shim identity probe 18/18.
- Iron: public `import name` preserved; no heat/i2v/pilot retune; giants left on-touch.

## [2.40.43] - 2026-08-06

### Changed (code metabolism round 4 · P3-1×10 + spine_helpers/render_defaults tests)
- **P3-1 migrate + hard-compat shims (10):** `cache`/`take_registry`/`motion_evidence`/`visual_text_repair`/`visual_text_audit`→`media/`; `performance_timeline`/`platform_package`→`post/`; `prompt_budget`/`optimization_dashboard`/`optimization_taxonomy`→`plan/`.
- **P4-1:** `tests/test_util_spine_helpers.py` (present/export_desktop_name) + `tests/test_final_render_defaults.py` (mix defaults).
- **Inventory** refreshed (non-shim top ~83→~73).
- Iron: public `import name` preserved; no heat/i2v/pilot retune.

## [2.40.42] - 2026-08-06

### Changed (CTO optimization · G0 + A1 fail-closed gates)
- **Single execution board:** `docs/plans/2026-08-06-cto-optimization-todoplan.md` (G0–Wave9). Old `next-optimization` / `optimization-todoplan` headers → RESIDUAL POINTER.
- **A1 fail-closed (gates):**
  - `quality_gates.evaluate_clip`: true-video infrastructure errors → `TRUE_VIDEO_POLICY_CHECK_FAILED` (no silent `ok:True` skip).
  - `production_gates` face-identity: corrupt `style-bible.json` → hard `STYLE_BIBLE_PARSE_FAILED` (never soft-skip).
  - `narrative_rebind`: graph_status probe failure → soft issue (not silent `pass`).
  - `cinematic_gate.assert_cinematic_gate_for_export`: record `ensure_machine_lane_error` when recovering via direct cinematic.
- **Tests:** `test_true_video_check_failure_is_fail_closed`, `test_corrupt_style_bible_is_fail_closed`.
- Iron: no heat/i2v/pilot retune; public CLI unchanged.

## [2.40.41] - 2026-08-06

### Changed (code metabolism round 3 · P3-1×10 + coerce_optional_float + core.constants tests)
- **P3-1 migrate + hard-compat shims (10):** `review_pack`/`picture_lock`/`auto_cut`/`local_omni_review`→`post/`; `speech_preview`→`audio/`; `reference_audit`→`media/`; `shortform_motion`/`prompt_compression_pilot`/`optimization_experiments`/`motion_plan`→`plan/`.
- **Peel:** `post/render_final.coerce_optional_float` for optional `in_point_sec`.
- **P4-1:** `tests/test_core_constants.py` (5 cases) for zero-coverage `core.constants`.
- **Inventory** refreshed.
- Iron: public `import name` preserved; no heat/i2v/pilot retune. Concurrent dirty `cli_pilot`/`cli_write_spec` left untouched.

## [2.40.40] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 4 测试缺口补漏 · P4-3)
- **P4-3 补 `core/emit.py` 测试（合并两名 agent 的并行实现）**：最终 `tests/test_core_emit.py` 共 11 用例，确定性、`capsys` 捕获、零依赖。覆盖：默认 compact（非 TTY 且无 env → `separators=(",",":")` 单行无空格）、`AIFILM_PRETTY_JSON` 取 `1/true/yes/on` 四态均 pretty（`indent=2` 且 `json.loads` round-trip）、`isatty()` 直测 TTY 分支、env=`0` 仍 compact（仅 1/true/yes/on 计入）、`ensure_ascii=False` 保留中文、嵌套/空 dict round-trip。ruff 干净，11 passed。（另一 agent 的 `c128dd3` 也独立加了 3 用例版，rebase add/add 冲突后取并集。）
- **顺带修复 `runtime-lock.json` 脚本指纹漂移**（恢复 `doctor` 全绿）：`d87fa36` 包化 5 个模块时改了 `scripts/spine/dispatch.py` 却未再生 lock（`doctor` 报 `script fingerprint drift`、CI 硬失败）；`c128dd3` 又包化 8 模块并再生了完整 lock（52 行）。最终 lock 采用 `c128dd3` 的完整再生版，`make lock-runtime` 复核 `doctor.ok=true`、`core_readiness.ok=true`、`failed=[]`。
- **下一步 P4 候选**（仍零覆盖，`util/core/node/final`）：`util.spine_helpers`、`core.constants`、`final.render_defaults`/`voice_mix_config`/`caption_text`、`node.backend_probe`/`latentsync_adapter`/`musetalk_adapter`/`stable_audio_probe`、`final.bgm_spotting`/`enhance`/`io`/`tts_tracks`/`watchdog`。另：23 个既有测试失败 + 75 个 `scripts/` ruff 违规可立项为独立稳定化/清理 phase。

## [2.40.39] - 2026-08-06

### Changed (code metabolism round 2 · P3-1×8 + plate-slot peel + core.emit tests)
- **P3-1 migrate + hard-compat shims (8):** `render_workspace`→`post/`, `vo_atempo`→`audio/`, `context_routing`→`spine/` (fix `SKILL_ROOT` depth parents[2]), `benchmark`/`product_brief`/`planning_autopilot`→`plan/`, `provider_canary`→`media/`, `elevenlabs_canary`→`audio/`.
- **Peel:** `resolve_plate_slot_sec` used for cue-window plate slot and visual-fit slot (default=0 path) in `post/render_final`.
- **P4-1:** `tests/test_core_emit.py` (3 cases) for zero-coverage `core.emit` (TTY vs compact vs `AIFILM_PRETTY_JSON`).
- **Inventory:** `docs/reports/2026-08-06-code-metabolism-inventory.md` refreshed (non-shim top ~92→~84).
- Iron: public `import name` preserved via shims; no heat/i2v/pilot retune.

## [2.40.38] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 4 测试缺口补漏 · P4-2)
- **P4-2 补 `core/film_io.py` 首测**（确定性清单/目录树 IO 模块，此前零覆盖）：新增 `tests/test_core_film_io.py`（9 用例，纯函数、`tmp_path` 隔离、零网络/ffmpeg 依赖）。覆盖全部 8 个对外契约：
  - `empty_manifest`：结构形态（title/theme/aspect、portrait 9:16 维度 width>0 且 height>width、必需键齐备）；`gates` 恰有一个 `True`（键 `brief`）；`created_at`/`updated_at` 均为含 `T` 的 ISO 字符串。
  - `film_dirs` / `ensure_tree`：7 个子目录（prompts/canonical/keyframes/clips/audio/out/receipts）均被创建且位于 root 下。
  - `save_manifest` / `load_manifest`：往返保留 title/aspect；缺失文件抛 `FilmError`。
  - 导演笔记：`director_notes_path` 指向 `director_notes.json`；`save`/`load` 往返一致；缺失时回退为空 `dict`（不抛）。
- ruff 干净，9 passed。纯增量、未动模块本体，`runtime-lock.json` 无需再生；`make doctor` 不受影响（仍全绿）。
- **顺带修复 Round 18/19 迁移遗留的测试 import 断点**（恢复 `tests/` 整套 CI 可收集）：`color_grade` 在 R18 迁到 `post/`、`golden_suite` 在 R19 迁到 `gates/`，但 `tests/test_closed_loop.py` 与 `tests/test_professional_golden.py` 仍在用旧顶层名，导致整套 `pytest tests/` 收集期 2 个 `ModuleNotFoundError` 中断。已分别改为 `from post.color_grade import plan_shot_grades` / `from gates.golden_suite import validate_golden_contract`（`tests/conftest.py` 已把 `scripts/` 注入 sys.path，包导入可解析）。修复后整套 `tests/` 收集恢复零错误。
- **下一步 P4 候选**（仍零覆盖，`util/core/node/final`）：`util.spine_helpers`、`core.emit`、`node.backend_probe`/`latentsync_adapter`/`musetalk_adapter`/`stable_audio_probe`、`final.bgm_spotting`/`caption_text`/`enhance`/`io`/`tts_tracks`/`voice_mix_config`/`watchdog`。优先挑纯函数/确定性者。

### Changed (code metabolism · P3-1 migrate + hard-compat shims + render_final peel)
- **Inventory:** `docs/reports/2026-08-06-code-metabolism-inventory.md` (DELETE/TOMBSTONE/MIGRATE/PEEL).
- **P3-1 migrate + thin top-level shims:** `vo_lint`→`narrative/`, `native_text_gate`→`gates/`, `seedance_bridge`→`media/`, `show_package`→`post/`, `gold_calibration`→`plan/`.
- **Compat shims added** for earlier moves missing hard-compat: `golden_suite`, `color_grade` (fixes collection ImportError on `test_professional_golden` / `test_closed_loop`).
- **Peel:** `resolve_plate_slot_sec` pure helper in `post/render_final` for silence/native caption-clock plate duration.
- Iron: public CLI import names preserved via shims; no heat/i2v/pilot retune.

## [2.40.37] - 2026-08-06

### Added (Real-ESRGAN formal upscale · canary → CLI → hooks)
- **Canary A/B 绿**：`aifilm upscale canary`；证据 `registry/evidence/realesrgan-canary-ab-20260806.json`（352×608→704×1280，ncnn `realesr-animevideov3`×2，~5.8s/1.5s@M1，audio copy；A=ffmpeg 0.27s）。
- **CLI**：`aifilm upscale plan|run|promote|canary` — 默认不 promote；GPU busy 零 submit；`--i-own-the-gpu` 显式放行。
- **核心**：`media/realesrgan_upscale.py`（ncnn 帧超分 + pad 到目标画布 + receipt）。
- **挂钩**：doctor soft `realesrgan`；next 在 `upscale.enabled` 时推 formal；H3 `ensure_h3_delivery_geometry(mode=ffmpeg|realesrgan|auto)` / env `AIFILM_H3_GEOMETRY`（**默认仍 ffmpeg**）。
- **测试**：`test_realesrgan_upscale.py` + probe；默认生产 **off**。
- **策略脚手架**：hard-defaults + memory + weapon `realesrgan-animevideo-research` + optimization challenger。

## [2.40.36] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 4 测试缺口补漏 · P4-1 续)
- **P4-1 补 `core/paths.py` 首测**（安全边界模块，此前零覆盖）：新增 `tests/test_core_paths.py`（11 用例，纯函数、零依赖、确定性）。覆盖三类对外契约：
  - `valid_shot_id`：合法模式（`s01`/`Shot-1_a`/64 长边界）返回原值；非法（`""`/`..`/`../x`/`/etc/passwd`/`a b`/`a.b`/65 长）抛 `FilmError`。
  - `film_output_path`：返回 `root/out/<name>.mp4` 且后缀为 `.mp4`；非法后缀（`.exe`）/路径穿越（`../escape.mp4`）/绝对路径（`/tmp/...`）均抛 `FilmError`。
  - `record_file_matches`：文件存在且 sha256 匹配→`True`；sha 不符/文件缺失/空 sha/缺 sha/非 dict 记录/无 path 字段→`False`（含 `field` 必填 kw 的调用修正）。
- ruff 干净，11 passed。未动模块本体，`runtime-lock.json` 无需再生；`make doctor` 不受影响（仍全绿）。
- **下一步 P4 候选**（仍零覆盖，`util/core/node/final`）：`util.spine_helpers`、`core.emit`/`core.film_io`、`node.backend_probe`/`latentsync_adapter`/`musetalk_adapter`/`stable_audio_probe`、`final.bgm_spotting`/`caption_text`/`enhance`/`io`/`render_defaults`/`tts_tracks`/`voice_mix_config`/`watchdog`。优先挑纯函数/确定性者。

## [2.40.35] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 3 迁移 & 去重 · P3-1 续 + 关键发现)
- **关键发现 — 顶层"重复模块"实为硬兼容 shim**：重新扫描发现 19 个零 importer 顶层模块里，**16 个有同名 package 副本且顶部 0 个顶层 def**——实为 W6/W7 包化迁移留下的 `sys.modules[__name__] = _impl` 兼容 shim（`audio_node_service`/`burn_srt_pil`/`cli_hub_residual`/`comfy_broker_service`/`duration_target`/`face_identity_hash`/`film_spec_lints`/`lipsync_*`/`mmaudio_*`/`shot_package`/`story_normalize` 等）。它们**不是** P3-1 待迁债务，而是延后的"兼容清理"阶段对象（部分仍被 `final_stages.py`/`*.ps1`/`runtime_policy.py` 按字符串路径调用）。故 P3-1 零 importer 真实可迁模块已基本见底。
- **P3-1 再迁 1 个真实模块**：`golden_suite.py`（零 importer、无 `__file__`/shell/跨脚本引用、非 shim）迁到 `gates/`（"golden contract" 校验语义归属校验门）。累计 **10/109+**（109 含 16 个 shim + 已包化的镜像计数，真实待迁远少于此）。
- **P4 补缺 — `golden_suite` 首测**：该模块此前零覆盖，新增 `tests/test_golden_suite.py`（4 用例，纯函数、零依赖）：有效契约 `ok=True` 无 issues；`GOLDEN_FORMAT_INVALID`（9:16/45s 不符）、`HUMAN_APPROVAL_MISSING`、`KEY_DIALOGUE_CHECKSUM_INVALID` 三类违规正确报 issue。ruff 干净，4 passed。
- **`runtime-lock.json` 再生**（`make lock-runtime`）：同步 `golden_suite` 路径变更。`make doctor` `runtime_lock.ok` 维持 `true`、0 errors，门禁全绿。
- 下一步开放项：① 危险模块（`backend_lock`/`burn_srt_pil`/`comfy_broker_service`/`lipsync_*`/`mmaudio_*`/`seedance_bridge`）需先改字符串路径调用方再迁，单独规划；② 16 个 shim 的兼容清理阶段（确认无调用后删除 + 更新 invoker）；③ P4 续覆盖 util/core/node/final、P5-1 扩 mypy 扫描。

## [2.40.34] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 3 迁移 & 去重 · P3-1 续)
- **P3-1 再迁 3 个业务模块**（累计 9/109+）到既有 package：`color_grade.py`→`post/`、`dailies_selects.py`→`post/`、`source_chain.py`→`assets/`（均 0 importer、无 `__file__` 相对资源路径、无 shell/跨脚本路径引用、`git mv` 保留历史）。
- **既有 1:1 测试随迁移更新**：3 个模块**已有** `tests/test_*.py`（共 17 用例），迁移时把 import 从顶层 `from X import (...)` 改为 `from post.X import (...)` / `from assets.X import (...)`；无 `@patch` 指向模块名，无测试体内 `X.` 前缀引用，改动面最小。
- **`runtime-lock.json` 指纹重生（关键修复）**：上一轮（v2.40.33）迁 4 个探针时只同步了 `registry/comfy-weapons.json`，**漏更 `runtime-lock.json`**——本次 `make lock-runtime` 一次性修掉这 4 个探针的路径漂移，并顺带消掉并发 `h3 8s cap` 合并带来的存量内容漂移（`adapters/`、`audio/`、`gates/`、`final/`、`media/h3_workflow.py`、`spine/advance.py` 等）。重生后 `make doctor` 的 `runtime_lock.ok` 由 `false`→`true`、`core_readiness.failed_checks` 由 `["runtime_lock"]`→`[]`，门禁恢复全绿。
- 全仓 grep 确认无 dangling 顶层引用；3 测试 17 passed；ruff 干净；`make doctor` 全绿。

## [2.40.33] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 3 迁移 & 去重 · P3-1 续)
- **P3-1 再迁 3 个媒体探针模块**（累计 6/109+）到 `media/`：`seedvr2_probe.py` / `wan_dancer_probe.py` / `wan_fun_control_probe.py`（均 0 importer、无 `__file__` 相对资源路径、`git mv` 保留历史；依赖 `comfy_armory`/`comfy_video` 仍为顶层模块，迁移零回退）。
- **既有 1:1 测试随迁移更新**：3 个探针**已有** `tests/test_*_probe.py`（共 12 用例），迁移时同步把 import 从顶层 `from X import` 改为 `from media.X import`，并把 `@patch("X._json_request")` 改为 `media.X._json_request`（修掉导入时绑定导致的 patch 失效）。这暴露并修正了一个既有隐患——测试原本只因模块在顶层才通过。
- **registry 引用同步**：`registry/comfy-weapons.json` 3 处武器 `probe_command` 从 `scripts/<name>.py` 改为 `scripts/media/<name>.py`，保证迁移后武器命令仍可定位模块。GRAPH/references 仅为文案提及，无需改。
- 全仓 grep 确认无 dangling 引用；registry JSON 校验通过；3 测试 12 passed；ruff 干净。

## [2.40.32] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 5 收尾 · 类型/文档/可复现)
- **[P5-2] 修文档漂移**：`make sync-docs` 已把 README/GRAPH 的 marker 块版本指针对齐当前版；另手动对齐 README 顶部「版本」表（2.39.69→2.40.31）与「插件元数据/版本」表（2.39.56→2.40.31）——这两处硬编码指针不在 sync-docs 的 marker 块内、脚本不覆盖，此前是真实漂移。建议 CI 加"README/GRAPH 全部版本指针 == plugin.json"校验。
- **[P5-3] 修可复现性**：仓库根此前**无任何依赖清单**。已生成 `requirements.lock`（479 行，运行时 Python 3.11.15 全环境冻结；已过滤 `-e` editable 本地路径如 `/Users/dex/YDEX/...`，避免破坏克隆复现）。后续可裁剪为项目真实 import 集合或改用 `--require-hashes`。
- **[P5-1] 类型均匀化（增量门禁已立）**：`skills/ai-film-grok/pyproject.toml` 新增 `[tool.mypy]`（`mypy_path="scripts"` + `explicit_package_bases=true`，解决 `scripts/` 自带 `__init__.py` 引发的模块名双映射）；新增 `make type` 作为 mypy 增量门禁**种子**，首批只扫已干净的 `util/validators.py` + `util/errors.py`（无错误）。全树扫描暴露 2315 处类型错误（跨 187 文件，集中在 `post/export_composition`/`core/gates` 巨型文件）——系真多轮工程，按"每清一模块即扩 `make type` 扫描列表"逐步推进，不一次性强开全树门禁。

## [2.40.31] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 4 测试缺口补漏 · P4-1 续)
- **零覆盖基座再补漏（P4-1）**：`util/validators.py`（`slugify` / `aspect_dims`，全局输入校验地基、此前零单测）补 `tests/test_util_validators.py`（10 用例，纯函数、零依赖、确定性）：`slugify` 大小写/空白/下划线/斜杠归一、连字符折叠、首尾去杠、CJK 保留、空串兜底为 `film`；`aspect_dims` 查表 5 档 + 不支持抛 `FilmError` 且错误信息含可用档。`ruff` 经 `--fix` 干净。
- **路线图**：P4-1 继续覆盖 `util`(subprocess/errors)、`core`(film_io/paths/constants/media_ops)、`node`(GPU 适配)、`final`(单元层)；P4-2 跟进校验类 `film_spec*`/`story_contract`/`subtitle_typesetter`/`edit_policy_*`。

## [2.40.30] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 3 迁移 & 去重 · P3-1 续)
- **P3-1 再迁 2 个 legacy 模块**（累计 3/109），均 0 importer、无 `__file__` 相对资源路径，`git mv` 保留历史：
  - `scripts/wan_s2v_probe.py` → `media/wan_s2v_probe.py`（Wan 2.2 声音条件 I2V 只读就绪探针；依赖 `comfy_armory`/`comfy_video` 仍为顶层模块，迁移零回退）。
  - `scripts/stable_audio_adapter.py` → `audio/stable_audio_adapter.py`（本地 Stable Audio 渲染器；`Path(__file__)` 取自身路径与位置无关，迁移零回退）。
- **1:1 测试**：`tests/test_wan_s2v_probe.py`（3 用例，`_model_names` 纯函数 + `probe_wan_s2v` 伪造 HTTP 层断言就绪/缺失 class_type 报告）、`tests/test_stable_audio_adapter.py`（3 用例，`_sha256` 与 hashlib 一致 + `_pinned_local_model` 拒 symlink/拒 checkpoint SHA 失配，torch 重依赖懒加载故纯测无需 GPU）。
- 全仓 grep 旧顶层路径无 dangling 引用。

## [2.40.28] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 4 测试缺口补漏 · P4-1 起手)
- **零覆盖基座测试起步（P4-1）**：`util/retry.py`（`retry_call` / `poll_until`，全局重试地基、此前零单测）补 `tests/test_util_retry.py`（8 用例，全用注入式 fake `sleep`/`clock`，确定性零等待）：首试即成功不 sleep；指数退避直到成功；全失败抛末次异常且 sleep 次数 = attempts-1；`retry_on` 不匹配即立即透传；`attempts<1` 报 `ValueError`；`poll_until` 就绪即返回不 sleep；超时抛 `TimeoutError`；`timeout_sec<=0`/`interval_sec<0` 参数校验。
- **路线图**：P4-1 继续覆盖 `util`(validators/subprocess/json_io/errors)、`core`(film_io/paths/constants/media_ops)、`node`(GPU 适配)、`final`(单元层)；P4-2 跟进校验类 `film_spec*`/`story_contract`/`subtitle_typesetter`/`edit_policy_*`。每补一个零覆盖模块即一个 PR，测试不降绿。

## [2.40.27] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 3 迁移 & 去重 · P3-1 起手模板)
- **首个 legacy 模块迁移（P3-1 模板）**：`scripts/ltx23_audio_canary.py`（66 行、零 importer）迁入 `audio/ltx23_audio_canary.py`。`_ROOT` 深度由 `parent.parent` 调为 `parent.parent.parent`（文件下沉一层到 `audio/`，仍指向 skill package 根，模板路径 `templates/comfy/ltx23-native-i2v-pilot-api.json` 解析结果与迁移前逐字节一致）。全仓 0 处引用该模块（无 importer、无动态按名加载），删除旧顶层文件零回退风险。
- **1:1 测试**：`tests/test_ltx23_audio_canary.py`（4 用例，锁定 `compile_audio_conditioned_workflow` 公共契约：缺参/帧越界/非 8n+1 抛 `ValueError`；合法调用注入 `source.image`/`audio_source`/`audio_encode`/`318.audio_latent` 链）。这是 P3-1 "每移一个补 1:1 测试" 的示范。
- **迁移配方（供团队复刻剩余 ~108 模块）**：见 `docs/senior-dev-code-quality-plan-2026-08-06.md` §P3-1 末尾「迁移配方」。核心：① `ast` 扫 top-level 模块按 importer 数排序，优先挑 **0–1 importer** 的低风险模块；② 按职责归入 `audio/gates/media/plan/util` 等 package；③ 调整一切 `__file__` 相对深度；④ 全仓 grep 旧模块名确认无 dangling 引用；⑤ 加 1:1 契约测试；⑥ 单 PR 单模块、测试不降绿、双远端 `fetch --all` 后收敛推送。

## [2.40.26] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 3 迁移 & 去重 · P3-2 路径外部化)
- **新增 `util/paths.py`（P3-2 基础设施）**：集中收口原本散落在 5 个模块里的 macOS-only 硬编码路径，提供三个纯函数——`plugin_root()`（从 `__file__` 推导插件根，绝不写死用户目录）、`homebrew_bin()`（按平台探测 `/opt/homebrew/bin` 或 `/home/linuxbrew/.linuxbrew/bin`，不存在则返回 `''`）、`build_subprocess_path()`（仅当 homebrew 存在才前置、永远带齐系统 bindir）、`first_existing_file()`（候选文件逐项 resolve 取首个存在者）。
- **消除"仅本机可跑"陷阱**：`adapters/piper_local_tts.py` 的 `DEFAULT_ROOT` 由 `/Users/dex/.grok/ai-film-grok/piper-voices` 改为 `plugin_root() / "piper-voices"`（本机解析结果完全一致，行为零回归）；3 处 subprocess `PATH` 硬编码（`piper_local_tts` / `audio/tts_backend` ×2 / `spine/advance`）改为 `build_subprocess_path()`；`narrative/dialogue_scene_package.py` 与 `piper_local_tts.py` 的 ffprobe/ffmpeg 候选列表补 `/home/linuxbrew/.linuxbrew/bin` 项。Linux/CI 现可复现，Mac 行为字节级不变。
- **测试**：`tests/test_util_paths.py`（4 用例，跨平台不假设 homebrew 存在：`build_subprocess_path` 永远含系统 bindir / homebrew 仅存在时注入 / `plugin_root` 指向本 checkout / `first_existing_file` 命中与 miss）。
- **未动项**：`adapters/cosyvoice_local_tts.py` 的 `/Users/dex/Developer/CosyVoice` 仅出现在 docstring 示例（运行期走 `COSYVOICE_*` env，已外部化），不视为可执行硬编码路径。

## [2.40.25] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 2 统一错误体系 · P2-1)
- **统一错误继承层级（P2-1）**：9 个子系统的 `*Error` 由 `RuntimeError` 改继承 `FilmError`（`util/errors`），保留原类名与 `RuntimeError` 兼容性：
  - gates 子系统：`ProductionGateError` / `PreflightError` / `CinematicGateError` / `GateAutoError` / `ContinuityProgrammaticError` / `NarrativeRebindError` / `DeliveryArtifactError`
  - final 子系统：`final/errors.RenderError`（含传递继承的 `RenderTimeoutError`）
  - post 子系统：`post/render_final_music.RenderError`、`post/render_final.LipSyncError`（位于 ImportError 回退块）
- **故意不动**：以 `ValueError` 为基类的错误保持原样，避免破坏现有 `except ValueError` 处理点（向后兼容器于 P2-1 范围之外）。
- **测试**：`tests/test_error_hierarchy.py`（参数化，9 类 + RenderTimeoutError 传递 + `FilmError` 兜底捕获，验证既继承 `FilmError` 又仍是 `RuntimeError`）。`tests/test_gate_fail_closed.py`/`tests/test_util_logger.py`/`tests/test_render_final_dimension.py` 19 用例全绿。
- **P2-2 结论**：复测发现 `read_json` 已被 `util.require_json_as`/`require_json_fnv`/`soft_json` 集中收口（本地 6 处是薄封装而非重复实现），判定为已完成，不做高风险删除重构。

## [2.40.24] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 1 拆解巨型函数 · 参考模式)
- **`render_final` 首抽纯函数（P1 起手）**：从 2,454 行的 `render_final` 单体函数中抽出无副作用的 `resolve_render_dimension(*sources, default)`（CLI > timeline > manifest > default 回退，逐源防御性 `int()` 转换，非数值降级而非中途抛错）。原 width/height/fps 三处内联回退链统一走该函数，去重且可单测。
- **测试**：`tests/test_render_final_dimension.py`（4 用例，纯函数验证 CLI 优先 / 逐级回退 / 非数值降级 / 0 视为未提供）。这是"抽纯函数 + 单测"参考模式的第一个落地，后续 74 个 ≥200 行函数按此模式逐个拆解（每 PR 一个、伴生测试不降绿）。

## [2.40.23] - 2026-08-06

### Changed (senior-dev 代码质量把控 · Phase 0 止血)
- **闸门 fail-closed 化（P0-1）**：`gates/production_gates.py::assert_pilot_allows_add` 中 `assert_pilot_go_allows_bulk` 抛出**非** `ProductionGateError` 的异常时，原 `except Exception: pass` 会静默吞掉并 `return {"ok": True}`（fail-open）。现改为 `raise ProductionGateError(...)`，验证子系统出错即拦截，不再放行坏产出。其余 `except Exception` 站点（`cinematic_gate`/`narrative_rebind` 的 best-effort 探针、`production_gates` 的 `{}` 回退与 legacy 阈值回退）经逐处审计确认为 fail-safe，保持原行为。
- **统一 logging 基础设施（P0-2）**：新增 `util/logger.py`（依赖无关、走 **stderr** 以免污染 stdout 的 JSON API 管道、`AIFILM_LOG_LEVEL` 可调）。库代码诊断性 `print` 改为 `log.info`（`post/burn_srt_pil.py`）；API 输出型 `print(json)` 保留 stdout 契约。
- **CI 聚合门禁（P0-3）**：`.github/workflows/ci.yml` 新增 `merge-gate` 聚合 job（依赖 `validate-core`+`hotpath`+`test-full`，`if: always()`），团队只需把 `merge-gate` 设为分支保护 required check，即可一次性要求三套件全绿。mypy/ruff 扩范围/文档版本校验三项因会令当前 CI 变红，留待其前置 Phase（P5 类型、P3 迁移、P5-2 文档修复）完成后激活。
- **测试**：`tests/test_gate_fail_closed.py`（2 用例，验证 bulk-check 非预期异常与 `ProductionGateError` 均 fail-closed）；`tests/test_util_logger.py`（util 零覆盖基座的首批测试，验证 emit + 走 stderr 不污染 stdout）。`tests/test_production_gates.py` 无回归。

## [2.40.22] - 2026-08-06

### Changed (quality P2 · 拔掉 sung 自动生成的 HeartMuLa 外部依赖阻塞)
- **`sung_beat` 不再因缺外部 HeartMuLa 而降级。** 新增 `scripts/audio/sung_provider.py`：`SungProvider` 抽象接口 + 两个实现——`HeartMuLaSungProvider`（外部 `AIFILM_MUSIC_ARGV`，保持原行为）+ `LocalFallbackSungProvider`（复用项目已捆绑的本地 TTS 适配器 cosyvoice/piper/kokoro/chatterbox，或 `AIFILM_LOCAL_SUNG_PROVIDER=1` 显式 opt-in，无需外部服务/网络）。`select_sung_provider()` = 外部优先否则本地；`sung_provider_ready()` = 任一可用即为 True。
- **`audio/audio_recipe.py` 门禁解除**：`probe_caps_for_root` 改用 `sung_provider.sung_provider_ready()`（不再只认 `AIFILM_MUSIC_ARGV`）；`degrade_recipe` 原因文案同步更新。原来的硬降级 `sung_beat → narrate_bed` 在无 HeartMuLa 时不再触发。
- **测试**：`tests/test_sung_provider.py`（12 用例，hotpath）覆盖抽象契约、HeartMuLa 仅 argparse 设置时可用、LocalFallback 注入 tts_callable 可用+写音频、外部优先于本地、全无时 `None`+`ready=False`，及关键回归 `test_sung_beat_no_longer_blocked_by_heartmula`（`AIFILM_LOCAL_SUNG_PROVIDER=1` + `AIFILM_MUSIC_ARGV=""` 时 `probe_caps_for_root` 报 `sung_provider_ready=True` 且 `resolve_shot_audio_recipe` 返回 `recipe=="sung_beat"` 不降级）。
- **注意**：本次仅解除 planning 门禁；渲染期实际调用 `LocalFallbackSungProvider.synthesize_beat` 接入留待后续（HeartMuLa 配置路径不变）。

## [2.40.21] - 2026-08-06

### Changed (quality P2 · H3 Fill-Idle 完整派单 · primary 分类纯函数化)
- **Primary-H3 shot classification extracted to a pure, unit-tested function** (`media/h3_fill_idle.py::classify_primary_h3_shot`): the `elif primary:` block of `classify_fill_idle_shot` — P0a/P0b/P0c tier selection plus the dual I2V+R2V leg logic (including the γ3 skip-blind-R2V when the identity leg is already strong) — was previously inline and untested as a unit. It is now an explicit, behavior-preserving function returning `(priority, lane, status, reasons)`; `classify_fill_idle_shot` calls it and extends its reasons — identical output. This closes the loop on the Fill-Idle auto-dispatch decomposition started in v2.40.15–17.
- Tests: `tests/test_fill_idle_primary_classify.py` (11 cases — P0a/P0b/P0c tiers / H3 above-floor done / H3 below-floor P1 retry + cap exhaustion / dual complete / dual-need-i2v with last-still / γ3 strong-skip vs weak-need-r2v / explicit-dual overrides γ3 skip). Zero external deps.



### Added (quality P2 · 介质自动路由 · 按角色稳定性选写实/漫剧)
- **Media auto-routing by cast-state stability** (`media/media_routing.py`): unblocks the long-stalled P2 "介质自动路由（按 cast_state 稳定性选写实/漫剧）". The film has a global `medium_key` (photoreal / anime / manhua …) locked for the whole movie; an unstable cast member drifts in photoreal, so routing them to anime/漫剧 at *planning time* keeps identity coherent.
  - `route_character_medium(film_medium, char_stability)` — pure policy: unstable + photoreal → `anime` (`unstable_cast_downgrade_to_anime`); otherwise film medium. Decision is planned, never switches mid-film, so the existing medium lock stays intact.
  - `load_cast_stability(root)` — data source: optional spec `cast_stability` map overriding per-character stability, seeding every known char (`cast_ids` / `characters`) to "stable" by default.
  - `resolve_shot_medium(root, shot, intent)` / `media_routing_report(root)` — orchestration + observable per-character decisions.
- Tests: `tests/test_media_routing.py` (15 cases — pure policy matrix / signal loader defaults+overrides+case-normalization / resolve+report downgrade counting). Zero external deps.

## [2.40.19] - 2026-08-06

### Fixed (ops hygiene · media_queue shim + XOR docs)
- **`media_queue.py` shim:** when run as a script, dispatch to `media.media_queue.main()` (same footgun as bare `render_final` shim exiting 0 with no work).
- **Docs:** `lipsync.md` records native XOR TTS + mix_report `shot_lanes` check; memory checklist partially checked for pipeline/gate.
- **Worktree:** incomplete concurrent peel (broke `COITUS_BEATS` import) stashed — do not blind-pop.

## [2.40.18] - 2026-08-06

### Fixed (P0 · native XOR TTS · no double dialogue)
- **Root cause:** `prefer_native` kept H3/Grok clip audio while Edge still synthesized the same `spoken_text` into `narration` → character + duplicate VO.
- **`resolve_dialogue_audio_lane`:** per-shot `native` \| `post_tts` \| `silence` (mutually exclusive).
- **`render_final`:** native lane = silent VO caption clock + plate/slot fit; post_tts suppresses native; mix fail-closed on XOR violation.
- **Gate:** `DUPLICATE_DIALOGUE_AUDIO` in `final_editorial_review`; mix_report `shot_lanes` / `dialogue_xor`.
- **Docs:** hard-defaults + stages/voice + memory card.
- **Tests:** `test_native_audio_mix` lane XOR · `test_final_editorial_review` duplicate gate.

## [2.40.17+] - 2026-08-06 (merged from main · quality P2 fill-idle + gates)

> Version numbers on `main` for these pure-function extractions overlapped with
> this branch's monolith/AD numbering; content is preserved under this banner
> and coexists with the structure entries below.

## [2.40.17] - 2026-08-06

### Changed (quality P2 · H3 Fill-Idle 完整派单 · P2 空闲挑战自动派纯函数化)
- **P2 idle-challenge auto-dispatch policy extracted to a pure, unit-tested function** (`media/h3_fill_idle.py::decide_p2_challenge`): the `has_still and has_any` branch of `classify_fill_idle_shot` — including the γ3 low-ROI-skip (`best >= floor + 6.0`) — was previously inline and untested as a unit. It is now an explicit, behavior-preserving function returning `(priority, lane, status, reasons)`, so the P2 soft-challenge decision is a CI-verifiable invariant. `classify_fill_idle_shot` calls it and extends its reasons — identical output.
- Tests: `tests/test_fill_idle_p2_challenge.py` (9 cases — H3 ok no-rechallenge / H3 below-floor P1 retry / baseline strong skip / boundary exact / just-below enqueue / weak+grok mark / weak no-marker / missing best guard / missing floor guard).

## [2.40.16] - 2026-08-06

### Changed (quality P2 · H3 Fill-Idle 完整派单 · 模式/Lane 选取纯函数化)
- **Fill-Idle mode/lane selection extracted to a pure, unit-tested function** (`media/h3_fill_idle.py::select_fill_idle_mode`): the R2V=energy-lane auto-selection that used to live as inline branches at the end of `classify_fill_idle_shot` is now an explicit, behavior-preserving module-level function. It encodes: (1) primary dual second leg — `dual_need_r2v` → `r2v`; `dual_need_i2v` → `flf` when end-still exists else `i2v`; (2) P2 soft challenge prefers face-lock (`flf`/`i2v`) over blind `r2v` unless genuine on-camera-close dialogue energy. `classify_fill_idle_shot` calls it and extends its reasons — identical output.
- Tests: `tests/test_fill_idle_mode_select.py` (10 cases — primary dual r2v / primary dual i2v flf+i2v / P2 challenge prefer flf / P2 challenge prefer i2v / P2 keep r2v dialogue-close / P2 keep r2v true-energy / passthrough primary / passthrough non-pending / default-mode fallback).

## [2.40.15] - 2026-08-06

### Changed (quality P2 · H3 Fill-Idle 自动派单 · dispatch-order 显式化)
- **Fill-Idle dispatch-order policy extracted to a pure, unit-tested function** (`media/h3_fill_idle.py::fill_idle_sort_key`): the P0→P1→P2 / dual-sticky-first / P1-fewest-H3-takes / P2-lowest-mean ordering was previously a nested closure inside `build_fill_idle_queue`, invisible to tests. It is now an explicit, behavior-preserving module-level function so the dispatch order is a CI-verifiable invariant. `build_fill_idle_queue` calls it directly (identical sort tuple).
- Tests: `tests/test_fill_idle_dispatch_order.py` (8 cases — priority rank / dual-sticky / P2 lowest-mean / P2 missing-mean-last / P1 fewest-h3-takes / P1 mean tiebreak / shot_id tiebreak / full stability).

## [2.40.14] - 2026-08-06

### Added (quality P2 · H3 Fill-Idle / 5090 统一调度器 · no-hog 程序化校验)
- **Multi-agent 5090 no-hog policy as a tested invariant** (`media/h3_fill_idle.py::gpu_no_hog_decision` + `gpu_no_hog_report`): the "busy queue ⇒ zero submit unless this session owns the GPU" rule (2026-08-06 IRON, user: '不准再犯') is now a **pure, GPU-free decision function** instead of an implicit side-effect of capacity probing. Encodes: `until_empty` execute requires explicit ownership; busy+not-owned ⇒ hold; dry-run always allowed; ownership (`AIFILM_I_OWN_THE_GPU`) overrides the hold.
- **Explicit guard wired into `run_next_fill_idle`**: before any job submission it reads the Comfy capacity probe's `COMFY_QUEUE_BUSY` blocker directly. This closes a real gap — `submission_capacity` can report `status=="ready"` while still carrying the busy blocker, which the existing `capacity_ready` check could miss. Busy+not-owned ⇒ early return `skipped_reason="no_hog_busy_hold"` (behavior-preserving hold, clearer audit reason).
- Tests: `tests/test_gpu_no_hog.py` (13 cases — dry-run / idle / busy-hold / owned-override / until_empty-ownership / report-wrap / env-override + wired-guard integration with mocked probe+planner).

## [2.40.13] - 2026-08-06

### Added (quality P2 · visual_bible 自动生成 / style-bible consistency)
- **Style-bible auto-derivation** (`assets/visual_bible.py::derive_style_bible_from_spec`): auto-generates/refreshes `style-bible.json` from the film spec — derives the lighting timeline from each shot's `heat_phase` (reusing `derive_lighting_timeline`), carries over declared `cast_masters` (including a `hero` entry inferred from `shot_role == hero` shots), persists via `save_bible`. Spec-driven (no pixel extraction) — the first increment of the "visual_bible 自动生成" P2 item.
- **Style-bible consistency gate** (`gates/production_gates.py::assert_style_bible_consistency` + `style_bible_consistency_report`): the style-bible is the canonical visual source of truth; when the spec declares visual content, reads back the on-disk `style-bible.json` and verifies it is consistent — `STYLE_BIBLE_MISSING` (no bible → run derive), `STYLE_BIBLE_HERO_CAST_MISSING` (spec has hero shots but bible lacks `cast_masters.hero`), `STYLE_BIBLE_LIGHTING_MISMATCH` (lighting_timeline count != shot count). Soft advisory by default; hard under `style_bible_strict` or adult `heat_scale` max/hot/extreme.
- Emergency escape: `AIFILM_SKIP_STYLE_BIBLE_GATE=1`.
- Wired into `preflight` as soft advisory.
- Tests: `tests/test_style_bible_consistency.py` (12 cases — no-content / root-none / missing / hero-missing / lighting-mismatch / consistent / auto-derive-then-consistent / soft-by-default / strict-raise / adult-max-raise / env-escape / force-skip).

## [2.40.12] - 2026-08-06

### Added (quality P2 · transition export read-back 全量)
- **Transition export read-back gate** (`gates/production_gates.py::assert_transition_export_readback` + `transition_export_readback_report`): closes the loop on the v2.40.11 controlled transition-policy gate. The policy gate validates the *plan* (`transition_intents`/`transition_styles`); this read-back validates the *built operations* (`spec["transition_ops"]`) actually materialise every declared seam and obey the policy — catching seams dropped or styles silently drifted during export/build.
- Coverage + consistency checks: `EXPORT_READBACK_NO_OPS` (declared seams but no built ops), `EXPORT_READBACK_OP_COUNT_MISMATCH` (a seam dropped/duplicated), `EXPORT_READBACK_CONTINUE_NOT_HARD` (continue seam not hard_cut/0.0s/no-overlay), `EXPORT_READBACK_PARAGRAPH_BAD` (chapter seam not soft xfade+fade/dissolve), `EXPORT_READBACK_SOFT_NOT_XFADE` / `EXPORT_READBACK_HARD_NOT_CUT`, `EXPORT_READBACK_STYLE_DRIFT` (built style != declared), `EXPORT_READBACK_FLASHY_STYLE` (whip/grid on scene cut), `EXPORT_READBACK_OP_INVALID` / `EXPORT_READBACK_OP_BASE_INVALID`.
- intro/outro / pure-MG roles relax (HF catalog open), mirroring the policy gate.
- Wired into `preflight` as soft advisory; hard under `transition_policy_strict` or adult `heat_scale` max/hot/extreme (same strictness as the policy gate, incremental rollout).
- Emergency escape: `AIFILM_SKIP_TRANSITION_READBACK_GATE=1`.
- Tests: `tests/test_transition_export_readback.py` (19 cases — no-ops / op-missing / count-mismatch / continue-softened / chapter-bad / style-drift / flashy / relax / strict-raise / env-escape / root-spec).

## [2.40.11] - 2026-08-06

### Added (quality P2 · controlled transition-policy gate / HF 转场受控策略全量)
- **Transition-policy gate** (`gates/production_gates.py::assert_transition_policy` + `transition_policy_report`): programmatic enforcement of the controlled transition grammar from `references/hf-transition-policy.md` — continue 接戏缝 must be hard match-cut (no xfade/dissolve); scene hard cuts must not use flashy styles (whip/grid); chapter/段落转场 restricted to soft fade/dissolve. Fills the gap left by `enforce_continue_hard_joins` (which silently auto-fixes continue seams) by *reporting* intent drift early; also covers scene-cut flashy-style and paragraph-transition rules nobody previously validated.
- intro/outro / pure-MG roles relax to allow-all (HF catalog open).
- Wired into `preflight` as soft advisory; hard under `transition_policy_strict` or adult `heat_scale` max/hot/extreme (incremental rollout like P0/P1 gates).
- Emergency escape: `AIFILM_SKIP_TRANSITION_POLICY_GATE=1`.
- Tests: `tests/test_transition_policy.py` (16 cases — continue-not-hard / paragraph-bad / scene-flashy / intro-relax / strict-raise / env-escape / root-spec).

## [2.40.10] - 2026-08-06

### Added (quality P1 · headroom / anti-crop timeline gate)
- **Headroom gate** (`gates/production_gates.py::assert_headroom_protected` + `headroom_report`): timeline half of "防裁头" — every shot must keep `duration_sec >= 2.0s` and each scene-opening shot needs `>= 3.5s` lead-in so the subject's entrance isn't cropped/abrupt. Complements `framing_lint.lint_framing_iron` (which covers the *frame* half). Wired into `preflight` as soft advisory; hard under `headroom_strict` or adult `heat_scale` max/hot/extreme.
- Emergency escape: `AIFILM_SKIP_HEADROOM_GATE=1`.
- Tests: `tests/test_headroom.py` (12 cases — floor / scene-opener / top-level / strict-raise / env-escape / root-spec).

## [2.40.17] - 2026-08-06

### Structure (monolith closeout — heat facade + export/final/film_spec leaves)
- **Heat DONE as packs:** `edit_policy_heat` pure re-export facade (~90 LOC). Packs: `heat_phase` · `heat_wardrobe` · `heat_coitus` · `heat_spice` · `heat_impact` · `heat_multi` · `heat_arc_lint`.
- **Final leaves:** `final/{render_defaults,io,manifest,voice_mix_config,bgm_spotting,watchdog}` wired into `render_final` (orchestrator body still residual for TTS/mix/subs loops).
- **Export leaves:** `post/export_cues.py` + `post/export_helpers.py` (phrase split / parse_srt / preset / caption clock).
- **Film-spec:** `plan/film_spec_lints.py` peeled from `film_spec_validate` (validate body residual).
- IRON defaults not retuned. Peel suite ~147 passed (export integration tests that need full dramatic_meaning fixtures are product-fixture, not structure).

## [2.40.16] - 2026-08-06

### Added (AD process implementation · code closeout)
- **Ship** `finalize_duration_density` + plan `adult-target-shot-lift` / `duration-density` receipts (A1/A2).
- **pilot-go v3:** `debrief_gate` + `three_look` (composition/wardrobe/poison).
- **closeout:** advisory `duration_honesty` + `official_final_readback` steps.
- **stages** agent/post/visual/voice/deliver AD discipline cards; hard-defaults row.
- **Plan:** `docs/plans/2026-08-06-ad-process-optimization-todoplan.md`.
- **Tests:** `tests/test_ad_process_optimization.py`.
- **Ops canaries:** artifacts AD wave D tunnel/OPEN_OPS + user-stopped exclusive drain.

## [2.40.14] - 2026-08-06

### Product (Wave N1 · nutrient L4 defaults)
- **N1.1 export plate block:** `export-desktop` refuses `OFFICIAL_FINAL_PLATE` / plate honesty conflict even when `gates.final_complete` is wrongly true.
- **N1.2 scale promote:** `register-clip` honors nested `decision.promote_ban` on `scale-fallback` receipt.
- **N1.3 shortlist promote fail-closed:** multi-seed `--promote` blocked when anti-hijack unavailable (unless intentional `AIFILM_SKIP_ANTI_HIJACK=1`); codes `SHORTLIST_PROMOTE_BLOCKED_*` + `next_cmd`.
- **N1.4 doctor:** optional `--root` soft `plate_vs_master` advisory (never hard-fails core doctor).
- Tests: `tests/test_nutrient_n1.py`.

### Structure (monolith relief round 3 · coitus + final/io)
- **M4 coitus pack:** `narrative/heat_coitus.py` — SEX_POSES, coitus grammar, sex-arc resolve/lint, pose variety; re-exported by `edit_policy_heat`. Wardrobe lazy import points at coitus leaf (no cycle at load).
- **M2.2c:** `read_json` → `final/io.py` (re-export hard-compat on `render_final`).
- IRON defaults not retuned. Verify: peel suite heat/final/write-spec/director/compose hotpath.

## [2.40.13] - 2026-08-06

### Structure (monolith relief round 2 · M2.2 + M4 wardrobe)
- **M2.2:** `build_final_film_manifest_entry` → `final/manifest.py` (``resolve_font`` stays on `render_final` for FONT_CANDIDATES monkeypatch hard-compat).
- **M4 wardrobe pack:** `narrative/heat_wardrobe.py` — wardrobe states, undress markers, continuity, `lint_sex_wardrobe` / `lint_both_undress`; re-exported by `edit_policy_heat`.
- Root shim `heat_wardrobe.py`. IRON defaults not retuned.
- Verify: peel suite heat/final/write-spec/director/compose hotpath (adult spine sex-floor float boundary still pre-existing).

## [2.40.12] - 2026-08-06

### Structure (monolith relief M1–M4 parallel)
- **M1 film_spec:** `plan/film_spec_constants.py` + `plan/film_spec_validate.py` + thin facade; root shims; public `import film_spec` unchanged.
- **M2 render_final:** `_run_with_watchdog` → `final/watchdog.py` (re-export hard-compat).
- **M3 export harness:** `tests/test_export_hotpath_contracts.py` (bad preset + missing root fail-closed).
- **M4 heat phase pack:** `narrative/heat_phase.py` re-exported by `edit_policy_heat` (no IRON retune).
- **Docs:** `docs/plans/2026-08-06-monolith-relief-todoplan.md` M0–M4 status.
- Verify: 144 passed on peel suite (shims/final/heat/write-spec/director/export/compose/suse iron).

## [2.40.11] - 2026-08-06

### Added (AD process optimization · 副导演三轴)
- **Duration density A1/A2**: `plan.duration_target.finalize_duration_density` binds heat-lifted target to actual shot count; plan writes `receipts/duration-density.json` + `adult-target-shot-lift.json` when lift/delta present.
- **Pilot A3/C1**: `pilot-go` schema v3 — `debrief_gate`, `three_look` (composition/wardrobe/poison), strict debrief blockers via env/design-go.
- **Closeout A4/B**: advisory `duration_honesty` + `official_final_readback` steps; `receipts/duration-honesty-closeout.json`.
- **Shortlist C2**: select-shortlist v2 — `mean_only_forbidden`, anti-hijack codes when multi-take without composition gate.
- **Register C3**: approved clips blocked when `scale-fallback` `promote_ban` unless review-note accepts soft-max (escape `AIFILM_SKIP_SCALE_PROMOTE_GATE=1`).
- **Stages B/C**: agent/visual/voice/post/deliver AD discipline cards.
- **Ops D canary**: `artifacts/2026-08-06-ad-wave-d-ops-canary.json` honest OPEN_OPS (no fake until-empty).
- Plan: `docs/plans/2026-08-06-ad-process-optimization-todoplan.md`.
- Tests: `tests/test_ad_process_optimization.py`.

## [2.40.10] - 2026-08-06

### Docs / honesty (next-optimization board closeout W0–W6)
- **ACTIVE plan:** `docs/plans/2026-08-06-next-optimization-todoplan.md`; closed boards → `docs/plans/archive/`.
- **W0.3:** CONTRIBUTING dual-checkout session open check (`git rev-parse`).
- **W1.5:** `stages/deliver.md` true-film final checklist (1 screen); post stage pointer.
- **W4:** `media_queue` silent `except Exception` paths now `note_queue_partial` (film-spec validate fallback + pilot approval load).
- **W5:** `stages/agent.md` director discipline card (anti-hijack / design-go / GPU max5).
- **W2 canary:** tunnel + capacity-plan honest status under `artifacts/`.

## [2.40.9] - 2026-08-06

### Added (quality closeout · auto-fix + auto multi-chapter + GPU safe ops)
- **Caption auto-fix**: `fix_chinese_caption_text/srt` removes CJK-internal spaces; `write_srt` + caption-pixel-check auto-heal SRT (backup `.pre-cjk-fix`).
- **BGM multi-chapter auto**: long-plate hard fatigue injects `inject_anti_fatigue_chapters` into mood/music timeline for procedural multi-motif beds.
- **Fill-Idle ops safe**: capacity-plan default `run-next --max 5`; until-empty only with `--i-own-the-gpu` in ops list.
- Tests: CJK fix · chapter inject · h3 capacity safe ops.

## [2.40.8] - 2026-08-06

### Added (quality P1 · motion mean / caption CJK / BGM fatigue / style NEG)
- **register-clip**: approved clips hard-fail `evaluate_shot_motion` mean floors (escape `AIFILM_SKIP_MOTION_MEAN=1`).
- **caption**: `lint_chinese_caption_spacing` (CJK internal spaces) wired into caption-pixel-check.
- **BGM anti-fatigue**: `bgm_anti_fatigue` receipt on final; long single-loop soft→hard at ≥180s.
- **style_lock**: `GLOBAL_DEFAULT_NEGATIVE` merged into still/I2V prompt prefixes.
- Tests: motion mean · CJK spacing · bgm fatigue · style neg merge.

## [2.40.7] - 2026-08-06

### Added (content-quality P0 hard gates — close the "gate-green-but-fails" gap)
Five auto hard gates from the expert-panel optimization plan, all fail-closed with `AIFILM_SKIP_*_GATE=1` emergency escapes and soft-by-default incremental rollout:

- **Anti-boring gate** (`gates/production_gates.py::assert_anti_boring_variety`): main beats >=4.5s, real shot-size changes, no adjacent motion duplicate, no flat size sequence; wired into `preflight`. (lesson: shot-variety-anti-boring)
- **Per-shot face-identity post_audit gate** (`assert_face_identity_passed`): rejects proven pixel drift; enrolled-gap / not-audited surfaced soft unless `face_identity_strict` or adult max heat. Injected into `cli_media.register_clip` (proven-drift-only block). (lesson: face-identity-pixel)
- **Nine-item continuity programmatic check** (`assets/continuity_chain.py`): byte-identical first/last reuse + nine-item checklist, plus new **forbidden-coverup detection** — long dissolve (>=0.28s) on a byte-identical match-cut join, and freeze/reverse/insert motion tokens on a continue join. First-class `assert_continuity_chain_passed` gate added. (references/continuity_chain.md §1.④)
- **render_final watchdog** (`post/render_final.py::_run_with_watchdog` + `--render-timeout` default 1800s, 0 disables): total wall-clock guard so a stalled pipeline raises a clean `RenderTimeoutError` instead of hanging (假死). Per-subprocess ffmpeg timeouts (AIFILM_FFMPEG_TIMEOUT) already cover individual calls.
- **TTS language ping-pong check** (`audio/voice_cast_profiles.py::detect_language_pingpong`): flags same-speaker adjacent language flips and A,B,A,B oscillation not explained by a speaker-layer change; surfaced in `audio_plan` (`tts_language_issues` + recommendation).

### Tests
- Added 56 cases across `test_production_gates.py`, `test_continuity_chain.py`, `test_render_watchdog.py`, `test_tts_language_pingpong.py`.

## [2.40.6] - 2026-08-06

### Added (quality P1 · narrative rebind + hair + adult arc closeout)
- **`narrative_rebind`**: closeout step + `receipts/narrative-rebind.json` — stale graph projection hard; max heat re-asserts SEX_ARC_*/coitus core (escape `AIFILM_SKIP_NARRATIVE_REBIND=1`).
- **style_lock**: `HAIR_LOCK_MISSING` hard when cast_locks lack hair; weak lock soft; default NEG gap soft.
- **compat**: re-export `COITUS_BEATS` / `_compatibility_vo_mode` (hotpath collection).
- Tests: `test_narrative_rebind` · `test_style_lock_hair`.

## [2.40.5] - 2026-08-06

### Fixed / Ops
- ship-native plate report via `write_official_final_report` (honest OFFICIAL_FINAL_PLATE).
- cli_post / production_gates residual honesty for final hang path.
- **S5 OPEN_OPS canary**: Comfy `18188`/`8188` down — no until-empty (`artifacts/2026-08-06-s5-until-empty-open-ops.json`).

## [2.40.4] - 2026-08-06

### Added / Fixed (final hang + volumedetect timeout honesty)
- **final heartbeat stages**: stretch / video_concat / audio_mix / done + `apply_final_ffmpeg_timeout_env`.
- **final timeout receipt**: `receipts/final-timeout.json` + clear `next_cmd` (no fake green).
- **volumedetect**: `TimeoutExpired` → `TimeoutError` (H3 soft `volumedetect_timeout` works again).
- Tests: antifragility H3 timeout suite · cut-silk memory/archive paths · heartbeat timeout receipt.

## [2.40.3] - 2026-08-06

### Added (shortform residual close · S1.3 / S2.3 / S3.1)
- **S2.3** `aifilm shortform export-spec` → draft `film-spec.json` + `timeline-draft.json` + receipt (force to overwrite).
- **S1.3** ship-native `mandarin_intelligibility` soft checklist (aac≠可懂中文); sparse audio soft codes.
- **S3.1** plan graph `project.wardrobe_honesty` (ambition vs honest_cap soft-max ladder).
- S5 still OPEN_OPS (Comfy :18188 unreachable this session — no until-empty).

## [2.40.2] - 2026-08-06

### Docs (shortform board CODE CLOSED + S5 probe)
- Mark `docs/plans/2026-08-06-shortform-optimization-todoplan.md` **CODE CLOSED**: S0–S4 shipped; residual **S5.1 OPEN_OPS** only.
- **S5 canary** `artifacts/2026-08-06-shortform-s5-open-ops-canary.json`: Comfy 18188 timeout (no drain); savani ep01/02 duration honesty **ok** after target≈media.
- memory: `2026-08-06-shortform-s5-open-ops.md`.

## [2.40.1] - 2026-08-06

### Added / Fixed (shortform closeout S1.2–S1.4 + S2 + S3)
- **S1.2** `resolve_skip_canonical_truth` + `receipts/skip-canonical-truth.json` + tests (default off).
- **S1.3** ship-native `NATIVE_AUDIO_MANDARIN_UNVERIFIED` soft + `listen_checklist`; hard via `AIFILM_NATIVE_AUDIO_MANDARIN_HARD=1`.
- **S1.4** closeout `plate_vs_master` + `plate_blocks_final_complete` (plate never final_complete).
- **S2.1** `references/shortform-director.md` decision tree + SKILL path picker.
- **S2.2** shortform/post lipsync tombstone (v2.40 path; enable/render hard-fail).
- **S3** scale-fallback `wardrobe_ambition` / `wardrobe_honest_cap` / `ambition_met`.
- hard-defaults / lipsync.md v2.40 tombstone wording; variety precheck hard pointer.

## [2.40.0] - 2026-08-06

### Breaking (post lipsync removed)
- **Production path**: `final --lipsync` **only `off`**; `enforce_dialogue_lipsync` hard-rejects auto/require/wav2lip/etc.
- **Tombstones**: `audio/lipsync_*.py`, `frw_lipsync`, `node/{latentsync,musetalk}_adapter`, CLI `lipsync-*`, shortform enable/render-lipsync — all raise / FilmError.
- **Doctor**: missing LatentSync no longer blocks core readiness.
- Policy doc: `references/lipsync.md` marks **code removal** (not “optional frozen backends”).

### Added (quality hard-gate MVP)
- `gates/continuity_programmatic.py`: continue-join forbidden dissolve + optional frame hash + wedge insert.
- Preflight: continuity programmatic issues + **ja cast_voices / dialogue_spoken_lang hard**.
- Still register: face-identity **default hard** when cast enrolled (`AIFILM_SKIP_FACE_IDENTITY=1` escape).
- `final/heartbeat.py` + render_final start heartbeat receipt.
- Tests: `test_lipsync_frozen` · `test_continuity_programmatic` · `test_final_heartbeat`; drop legacy lipsync suite.

## [2.39.99] - 2026-08-06

### Added / Fixed (shortform S0.3–S0.4 + S1.1 + lipsync freeze)
- **S0.3** `rebalance_adult_beat_durations`: grow `shots_n` first; meat paper ≤ `shots_n × 5.2`; no unstretchable pad.
- **S0.4** heat-lifted target → `project.duration_density` + min-shots H3 advice in graph.
- **S1.1** `h3 ship-native --caption/--music-mood` → receipt `stage2.command` only (no silent hardburn).
- **Post lipsync freeze (v2.40 path)**: tombstone LatentSync/MuseTalk/FRW/node clients; `--lipsync` must be `off`; prefer_native dialogue.
- Tests: adult rebalance S0.3 · lipsync routing frozen · ship-native density suite still green.

## [2.39.98] - 2026-08-06

### Added / Fixed (multi-agent GPU gate + memory slim)
- **until-empty execute gate**: `--until-empty --execute` requires `--i-own-the-gpu` or `AIFILM_I_OWN_THE_GPU=1` (dry-run free). Stop `exclusive_gpu_required`.
- **Default next**: h3_primary → `run-next --max 5` / single cycle; until-empty only with exclusive flag (dispatch + pilot_pack + SKILL).
- **Receipt honesty**: `takes_count_*` + `pending_reason_breakdown` on until-empty report.
- **ship-native**: stage-2 next = `final --skip-canonical-truth` hardburn/rnb (plate stays OFFICIAL_FINAL_PLATE).
- **media_queue**: scale-fallback write fail → job `honest_limits`.
- **memory/**: archive ~47 cards → `memory/archive/`; active ~39; README Active P0.
- hard-defaults multi-agent row documents machine gate.

## [2.39.97] - 2026-08-06

### Fixed (shortform S0.1–S0.2 · plan H3 duration honesty)
- **S0.1** `DEFAULT_DURATION_SEC=5.2` (was 6.0); shot planner caps act/climax plates at H3 nominal — removes 8s paper floor that invented unstretchable slots.
- **S0.2** `check_duration_target` adds `DURATION_SHOT_COUNT_SHORT_HARD` when `shot_count < ceil(target/5.2)` even if `duration_sec` is padded; `overlong_planned_shots` soft code.
- **write-spec** always writes `receipts/duration-target.json`; **fail-closed** on hard codes (escape `AIFILM_SKIP_DURATION_TARGET=1`).
- **plan run** attaches duration-target receipt + next hints (non-blocking draft).
- Strategy default: fail-closed + clear next (add shots / lower target); no silent pad.
- Tests: `test_duration_target_ship_native` · `test_vo_budget` default 5.2.
- Plan: `docs/plans/2026-08-06-shortform-optimization-todoplan.md`.

## [2.39.96] - 2026-08-06

### Validated (H3 prompt R5 · 5090)
- GPU revalidation of round-4 matrix under family-apply stack: 7/7 ok (`artifacts/.../h3-combo-r5-family-20260806`).
- Winners written: soft `soft_portrait_alive` i2v · high `high_motion_max` r2v mean≈25.4 · dialogue mouth-metric `dialogue_mouth_flat` i2v (runner_up max for identity).
- **combo-eval free-memory after every job** (VRAM residual floor stall fix).
- Evidence: `registry/evidence/h3-combo-r5-summary-20260806.md`.

## [2.39.95] - 2026-08-06

### Added / Fixed (quality closeout)
- **pre-push always runs** `scripts/secret_scan.py` (no silent skip when gitea-publish missing).
- **`make review`**: secret-scan + hotpath fail-closed contracts.
- **MEMORY_GOVERNANCE** + CONTRIBUTING links; quality plan marked **CLOSED**.
- **`util.retry.poll_until`**: frw_lipsync `poll_task` uses it; tests for timeout/success.
- **media_queue `scheduled_backoff_sec`**: single job-level backoff lookup (process sleep remains out of scope).
- `scripts/check-all.sh` **step 7 coverage gate** (58% + per-file floors), local check-all fully ≡ CI.

### Quality / tooling (close the local gate-trust gap, cont.)
- Coverage step mirrors CI `validate-core`; Makefile help documents coverage 58%.

## [2.39.94] - 2026-08-06

### Added / Refactored (quality round 4)
- **Shim policy**: `docs/SHIM_POLICY.md` (linked from CONTRIBUTING); tests cover `edit_policy_shared` thin shim + cycle-free heat import.
- **frw_rate_limit** exclusive lock wait → `util.retry.retry_call` (constant 50ms backoff, 120s budget).

## [2.39.93] - 2026-08-06

### Fixed / Refactored (quality round 3)
- **Cycle-free heat/policy**: `narrative/edit_policy_shared.py` holds `PolicyError` + coitus markers; `edit_policy_heat` no longer uses `sys.modules` probe; top-level shim `edit_policy_shared`.
- **comfy_recovery** remote probe loop → `util.retry.retry_call` (injectable sleeper preserved).

## [2.39.92] - 2026-08-06

### Quality / tooling (close the local gate-trust gap)
- `scripts/check-all.sh`: local green line now mirrors CI — added **secret-scan** (`scripts/secret_scan.py`) as step 1 and **hotpath fail-closed contracts** (`pytest -m "hotpath and not slow"`) as step 6. Local `make check-all` ≡ CI gates (validate + ruff + doctor + pytest not-slow + secret-scan + hotpath).
- `Makefile`: corrected misleading header (was pointing at `plugins/ai-film-grok` as the root; now documents the dual checkout — git root `ai-film-grok` vs runtime mirror `plugins/ai-film-grok` — and that CI is the real gate, not local pre-push). Updated `help` text for `check-all`/`release-light`.

### Fixed / Refactored (quality round 2 · residual)
- **Volume probe residual**: `elevenlabs_canary`, `quality_check_video`, `reference_audit` use `core.media_ops.probe_volume_stats` / mean probe (no local volumedetect paste).
- **`probe_volume_stats` / `parse_max_volume_db`**: mean+max+raw log from one ffmpeg pass.
- **Edge TTS empty-stream retry** via `util.retry.retry_call` (sample hot-path wire-up).

## [2.39.91] - 2026-08-06

### Quality / tooling (follow-up to 2.39.90)
- AGENTS.md: fix wrong source-checkout path (was `plugins/ai-film-grok`, now documents both diverged checkouts); declare CI as the only real gate (local pre-push hook is not wired); note split-brain repo risk.
- Tag fail-closed gate suites (`test_bulk_preflight_hard_gate`, `test_strict_gate_paths`, `test_production_gates`) with `pytest.mark.hotpath` so they stay in the fast fail-mode contract path (CI hotpath job now covers them).

## [2.39.90] - 2026-08-06

### Added (engineering quality + team uplift)
- **CONTRIBUTING** + **REVIEW_CHECKLIST**: `docs/CONTRIBUTING.md`, `docs/REVIEW_CHECKLIST.md` (linked from README/AGENTS).
- **CI secret scan**: `scripts/secret_scan.py` on every push/PR (honest gate when local pre-push skips gitea-publish).
- **CI hotpath job**: `pytest -m "hotpath and not slow"` fail-closed contracts.
- **IRON coverage table**: `docs/reports/2026-08-06-iron-gate-coverage.md`.
- **`util.read_json_source`**: secure nofollow JSON read; `semantic_index` delegates.
- **`util.retry.retry_call`**: shared backoff helper for new call sites.
- **Volume probe single path**: `core.media_ops.probe_native_audio_mean_volume` (+ `parse_mean_volume_db`); hub/compose/h3_ship_native/h3_workflow converge.
- Tests: `tests/test_util_retry_json_source.py`.
- Quality plan status refresh: `docs/plans/2026-08-06-codebase-quality-todoplan.md`.

## [2.39.89] - 2026-08-06

### Added (H3 prompt system · family → production)
- **Production family apply**: registry `prompt_family` now hole-fills empty shot DSL on `h3_primary`/`hybrid_h3` via `apply_combo_family_to_shot` (escape `AIFILM_H3_FAMILY_APPLY=0`). Plan annotate-only gap closed.
- **`registry/h3-prompt-system.json`**: versioned system clauses; `motion_prompt_spine.system_clause` for HIGH/SOFT/MOUTH/style-lock.
- **Winners**: `dialogue_mouth_energy.winner.family` aligned to `dialogue_mouth_max`.
- Audit: `docs/plans/2026-08-06-h3-prompt-system-audit.md`.
- Tests: `FamilyApplyTests` in `test_h3_combo_eval.py`.

## [2.39.88] - 2026-08-06

### Fixed (C1 floor-retry residual)
- Fill-Idle P1 `h3_below_floor`: after **N H3 takes** (default 5, env `AIFILM_H3_FLOOR_RETRY_CAP`, 0=unlimited) still under motion floor → **residual done** (`h3_floor_retry_exhausted`), drop command so until-empty can reach `queue_empty` without infinite 5090 burn. No silent promote.

## [2.39.87] - 2026-08-06

### Fixed
- heat_agent queue: soft codes no longer hard_fail media-queue; lengthen_meat cap 5.9s; pilot 批准 phrases.

## [2.39.86] - 2026-08-06

### Fixed (C1 free-after-idle)
- capacity wait: when queue goes idle but VRAM/RAM floors remain, **free-memory once** (`free_first_when_idle`); final free attempt after wait timeout. Never cancel foreign prompts.

## [2.39.85] - 2026-08-06

### Fixed (C1 ops heartbeat)
- until-empty writes mid-loop `stop_reason=capacity_waiting` receipt so ops do not read a stale `run_failed` while free-first waits for foreign GPU.

## [2.39.84] - 2026-08-06

### Fixed (C1 capacity wait clamp)
- **`_CAPACITY_WAIT_SEC_HARD_MAX`**: 600s → **28800s (8h)** so `--capacity-wait-sec 7200` is not silently clamped; foreign H3 jobs no longer force premature `capacity_not_ready` stop every 10 minutes.
- Test: `test_capacity_wait_hard_max_allows_overnight` in `test_h3_until_empty.py`.

## [2.39.83] - 2026-08-06

### Fixed (savani media honesty)
- **Q4.1b** bulk-preflight `duration_target` now probes **approved/candidate clip media sum** when ≥50% shots measurable; catches planned `duration_sec` padded to target while real H3 clips ~5.2s (`DURATION_MEDIA_SHORT_HARD`). Film canary: `artifacts/2026-08-06-effect-board-film-canary.json` (suse + savani ep01–03).

## [2.39.82] - 2026-08-06

### Added (effect board Q1.4 + Q5.2 closeout)
- **Q1.4** `crop_master_still_report` in `assets/still_uniqueness.py`: flag whole-episode cast-master crop stills (path/note/parent_sha); soft ≥35% / hard ≥55%; bulk-preflight check + `receipts/crop-master-still.json`. Escape `AIFILM_SKIP_CROP_MASTER_STILL=1`.
- **Q5.2** `h3 ship-native` native audio sample audit: stream + `volumedetect` mean_volume (soft codes `NATIVE_AUDIO_*`); notes aac≠Mandarin.
- Tests extended in `test_duration_target_ship_native.py`.

## [2.39.81] - 2026-08-06

### Added (effect board Q4.1 + Q5.1)
- **Q4.1** `plan/duration_target.py`: planned sum vs `target_duration` honesty; soft >12% / hard >20% shortfall; H3 ~5.2s shot-count advice; receipt `receipts/duration-target.json`; wired into `bulk-preflight` (hard gap blocks bulk). Escape `AIFILM_SKIP_DURATION_TARGET=1`.
- **Q5.1** `aifilm h3 ship-native`: timeline-order concat keep clip aac; delivery `OFFICIAL_FINAL_PLATE` (not master); dry-run + duration sub-report; `receipts/h3-ship-native.json`.
- Tests: `tests/test_duration_target_ship_native.py` (savani 41×5.17 vs 300s hard; ship dry).

## [2.39.80] - 2026-08-06

### Added / Fixed (C1 drain launch · D2 · E peel)
- **C1** background drain launch: `h3 cycle --until-empty --execute --free-first --capacity-wait-sec 7200` on velvet-stage-dual; artifacts `2026-08-06-c1-drain*`; honest capacity_not_ready while VRAM/queue busy.
- **D2** cosyvoice ffmpeg `timeout=180`; hotpath timeout contract tests; AST audit residual only Popen long-runners + media_qa setdefault.
- **E** peel `plan/film_spec_sex_floor.py` (+ shim) for A1 sex-floor fail-closed (no duration invent).

## [2.39.79] - 2026-08-06

### Added (Wave B scale-fallback + D1 + C1 OPEN_OPS)
- **B** `narrative/scale_fallback.py`: soft-max / bare-tease / **SCALE_HARD_ON_BAN** (poison streak stop); final writes `receipts/scale-fallback.json` + wardrobe tier on official-final.
- **B** media_queue fail: moderation/poison → scale-fallback receipt (stop hard-on honesty).
- **D1** generation_request optional path: `note_queue_partial` instead of silent pass.
- **C1** dry until-empty canary: `artifacts/2026-08-06-c1-until-empty-dry-open-ops.json` (queue_busy + VRAM/RAM floors; full drain still OPEN_OPS).
- Tests: scale-fallback + HEAT_WARDROBE_RE_DRESS in `test_suse_final_iron`.

### Fixed (Stage 3 business logic regression)
- **F1** `registry/h3-combo-winners.json`: corrected `dialogue_mouth_energy` lane `prompt_family` from stale `dialogue_mouth_flat` to `dialogue_mouth_max` (aligned with R4 policy in `h3_combo_eval.py`).
- **F2** `spine/dispatch.py`: added `_STATE_OK_ONLY` frozenset with `select-shortlist.json` entry so `select-shortlist` contract is wired and `test_dispatch_source_mentions_wave_h` passes.
- **F3** `tests/test_music_template.py`: fixed mock path resolution — moved library fixture from `shared/assets/bgm/rnb` to `assets/bgm/rnb` to match `Path(__file__).resolve().parents[2]` convention.

## [2.39.78] - 2026-08-06

### Added (suse EP01 Wave A4–A5)
- **A4** BGM honesty: `mood_library_status` + `build_bgm_source_receipt` → `receipts/bgm-source.json`; rnb license-only (no wav) → procedural + `honest_limits` on final-delivery.music.
- **A5** Plate vs master: `final.delivery_class.classify_official_final` → `receipts/official-final-report.json`; skip-preflight/heat / gate-auto red → `OFFICIAL_FINAL_PLATE` (never auto `master_lock`). CLI passes skip flags into plate renderer.
- Tests extended in `test_suse_final_iron.py`.

## [2.39.77] - 2026-08-06

### Fixed (suse EP01 official final IRON · Wave A)
- **A1** `validate_film_spec`: remove silent act/climax `duration_sec=max(10,…)` pad on `HEAT_SEX_DURATION_LOW`. Fail-closed with next steps (re-I2V / add shots / lower floor) — short H3 sources must not invent unstretchable 10s slots.
- **A2** Timed voice cues: `check_vo_window_triangle` (tts≤cue≤slot); try `vo_atempo`→cue window before hard fail; clear error if cue exceeds plate.
- **A3** Tests: `tests/test_suse_final_iron.py` (no pad · triangle · `render_final.py` shim `__main__`→`main`).
- Plan: `docs/plans/2026-08-06-optimization-todoplan.md` (next residual board).

## [2.39.75] - 2026-08-05

### Changed (routing rewire R2–R7 complete)
- **R2** `spine/stage_model.py` — public craft / pipeline / craft-eight projection; `design`→post.
- **R4** `spine/action_policy.py` — spend/skill maps; dispatch `resolve_*`; advance catalog cross-check tests.
- **R5** `layer=capability|weapon` on route-plan / weapon_route; schema allows `layer`; **no** silent lane switch.
- **R6** compact: `stage_public` + `route_catalog_id`; context-routing public aliases; routing-map contract.
- **R7** `test_stage_model` · `test_action_policy`; production_router suite green.
- Public CLI argv / pilot / `i2v_provider` unchanged.

### Changed (ltx23 next_action concrete shot)
- `next_actions` LTX audio unit picks first missing-clip **general** `frw-ltx23` shot (never restricted/meat).
- Refresh `runtime-lock.json` after script fingerprint drift.

## [2.39.74] - 2026-08-05

### Changed (routing rewire R0–R1–R3 · behavior-neutral)
- **Route inventory** `scripts/tools/route_inventory.py` — coverage matrix of CLI / next_actions / advance / skills.
- **Route catalog** `registry/route-catalog.json` + `route_catalog.py` + `tests/test_route_catalog.py`.
- **Hub residual** ~35 if-ladder cmds → `cli/cli_hub_residual.py`; hub main is table-driven (`_SIMPLE_DISPATCH` → residual).
- Docs: `docs/plans/2026-08-05-routing-rewire.md`, `references/routing-map.md`; `cli-extract-map` R3 note.
- Public subcommand strings unchanged; no pilot / provider policy change.

## [2.39.73] - 2026-08-05

### Added (2V Reference Stage — H3 Layer-4)
- When a model supports image input (I2V/FLF/R2V) and reference images are
  available, the H3 prompt compiler injects a Grok reference-composition
  stage before the timeline segments. The first frame is generated via
  Grok image model from a composition prompt, then used as the start-frame
  reference for H3 video generation.
- `_collect_ref_images()` in `h3_workflow.py` gathers `still_path`/
  `last_path`/`ref_paths` from the plan for the 2V stage.
- `supports_image_input()` in `h3_mode.py` detects whether a mode accepts
  image input.
- `build_reference_composition_prompt()` and `inject_2v_reference_stage()`
  in `h3_timeline_prompt.py` generate the Grok image prompt and wrap the
  timeline.
- `build_h3_temporal_prompt()` in `motion_prompt_spine.py` accepts
  `ref_image_paths` and passes them through to the 2V injection.

## [2.39.72] - 2026-08-05

### Added (LTX 2.3 adult audio lane + FRW i2i repair plan)
- Profile **`ltx23_adult`**: safe dialogue/soft → FRW LTX 2.3 `img2video-audio` (`prefer_native`); restricted/bare/meat → **H3 hard**.
- `production_router`: lane `cloud_ltx23_audio` when profile or `motion_lanes.dialogue=frw_ltx23` / `allow_ltx_dialogue`.
- Docs: `docs/plans/2026-08-05-ltx23-adult-audio-lane.md`, memory card, hard-defaults + weapon-lane patches.
- Still repair remains `still-challenge` (FRW i2i ≥30s); not a silent still primary over Qwen.
- **dispatch/next**: `frw-ltx23-canary` · `frw-ltx23-audio-unit` · `still-challenge-repair` · `h3-lane-meat` under `ltx23_adult`.

## [2.39.71] - 2026-08-05

### Fixed (H3 · dialogue timeline freeze from R3 A/B)
- Live 5090 R3 A/B: high_motion timeline R2V wins (mean~26); dialogue v1 timeline froze (mean~1).
- Dialogue path: compact continuity + **MOUTH ENERGY** (not HIGH MOTION); `dialogue_mouth_max` heat=build.
- Combo eval film genre `drama` to avoid meat variety preflight on 5s pilots.
- Evidence: `registry/evidence/h3-timeline-ab-summary-20260805.json`.

## [2.39.70] - 2026-08-05

### Changed (H3 · timeline combo families + R3 flat/timeline A/B)
- Combo `author_prompt` defaults to Layer-4 compile via `compile_family_author_prompt`.
- Families carry `prompt_format` + camera/env seeds; flat baselines `high_motion_flat` / `dialogue_mouth_flat`.
- `aifilm h3 combo-eval --round 3` = flat vs timeline A/B grid; prep root `artifacts/.../h3-timeline-ab-20260805`.
- `dsl.prompt_format=flat|timeline` overrides 5090 auto-timeline for controlled A/B.
- Fix plan test: dialogue lane winner family `dialogue_mouth_max`.

## [2.39.69] - 2026-08-05

### Changed (H3 · Layer-4 timeline prompt compiler for 5090)
- **New** `scripts/h3_timeline_prompt.py`: temporal decomposition (`[0s-2s]…`), continuous coverage, continuity anchors, one primary action/segment, subject+camera+env motion, ending pose, continuous vs multi-cut, implied diegetic sound + dialogue inject; `validate_timeline_coverage`.
- **`build_h3_temporal_prompt`**: no longer round-robin clause split — full Layer-4 timed action script.
- **`h3_workflow._prompt_for_shot`**: `h3_primary`/`hybrid_h3` always compile timeline (author files get markers if missing); non-5090 stays flat spine with `Vertical 9:16`.
- Docs: lesson H3-max §Layer-4 · memory `2026-08-05-h3-timeline-prompt-layer4` · tests `test_h3_timeline_prompt` + temporal spine cases.

## [2.39.68] - 2026-08-05

### Changed (dialogue · native audio IRON)
- **Spoken shots** generate on **Grok Imagine Video** (safe) or **5090 H3** (restricted / `h3_primary`); mix keeps **`prefer_native` / `use_clip_audio`**.
- **Frozen** post lipsync: LatentSync / MuseTalk / InfiniteTalk / FantasyTalking / FRW lipsync — out of production DAG; `final --lipsync off`.
- LTX dialogue棚 exits default path (`cloud_dialogue_grok` replaces `cloud_dialogue_ltx`).
- Code: `dialogue_competition` policy `native_audio_grok_h3_v1`; `production_router` lane/provider updates; schema run_conditions.
- Docs: hard-defaults · dialogue-first · lipsync · weapon-lane · stages/voice · SKILL P0 · memory card.

## [2.39.67] - 2026-08-05

### Fixed (docs · S5.3 canary honesty)
- Corrected false `queue_empty` narrative: live receipt is **stop_reason=capacity_not_ready** (pending_after=2, jobs_ran=0).
- Aligned canary JSON, memory, optimization-todoplan, strategy R-ops (PARTIAL; overnight drain OPEN).


### Fixed (doctor core · release-light clean checkout)
- **cli_status doctor**: `core_readiness.tts_backend` passes when edge-tts is installed even if preferred (mimo) is unconfigured — unblocks pre-push light gate without keys.
- Preferred-unready still reported in `tts.ok` for honest production synthesis path.


## [2.39.66] - 2026-08-05

### Added (S5.3-ops · capacity-wait on until-empty)
- **`wait_for_comfy_capacity` / `recover_capacity_contention`**: free-first again (if safe) then poll ready; never cancel foreign; hard max 600s.
- **CLI** `aifilm h3 cycle --capacity-wait-sec N` (with `--until-empty`); receipts include `capacity_waits`.
- On capacity recover → continue loop; timeout still stop_reason=`capacity_not_ready`.
- **Tests**: CapacityWaitTests in `test_h3_until_empty.py`.

### Changed (H3 combo R2 best-of live → workflow)
- **Registry** `h3-combo-winners.json`: best-of R1+R2 idle grid on 5090.
  - high_motion_energy → **R2V + high_motion_max** (mean~21.6)
  - dialogue_mouth_energy → **I2V + dialogue_mouth_max** (motion~12)
  - hero_identity keeps soft_i2v; faceless_env keeps env_no_face
- `resolve_h3_mode` picks preferred_mode + prompt_family from registry.

### Changed (R1c residual · voice cast normalize)
- **`final.voice`**: peel `normalize_cast_voices` / `normalize_cast_tts_backends` from `post/render_final`; hard-compat re-export.
- **`render_final`** calls the normalize leaves (no policy change); Chinese locks; remap legacy `ja-JP-*`.
- **Tests**: `test_final_voice_normalize.py`.

## [2.39.65] - 2026-08-05

### Fixed (hang-proof · adapters + node lipsync + canary/opt)
- **adapters**: elevenlabs/voicebox ffmpeg `timeout=120`; music normalize `300`; higgs command `1800`.
- **node**: latentsync / musetalk inference timeouts (env `AIFILM_*_TIMEOUT`, default 3600); musetalk normalize `600`; hang exit `76`.
- **mmaudio_adapter**: `_run_checked` default `timeout=1800` + TimeoutExpired map.
- **elevenlabs_canary** metrics: ffprobe `30` / volume+silence `60`.
- **optimization_program** audio lane probe: `timeout=30`.
- **visual_text_repair**: catch TimeoutExpired on rebuild path.
- **Tests**: Wave3AdapterNodeTimeoutTests.
- R-ops overnight drain still OPEN (capacity floors / queue busy).



## 2.39.64 — 2026-08-05

### Changed
- W7 narrative: 21 modules → `scripts/narrative/` + thin shims; shim-safe edit_policy↔heat cycle.
- R1c: peel TTS + native/vocal-color track builders → `final/tts_tracks.py` (re-export hard-compat).
- R3a: peel I2V/H3 profile resolve → `film_spec_profile.py` (re-export from `film_spec`; no provider policy change).
- LOC: `post/render_final` ~3014→~2735; `film_spec` ~3234→~3136.

## [2.39.63] - 2026-08-05

### Changed (W7 · plan package expand)
- Move 18 plan-domain modules into `scripts/plan/` (film_spec, story_*, production_*, shot_*) with thin top-level shims.
- Tests: `test_w7_plan_package_and_shim_identity`.

### Fixed (film-spec write-spec scaffolds + glue)
- **templates** example/adult-max/h3-primary/hybrid-h3: pose chain, size variety, arc_node, performance/craft, director_board → real `write-spec` green.
- **cli/cli_write_spec**: wardrobe hard-fail only when bible authored `wardrobe_variants` (empty init no longer blocks scaffolds).
- **framing_lint `_size_rank`**: normalize close-up / medium full / insert; medium-close before bare close.
- **tests**: shipped templates write-spec path; size-rank normalize; health report follow-up.



## [2.39.62] - 2026-08-05

### Changed (W7 · post package expand)
- Move 22 post-domain modules into `scripts/post/` (compose/export/closeout/caption/subtitle/post_*) with thin top-level shims.
- Path depth fixes for burn_srt_pil / final_stages / compose_preview / agent_review_final.
- Tests: `test_w7_post_package_and_shim_identity`.

## [2.39.61] - 2026-08-05

### Changed (W7 · cli package boundary)
- Move all `cli_*.py` implementations into `scripts/cli/` with thin top-level `sys.modules` shims (hard-compat).
- Path depth: skill root `parents[2]`; scripts dir `parents[1]`.
- Tests: `test_w7_cli_package_and_shim_identity`.

## [2.39.60] - 2026-08-05

### Fixed
- R1b complete: add missing `final/{enhance,native_audio,cards}.py` leaf modules (were imported but not committed in 2.39.59) + `final` re-exports; font fail-closed test patches source of truth.

## 2.39.59 — 2026-08-05

### Changed
- R1b structure: peel native/cards/enhance leaves from post/render_final into final/* (re-export hard-compat). LOC ~3271→~3006.

### Fixed
- Ship missing `final/{cards,enhance,native_audio}.py` leaf modules (R1b import was incomplete on origin-bound tree).
- `resolve_font` stays patchable via `render_final.FONT_CANDIDATES` (hard-compat with tests).

## [2.39.58] - 2026-08-05

### Fixed (hang-proof · audio TTS + shortform + media probe paths)
- **`audio_tts_render`**: ffprobe duration `timeout=30`; mp3→wav ffmpeg `timeout=120`.
- **`event_voice_stem`**: decode `timeout=180`; write stem `timeout=120`.
- **`audio_delivery_gate`**: ffprobe streams `timeout=30` (soft fail map).
- **`shortform_director`**: pcm hash / probe / remux / concat paths bound with timeouts (30–300s).
- **`burn_srt_pil`**: burn ffmpeg `timeout=1800` (exit 124 on hang).
- **`narrative_evidence`**: media duration ffprobe `timeout=30`.
- **Tests**: Wave3AudioPipelineTimeoutTests (+ shortform source checks) in `test_antifragility_af.py`.

## [2.39.57] - 2026-08-05

### Changed
- R1 structure: `post/render_final` re-exports caption/voice/media leaves from `final/*` (AST-identical de-dupe; public import surface unchanged). LOC 4333→3271.

## [2.39.56] - 2026-08-05

### Added (S5.3-ops · h3 cycle --free-first)
- **`prepare_capacity_free_first`**: queue idle + only RAM/VRAM floors → free models once before cycle/until-empty.
- **Never** free on `COMFY_QUEUE_BUSY` (no cancel foreign prompts).
- CLI: `aifilm h3 cycle --free-first` (with `--until-empty`); receipts include `free_prep`.
- **Tests**: disabled / queue_busy / dry would_free / free once / until-empty free_prep.
- **Canary PARTIAL**: `artifacts/2026-08-05-s53-free-first-canary.json` · strategy rev 2026-08-05e.
- Full overnight `queue_empty` drain still OPEN_OPS (5090 contention).

### Fixed (W6 path depth · local TTS argv trust)
- **`audio/tts_backend`**: chatterbox/piper trusted interpreter uses `parents[4]` (plugin root) after nest into `scripts/audio/` (was `parents[3]` → wrong `skills/`).
- Restores `chatterbox_local_argv_configured` / `piper_local_argv_configured` vs `SCRIPTS.parents[2]` contract.

### Fixed (hang-proof · h3_workflow + continue handoff)
- **h3_workflow**: all bare `subprocess.run` paths now use `timeout=` — strip audio (120/300s), volumedetect (60s soft), geometry upscale (600s), register-clip (300s). Timeouts raise `H3WorkflowError` (volumedetect soft-keeps native).
- **continue_handoff**: end-frame ffmpeg extract `timeout=60` (was hang risk overnight).
- **Tests**: Wave3H3WorkflowTimeoutTests in `test_antifragility_af.py`.
- **Strategy residual**: R-af1/R-util hot H3 paths tightened; bulk bare migration still open.

## [2.39.55] - 2026-08-05

### Added (media-queue inventory primary tags on fail)
- **media_queue**: `_queue_error` / `_inventory_weapon_tags` append still/edit/motion/tts primaries on enqueue hard fails.
- H3 cloud-block, bulk-preflight, pilot/heat, motion-core, budget errors name documented weapons.
- **Tests**: `test_media_queue_inventory.py`.

## [2.39.54] - 2026-08-05

### Fixed (film-spec health · H3 templates validate)
- **templates/film-spec.h3-primary.example.json** + **hybrid-h3**: expand from profile skeletons to adult-max IRON arc so real `validate_film_spec` accepts them (keep h3 / motion_lanes notes).
- **tests/test_director_intent.py**: all shipped `templates/film-spec*.json` must pass validate; H3 templates retain weapon-lane fields.
- **docs/reports/2026-08-05-film-spec-health.md**: probe of templates, H3 canaries, Desktop historical roots (seedance / dramatic_meaning deferred).

## [2.39.54] - 2026-08-05

### Changed (module refactor · W6 audio/media packages)
- **`scripts/audio/`**: TTS/BGM/SFX/lipsync/sound/voice clusters (45 modules) + top-level shims.
- **`scripts/media/`**: I2V/Comfy/H3/FRW/queue/pilot/weapon clusters (32 modules) + top-level shims.
- Path fixes for skill-root / adapters / sibling script resolution after nesting.
- Public import names unchanged (`sys.modules` hard-compat).

## [2.39.53] - 2026-08-05

### Fixed (hang-proof · shortform motion + residual table truth)
- **shortform_motion**: full-decode ffmpeg + ffprobe use `timeout=` (was bare hang risk).
- **Strategy residual table**: R-af2/R-doc SHIPPED; R-af1 core hang paths reduced; R-ops/R-util PARTIAL.
- **Tests**: shortform timeout asserts in `test_antifragility_af`.

## [2.39.52] - 2026-08-05

### Added (bulk-preflight weapon inventory hints)
- **bulk_preflight** attaches `weapon_inventory` primaries; failed checks get `weapon_hint`.
- **next_cmd / next_why** name still/edit/motion primaries (Qwen / H3) on hard fails.
- **assert_bulk_preflight** error strings include still= / motion= weapons.
- **next_actions** bulk-preflight why tags inventory primaries.
- **Tests**: `test_bulk_preflight_inventory.py`.

## [2.39.51] - 2026-08-05

### Changed (module refactor · W4/W5 finish)
- **W4**: `render_final` → `scripts/post/`; `edit_policy_heat` → `scripts/narrative/`; top-level hard-compat shims.
- **W5**: AGENTS package layout + AREA pointers; refactor tracker W3–W5 DONE; REFACTORING_PLAN superseded.
- Public import/CLI names unchanged.

## [2.39.50] - 2026-08-05

### Fixed (Workflow wire · recompute_gates phase/primary alignment)
- Legacy readiness **only** trusts `recompute_gates` for style/spec/clips (no shots-list-as-spec).
- Plate on disk advances public phase to `post_master` (same family as closeout primary).
- Bulk/H3 next require `gates.spec` green.
- Tests drive disk → `recompute_gates` → `build_dispatch`.

## [2.39.50] - 2026-08-05

### Docs / Ops (S5.3 execute canary PARTIAL)
- Real `h3 cycle --until-empty --execute` on angles film; **stop_reason=capacity_not_ready** (fail-closed honesty).
- Receipt: `artifacts/2026-08-05-s53-until-empty-canary.json` · strategy rev 2026-08-05d.
- Full `queue_empty` overnight drain still needs free 5090 VRAM/RAM + idle Comfy queue.

## [2.39.49] - 2026-08-05

### Added (Weapon inventory → generation_ready / next_actions)
- **generation_ready**: `weapon_inventory` primaries + `still_wp`/`motion_wp` line tags + material hints.
- **next_actions**: visual H3/queue why strings tag `wp=<motion primary>`.
- **dispatch** packet exposes `weapon_inventory`; compact surfaces primaries + inventory_line.
- **Tests**: generation_ready inventory, next_actions wp tag, compact line.

## [2.39.48] - 2026-08-05

### Added / Fixed (strategy residual closeout · S2.3–S7)
- **S2.3** final hotpath: env force ship, film-spec caption_path, master_hf single-layer ok.
- **S5.1** `design_go` craft one-pager + `receipts/design-go-onepager.md`.
- **S5.2** doctor advisory when Comfy tunnel ok but profile not h3_primary/hybrid_h3.
- **S3.3–S3.4** W3 packages SHIPPED; AGENTS AREA package pointers; refactor tracker W0–W3/W5 DONE.
- **S4** hotpath failure contracts closed; further leaf peel optional (W4 peels may coexist).
- **S5.3** remains **OPEN_OPS** (true overnight canary needs human GO + 5090).
- **S5.4 / S6 / S7** closed to evidence (generation_ready compact · util · timeout floors).
- Strategy rev **2026-08-05c**: `docs/plans/2026-08-05-strategy-director-engineer-upgrade.md`.

## [2.39.47] - 2026-08-05

### Changed (module refactor · W4 render_final peel)
- New package `scripts/final/`: `caption_text` · `voice` · `media_ops` · `errors`.
- Peel pure caption/voice/media helpers from `render_final.py` (~4333 → **~3305** LOC).
- Hard-compat: `render_final` re-exports public symbols for existing tests/importers.
### Added / Fixed (strategy residual closeout · S2.3–S7)
- **S2.3** final hotpath: env force ship, film-spec caption_path, master_hf single-layer ok.
- **S5.1** `design_go` craft one-pager + `receipts/design-go-onepager.md`.
- **S5.2** doctor advisory when Comfy tunnel ok but profile not h3_primary/hybrid_h3.
- **S3.3–S3.4** W3 packages SHIPPED; AGENTS AREA package pointers; refactor tracker W0–W3/W5 DONE.
- **S4** hotpath failure contracts closed; monolith leaf peel deferred (honest residual).
- **S5.3** remains **OPEN_OPS** (true overnight canary needs human GO + 5090).
- **S5.4 / S6 / S7** closed to evidence (generation_ready compact · util · timeout floors).
- Strategy rev **2026-08-05c**: `docs/plans/2026-08-05-strategy-director-engineer-upgrade.md`.
## [2.39.47] - 2026-08-05

### Changed (module refactor · W4/W5 finish)
- **W4 packages**: `scripts/post/render_final.py` · `scripts/narrative/edit_policy_heat.py` with top-level hard-compat shims.
- **W5 docs**: AGENTS layout/AREA pointers · refactor tracker closeout · REFACTORING_PLAN superseded pointer.
- Public import names and CLI strings unchanged.

## [2.39.46] - 2026-08-05

### Added (Weapon inventory CLI + doctor/dispatch surface)
- **`aifilm weapon inventory`**: list/filter tiers; `--primary-for`; `--validate` cross-check.
- **`inventory_report()`** on `weapon_inventory.py`.
- **doctor** soft field `weapon_inventory` (line + primaries + validation).
- **weapon_router** `inventory_line`; compact dispatch `weapon_inventory_line`.
- **Tests**: `test_cli_weapon` inventory cases · compact line · report helpers.

## [2.39.45] - 2026-08-05

### Changed (module refactor · W3 package layout)
- Packages: `scripts/spine` · `assets` · `plan` · `gates` (plus existing `core`).
- Top-level shims rebind via `sys.modules` (public import names unchanged).
- Nested `Path(__file__)` roots fixed for dispatch/advance/plan schemas.
- Hub re-exports write-spec `_compatibility_*` for hard-compat tests.

## [2.39.44] - 2026-08-05

### Changed (module refactor · W3 package dirs + shims)
- Domains: `scripts/assets/` · `scripts/spine/` · `scripts/gates/` · `scripts/plan/` (42 modules).
- Top-level hard-compat shims via `sys.modules` replacement.
- Skill-root schema path parents fix in plan loaders.
- Tests: `tests/test_w3_package_shims.py`.

## [2.39.43] - 2026-08-05

### Changed (module refactor · W3 package dirs + shims)
- Package domains under `scripts/`: **assets/** · **spine/** · **gates/** · **plan/** (42 modules).
- Top-level `import X` kept via thin `sys.modules` shims (hard-compat).
- Path fixes for skill-root schemas (`parents[2]`) in plan loaders.
- Tests: `tests/test_w3_package_shims.py`.

## [2.39.42] - 2026-08-05

### Fixed (S1 hang residual · strategy tick)
- **scene_sound_stems** ffmpeg encode/decode: `timeout=120/180` → `SceneSoundError` on hang (no overnight pipe freeze).
- **tts_backend** local adapter: `timeout=600` → `TTSError` on hang.
- **AF1 test**: behavioral `_soft_identity_penalty` TimeoutExpired soft-skip + scene_sound timeout structural assert.
- **Strategy plan**: S0/S1/S2.1–2 checkboxes aligned to SHIPPED evidence (S2.3 still open).

## [2.39.41] - 2026-08-05

### Added (H3 idle-gated combo eval)
- `h3_combo_eval.py` + `aifilm h3 combo-eval` + `registry/h3-combo-winners.json`
- Wired into `effect_tips` / `preferred_mode_for_lane`
- Tests: `test_h3_combo_eval.py`


## [2.39.40] - 2026-08-05

### Fixed (Workflow wire · primary next ↔ seven-step phase)
- **Legacy public phase** no longer freezes at `define_story` when drama-graph is absent: production evidence (style/spec/pilot/clips/plate/final) advances the seven-step phase.
- **Plate thrash**: after plate exists, primary is `closeout-run` — not `audio-plan` / `gate-auto` / `post-plan-init`.
- **Visual stage label**: drop Seedance-as-default wording → `Grok still + H3/Grok I2V`.
- **Tests**: `tests/test_workflow_wire_primary.py` state-matrix regression; compact dispatch phase expectations aligned.

## [2.39.33] - 2026-08-05

### Added (Weapon armory inventory · primaries + handoff)
- Cross-modality weapon inventory SSoT (see prior commit e4dca61f).

## [2.39.34] - 2026-08-05

### Fixed / Added (antifragility AF1–AF6 + AF8)
- **AF1** `h3_fill_idle` identity midframe ffmpeg → `util.subprocess.run(..., timeout=30)`; hang soft-skips with caution.
- **AF2** `media_queue.complete` handoff/sidecar failures write `receipts/media-queue-partial.json` (no silent `pass`).
- **AF3** `closeout` ladder runs `post_doctor`; hard codes block; `MIX_PARTIAL` advisory.
- **AF4** TTS opt-in fallback writes `receipts/tts-partial.json` + `partial`/`honest_limits` on result.
- **AF5** until-empty `capacity_not_ready` stop covered in tests.
- **AF6** closeout evidence probe crash with final present is fail-closed (not advisory green).
- **AF8** hard-defaults hero bulk prose → **h3_primary** (FRW-first stale line removed).
- **Plan**: `docs/plans/2026-08-05-antifragility-todoplan.md` · tests `test_antifragility_af.py`.

## [2.39.30] - 2026-08-05

### Changed (module refactor · W1 core + W2 hub ≤2500)
- **W1** `scripts/core/*`: emit / film_io / gates / media_ops / paths / constants; hub re-exports for hard-compat.
- **W2** CLI extract: `cli_media/post/status` parsers + `cli_quality_ops` / `cli_director_ops` / `cli_motion_ops` / `cli_review_ops` / `cli_misc_ops`.
- **`aifilm_grok.py`**: ~5028 → **~1513** LOC (target &lt;2500 **met**).
- Public subcommand strings unchanged; `probe_native_audio_mean_volume` keeps hub-level `run` patchability.

## [2.39.29] - 2026-08-05

### Added (Post P3 · agent-review-final machine lane)
- **`agent_review_final` L0** merges post machine lane into objective dims: caption-pixel, post-route double-burn, timeline dual-clock, post-doctor hard codes, mix PARTIAL notes, true-video / cinematic-gate.
- **Never** auto-approves `review-final` / `final_complete`; `--apply` still requires verbatim user phrase.
- Receipt exposes `machine_lane` + `p3_post_lane`.
- **Tests**: `test_agent_review_final` P3 cases (double-burn, dual-clock, mix PARTIAL note).

## [2.39.28] - 2026-08-05

### Changed (CLI extract · W5d2 parsers)
- Move `add_orchestrate_parsers` / `add_oauth_parsers` / `add_evidence_parsers` / `add_bootstrap_parsers` out of `build_parser`.
- `aifilm_grok.py` ~5348 → ~5029 LOC; public subcommand strings unchanged.
- Tests: extend `test_cli_w5d_extract.py`.

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
