# Voice 阶段卡

## P0 · 声线分轨（2026-07-24 强化 · 勿再犯）

| 层 | TTS | speaker | 字段 |
|----|-----|---------|------|
| **口白 / 说书** | **中文** Edge | `storyteller` / `narrator` | 只 `nar`；**禁止** `nar_ja` |
| **角色开口** | **日文** Edge（女 Nanami / 男 Keita） | `heroine` / `partner` / 具名 | `nar`(中文·字幕) + **`nar_ja` 必填** |
| **字幕像素** | — | — | 永远中文 `nar`；不烧 `nar_ja` 作主轨 |

- **禁止突然中日切换**：成块切换（说书段→角色段→说书段）；相邻镜 ZH↔JA 必须有 speaker 层变化；禁止镜镜乒乓。
- **禁止赶片删轨**：用户要 hybrid 时不得清空全部 `nar_ja` 改「全中文方案 B」。
- `nar` 是字幕/中文语义，`nar_ja` 是角色日文口语，不得互相覆盖。
- final 前自检：打印 `speaker | voice | spoken_lang`，无理由跳变 = 不合格。

色气或亲密段落 BGM 默认 rnb；dark 只用于恐怖，曲库缺失才走程序生成。  
dialogue、SFX、BGM 与 mixed 各自保留来源、hash 和 mix evidence。  
外部 TTS、克隆声线与 lipsync 不静默启用，也不把普通 I2V 口部运动宣称为真实口型同步。

深入资料：  
[voices.md](../voices.md) · [audio-recipe.md](../audio-recipe.md) ·  
[character-dialogue-ja](../lessons-2026-07-23-character-dialogue-ja.md) ·  
**[ep2-voice-heat-final（今天全量坑）](../lessons-2026-07-24-ep2-voice-heat-final.md)**
