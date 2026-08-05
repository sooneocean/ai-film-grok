# Lip-sync 后端政策（2026-08-05 冻结）

## 生产结论（先读这三行）

1. **对白有声镜 = Grok Imagine Video 或 5090 MiniMax H3 原音**（`prefer_native` / `use_clip_audio`）。
2. **后期对嘴工具全部冻结**，不进 bulk / final 默认路径。
3. Edge TTS 只做字幕时钟与可选 ADR，**不**驱动嘴型重渲染。

详见 [dialogue-first-workflow](dialogue-first-workflow.md) · [hard-defaults 对白原音 IRON](hard-defaults.md) · `dialogue_competition` policy `native_audio_grok_h3_v1`。

## 冻结清单（勿默认启用）

| 后端 | 状态 |
|------|------|
| RTX LatentSync 1.6 | 冻结 |
| RTX MuseTalk 1.5 | 冻结 |
| InfiniteTalk / FantasyTalking | 冻结（仅历史 pilot 证据） |
| FRW `ltx-lipsync` / `wan-lipsync` / `seedance-*-lipsync` | 冻结 |
| 本机 Wav2Lip / external argv | 冻结 |

历史 canary / 研究笔记仍可查：

- [lessons-2026-07-28-rtx5090-lipsync-routing.md](lessons-2026-07-28-rtx5090-lipsync-routing.md)
- [lipsync-challenge.md](lipsync-challenge.md)
- [frw-lipsync.md](frw-lipsync.md)

**禁止**把「节点 technical_ready」或旧 canary 写成生产 ready。用户未**显式**点名恢复前，agent 不得跑 `final --lipsync auto`、不得 enqueue lipsync 节点 bulk。

## 正确生产路径

```text
批准 still
  → 软/安全对白：Grok Video（台词进 prompt）
  → restricted / h3_primary：aifilm h3 run --register（台词注入）
  → register clip use_clip_audio=true（原声可用时）
  → final --lipsync off + Edge 字幕硬烧
```

人审只听：**原声是否可懂、台词是否对、有无供应商烧字、身份是否漂**——不再验收「LatentSync 对齐分数」。

## final 默认

```bash
aifilm final --root "<film>" --lipsync off --music-mood rnb --tts-backend edge
```

`AIFILM_LIPSYNC_BACKEND` 默认 `off`。逃生恢复旧工具须用户圣旨 + 写回 hard-defaults（本页解冻段）。
