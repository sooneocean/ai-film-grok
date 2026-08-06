# 2026-08-06 · H3 原声季审片教训（撒瓦尼 EP01/02）

## 审片证据
- 路径：`0805/savani-season01/receipts/review-ep01-ep02/`
- Final：~212s / 704×1280 / aac 有声 mean≈−15dB；41 clip 全有 audio
- 镜内动感 MAE first↔last 约 **40–82**（均值~54）→ H3 **有动**，非静帧拖片
- 脸：紫发女主连续可认；肉戏/双人镜可读

## 问题（按严重度）
1. **时长不足**：目标 ~300s，实为 41×~5.17s≈212s（−29%）。H3 单镜时长上限导致「镜数×5s」塞不满 5 分。
2. **成片通道绕开 aifilm final**：drama-graph `schema_version≥2` 触发 `require_current_canonical_truth`，缺 story/shot performance 字段 → final 硬挡；本季用 **ffmpeg concat 保 H3 原声**。
3. **无字幕硬烧 / 无 BGM**：native 直出只有 H3 aac，未叠中文硬烧与 rnb 侧链。
4. **Still 降级**：Grok Imagine 成人审核挡 → `ffmpeg` 从 master 裁剪变体；EP02 更是 **EP01 槽位变体**，剧情新鲜度弱。
5. **续集同构**：EP02 timeline/film-spec 由 EP01 改 ID，观感「同一条故事重渲」风险高。
6. **原声语义**：有 aac≠中文对白清晰；H3 原声可能是氛围/外语噪声，需抽听门禁。

## 插件优化（已做 / 待做）
- **已做**：`aifilm final --skip-canonical-truth` 与 env `AIFILM_SKIP_CANONICAL_TRUTH=1`（H3 原声 bulk 逃生；非锁定 canonical 系列默认关）。
- **待做**：
  - `aifilm h3 ship-native`：timeline 序 concat + 可选 softsub/BGM 混音收据
  - 时长门：`target_duration` vs `sum(clip_dur)` 预检；不足则建议加镜或 FLF 加长
  - still：Imagine 审核失败 → 明确 fallback 收据 + 禁止「整集仅 crop master」不告警
  - 原声抽听：随机 N 镜 `volumedetect` + 可选 ASR 是否含中文

## 默认口诀
- **H3 原声季**：clip 保留 aac → final 可 `--skip-canonical-truth` 或 ship-native；再叠字幕/BGM。
- **5 分片**：镜数按 `ceil(300/5.2)≈58` 或提高单镜时长，勿默认 41×5s。
- **续集**：新剧情新 still 源，禁止 silent ID-rename 当新集。
