# 2026-07-24 · ep2 声线分轨 + final 工程（P0）

**用户硬令**：口白中文 · 角色日文 · **禁止突然中日切换** · 肉戏动态要猛 · 别再犯今天错误。

## 必读课

- [lessons-2026-07-24-ep2-voice-heat-final.md](../references/lessons-2026-07-24-ep2-voice-heat-final.md)
- 叠加 [character-dialogue-ja](../references/lessons-2026-07-23-character-dialogue-ja.md)

## 铁律（复制进脑）

1. **口白/说书** = 中文 TTS only · `speaker=storyteller` · **禁止** `nar_ja`
2. **角色开口** = 日文 TTS · `speaker=heroine|…` · **必填** `nar`（中文字幕）+ `nar_ja`
3. **字幕** = 永远中文 `nar`；与 TTS 语言解耦
4. **禁乒乓**：相邻镜 ZH↔JA 必须有 speaker 层切换理由；成块切换，勿镜镜乱跳
5. **禁赶片删轨**：不要为出片清空全部 `nar_ja`
6. **final**：`sub_lead=0` + SRT 非重叠；长片直调 `render_final.py`；review 后还要 `register-clip --status approved`
7. **肉戏 2×**：重跑 I2V 高动态 edge prompt + 加长日文喘息；不赌露点审核

## 片例

- root: `/Users/dex/AI FILM SPACE/0724/ep2`
- delivery: `out/film_delivery.mp4`（hybrid JA/ZH + heat2x 肉镜）
- receipt: `receipts/heat2x-ja-delivery.json`
