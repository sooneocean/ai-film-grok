# Visual 阶段卡

先验后生：静帧、身份、状态、几何未过闸，不得进入 I2V。

- 有角色的 still 使用已批准 cast/face/state 来源；禁止从零抽脸绕过 moderated 结果。
- 9:16 keyframe 默认至少 704×1280，接受 provider 原生 704×1280 且不强制放大；禁止横图、缩略图和压糊来源。
- `state-index check|plan` 先于 bulk；衣着状态只前进，已脱不得回穿。
- Continue 镜使用已批准末帧作为下一镜输入，按实际姿势、服装与视线接戏。
- pilot 必须由用户批准；付费或外部生成必须实时 capability 检查。
- **Pilot GO 包**：`aifilm pilot pack` → `receipts/pilot-go.json`（三镜+卸装三拍+score+heat+state）；bulk 前一屏。
- **Bulk 单门**：`aifilm bulk-preflight`；**pilot 已批后 media-queue 默认硬拦**（逃生 `AIFILM_SKIP_BULK_PREFLIGHT=1` / `--allow-without-pilot`）。
- **设计期 variety**：`aifilm variety-precheck`（体位/脸 CU/邻镜 motion）— bulk 前改 spec 比重渲便宜。
- **5090**：`aifilm gpu-lease acquire|heartbeat|release`；`tunnel-probe`（18188→8188）；进度只认 `queue-progress` 非空 takes。
- **双车道武器路由（P0 · 2026-08-03）**：成人 max **默认 dual-lane**（片级 `h3.enabled` 自动开 / `_i2v_profile→hybrid_h3`；`h3.enabled=false` 退出）。setup→**Grok Video 1.5**；肉戏/bare/高难→**MiniMax H3**（`aifilm h3 run`；cloud bulk 硬拦，逃生 `AIFILM_ALLOW_CLOUD_RESTRICTED=1`）；对白→FRW LTX。高难信号：`coitus_beat` deep/creampie、L4+contact、`force_local_h3`。bulk 前 `h3 list`+variety+preflight。产能：云 setup → 本地卸装 still → **5090 独占 H3 meat** → 云桥接/对白 → final。H3 出片自动 ≥704×1280。见 [weapon-lane-matrix](../weapon-lane-matrix.md)。
- **MiniMax H3（hybrid_h3 / 片级 h3.enabled）**：敏感/肉戏本地 lane → `aifilm h3 list|plan|run --register`（pilot 闸；禁静默 bulk；**原声 prefer_native**：可用则保留，不可用再 strip→TTS）。云 bulk 仅 general 镜走 Grok media-queue。
- **高动态常态（P0 · 2026-07-27）**：I2V 后逐镜 mean 平常≥18、肉戏≥20；多 take 取最高动且时长够；肉戏 10s 优先 6s×2。禁止 Ken Burns/微抖装片。见 [high-motion-style-lock](../lessons-2026-07-27-high-motion-style-lock-final.md)。
- **MEDIUM LOCK（P0 · 同案）**：每条 I2V 源= style-locked still；prompt 首段 cel 动漫锁；高动/连戏不得漂半写实；装片竞标 motion×medium 双过。

深入资料：[weapon-lane-matrix.md](../weapon-lane-matrix.md) · [consistency.md](../consistency.md) · [keyframe-first-state-index.md](../keyframe-first-state-index.md) · [i2v-grok-primary.md](../i2v-grok-primary.md) · [frw-degrade-dispatch.md](../frw-degrade-dispatch.md) · [high-motion-style-lock](../lessons-2026-07-27-high-motion-style-lock-final.md)
