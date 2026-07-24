# Agent 阶段卡

只处理当前 `next_action`。故事真相是 `drama-graph.json`，`film-spec.json` 是可执行投影。

- 顺序：brief → story/beat/shot authoring → strict validate → story/beats/shots/panels locks → graph project → write-spec。
- 上游变化会使后代和投影 stale；先修正与重新投影，禁止带 stale hash 进入媒体阶段。
- 用户原文、主题、角色目标与表演意图必须保留；模板只能补结构，不能覆盖创作。
- 人类锁定与批准不可由 Agent 代签。

深入资料：[craft-spine.md](../craft-spine.md) · [directors-lens.md](../directors-lens.md) · [professional-director-system.md](../professional-director-system.md)
