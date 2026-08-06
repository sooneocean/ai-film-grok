# Lip-sync 后端政策（2026-08-05 冻结 · **2026-08-06 v2.40 代码移除**）

## 生产结论（先读这四行）

1. **对白有声镜 = Grok Imagine Video 或 5090 MiniMax H3 原音**（`prefer_native` / `use_clip_audio`）。
2. **后期对嘴工具已从生产路径移除**（非仅文档冻结）：`final --lipsync` **仅允许 `off`**；`lipsync-*` CLI / shortform enable-render / 节点适配器均为墓碑。
3. Edge TTS 只做字幕时钟与可选 ADR，**不**驱动嘴型重渲染。
4. **不做** lipsync canary 自动晋级（专家团旧建议已作废）。

详见 [dialogue-first-workflow](dialogue-first-workflow.md) · [hard-defaults 对白原音 IRON](hard-defaults.md) · `dialogue_competition` policy `native_audio_grok_h3_v1`。

## 移除 / 墓碑清单（v2.40）

| 后端 / 面 | 状态 |
|-----------|------|
| RTX LatentSync / MuseTalk 节点 | **代码墓碑**（`node/*_adapter.py` raise） |
| InfiniteTalk / FantasyTalking | 历史 pilot only |
| FRW `ltx-lipsync` / `wan-lipsync` / seedance lipsync | **代码墓碑**（`frw_lipsync` raise） |
| 本机 Wav2Lip / external argv | **移除** |
| `aifilm lipsync-canary|pilot|challenge|node` | **exit / FilmError** |
| `shortform enable-lipsync / render-lipsync` | **ShortformError** |

历史 canary / 研究笔记仍可查（只读）：

- [lessons-2026-07-28-rtx5090-lipsync-routing.md](lessons-2026-07-28-rtx5090-lipsync-routing.md)
- [lipsync-challenge.md](lipsync-challenge.md)
- [frw-lipsync.md](frw-lipsync.md)

**禁止**把「节点 technical_ready」或旧 canary 写成生产 ready。恢复须用户圣旨 + 回滚到 pre-2.40 tag，不得在主枝静默复活。

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

`AIFILM_LIPSYNC_BACKEND` 默认 `off`。非 `off` 在 `enforce_dialogue_lipsync` / argparse 硬拒。
