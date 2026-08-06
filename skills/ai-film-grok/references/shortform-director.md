# 短版导演链

`aifilm shortform` 是 15–60 秒的编排控制层，不是新云端生成器。它统一三种输入：

- `topic`：已批准文案 → beat 与主镜/细节镜计划。
- `aroll`：本地 Whisper 的词级 transcript → 不超过 9.5 秒的 source-audio 分段；原片音轨是唯一口型真相。
- `croll`：已批准文案与锚定图 → 冻结身份的主镜/细节镜计划。

先建立 package，再分别记录 `plan` 与 `sample` 人审；两者批准前不可 A-roll 合成。B/C 的近景对白要以 `enable-lipsync` 绑定 speaker、face target 与最终音频 SHA-256；A-roll 禁止重做 lip-sync。

```bash
$AIFILM shortform plan --root artifacts/short --mode topic --approved-script artifacts/short/approved.txt
$AIFILM shortform review --root artifacts/short --stage plan --reviewer dex --note "节奏通过" --approve
$AIFILM shortform review --root artifacts/short --stage sample --reviewer dex --note "样片通过" --approve
$AIFILM shortform validate --root artifacts/short --require-approved
```

`assemble-aroll` 只会写 `candidate_only` 收据。之后仍必须走既有 decode、字幕、混音和完整人工 review-final 门禁，不能把技术合成当 final。
