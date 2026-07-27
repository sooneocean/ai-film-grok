# 生成用量账本

## 目的

`ai-film-grok` 对 T2I、image edit、I2V/T2V 与 TTS 采用“真实回执优先”：

- 每次发给 provider 的生成请求计一次；provider retry 另计。
- 异步影片的 submit 与后续 poll 属于同一次，以 `generation_id` 绑定。
- xAI 回应若含 `usage.cost_in_usd_ticks`，以整数 ticks 保存；显示时才换算美元。
- token 只有 provider 实际返回才显示；图像/影片没有 token 时为 `N/A`。
- 不用镜头数、队列数或总 quota 差倒推单次费用。

账本位于 `<film-root>/receipts/generation-usage.json`。事件只追加
`started → accepted → finished`，不保存 prompt、凭据或完整 provider 回应。

## 查看

```bash
aifilm usage status --root "<film-root>"
aifilm usage list --root "<film-root>" --format table
aifilm usage list --root "<film-root>" --operation i2v
aifilm usage summary --scan-root "/Users/dex/AI FILM SPACE"
```

汇总中的 `cost_in_usd_ticks` 只加总 `provider_exact`、`manual_exact` 与
`local_zero`。`unknown_cost_requests` 必须单独显示，不能当成零费用。

## Grok Build 原生工具

会话内 `image_gen`、`image_edit`、`image_to_video` 不经过本地 HTTP adapter，
插件无法自动拦截。每次工具结束后立刻补录：

```bash
# 成功：输出 hash 作为幂等身份
aifilm usage record --root "<film-root>" \
  --operation t2i --provider grok_native --model image_gen \
  --status succeeded --output "<still.png>" --shot-id shot01

# 失败：没有输出时必须提供稳定 idempotency key
aifilm usage record --root "<film-root>" \
  --operation i2v --provider grok_native --model image_to_video \
  --status failed --measurement unknown \
  --idempotency-key "shot01-attempt-2" --shot-id shot01
```

若工具确实提供可核对的精确值，可使用 `--measurement manual_exact` 搭配
`--cost-in-usd-ticks` 和 token 参数；没有真实字段时保持 `unknown`。

## OAuth / API 路径

传 `--root` 后自动记账：

```bash
aifilm grok-oauth image --root "<film-root>" --shot-id shot01 \
  --prompt "..." --out "<still.png>"

aifilm grok-oauth video --root "<film-root>" --shot-id shot01 \
  --image "<keyframe.png>" --prompt "..." --out "<clip.mp4>" --wait
```

不传 `--root` 时保持旧行为，只返回调用结果，不落项目账本。异步分离调用
必须把 submit 返回的 `generation_id` 传给 `video-status --generation-id`，
否则 poll 不能安全归入原请求。

## TTS

- Edge 与本机 Voicebox：`local_zero`。
- Grok TTS：有真实费用字段才是 `provider_exact`，否则 `unknown`。
- Fish、MiniMax 与任意 external adapter：没有标准化真实回执时为 `unknown`。
- fallback 是新的实际调用，必须单独计数。

旧项目没有账本时，`usage status` 返回 `tracking_not_started`，不会伪造历史
或阻断 dispatch/final。

## 成片复盘报告

人工 `review-final` 通过后，插件自动建立 `receipts/production-report.json` 与
`out/production-report.html`。报告以账本中的实际请求为准，按 T2I、I2I、I2V、T2V、
TTS 展示成功、失败、重试、Token 覆盖率和成本覆盖率；没有回执的原生调用会被明确标成
未知，不能当成免费或未发生。

跨作品趋势只比较 `production-book.json` 的 `optimization.template_id` 相同、最终审核
通过的作品。`optimization.history_root` 必须显式指定，或在报告命令传入
`--history-root`；插件不会猜测项目父目录，也不会自动改 provider、prompt 或模型。

## 队列绑定与重试证据

媒体队列在 `complete --generation-id` 时会读取同一 film root 的账本，并要求：

- `generation_id` 恰好对应一条记录；
- 记录的 `job_id` 与队列 job 相同（旧记录未填 job id 时仍可兼容）；
- provider 请求已经进入 `succeeded`、`failed` 或 `moderated` 终态；
- 只有 `succeeded` 才能把媒体标记为队列成功，并把用量、provider request id、成本 ticks
  写进 `media-queue.json` 的 `receipt.generation_usage`。

队列每次自动失败或人工 requeue 都追加 `retry_history`，记录 attempt、标准化失败原因、
是否可重试、退避时间和错误摘要。这样可以区分“重新计算了媒体”与“只是重新提交了同一请求”，
也能在成本回读时把 provider 请求数与最终媒体 job 对上。
