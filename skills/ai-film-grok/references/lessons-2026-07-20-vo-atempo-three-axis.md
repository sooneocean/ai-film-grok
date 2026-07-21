# VO atempo 贴 plate（三轴：视频定长 · 语音贴合）

> 2026-07-20 · 从 **ai-film-cn 坑#29** 沉淀进 grok  
> 映射 **P2 时空连续**（时间轴真相）+ **P4 语义绑定**（旁白不靠 loop 撑戏）

## 白话

旧做法容易「视频被拉长去凑旁白」→ 总时长漂、字幕窗错、loop 发腻。  
正确做法：**镜长（plate）定死** → **旁白用 atempo 变速贴合** → 字幕/拼接共用同一时钟。

## 规则

| 轴 | 定长来源 | 调整手段 |
|----|----------|----------|
| 视频 | `duration_sec` / slot | 只 stretch **到 plate**，禁止为超长 VO stream_loop（仍受 hook/action forbid） |
| 语音 | 实测 TTS 秒数 | `atempo = vo_sec / plate_sec`（**方向勿反**） |
| 字幕/拼接 | 与 plate 对齐 | final 既有 pad/trim 段长 = target(=plate) |

- **atempo > 1**：加速、变短（VO 比 plate 长）  
- **atempo < 1**：变慢、变长（VO 比 plate 短）——**仅允许轻微**（默认 **≥0.92**）  
- **拖腔禁令（星声 2026-07-20）**：`raw atempo < 0.92` 时 **禁止**继续拉慢语速 → **`pad_natural` 静音垫**；要满时长用 **加镜/加字** 或 `visual_fit: vo`。见 [lessons-2026-07-20-vo-drag-motion-snap.md](lessons-2026-07-20-vo-drag-motion-snap.md)  
- **上限 1.5**（cn 防 choppy）；压不进 plate → **fail**（拆 nar / 升 10s），不硬卡  
- `visual_fit: vo` / `cut_on: mid_motion`：**仍跟 VO 走**（动能接戏 + 听感利落；说书短片常更优）  
- 默认：`visual_fit: slot` + `vo_fit: atempo`（执行层已带 drag guard）  
- 应急：`vo_fit: legacy` 或 `--vo-fit legacy`（旧 pad + 可能 stretch 视频到 VO，不推荐）；`allow_speech_drag=True` 仅显式需要拖腔

## 代码

| 模块 | 作用 |
|------|------|
| `scripts/vo_atempo.py` | `plan_vo_atempo` · `fit_voice_to_plate` |
| `scripts/render_final.py` | slot 路径默认 atempo；delivery 写 `vo_atempo_plan` |
| `tests/test_vo_atempo.py` | 方向、clamp、fail_over、真 ffmpeg |

## 命令

```bash
# 默认 slot + atempo（推荐）
"$AIFILM" final --root "<root>" --tts-backend edge --music-mood rnb

# 显式
# film-spec: "vo_fit": "atempo" | "legacy"
"$AIFILM" final --root "<root>" --vo-fit atempo
```

## 与既有门禁

- write-spec `vo_pacing` / tts-rehearsal **measured** 已挡「旁白远超 plate」  
- atempo 是 **final 执行层** 的最后一公里：估时过了但实测略长时 ≤1.5x 微调贴合  
- 仍禁止指望 stream_loop 撑旁白

## 非 port

不搬 cn make_v6 全套 pause_cuts / 字幕第三轴脚本；字幕仍走 grok final 既有 cues。
