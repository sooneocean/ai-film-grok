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

色气或亲密段落 BGM 默认 **rnb**；dark 只用于恐怖，曲库缺失才走程序生成。  
dialogue、SFX、BGM 与 mixed 各自保留来源、hash 和 mix evidence。  
final：`sub_lead=0`；长片直调 `render_final`；review 后还要 `register-clip approved`。  
外部 TTS、克隆声线与 lipsync 不静默启用；RTX 5090 口型须逐镜 canary（LatentSync 1.6 → MuseTalk 1.5）。

机读门禁：[hard-defaults](../hard-defaults.md)。  
深入（按需，不默认加载）：[voices](../voices.md) · [audio-recipe](../audio-recipe.md) ·  
[character-dialogue-ja](../lessons-2026-07-23-character-dialogue-ja.md) ·  
[ep2-voice-heat-final](../lessons-2026-07-24-ep2-voice-heat-final.md) ·  
[5090 lipsync](../lessons-2026-07-28-rtx5090-lipsync-routing.md)
