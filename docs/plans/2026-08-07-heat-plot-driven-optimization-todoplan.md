# 色气剧情驱动优化 Todo Plan（2026-08-07）

**结论：** 现行「成人信号 → 自动钉 heat_scale=max + 全套硬闸」政策（2026-07-27 起源）导致**强制容易崩坏**：
plan 纸面抬 target（55/60/100s）却不增镜、rebalance 只加长单镜时长、H3 高难项硬做 → 反复硬刷崩坏。
本 plan 将色气政策改为 **剧情驱动档位 + 显式 max 才硬 + H3 能力边界 + PARTIAL 诚实兜底**（用户本次明示，覆盖旧裁决）。

| 项 | 值 |
|----|-----|
| Status | **SHIPPED code path 2.41.0**（真片冒烟 OPEN_OPS） |
| 用户决策 Q1 | **全套：代码+gate+文档** |
| 用户决策 Q2 | **显式 max 才硬 + PARTIAL 兜底**（剧情档 soft/hot 不套 max 硬闸；禁为冲 S 反复硬刷） |
| 目标版本 | plugin.json **2.41.0** |
| 上游衔接 | [optimization-todoplan](2026-08-06-optimization-todoplan.md) A1/B1/B2 · [shortform](2026-08-06-shortform-optimization-todoplan.md) S4 · [shot-generation-lane](2026-08-07-shot-generation-lane-todoplan.md) |
| 测试 | `test_story_plan` · `test_heat_arc_multi` · `test_heat_check` · `test_adult_max_wave3/4/5/6` · `test_delivery_gates` |

---

## 问题帧（为什么改）

1. **自动钉 max（P0）**：`detect_heat_signals`（story_plan.py:294）adult marker → `heat_scale=max`；`story_plan.py:907-931` `genre==adult` 且非 soft/medium → **无条件钉 max+extreme+evidence_max**（`pinned_by: genre_adult_default`）。→ 空 brief / 轻剧情也被强行拉满。
2. **纸面抬 target（P0）**：`story_plan.py:1070-1072` heat_scale=max → target 无条件抬 50/55/60/100s，**只抬纸面不增镜** → 单镜目标超 H3 实际能力（official high ~68s 实测）。
3. **凑数加长（P1）**：`rebalance_adult_beat_durations` 为凑 sex_floor 只加长 meat 时长 → 长镜崩坏（plate-boring P0 同理：长≠好看）。
4. **硬闸错挂（P0）**：`hard-defaults.md:15/18/19` 成人信号→自动 max+act+climax≥50% fail-closed+卸甲 IRON，全部绑定在「genre==adult」而非「用户显式拉满」。
5. **无诚实出口**：max 硬闸下做不了 → 反复硬刷（anti-hijack 只防画面，不防语义崩坏）；`scale_fallback` 兜底码（SCALE_SOFT_MAX/BARE_TEASE）存在但未与档位推导打通，且文档仍写「禁静默降档」。

## 新政策（目标态）

| 档 | 触发 | 硬闸 |
|----|------|------|
| **剧情驱动档（默认）** | brief 无显式拉满要求（含空 brief、轻剧情、普通成人题材） | **不套 max 硬闸**；act/climax 比例按剧情自然分布；卸甲/定器 advisory 不强做 |
| **显式 max 档** | brief 显式拉满（「尺度拉到最高」「办事戏完整」「重口」等明确 marker） | 全套硬闸保留（act+climax≥50%、四拍、定器、卸甲 IRON、冲 S） |
| **PARTIAL 兜底** | 显式 max 但 H3 能力达不到 | 允许 `scale_fallback` 诚实降档交付（全裸诱惑→模型极限），**禁反复硬刷崩坏**；receipts 记录 honest_cap |

**核心原则（用户原话）**：顺应剧情就好；以 H3 能发挥的内容为准；不要硬做你做不了的视频。

---

## 实施单元

### U1 — 档位推导改剧情驱动（代码 · P0）
**Files:** `skills/ai-film-grok/scripts/plan/story_plan.py`
- `detect_heat_signals`（:294）：adult marker 不再默认产出 `heat_scale=max`；改为**剧情强度推导**（light/romance → hot；hardcore 显式 marker → max）。保留 soft/medium 显式降档。
- `normalize_story` genre=adult pin（:907-931）：**删除无条件钉 max**。改为三态：
  - `heat.heat_scale in {soft, medium}` → 尊重降档；
  - brief 显式拉满（`want_max` / `hardcore` / 拉满 marker）→ `max` + `pinned_by: explicit_max`；
  - 其余 → **剧情驱动档**：`heat_scale="hot"`（或剧情推导值）、`spice_level` 由剧情定、不设 `evidence_max`。
- 新增/保留 `pinned_by` 字段值域：`explicit_max` | `plot_driven` | `user_soft`。

**Approach:** 抽 `_derive_heat_scale(raw, heat_signals) -> tuple[str, str]`（scale, pinned_by）；单测直接覆盖三态。**不碰** `detect_genre`（genre=adult 仍是题材事实）。

**Test scenarios:**
- 空 brief + genre=adult → `heat_scale="hot"`（剧情档），**不再 max**。
- brief 含「尺度拉到最高」/「办事戏」→ `max` + `pinned_by=explicit_max`。
- brief 含「纯爱」「轻喜剧」→ soft/medium 尊重。
- 既有 `test_story_plan` 中依赖「adult→max」的用例更新为显式 max 写法。

**Verification:** `pytest tests/test_story_plan.py -k "heat or adult"` 绿；`story_plan` 集成用例断言 `evidence_max` 仅显式档出现。

### U2 — plan 侧不纸面抬 target（代码 · P0）
**Files:** `skills/ai-film-grok/scripts/plan/story_plan.py`（`build_planned_graph` :1070-1072）· `film_spec.py`（:3176 大石，act/climax 静默拉 10s）
- `heat_target_lift`：仅 `pinned_by==explicit_max` 且剧情 beat 数支持时抬；抬升值 = `ceil(剧情需求 / H3_NOMINAL) * H3_NOMINAL`（H3_NOMINAL≈60s 基准），**禁直接写 55/60/100 纸面常量**。
- 剧情驱动档：target 由 beat 数自然推导，不抬。
- `film_spec` act/climax 静默拉 10s（A1 已有）：确认保留 fail 路径，不 auto-extend 超 H3_NOMINAL。

**Test scenarios:**
- 显式 max + 单 meat beat → target ≤ 1×H3_NOMINAL，不抬到 100。
- 剧情档 + 短剧情 → target 不因 genre=adult 抬升。

### U3 — rebalance 禁只加长不增镜（代码 · P1）
**Files:** `skills/ai-film-grok/scripts/plan/story_plan.py`（`rebalance_adult_beat_durations`）
- 凑 sex_floor 时：优先**新增镜 / 邻镜辅助镜**；单一 meat 镜时长 > H3_NOMINAL → 触发 fail + 建议 PARTIAL，**禁无限加长单镜**。

**Test scenarios:** 构造 floor 缺口 → 断言产生新 beat 而非单镜超 68s。

### U4 — 硬闸挂显式 max（gate · P0）
**Files:** `skills/ai-film-grok/scripts/narrative/heat_check.py`（`heat_check` :31 / `heat_agent_status` :322）· `edit_policy_heat.py`（:4026 大石）
- 读 spec 的 `pinned_by`/`heat_scale`：仅 `explicit_max` 时启用 act+climax≥50% fail-closed、四拍、定器、卸甲 IRON、S≥90 冲分。
- 剧情驱动档：上述转 **soft gate / advisory**（heat_agent_status 输出 advisory 提示，不 fail）。
- 显式 max + 实测达不到 → `scale_fallback` 诚实路径（SCALE_SOFT_MAX/BARE_TEASE/HARD_ON_BAN），**禁冲 S 反复硬刷**（S 目标降为「本次可达」）。

**Test scenarios:** `test_heat_arc_multi`（剧情档 soft）· `test_heat_check`（显式 max 仍 hard）· `test_adult_max_wave3/4/5/6` 显式 max 用例保持硬闸断言。

### U5 — hard-defaults 法条改（机读 gate · P0）
**Files:** `skills/ai-film-grok/references/hard-defaults.md`（:15/:18/:19/:23/:24）
- **:15** 成人信号 → 自动 max：改为「**显式拉满才 max**；剧情驱动档默认 hot；禁静默降档 → 允许 PARTIAL 诚实降档（receipts 留痕）」。
- **:18** act+climax≥50%：加注「仅显式 max」；剧情档按剧情分布（衔接 S4 peel）。
- **:19** 卸甲 IRON：加注「仅显式 max 强制；剧情档 advisory」。
- **:23/:24** 兜底保留，强化「禁反复硬刷崩坏，一次可达即收」。

**Test scenarios:** `test_hard_defaults`（若存在契约测）更新断言；`doctor` 过。

### U6 — 文档同步（文档 · P1）
**Files:** `skills/ai-film-grok/references/adult-max-playbook.md`（头部触发逻辑）· `skills/ai-film-grok/memory/2026-07-27-adult-scale-max-sex-arc.md`（新裁决覆盖）· `memory/2026-07-21-sex-hard-floors.md`（加「显式 max 才硬」）· `AGENTS.md`（硬规则 5/7 指针）· `CHANGELOG` + `plugin.json` bump 2.41.0
- 07-27 memory 追加**本次用户裁决**：原「尺度要拉到最高」为**用户显式要求**语境；本次「不一定要 max、顺应剧情、以 H3 能发挥的为准」**覆盖默认政策**。保留原文（memory 契约：原话+三句+清单+链 lesson）。

### U7 — 测试与验证收口（P0）
- `make -C "$ROOT" check-all`（validate + ruff + doctor + pytest -m 'not slow'）全绿。
- 专项：`test_story_plan` · `test_heat_arc_multi` · `test_heat_check` · `test_adult_max_wave*` · `test_delivery_gates`。
- `plugin validate`（改 CLI 面后）。

---

## 依赖关系

```
U1 ──► U2 ──► U3        （plan 侧同链，先档位后 target/rebalance）
U1 ──► U4               （gate 读 pinned_by，依赖 U1 输出字段）
U1/U4 ──► U5 ──► U6     （文档对齐代码语义）
U1..U6 ──► U7           （收口验证）
```

## 并行机会

- U1+U2+U3 可在同一 checkout 顺序推进（同文件 story_plan.py，避免冲突→串行或同 agent 一个 session）。
- U4 与 U5 可与 U2/U3 并行（不同文件面）。
- U6 文档可在 U1 定稿 `pinned_by` 语义后并行。

## 明确不做（deferred / out-of-scope）

- **不改 H3 模型/后端本身**（能力边界以现状为准，本次只改「要求」不吹「能力」）。
- **不改 `detect_genre`**：genre=adult 仍是题材事实，只改 heat 档位推导。
- **不删旧 memory**：07-27 裁决保留原文 + 追加覆盖记录（memory 契约）。
- **多后端编排（ai-film-pipeline / Seduction Logic Gate）**不在本仓范围。
- **anti-hijack / plate-boring** 已有 P0 机制，本次只保证不冲突。

## 验收定义（Done）

- [x] U1 三态档位推导落地，`pinned_by ∈ {explicit_max, plot_driven, user_soft}`，空 brief 不再 max。
- [x] U2 target 仅 explicit_max 抬升（H3-nominal）；U3 rebalance 既有 H3 cap 保留。
- [x] U4 gate 仅显式 max 硬；剧情档 advisory（heat_check / heat_agent_status）。
- [x] U5 hard-defaults 法条改完。
- [x] U6 CHANGELOG + 版本 2.41.0（memory 长文覆盖可选 follow-up）。
- [x] U7 专项 pytest 绿（heat_plot_driven + adult_heat + onboarding + hard_defaults + waves）。
- [ ] 真片冒烟：跑 1 条剧情驱动档短片（出片日 OPEN_OPS / 用户点名）。

---

*Status: SHIPPED code path 2.41.0 · 2026-08-07 · 用户决策：全套 + 显式 max 才硬 + PARTIAL 兜底*
