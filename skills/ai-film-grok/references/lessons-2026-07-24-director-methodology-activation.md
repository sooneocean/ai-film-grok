# Lessons · 2026-07-24 · 导演方法论死代码接活 + 门禁升级

> **P 码**：P1（接活死代码）/ P2（升级门禁硬度）/ P3（补齐 stub）
> **层**：方法论 / 工程门禁

## 背景

全量扫描发现 5 处死代码（已实现 lint 但零调用零门禁）、6 处门禁 opt-in/soft-only、
3 处 stub、1 处 LUFS 标准冲突。本次迭代全部接活/升级/补齐。

## P1 · 接活死代码（5 处）

| # | 死代码 | 位置 | 接入点 | 测试 |
|---|---|---|---|---|
| P1-1 | `lint_production_consistency`（7 维漂移） | continuity.py:1098 | preflight + write-spec `production_consistency_strict` | test_production_consistency.py (18 tests) |
| P1-2 | `lint_composition_rules`（180°/30°/eyeline） | framing_lint.py:221 | preflight + write-spec `composition_strict` | test_composition_rules.py +6 tests |
| P1-3 | `validate_dialogue_contract`（时序/来源/lipsync） | dialogue_contract.py | preflight + write-spec `dialogue_contract_strict` | test_dialogue_contract.py +7 tests |
| P1-4 | `derive_character_state_timeline`（5 轴单调） | asset_registry.py:725 | assets_check（state_regression_issues） | test_character_state_continuity.py +2 tests |
| P1-5 | `derive_lighting_timeline`（heat→lighting） | visual_bible.py:185 | color_grade.plan_shot_grades | test_color_grade.py +2 tests |

**方法论**：导演方法论写在代码里但不接线 = 不存在。"考验三件套"（schema→lint→门禁→测试）
缺任一即不可被考验。

## P2 · 升级门禁硬度（6 处）

| # | 维度 | 原 | 升级后 |
|---|---|---|---|
| P2-6 | face identity drift | post_audit soft | premium 默认 hard |
| P2-7 | meaningful_motion | preflight soft-only | preflight hard when `meaningful_motion_strict` |
| P2-8 | color_grade | opt-in strict | premium 默认 strict |
| P2-9 | rhythm | strict 路径无测试 | strict 路径有测试覆盖 |
| P2-10 | vo_lint | advisory only | `vo_lint_strict` 升级 hard |
| P2-11 | audio_bible/post_bible | `advisory_only:True` | premium 项目 → hard |

**方法论**：40 年导演的标准是"软规则在 premium 成为铁律"。standard 项目保持弹性；
premium 项目每个维度都是 hard gate。

## P3 · 补齐 stub（3 处 + 1 标准统一）

| # | stub | 原 | 实现后 |
|---|---|---|---|
| P3-12 | audio_visual_alignment | 49 行只查文件 | BGM cue vs shot boundary + VO onset vs cut + av_alignment_score (0-100) |
| P3-13 | lint_locations | 无 | SCENE_LOCATION_UNREGISTERED / RECURRING_OBJECT_MISSING / RULE_VIOLATION |
| P3-14 | BGM spotting 对齐 | 无 | 由 P3-12 `lint_bgm_cue_alignment` 覆盖 |
| P3-15 | LUFS 标准冲突 | 三套（-24..-14 / -18..-14 / -22..-16） | 统一 -16±2 (-18..-14) |

**方法论**：响度标准必须唯一。三套不同阈值 = 一片可过 A 失败 B。

## 测试增量

| 新增/扩展测试文件 | 新增测试数 |
|---|---|
| test_production_consistency.py | 18 |
| test_composition_rules.py | +6 |
| test_dialogue_contract.py | +7 |
| test_character_state_continuity.py | +2 |
| test_color_grade.py | +2 |
| test_post_audit.py | +10 |
| test_strict_gate_paths.py | 9 |
| test_audio_visual_alignment.py | 16 |
| test_asset_registry.py | +6 |
| **合计** | **+76 tests** |

全套从 713 → 807 passed（+94），0 failures，doctor green。

## 铁律

1. **方法论接线审计**：每季度扫描一次 `grep -L "def lint"` callers，确保无死代码
2. **premium = hard**：standard 弹性、premium 铁律；不允许 advisory_only 混进 premium
3. **标准唯一**：响度/LUFS/true-peak 等度量标准全模块统一，禁止多套阈值
4. **stub 即债**：49 行只查文件存在的"对齐度量"不算实现——必须有真实算法 + 度量 + 测试
