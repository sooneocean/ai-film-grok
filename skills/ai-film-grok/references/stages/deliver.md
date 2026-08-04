# Deliver 阶段卡

- 每个批准镜头须有当前 SHA-256 绑定的 review receipt。
- 最终 MP4、字幕、混音、时间线与 screening evidence 必须互相绑定且未 stale。
- 十一维 review-final 全部通过、重拍单关闭、字幕像素可读后，才允许 `final_complete`。
- 自动评分只作 advisory；完整观看、人类批准和盲审不能由模型代替。
- export 后回读文件、hash、ffprobe 与交付 sidecar；“生成过”不等于“交付完成”。
- **I2V/成片门（P0 · 2026-07-27）**：`receipts/i2v-final-gate.json` ok 前 **禁止** 覆盖桌面 `film_final`。Gate = 全镜真实 I2V + motion 分级过门 + 包络 after_60 + style 抽帧。I2V raw 完成 ≠ 交付。见 [high-motion-style-lock](../lessons-2026-07-27-high-motion-style-lock-final.md)。
- **收尾门禁（P0 · 2026-07-29）**：plate 有了仍须 heat codes 清零、adult sensory、truth_contract、字幕真钟、quality 无缓存毒、narrative 哈希当前，再 review-final → post-audit → export-desktop。改 final 必删 `quality-report.json` 并重绑叙事证据。见 [closeout-gates](../lessons-2026-07-29-closeout-gates-chaebol.md)。
- **一键收尾（2026-08-03）**：`aifilm closeout run --root`（status 只读）串 heat→review 闸→post-audit；**不**自动批 review-final。plate 存在时 dispatch 优先 `closeout-run`。
- **Cinematic-gate（P0 · 2026-08-04 ε）**：`aifilm cinematic-gate --root` → true-video + inventory + i2v-final + variety + five-track。**export-desktop** 要求 `receipts/cinematic-gate.json` ok。clips 齐后 dispatch 推此步再 final。

深入资料：[quality-closure.md](../quality-closure.md) · [hard-defaults.md](../hard-defaults.md) · [high-motion-style-lock](../lessons-2026-07-27-high-motion-style-lock-final.md) · [closeout-gates](../lessons-2026-07-29-closeout-gates-chaebol.md)
