# Premium quality closure

`premium_vertical` 的合同测试只能证明门禁和回执结构正确，不能证明影片已经达到艺术品质。

## 无花费准备

```bash
aifilm quality-closure package --root <film-root>
aifilm quality-closure report --root <film-root>
```

这会写入固定版本的 benchmark package，并明确把证据分为：`contract`、`local_render`、`real_provider`、`human_reviewed`。缺真实 provider 或两位独立审阅者时，报告必须保持 `artistic_quality_verified: false`。provider evidence 必须是已 `register-clip`、hash 相符、`approved` 且 active 的 manifest clip；单独手写回执或本机文件不构成 provider 证据。

## 真实 Pilot 后的盲审

每位审阅者独立以 1–5 分评价：叙事节奏、身份连续性、表演、摄影、运动可信度、声音、字幕可读性、整体完成度。

```bash
aifilm quality-closure review --root <film-root> --reviewer reviewer-a \
  --scores-json '{"narrative_rhythm":4,"identity_continuity":4,"performance":4,"cinematography":4,"motion_credibility":4,"sound":4,"caption_readability":4,"overall_completion":4}'
```

同一 reviewer 不能重复提交。两份评价相差两分以上会被记录为分歧；任一维度低于等于 2 会创建带问题代码的重拍队列。`aifilm next` 只会返回最高优先级、带 receipt 的修复动作。

真实 provider 调用、预算批准与外部发布仍须由使用者单独授权；本命令不会发起任何生成或花费。
