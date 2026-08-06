# 短版导演链

`aifilm shortform` 是 **15–60 秒编排控制层**（provider 中立），**不是**默认 AI 漫剧主产线。

## 决策树（30 秒选型）

| 你要做的事 | 走哪条 |
|------------|--------|
| 剧本/小说 → 竖屏 AI 成片（H3 / Grok I2V、dispatch、bulk、final） | **主产线 A**：`plan run` → `write-spec` → pilot → bulk → `gate-auto` → `final`（`production_mode=shortform` 默认） |
| 真人 A-roll 口播 + 词级 transcript，源音是口型真相 | **旁路 B · aroll**：`aifilm shortform plan --mode aroll` |
| 已批准短文案 + 锚定图，15–60s topic/C-roll 编排 | **旁路 B · topic/croll**：`aifilm shortform plan --mode topic\|croll` |
| 长片 8–15 分 | **longform**：`plan run --production-mode longform` |

**默认用 A。** 只有明确要 A-roll 源音或 15–60s package 时用 B。  
旁路 **不进** `dispatch` next_action；`assemble-aroll` 只出 `candidate_only`，须再接主产线 final/字幕/混音。

## 口型政策（v2.40 冻结）

- **禁止** `enable-lipsync` / `render-lipsync`（生产已移除后期对嘴）。
- 对白有声镜：**Grok / H3 `prefer_native`**。
- A-roll：源片音轨是唯一口型真相，禁止重做 lip-sync。

## 命令骨架

```bash
$AIFILM shortform plan --root artifacts/short --mode topic --approved-script artifacts/short/approved.txt
$AIFILM shortform review --root artifacts/short --stage plan --reviewer dex --note "节奏通过" --approve
$AIFILM shortform review --root artifacts/short --stage sample --reviewer dex --note "样片通过" --approve
$AIFILM shortform validate --root artifacts/short --require-approved
# aroll only:
# $AIFILM shortform assemble-aroll --root … --visual-dir …
```

`assemble-aroll` 写 **candidate_only**。之后仍须 decode/字幕/混音 + `review-final`，技术合成 ≠ master。

## 与主产线时长诚实（S0）

H3 单镜 ~**5.2s**；计划默认勿写 6/8s 纸面槽；镜数不足 `ceil(target/5.2)` → hard。  
见 [shortform optimization plan](../../docs/plans/2026-08-06-shortform-optimization-todoplan.md)。
