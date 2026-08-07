# 镜头生成逻辑优化 Todo Plan

**Status:** **Wave 0–4 SHIPPED (2.40.56)** · Wave 5–6 OPEN  
**日期：** 2026-08-07  
**范围：** 按镜头类型（对白镜 · 毒镜 · 肉戏 · setup · env · 续镜…）**依序**优化生成逻辑  
**Repo：** `/Users/dex/.grok/plugins/ai-film-grok`

## 结论先行

分类曾散落在多门禁；现已有机读 **`aifilm shot-lane`**。  
优先堵：毒 still 进 H3 / 对白 speaker 错 / 首帧小主体。

## 已 ship（Wave 0–1）

| 项 | 证据 |
|----|------|
| S0.1 `resolve_shot_lane` | `scripts/media/shot_lane.py` |
| S0.2 CLI | `aifilm shot-lane --root` |
| S0.3 测 | `tests/test_shot_lane.py` |
| S0.4 list 字段 | fill-idle row `generation_lane` |
| S1.1–1.2 毒拦 | `is_poison_blocked` 含 `anatomy_safe=false`；h3 run 仍 `assert_still_anatomy_for_i2v`；visual 5 行 SOP |
| S1.4 测 | poison_blocked fixture |

## Wave 2 SHIPPED（2.40.53）

| 项 | 证据 |
|----|------|
| S2.1 still 配方 | `lint_dialogue_still_recipe` + register-still + preflight |
| S2.2 no-speech lint | h3 `_prompt_for_shot` → `assert_dialogue_prompt_allows_speech` |
| S2.3 audio_lane | write-spec apply + preflight lint |
| S2.4 VO-fit/cut_on | `edit_policy` dialogue → mid_motion + vo |
| S2.5 测 | `tests/test_dialogue_wave2.py` |

## Wave 3 SHIPPED（2.40.55）

| 项 | 证据 |
|----|------|
| S3.1 fill on h3 run | `assert_still_path_ready_for_i2v` in `run_h3_shot` |
| S3.1 plan advisory | `plan_h3_shot.composition_fill` + `generation_lane` |
| S3.1 queue | media-queue I2V first input fill |
| S3.3 pilot | three_look composition_fill + lanes |
| 测 | `tests/test_composition_fill_wave3.py` |

## Wave 4 SHIPPED（2.40.56）

| 项 | 证据 |
|----|------|
| S4.1 variety hard bulk | `bulk_preflight` variety check hard + richer floors fields |
| S4.4 insert ban silent T2V | restricted insert no still → i2v blocked (`INSERT_NEEDS_DETAIL_STILL`) not t2v |
| 测 | `tests/test_wave4_variety_insert.py` |

## 开放序（go next）

- **Wave 5** continue endframe 毒/回穿  
- **Wave 6** canary + memory 短卡

## 关联

- [weapon-lane-matrix](../../skills/ai-film-grok/references/weapon-lane-matrix.md)  
- [stages/visual](../../skills/ai-film-grok/references/stages/visual.md)  
- [h3-core-workflow](2026-08-06-h3-core-workflow-todoplan.md)  
- 毒镜 memory `2026-07-29-poison-shot-anatomy-iron.md`
