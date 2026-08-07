# Voice 阶段卡

## P0 · 电影对白主链（口白中文 · 2026-08-03 · 勿再犯）

| 层 | TTS | speaker | 字段 |
|----|-----|---------|------|
| **角色对白 / 口白** | **模型原声优先**（Grok Video / H3）；**原声 XOR Edge**（同句禁双轨）；Edge 真字幕时钟 = mix gain 0 | 具名角色 | 中文 `spoken_text` + `caption_text`；**禁**后期 lipsync bulk；强制 ADR 用 `post_vo` / strip |
| **无对白** | 无 VO | — | silence/reaction/action_cover；禁第三人称 `nar` 填钟 |
| **旁白 gap** | 中文 Edge | narrator | 目标 0、硬顶 **5%** |
| **字幕像素** | 正式 HF / ship 硬烧 | — | 中文 `caption_text`；验收=抽帧可读（见 post v3） |

- 默认 `vo_mode=dialogue_drama` + `dialogue_spoken_lang=zh`；日文对白仅显式 `ja`。
- **`cast_voices` 必须跟 spoken_lang**：zh → 男 Yunxi / 女 Xiaoyi；**禁止** zh 片挂 `ja-JP-*`（2026-08-03 荒岛）。
- 散文拆句 → 互动正反打（A 说 B 听 / reverse OTS）。
- 有对白=角色口型；无对白=纯画面。
- **对白镜 VO-fit**：时长≈pre+VO+post，禁短口白硬贴 6s 死气；write-spec 自动 `cut_on=mid_motion` + `visual_fit=vo`；见 [vo-drag](../lessons-2026-07-20-vo-drag-motion-snap.md) · [huangdao](../lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md)。
- **Wave 2 生成链：** still=speaker 脸 MCU（禁 fullbody 挂台词）· H3 prompt 禁 `no speech` · 每镜 `dialogue_audio_lane=native|post_tts|silence`（write-spec 默认 native）。
- **字幕验收 = 像素可见（P0 · v3）**：每条对白 cue 抽帧人眼可读；ship 硬烧优先。用户报「没字幕」先抽帧再改，勿只改 HF CSS。
- final 前自检：`speaker | voice | spoken_lang=zh | screen_mode | caption_pixels=ok`。
- **口白窗**：TTS ≤ cue ≤ slot；超窗 **砍 spoken / vo_rate**，禁只拉长 cue。
- **抽听（AD B3）**：ship 前每场 ≥1 句人耳可懂中文；有 aac ≠ 可懂。

### H3 原声 · 音乐总监（2026-08-07）

> 口白走 **prefer_native** 时：BGM / 爆音 / 错台词 mute **取决于总监 plan**，禁止各镜私拧旋钮。

1. `aifilm music-director draft --root …` → `audio/music-director-plan.json`
2. 导演改 plan：`mute_windows`（plate 内错句静音）· `mute_entire`/`lane=silence` · `peak_fix=auto` · BGM `duck_db`
3. `aifilm music-director apply --root …` → `audio/native_directed/{shot}.wav` + apply 回执
4. `aifilm music-director review --root …` → 抽听点 / mute 列表 / peak
5. `aifilm final …` 自动优先 directed stem（仍 XOR 禁叠 Edge）

v1 **只 mute 音频**，不改画面时长（剪画面走 editor_cut）。

色气 BGM 默认 **rnb**。中文 VO primary=Edge。机读：[hard-defaults](../hard-defaults.md) · [weapon-inventory](../weapon-inventory.md)。  
深入：[dialogue-first-workflow](../dialogue-first-workflow.md) · [vo-modes](../vo-modes.md) · [voices](../voices.md) · [caption-hardburn](../memory/2026-08-03-huangdao-caption-hardburn-meat-variety.md)
