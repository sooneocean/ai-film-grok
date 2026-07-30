# 私网多模态影格审片（候选层）

`aifilm local-omni-review` 把私网 OpenAI-compatible 多模态模型接为影格审片侧车。它只分析工作区内、明确声明为技术安全样本的 1–5 张静态影格；不会上传视频、音频、导演合约或任何资料到第三方。

先用只读探针确认模型确实仍在 LM Studio：

```bash
aifilm local-omni-review probe \
  --base-url http://192.168.88.52:1234/v1 \
  --model nvidia/nemotron-nano-3-30b-a3b
```

再建立工作区内的 frame index（每项含相对 `path` 和 `timestamp_sec`），并执行候选审片：

```bash
aifilm local-omni-review run \
  --root artifacts/<film> \
  --frame-index receipts/sanitized-frames.json \
  --sanitized
```

结果写入 `receipts/local-omni-review.json`，绑定每张影格的 SHA-256。它只会提出黑帧、冻结、字幕遮挡、明显连续性漂移或视觉瑕疵的候选问题。所有结果都是 `candidate_only`：不能批准镜头、改变 provider、提交生成任务，亦不能代替真人审片或既有技术 QA。影格以拒绝 symlink 的文件描述符读取，每张最多 8 MiB，并在传送前后重验 SHA-256；发生变化即失败，不产生可用报告。模型若把本机 token 原样回显，probe 结果与候选 receipt 会先遮罩该值。

模型或端点不可用时应记录为 canary 未完成，继续使用既有 deterministic QA 与真人审片；不得静默改走云端或其他模型。
