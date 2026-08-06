# Agent 阶段卡

只处理当前 `next_action`。故事真相是 `drama-graph.json`，`film-spec.json` 是可执行投影。

- 顺序：brief → **story.receive** → **script-value-debrief（L0–L4）** → 用户确认 promise/不可砍 beat → story/beat/shot authoring → strict validate → locks → graph project → write-spec。
- 上游变化会使后代和投影 stale；先修正与重新投影，禁止带 stale hash 进入媒体阶段。
- 用户原文、主题、角色目标与表演意图必须保留；模板只能补结构，不能覆盖创作。
- 人类锁定与批准不可由 Agent 代签。
- **呈现价值**：lock 前写 `receipts/script-value-debrief.json`；回显 promise + must_have + ≥2 不可砍 beat；仲裁：用户 must_* > 原文事实 > creative_suggestion。详见 [script-value-debrief.md](../script-value-debrief.md)。

## 导演纪律快卡（W5 · process）

| 纪律 | 要求 |
|------|------|
| **design-go** | pilot 前须有 design-go / script-value-debrief receipt；缺则先补 |
| **anti-hijack** | multi-seed shortlist/PK **禁只比 mean/音量**；须 `composition_anti_hijack` / `aifilm anti-hijack` |
| **对白主链** | 中文口白 + 原音优先（Grok/H3 native）；禁后期对嘴复活当主轨 |
| **人审边界** | gate-auto 后人只做 pilot / PK / review-final；减 thrash |
| **GPU** | 默认 `run-next --max 5`；until-empty 须 `--i-own-the-gpu`；busy 零 submit |

深入资料：[craft-spine.md](../craft-spine.md) · [directors-lens.md](../directors-lens.md) · [script-value-debrief.md](../script-value-debrief.md) · [professional-director-system.md](../professional-director-system.md)
