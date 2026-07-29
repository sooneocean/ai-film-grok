# 候选到晋升报告（报告期）

生成成功、文件存在、或单一总分通过，都不等于可交付资产。`aifilm promotion-report --root <film>` 只读取当前媒体与回执，逐层说明每个镜头和最终文件是否具备候选、技术、视觉、语义与整合证据。

本期是**只报告**：不会改动 manifest、审批、媒体、final 或任何门禁结果。只有明确给出 `--out <film-root>/reports/promotion-report.json` 才会写一份报告副本。

高风险修改应记录到 `receipts/experiment-a-b.json` 的 `experiments` 数组；每项至少包含 `id`、`category`、`shot_id`、`baseline_sha256`、`candidate_sha256` 与 `human_conclusion`。两个 hash 必须是同一镜头 dailies/当前 manifest 中不同的已知候选。例如神经口型、调色、字幕、ducking、Foley 或 BGM 的新方案，先做 2–3 秒局部样本，再记录 A/B 人工结论。缺少这些字段或绑定不成立只会报告 `EXPERIMENT_EVIDENCE_MISSING`，不会阻断现有 final。

`aifilm status` 会保留它原有的 scene-sound 与 gate 刷新行为；其中的 `promotion_report` 字段只读计算，不会改变任何 ready/blocked 判断。要取得完全无写入的报告，请直接使用 `promotion-report`。

真实降级要如实表达：逐音素口型失败时，可以降级为局部音频特征口型、正确对白音频或原始画面；不得把字幕、进程成功或嘴部微动描述成完整口型同步。报告期结束后，应基于真实报告结果逐项决定哪些代码升格为硬门禁，而不是一次性阻断旧项目。
