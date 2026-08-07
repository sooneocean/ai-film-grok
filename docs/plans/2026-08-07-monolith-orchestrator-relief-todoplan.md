# 巨石模组舒缓 Todo Plan（2026-08-07 · 现状诊断 + 分步队列）

**Status:** ACTIVE · 结构债单一执行板（2026-08-07）  
**Plugin:** **2.41.7** · checkout `plugins/ai-film-grok`  
**历史主档（勿重开已 ship 波）：**  
- [project-module-refactor](docs/plans/2026-08-05-project-module-refactor.md) · W0–W7 **DONE**  
- [residual-monolith-w4](docs/plans/2026-08-05-residual-monolith-w4-todo.md) · 包边界 + pure leaf **DONE**  
- [monolith-relief M0–M4](docs/plans/2026-08-06-monolith-relief-todoplan.md) · heat facade / film_spec 拆 / final 叶子 **SHIPPED**  
- [metabolism inventory](docs/reports/2026-08-06-code-metabolism-inventory.md) · **SAFE MIGRATE QUEUE 已空** · 顶层只剩 hub + `workflow_pack`  
- [monolith-closeout](docs/plans/2026-08-06-monolith-closeout.md)

---

## 0. 结论先行（一句话）

**厂房门牌已贴完；真巨石不再是「放错目录的文件」，而是 5～8 个「两千行单函数总控台」。**  
舒缓策略 = **先 harness → 再按阶段抽纯叶 → 最后把编排函数压成 stage 序列**；禁止虚荣 LOC 冲刺、禁止预防性重拆 heat、禁止再搬整仓 package。

---

## 1. 类比（文科可读）

| 片厂 | 代码现状 |
|------|----------|
| 各车间已有门牌 | `core/ post/ narrative/ plan/ media/ audio/ cli/ gates/ final…` |
| 前台接待台要留着 | `aifilm_grok.py` hub ≤2500 · **禁止埋进包** |
| 旧电话簿还得能拨通 | 顶层 ~346 薄 shim（hard-compat）· **禁止一夜删光** |
| 总控室旋钮仍全挤在一张桌子上 | `render_final()` **2525 行**、`validate_film_spec()` **2360 行**、`run_preflight()` **2119 行** |
| 色气规章已拆成小册 | heat facade **136 行** + `heat_*` packs · **结构 DONE，勿再拆** |

---

## 2. 已 ship（禁止重开 / 禁止当 TODO）

| 波次 | 内容 | 证据 |
|------|------|------|
| W0–W3 | hub extract · `core/*` · package dirs · shims | AREA 表 · `test_w3_package_shims` |
| W4 包边界 | `post/render_final` · heat 进 package | 顶层 4 行 shim |
| W5–W7 | docs · audio/media · cli 扩包 | metabolism inventory |
| heat 内部 packs | phase/wardrobe/coitus/spice/impact/multi/arc_lint + facade | facade **136 LOC** |
| film_spec 外壳 | facade + `film_spec_validate` + constants/profile/lints | 禁再写单文件 3k |
| final 叶子 | `final/*`（tts/voice/watchdog/manifest/…） | 文件在，**编排体仍厚** |
| C6 migrate | 安全整文件迁移队列 **空** | `test_c6_migrate_queue_empty` |
| 顶层 intentional residual | **仅** `aifilm_grok.py` + `workflow_pack.py` | inventory IRON |

**诚实语言：** 搬进包 ≠ 内部 peel DONE；heat facade 化 ≠ 色气债清零（那是产品 IRON，不是结构债）。

---

## 3. 2026-08-07 探针（本会话实测）

### 3.1 仓体量

| 指标 | 值 |
|------|-----|
| scripts 总 Python | **~187.7k LOC** |
| 顶层 `*.py` | **~381**（绝大多数 thin shim，avg ~27 行） |
| 最大领域包 | plan **35.5k** · media **32.5k** · post **19.7k** · audio **19.1k** · cli **17.7k** · narrative **15.7k** |

### 3.2 真巨石表（风险 × 触达 · 按最长函数）

| Pri | 模块 | 文件 LOC | 最长函数 | 形态 | 策略 |
|-----|------|--------:|----------|------|------|
| **P0** | `post/render_final.py` | **3128** | `render_final` **2525** | 出片总编排 · 已有编号注释 stage | **StageContext + 分阶段 peel** |
| **P0** | `plan/film_spec_validate.py` | **2468** | `validate_film_spec` **2360** | 契约混装单过程 | **按校验节拆 leaf · 入口组装** |
| **P1** | `gates/preflight.py` | **2197** | `run_preflight` **2119** | doctor/开工总检 | **按检查段拆 pack** |
| **P1** | `post/export_composition.py` | **2574** | `write_hyperframes` **785** + remotion **538** | 导出 writer 厚 | harness 已有 · **writer peel** |
| **P1** | `cli/cli_post.py` | **2526** | `cmd_final` **771** | CLI 层膨胀 | **参数装配 vs 领域调用分离** |
| **P2** | `workflow_pack.py` | **2713** | `ship_prep` **692** | 收工编排 · **故意留顶层** | **仅 bug 挡路再 peel** |
| **P2** | `plan/story_plan.py` | **3122** | `project_graph_to_film_spec` **697** | 高覆盖规划 | **仅双路径/ thrash** |
| **P2** | `media/h3_fill_idle.py` | **3035** | until_empty **372**（多中等函数） | 运维吞吐 | **capacity/until-empty thrash 才拆** |
| 健康 | `narrative/edit_policy_heat.py` | **136** | facade | 已拆完 | **冻结** |
| 健康 | `aifilm_grok.py` | **~1010** | hub | ≤2500 | **冻结入口形态** |
| 较健康 | `gates/production_gates.py` | **2395** | 最长 ~243 | 多中等函数 | 触达小改即可，**不强制巨石化 peel** |

### 3.3 次级厚体（watch list，不默认排期）

`media/h3_workflow` · `audio/tts_backend` · `post/compose_render` · `narrative/edit_policy` · `cli/cli_media` · `media/media_queue` · `media/grok_oauth` · `media/comfy_video` · `plan/narrative_control` · `spine/dispatch` · `media/i2v_provider`

### 3.4 附加税（结构外但仍伤维护）

1. **双 checkout**：`~/.grok/ai-film-grok` vs `plugins/ai-film-grok` — 禁手拷；只改当前 `git rev-parse` 树  
2. **plan 文档发散**：多份 optimization/monolith 板状态过期 → agent 重做已 ship 项（本档应成为 **结构债单一执行板**）  
3. **shim 海**：保留 hard-compat；不把「删 shim」当进度  
4. **领域包巨胖**（plan/media）：那是能力面宽，不是单文件失败；**禁止**为瘦包而乱切垂直边界

---

## 4. 根因（为何仍「像巨石」）

1. **编排型债务**：叶子已抽走，**控制流仍在一个函数里顺序写满**（final / validate / preflight）。  
2. **契约混装**：校验 / 投影 / 默认值 / 报错同过程（film_spec_validate）。  
3. **CLI 与领域粘连**：`cmd_final` 既解析参数又写业务分支。  
4. **覆盖不均**：final 有 hotpath；export/preflight/validate 偏「人肉或宽测」。  
5. **错误叙事**：旧 plan 仍写 heat 3788——**已过时**；应以本探针为准。

---

## 5. 铁律（binding）

1. **挡路才拆**；无 bug / 无多段同改 = 可标 `PARTIAL(无触发)`，禁止硬拆。  
2. **纯叶优先**；先无 IO 纯函数 + 单测，再动 orchestrator。  
3. **行为 vs 结构分 commit**；peel commit **禁** retune heat / `i2v_provider` / pilot / adult floor。  
4. **Public `aifilm` 子命令字符串 + shim hard-compat 不变**。  
5. **禁止「全员 <1500 LOC」虚荣冲刺**；成功标准 = 最长函数可测可跳读 + 热路径回归绿。  
6. **DONE** = 路径 + LOC/函数 span 前后 + 相关测绿 +（指纹变）`lock-runtime` + CHANGELOG/semver 按仓规。  
7. **出片诚实优先于 peel**；运维日 / 真片日默认不做结构大手术。  
8. **不重开**：整文件 migrate 队列、heat 预防性再拆、一夜删 shim、双树手拷。

---

## 6. 舒缓方法论（每石同一套四步）

```text
S0 探针   → 最长函数 span + 调用图 + 现有测覆盖
S1 Harness → 缺 failure-mode 测先补（垃圾输入 / 缺文件 / 门红诚实）
S2 Pure leaf → 无副作用助手先出包（已有 final/* 模式）
S3 Stage peel → 编排函数只剩：load ctx → stage1()…stageN() → receipt
```

**Stage 切分启发式（已在 `render_final` 注释里天然存在）：**

| 注释锚点（约） | 候选 leaf / stage |
|----------------|-------------------|
| Per-shot TTS / native XOR | `final/stages_tts_stems.py` |
| stretch / visual_fit / plate slot | `final/stages_plate_stretch.py` |
| concat + join transitions | `final/stages_picture_concat.py` |
| Music / spotting / procedural bed | `final/stages_music_bed.py` + `render_final_music` |
| Dual-track mix / sidechain / partial | `final/stages_dual_mix.py` |
| Subtitle burn / SRT clock | `final/stages_subs.py` (**SHIPPED**) |
| Mux + manifest delivery_class | `final/stages_mux_manifest.py` |

**RenderContext（已落地 `final/render_context.py`）：**  
`root, paths, args, spec, manifest, shots, vo_cfg, work_dirs, receipts` 显式对象，避免 80 个局部变量闭包。

---

## 7. Todo 队列（可勾选 · 分波）

### Wave 0 · Hygiene 与单一真相（半日 · 低风险）

- [x] **W0.1** 冻结本探针表到 `docs/plans/2026-08-07-monolith-orchestrator-relief-todoplan.md`  
- [x] **W0.2** 旧板 header 指到本档（residual-monolith / monolith-relief / module-refactor / metabolism inventory）——**只改指针**  
- [x] **W0.3** 护栏确认：hub **1009** ≤2500 · `runtime-python` pytest shim+c6 **10 passed**  
- [x] **W0.4** mega-fn budget 测：`tests/test_mega_fn_budget.py`（>800 行须白名单；peel 后低于预算须删白名单项）

**DONE：** 单一结构板生效 · hub 仍 ≤2500 · shim 测绿 · mega-fn 防复发

---

### Wave 1 · `render_final` 编排体（P0 · 最高 ROI · 可多 PR）

> 目标不是「文件 <1500」，而是 **`render_final` 变成 <400 行 stage 序列**，每 stage 可单测。

#### W1.0 stage 地图（探针 · `render_final` L328–2855 · 2026-08-07）

| # | 约行 | 阶段 | 候选模块 | 铁律/备注 |
|---|------|------|----------|-----------|
| 0 | 328–460 | load ctx / paths / vo_cfg / lipsync gate | `final/render_context.py` | 入口装载 |
| 1 | 461–1027 | Per-shot TTS · native XOR · 口白窗三角 · visual_fit | `final/stages_tts_stems.py` | A2 · Chinese-only |
| 2 | 1028–1139 | Stretch clips to plate/VO | `final/stages_plate_stretch.py` | post lipsync removed |
| 3 | 1140–1174 | Title / end cards | 既有 `final/cards.py` | |
| 4 | 1175–1285 | Concat + join transitions | `final/stages_picture_concat.py` | T4 transition_ops |
| 5 | 1286–1367 | Narration track / acrossfade | 可并入 stems 或 concat | |
| 6 | 1368–1940 | Music bed · spotting · procedural · provenance | 深化 music leaf | A4 rnb→procedural |
| 7 | 1941–2438 | Dual mix · sidechain · PARTIAL · loudness | `final/stages_dual_mix.py` | Wave D PARTIAL 诚实 |
| 8 | 2439–2542 | Subtitle cues · PIL burn | `final/stages_subs.py` | HF owner / plate subs=off |
| 9 | 2543–2855 | Mux · manifest · delivery_class | `final/stages_mux_manifest.py` | A5 plate≠master |

- [x] **W1.0** stage 地图（上表）  
- [x] **W1.1** `final/render_context.py` + `load_render_context` 已挂 `render_final`；helpers→`render_helpers`；**行为零变**  
- [x] **W1.2** peel **music/spotting 残留** → `final/stages_music_bed.py`（seed/anti-fatigue/timelines/materialize + A4 receipt）  
- [x] **W1.3** peel **dual mix + partial receipt**（已有 `mix_partial` / sidechain 诚实语义 · 禁改 PARTIAL 语义）  
- [x] **W1.4** peel **subs burn / caption clock** → `final/stages_subs.py`  
- [ ] **W1.5** peel **TTS stems + native XOR + 口白窗三角**（A2 IRON · 测锁死）  
- [ ] **W1.6** peel **stretch/concat/join**  
- [x] **W1.7** (mux leaf + official finalize leaf) peel **mux + delivery_class / master_lock 诚实字段**（A5 · plate≠master）  
- [ ] **W1.8** `render_final()` 只编排；`main` 不变；shim `main()` 仍进真实现

**Verify（每子波）：**
```bash
cd skills/ai-film-grok
python -m pytest tests/test_final_hotpath_contracts.py tests/test_render_core_helpers.py \
  tests/test_suse_final_iron.py tests/test_w3_package_shims.py -q
# 指纹变： make -C "$ROOT" lock-runtime
```

**Iron：** caption 双烧禁、VO-BGM gain、native XOR、`delivery_class` 语义、timeout/watchdog **不得在 peel commit 改**

**默认触发：** final 相关 bug 或「同一 PR 要改 3+ stage 段」→ 先 peel 该段；**纯工程日可按 W1.1→W1.3 推进**

---

### Wave 2 · `film_spec_validate` 节拆（P0 · 触达 write-spec / lock）

- [x] **W2.1** 盘点 `validate_film_spec` 内自然段落（provider / heat floor / dialogue / audio / continuity / …）  
- [x] **W2.2** (heat/cast/adult tail → film_spec_validate_heat) 每节 → `plan/validate_*.py` 或 `plan/film_spec_validate_*.py`，返回 issue 列表  
- [x] **W2.3** 入口 `validate_film_spec` 只聚合 + 排序 + 兼容旧 schema  
- [ ] **W2.4** 与已 peel 的 `film_spec_lints` **去重**（禁双实现）

**Verify：** `test_cli_write_spec_extract` · director intent · 相关 story contract 测

**Iron：** 禁 silent 改 `i2v_provider` / h3 默认 / adult sex floor

---

### Wave 3 · `preflight` 段拆（P1 · doctor / 开工）

- [ ] **W3.1** `run_preflight` 分段地图（env / tools / film root / gates / receipts…）  
- [ ] **W3.2** 每段 pure report builder → `gates/preflight_*.py`  
- [ ] **W3.3** 入口组装 status；CLI `main` 不变  
- [ ] **W3.4** 补 2～3 条 harness：缺 ffmpeg / 坏 root / 最小绿片

**Verify：** doctor 相关测 + 手跑 `aifilm doctor`（或 project 等价入口）

---

### Wave 4 · export writers（P1 · harness-first 已部分存在）

- [ ] **W4.1** 确认 `test_export_hotpath_contracts` / `ParseSrt` 仍绿  
- [ ] **W4.2** peel `build_timeline_package` 纯构建  
- [ ] **W4.3** peel `write_hyperframes` 子构建（title/end-roll/timeline HTML）  
- [ ] **W4.4** peel `write_remotion` 对称  
- [ ] **W4.5** `export_composition` 入口变薄

**Iron：** HF 字幕 owner · plate `subs=off` 契约 · 禁双烧

---

### Wave 5 · CLI 装配层（P1 · 可选）

- [ ] **W5.1** `cli_post.cmd_final`：只做 argparse → namespace → 调 `render_final` / gates；业务 if 下沉 domain  
- [ ] **W5.2** `add_post_parsers` 若继续胀 → `cli/parsers_post_*.py`  
- [ ] **W5.3** `cli_media` 仅当 register/i2v  thrash

**Iron：** 子命令字符串与 flag 名不变

---

### Wave 6 · 故意残留 / 次级（默认不排 · 条件触发）

| ID | 模块 | 触发条件 |
|----|------|----------|
| W6.1 | `workflow_pack.ship_prep` / `bulk_preflight` | 收工门连改 ≥2 段 或 假绿 bug |
| W6.2 | `story_plan.project_graph_to_film_spec` | 双路径 / graph→spec 不一致 |
| W6.3 | `h3_fill_idle` | until-empty / free-first 再变政策时 |
| W6.4 | `edit_policy` vs heat | 双 owner 痛 |
| W6.5 | production_gates | **不默认 peel**（已是多中等函数） |
| W6.6 | `spine/dispatch.build_dispatch` (~1258) | dispatch 契约 thrash |
| W6.7 | `post/closeout.closeout_status` (~994) | 收工门连改 |

**`workflow_pack` IRON：** 禁止 whole-file 再 migrate；bug-driven leaf only。

---

### Wave 7 · 防复发与文档税（持续）

- [x] **W7.1** mega-fn 白名单测（见 W0.4 · `test_mega_fn_budget`）  
- [ ] **W7.2** 新代码禁止在顶层加厚实现（只许 shim 或 hub 路由）  
- [ ] **W7.3** 结构 peel 完成后：本档勾选 + metabolism inventory 一行刷新 · **禁**再开第三份 monolith plan  
- [ ] **W7.4** 双 checkout：改前 `git rev-parse --show-toplevel` 自检写进 PR 模板一句（可选）

---

## 8. 执行序（给圣旨短令用）

```text
纯工程日 go：
  W0 → W1.1（context）→ W1.2/W1.3（最纯 mix/music）→ check-all
  若仍有额度：W2.1 地图（只文档）或 W1.4

有 final bug go：
  只 peel 挡路 stage（W1.x 对应段）+ hotpath 测 · 禁止顺手 retune

有 write-spec / lock bug go：
  W2 一节 · 禁止全文件重排

出片日 / 5090 运维日：
  不做 peel · PARTIAL(无触发) 合法

默认结构 go（无触达）：
  W0 落档 + 指针 · 不要硬拆 heat / workflow_pack / story_plan
```

**Dispatch 地图（α.2）：** [2026-08-07-dispatch-stage-map.md](2026-08-07-dispatch-stage-map.md)

**Top-5 ROI：**  
1) final stage 序列化  
2) validate 节拆  
3) preflight 段拆  
4) export writer  
5) mega-fn 防复发测  

---

## 9. 非目标

- 虚荣把任意文件压到 1500 行  
- heat 再拆 10 包 / 删 facade  
- 一夜删除 hard-compat shim  
- 全仓 FilmError / 静默 except 大扫除（触达才改）  
- 重写 IRON 产品规则当「结构优化」  
- 把 `workflow_pack` 或 hub 整文件搬进 package  
- 为瘦 `plan/` `media/` 包而做垂直大搬家  

---

## 10. 成功定义（一迭代结束）

| 标准 | 信号 |
|------|------|
| 可读 | `render_final` 主函数 span **显著下降**（目标方向 <400；未达也须 ≥1 个 stage 独立文件） |
| 可测 | 新 stage 有单测或 hotpath 命中；peel 后 final 相关测全绿 |
| 诚实 | 无行为漂移；plate/master、PARTIAL mix、native XOR 测仍锁 |
| 单一真相 | 结构债只认 **2026-08-07 orchestrator relief** 板；旧板只作证据 |
| 不伤产线 | public CLI · shim · hub 预算 · migrate 空队列 仍成立 |

---

## 11. Verify 总清单

```bash
ROOT="$(git rev-parse --show-toplevel)"
test "$(wc -l < "$ROOT/skills/ai-film-grok/scripts/aifilm_grok.py")" -le 2500
cd "$ROOT/skills/ai-film-grok"
python3 -m pytest \
  tests/test_w3_package_shims.py \
  tests/test_c6_migrate_queue_empty.py \
  tests/test_final_hotpath_contracts.py \
  tests/test_render_core_helpers.py \
  tests/test_suse_final_iron.py \
  tests/test_export_hotpath_contracts.py \
  tests/test_heat_check.py \
  tests/test_heat_arc_multi.py \
  -q
# 大 peel 后：
# make -C "$ROOT" check-all && make -C "$ROOT" lock-runtime
```

---

## 12. 与历史板关系

| 旧板 | 关系 |
|------|------|
| module-refactor W0–W7 | **DONE** · 本档不重复 |
| residual-monolith R* | pure leaf **DONE** · orchestrator residual **由本档 Wave 1–4 接管** |
| monolith-relief M0–M4 | **SHIPPED** · M5 并入本档 Wave 6 |
| metabolism terminal freeze | **仍 binding** · 顶层只留 hub + workflow_pack |
| CTO / next-opt 总板 | 产品/运维项仍归它们；**结构 orchestrator 债以本档为准** |

---

*Baseline probe: 2026-08-07 · plugin 2.41.4 · render_final 2525 · validate 2360 · preflight 2119 · heat facade 136.*
