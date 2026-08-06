# Deliver 阶段卡

- 每个批准镜头须有当前 SHA-256 绑定的 review receipt。
- 最终 MP4、字幕、混音、时间线与 screening evidence 必须互相绑定且未 stale。
- 十一维 review-final 全部通过、重拍单关闭、字幕像素可读后，才允许 `final_complete`。
- 自动评分只作 advisory；完整观看、人类批准和盲审不能由模型代替。
- export 后回读文件、hash、ffprobe 与交付 sidecar；“生成过”不等于“交付完成”。
- **I2V/成片门（P0 · 2026-07-27）**：`receipts/i2v-final-gate.json` ok 前 **禁止** 覆盖桌面 `film_final`。Gate = 全镜真实 I2V + motion 分级过门 + 包络 after_60 + style 抽帧。I2V raw 完成 ≠ 交付。见 [high-motion-style-lock](../lessons-2026-07-27-high-motion-style-lock-final.md)。
- **收尾门禁（P0 · 2026-07-29）**：plate 有了仍须 heat codes 清零、adult sensory、truth_contract、字幕真钟、quality 无缓存毒、narrative 哈希当前，再 review-final → post-audit → export-desktop。改 final 必删 `quality-report.json` 并重绑叙事证据。见 [closeout-gates](../lessons-2026-07-29-closeout-gates-chaebol.md)。
- **一键收尾（2026-08-03 / 08-05）**：`aifilm closeout run --root` 串 heat→review 闸→**caption-pixel**→post-audit；**不**自动批 review-final。字幕机检红则停 + `next_cmd`。
- **Gate-auto（P0 · 2026-08-04）**：`aifilm gate-auto --root` 一键机写 mean / i2v-final / sex_sfx / five-track / true-video / variety / cinematic。**优先于**手工点闸；closeout 红时自动跑。仍须人：pilot / 多 take PK / review-final。逃生 `AIFILM_SKIP_GATE_AUTO=1`。
- **Cinematic-gate（P0 · 2026-08-04 ε）**：`aifilm cinematic-gate --root` → true-video + inventory + i2v-final + variety + five-track（默认 auto_i2v）。**export-desktop** 要求 `receipts/cinematic-gate.json` ok。clips 齐后 dispatch 推 **gate-auto** 再 final。

深入资料：[quality-closure.md](../quality-closure.md) · [hard-defaults.md](../hard-defaults.md) · [high-motion-style-lock](../lessons-2026-07-27-high-motion-style-lock-final.md) · [closeout-gates](../lessons-2026-07-29-closeout-gates-chaebol.md)
- **审片 assist（P3 · 2026-08-05）**：`aifilm agent-review-final` 机读预填字幕/单钟/门闸；**禁止** 代签 review-final；须人短语 `--apply`。

## 真片 final 抽检清单（W1.5 · 1 屏）

> 门绿 ≠ 可交 master。交付前 **逐项读回执**，禁止口头「final 好了」。

| # | 查什么 | 路径 / 命令 | 红线 |
|---|--------|-------------|------|
| 1 | 交付语义 | `receipts/official-final-report.json`（或 closeout 字段） | `OFFICIAL_FINAL_PLATE` / PARTIAL **≠** master-lock / `final_complete`；**export-desktop 机读拦 plate**（2.40.14） |
| 2 | final 入口诚实 | 成片时长 + 有 aac/口白；禁 ~1s 假绿 | shim 必须调 `main()`（`test_suse_final_iron`） |
| 3 | 超时/假死 | `receipts/final-timeout.json` 若存在 | 有则按 `next_cmd` 重跑；勿当成功 |
| 4 | 口白窗 | TTS ≤ cue ≤ slot（stretch 前） | 溢出 → 砍 spoken / vo_rate，**禁**只拉长 cue 超槽 |
| 5 | 槽长认源 | H3 ~5s 源勿被 validate 静默拉到 10s | sex floor strict / `film_spec_sex_floor` |
| 6 | BGM 来源 | final receipt 标 licensed wav vs procedural | rnb 仅 license 无 wav → procedural 诚实 |
| 7 | 字幕像素 | `caption-pixel-check` + 抽帧 | 用户可见=画面有中文；CJK 内空格已 auto-fix |
| 8 | gate-auto | `aifilm gate-auto --root` / closeout | 红则 plate PARTIAL；**禁**刷假 master |
| 9 | 混音 partial | `receipts/final-mix-partial.json` | sidechain 降级须标 PARTIAL |
| 10 | 人审 | review-final / pilot / PK | 机读不代签 |
| 11 | 时长诚实 | `receipts/duration-honesty-closeout.json` · closeout `duration_honesty` | planned/media/shot_n vs target；硬门仍 bulk-preflight |
| 12 | 抽听中文 | 每场 ≥1 句人耳可懂 | aac 存在 ≠ 可懂；升 hard 仅用户要 `AIFILM_NATIVE_AUDIO_MANDARIN_HARD` |
| 13 | 门红话术 | gate-auto 红 → **PARTIAL plate ship** | 禁称 master-lock / final_complete |
| 14 | 改 final 清缓存 | 删陈旧 `quality-report.json` + 叙事重绑 | 见 closeout / post 纪律 |

### Agent 回报用户前（B1 肌肉 · 禁口头「final 好了」）

1. 读 `receipts/official-final-report.json` → `status` / `master_lock` / path  
2. 读 closeout `plate_honesty` + `duration_honesty`  
3. 有 `final-timeout.json` → 按 `next_cmd`，勿当成功  
4. 三字段写进对话再给用户看片路径  

链：`stages/post.md` · memory `suse-ep01-official-final-iron` · plan `2026-08-06-ad-process-optimization-todoplan` · next-optimization W1。
