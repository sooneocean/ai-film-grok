# Voice 阶段卡

## P0 · 电影对白主链（口白中文 · 2026-08-03 · 勿再犯）

| 层 | TTS | speaker | 字段 |
|----|-----|---------|------|
| **角色对白 / 口白** | **中文** Edge（女 Xiaoyi / 男 Yunxi） | 具名角色 | 中文 `spoken_text` + `caption_text`；近景 lipsync |
| **无对白** | 无 VO | — | silence/reaction/action_cover；禁第三人称 `nar` 填钟 |
| **旁白 gap** | 中文 Edge | narrator | 目标 0、硬顶 **5%** |
| **字幕像素** | **仅 HyperFrames** | — | 中文 `caption_text`；plate `subs=off` |

- 默认 `vo_mode=dialogue_drama` + `dialogue_spoken_lang=zh`；日文对白仅显式 `ja`。
- **`cast_voices` 必须跟 spoken_lang**：zh → 男 Yunxi / 女 Xiaoyi；**禁止** zh 片挂 `ja-JP-*`（2026-08-03 荒岛）。
- 散文拆句 → 互动正反打（A 说 B 听 / reverse OTS）。
- 有对白=角色口型；无对白=纯画面。
- **对白镜 VO-fit**：时长≈pre+VO+post，禁短口白硬贴 6s 死气；见 [vo-drag](../lessons-2026-07-20-vo-drag-motion-snap.md) · [huangdao](../lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md)。
- final 前自检：`speaker | voice | spoken_lang=zh | screen_mode`。

色气 BGM 默认 **rnb**。机读：[hard-defaults](../hard-defaults.md)。  
深入：[dialogue-first-workflow](../dialogue-first-workflow.md) · [vo-modes](../vo-modes.md) · [voices](../voices.md)
