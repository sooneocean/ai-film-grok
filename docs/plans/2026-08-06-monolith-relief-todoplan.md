# 巨石舒缓 Todo Plan（2026-08-06 · 诊断 + 执行队列）

**Status:** ACTIVE · **M0–M4 SHIPPED (2.40.12)** · M5 deferred  
**Plugin:** **2.40.12** · checkout `plugins/ai-film-grok`  
**结构主档（历史 wave）：** [residual-monolith-w4-todo](2026-08-05-residual-monolith-w4-todo.md)  
**综合执行板：** [next-optimization-todoplan](2026-08-06-next-optimization-todoplan.md) Wave 3  
**Tracker：** [project-module-refactor](2026-08-05-project-module-refactor.md)

---

## 结论先行

包边界（W0–W7）**已 ship**；真痛不是「整仓一坨」，而是 **5～6 个 2.5k–4k 行领域总控台** 难改、难测。

**舒缓 = 挡路才拆 + 先 harness 再 peel + 禁止虚荣 LOC 冲刺。**  
日常出片优先诚实回归；结构债不是默认主业。

| 探针（2026-08-06） | 值 |
|--------------------|-----|
| scripts `.py` / LOC | ~637 / ~163k |
| tests | ~407 |
| ≥2k 文件 | **10** |
| ≥1k 文件 | **34** |
| 最大石 | heat **4024** · film_spec **3147** · render_final **2985** · story_plan **2948** · export **2804** |
| hub | **994** ≤2500 |
| render_final 形态 | **7 def**，载荷在 `render_final()` |
| heat 形态 | **53 def**（phase/wardrobe/coitus/spice…） |

**诚实语言：** 搬进包 ≠ 内部 peel DONE。residual = orchestrator / heat packs / film_spec validate / export harness。

---

## 1. 类比

| 工厂 | 代码 |
|------|------|
| 厂房已贴门牌 | `core/post/narrative/audio/media/plan/cli/final…` + 顶层 shim |
| 总控室仍塞满旋钮 | `render_final()` 单函数编排；heat 多主题挤一文件 |
| 规章已上墙 | hard-defaults / IRON 测 |
| 真痛 | 改一处要通读整本总控；假绿比「行数」更贵 |

---

## 2. 已 ship（禁止重开）

| 波次 | 内容 |
|------|------|
| W0–W3 | hub · `core/*` · package dirs · shims |
| W4 | `post/render_final` · `narrative/edit_policy_heat` **包边界** |
| W5–W7 | docs AREA · audio/media · cli 扩包 |
| R1/R1c | `final/*` 叶子 · final 4333→~2985 |
| R3a | `film_spec_profile` · `film_spec_sex_floor` 等纯叶（validate 仍 residual） |

---

## 3. 巨石表（风险 × 触达）

| Pri | 模块 | ~LOC | 策略 |
|-----|------|-----:|------|
| P0 | `post/render_final.py` | 2985 | 挡路 peel stages → `final/*` |
| P1 雷区 | `narrative/edit_policy_heat.py` | 4024 | **仅 bug-driven** pack peel |
| P1 | `plan/film_spec.py` | 3147 | 触达拆 validate vs projectors |
| P2 | `export_composition` / `story_plan` / `edit_policy` / `h3_fill_idle` / cli_* | 2.1k–2.9k | harness 先 / 双路径 / growth guard |
| 健康 | hub · `core/*` | ≤1k | 守住 |

**附加税：** root shim 海 · 双 checkout · plan 文档发散 · 407 测+refs 上下文。

**包体积（告警）：** root~35k · media 22k · plan 17k · audio 17k · cli 16k · post 14k · narrative 13k。

---

## 4. 根因（为何仍「像巨石」）

1. **编排型**：`render_final` 行数降了，单函数控制流仍厚。  
2. **领域词典型**：heat 可切但交叉引用多，预防性全拆易 cycle。  
3. **契约混装**：film_spec validate/write/projector 同文件。  
4. **覆盖不均**：final 有 hotpath；export 偏人肉。  
5. **错误叙事**：W4 包边界 ≠ 结构债清零。

---

## 5. 铁律

1. 挡路才拆 · 纯叶优先 · 行为与结构分 commit  
2. public CLI + shim hard-compat 不变  
3. 禁 1500-LOC 虚荣冲刺 · 禁 peel 里 retune heat/i2v/pilot  
4. DONE = 路径 + LOC + 测绿 +（指纹变）lock-runtime  
5. 出片诚实优先于 peel  

---

## 6. Todo 队列（可勾选）

### M0 · Hygiene — **SHIPPED 2026-08-06**

- [x] hub ≤2500（994）  
- [x] `core/` · `post/render_final` · `narrative/edit_policy_heat`  
- [x] `pytest tests/test_w3_package_shims.py` → **9 passed**  
- [x] `git rev-parse` = plugins checkout  

### M1 · `film_spec` peel — **SHIPPED 2.40.12**

- [x] M1.1 `plan/film_spec_validate.py` + `film_spec_constants.py` + thin facade  
- [x] M1.2 constants vs validate 分文件 · 无 cycle（profile 仍 root）  
- [x] M1.3 structure-only（IRON 默认未改）  

**LOC：** facade ~80 · constants ~130 · validate ~3020（was 3147 monolith）。

### M2 · `render_final` stages — **SHIPPED partial 2.40.12**

- [x] M2.1 `_run_with_watchdog` → `final/watchdog.py`  
- [ ] M2.2 更多 stage（plate/mix/subs）— residual  
- [x] M2.3 shim `main()` 仍调实现（hotpath 测绿）  

**LOC：** render_final 2985→~2958 · watchdog ~67。

### M3 · export/compose harness — **SHIPPED partial 2.40.12**

- [x] M3.1 `tests/test_export_hotpath_contracts.py`（preset garbage + missing root）  
- [ ] M3.2 export builder peel — residual  

### M4 · heat phase pack — **SHIPPED 2.40.12**（用户 go 全开）

- [x] `narrative/heat_phase.py`：scale/phase normalize + escalation  
- [ ] wardrobe / coitus / spice packs — residual  
- 行为未 retune；`test_adult_heat_upgrade` 一条 sex ratio 0.495 vs floor 0.50 边界预存（未改 floor）  

**LOC：** heat 4024→~3788 · heat_phase ~264。

### M5 · 次级（默认不排）

| ID | 条件 |
|----|------|
| M5.1 h3_fill_idle | capacity/until-empty 再变 |
| M5.2 edit_policy | 与 heat 双 owner 痛 |
| M5.3 story_plan | 双路径残留 |
| M5.4 cli_post/media | 子命令继续胀 |

### M6 · 上下文税

- [x] 本档落库 + residual / next-opt 互指  
- [ ] memory 长文 archive（可选）  
- [ ] pytest slow/hotpath 再分层（可选）  

### S0 护栏（触达时）

- [ ] S0.3 顺手改 silent `except` / bare subprocess timeout（不扫全仓）  
- peel PR 写：动机 · 不动行为 · 测 · LOC before/after  

---

## 7. 执行序

```text
纯工程日：M0（已绿）→ 有 write-spec/final 触达则 M1 或 M2 一块 → check-all
出片日：final 诚实回归优先；仅大段改 final 时顺带 M2.1
运维日：不做 peel
默认 go（结构）：无触达 → PARTIAL(无触发)，禁止硬拆 heat
```

**Top-5 ROI：** final hotpath 守住 · 下次 film_spec→M1.1 · 下次 final→M2.1 · export bug→M3.1 · 双 checkout 纪律。

---

## 8. 非目标

一夜删 shim · heat 预防性 10 包 · 全仓 FilmError · 重写 IRON · 与行为混大 commit。

---

## 9. Verify

```bash
ROOT="$(git rev-parse --show-toplevel)"
test "$(wc -l < "$ROOT/skills/ai-film-grok/scripts/aifilm_grok.py")" -le 2500
cd "$ROOT/skills/ai-film-grok"
# use project Python 3.11+
python3 -m pytest tests/test_w3_package_shims.py tests/test_final_hotpath_contracts.py -q
# after peels:
# make -C "$ROOT" check-all && make -C "$ROOT" lock-runtime
```

---

*Baseline probe 2026-08-06 · M0 evidence: hub 994 · shim tests 9 passed.*
