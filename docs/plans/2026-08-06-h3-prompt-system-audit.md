# H3 Prompt System Audit · 2026-08-06

## 三行摘要
1. **断点已证**：`combo_prompt_family` 只标注 plan，生产 `_prompt_for_shot` 原先不吃 family DSL → 空 DSL 镜只剩 generic SOFT/HIGH 头 + 模板 arc。
2. **接线已做**：`apply_combo_family_to_shot` + `AIFILM_H3_FAMILY_APPLY`（默认开）；系统句入 `registry/h3-prompt-system.json`。
3. **Comfy negative**：`DEFAULT_NEGATIVE` 在 **Wan** `build_wan22_i2v_prompt`；H3 MiniMax 武器走 armory graph，**不要**假设改 Wan negative 会抬 H3 画质。

## Gap（P0 抽样）

| 场景 | 无 family | 有 soft_portrait_alive |
|------|-----------|------------------------|
| 软英雄 5s timeline | SOFT MOTION + continuity + generic primary arc | + eyes track / breath / hair micro-drift 段内动作 |
| 高动 | 需 heat/DF 才 HIGH MOTION | family 填 action 后段内有 weight shift 等 |

## Winners 字段
- `dialogue_mouth_energy.winner.family` 已与 `prompt_family=dialogue_mouth_max` 对齐（原 flat 陈旧）。

## 下一步
- R5 combo-eval（5090 idle）：soft alive 动感 floor；high 段数；mouth 可懂
- 真片 2–3 镜 canary
