# 挑战者与两阶段优化节目册

本节目册把模型、音频和后期的候选能力统一为**不自动花费、不自动切主线**的证据链。
它不取代既有 provider canary、pilot、人审、`post-plan` 或最终交付门禁。

## 初始化与两阶段

```bash
aifilm optimization-program init --root "<film>"

# 只有静帧、构图、动作、连续性都过，才可产生正式档授权收据。
aifilm optimization-program draft --root "<film>" --shot-id shot01 --model ltx-fast \
  --still-approved --composition-pass --motion-pass --continuity-pass
aifilm optimization-program formal --root "<film>" --shot-id shot01 --model hunyuan-720p-sr
```

`formal` 只授权下一步，绝不投递 provider job、更改默认路由或批准 pilot。坏静帧没有
`--still-approved`，因此不能进入正式阶段。

## 挑战者

| 能力 | 角色 | 允许阶段 |
|---|---|---|
| InfiniteTalk | 有脸角色对白口型 | 正式候选；仍须最终对白和人审口型 |
| LTX Fast | 低成本动作草稿 | 草稿；不得晋升为身份主线 |
| Hunyuan 720p+SR | 720p 生成与超分 | 正式候选；须解码与超分伪影人审 |

要申请人工晋级，至少输入 3 个完整项目的 `receipts/metrics.json`：

```bash
aifilm optimization-program evaluate --root "<program-film>" --challenger ltx-fast \
  --metrics-root "<film-a>" --metrics-root "<film-b>" --metrics-root "<film-c>"
```

所有项目都必须 data quality=known、硬门通过、最终人工审核通过。输出仅为
`request_human_promotion`，不改变主线。

## 四条音频支线

Qwen3-TTS、ACE-Step、Stable Audio、MMAudio 每条都必须绑定音频 SHA-256、成功解码和人工听审。
Stable Audio 与 MMAudio 在此层仍是 review-gated candidate，不能记录为 production eligible。

## 周度十项指标

看板固定追踪：硬门通过率、最终审核通过率、评分中位数、动作 P10、动作失败率、阶段产出率、每合格分钟成本、每镜 I2V P50、重试数、人工分钟。未知值保持 unknown，不能补零。

```bash
aifilm dashboard build --roots-dir "<film-collection>" --days 7 --out "<dashboard-dir>"
```

## 后期边界

每部片只能选一个 `post_owner`：HyperFrames 或 Remotion。FFmpeg 只负责拼接、混音和编码；标题与字幕只能烧录一次。`post-plan` 是最终权威，本节目册不修改它。
