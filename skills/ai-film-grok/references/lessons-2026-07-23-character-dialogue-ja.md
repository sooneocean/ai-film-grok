# Lessons · 人物对白日文 TTS（旁白/字幕仍中文）

> 2026-07-23 · **P0 声线**  
> 用户诉求：人物讲话用日文更好听、更像里番/漫剧；观众字幕仍要中文。

## 一句话

**角色开口（对白）→ 日文 TTS；说书旁白 → 中文 TTS；烧进画面的字幕 → 默认中文。**  
禁止把 `zh-CN-*-Neural` 塞给「角色在说」的镜，也禁止用日文 TTS 文本当唯一字幕源。

---

## 为什么

| 层 | 默认 | 理由 |
|----|------|------|
| 人物对白音 | **日文** edge `ja-JP-NanamiNeural`（女）/ `ja-JP-KeitaNeural`（男） | 色气/漫剧听感更贴；中文 Neural 对白易「配音感」 |
| 说书/OS 旁白 | **中文** edge `zh-CN-XiaoxiaoNeural` 等 | 叙事清楚；与 Agent 回复语言一致 |
| 字幕像素 | **中文**（`nar` / `nar_zh`） | 交付门：主 mp4 须有中文字幕；日文可作副轨 `nar_ja` 不上屏除非 `caption_mode` 显式改 |

---

## film-spec 约定

```json
{
  "tts_backend": "edge",
  "vo_mode": "hybrid",
  "vo_voice": "zh-CN-XiaoxiaoNeural",
  "dialogue_spoken_lang": "ja",
  "narration_spoken_lang": "zh",
  "caption_lang": "zh",
  "cast_voices": {
    "storyteller": "zh-CN-XiaoxiaoNeural",
    "heroine": "ja-JP-NanamiNeural",
    "partner": "ja-JP-KeitaNeural",
    "male_hero": "ja-JP-KeitaNeural"
  },
  "shots": [{
    "id": "ep01_sc01_bt08_sh01",
    "speaker": "heroine",
    "nar": "「这个病毒，不简单。」她湿透了，仍强迫站稳。",
    "nar_ja": "「このウイルス、ただ者じゃないわ。」彼女はすでに濡れているのに、無理に立ち尽くしている。",
    "vo_voice": "ja-JP-NanamiNeural"
  }]
}
```

| 字段 | 含义 |
|------|------|
| `dialogue_spoken_lang` | 角色对白 TTS 语言；**默认 `ja`**（产品偏好，可 `zh` 覆盖） |
| `narration_spoken_lang` | 说书旁白 TTS；默认 `zh` |
| `caption_lang` | 烧字语言；默认 `zh`（与 `caption_mode` 兼容） |
| `shot.speaker` | `heroine` / `partner` / `storyteller` … → 选 `cast_voices` |
| `shot.nar` | **中文**口白/字幕主源（观众读） |
| `shot.nar_ja` | **日文**成片 TTS 源（角色开口时必填；缺则 write-spec soft warn） |
| `shot.dialogue` / `dialogue_ja` | 纯对白字段（可选；优先于整段 nar 当 spoken） |

---

## 判定：什么算「人物讲话」

下列任一为真 → 走 **日文对白轨**（当 `dialogue_spoken_lang=ja`）：

1. `shot.speaker` / `role` ∈ 角色（非 `storyteller`/`narrator`/`vo`）
2. `shot.dialogue` / `dialogue_ja` 非空
3. `shot.vo_voice` 已是 `ja-JP-*`
4. `cast`/`dsl.cast` 首角在 `cast_voices` 且对应 voice 为 `ja-JP-*`
5. 文本以全角引号对白为主且 `speaker` 标明角色（推荐显式 `speaker`，勿靠猜）

**说书镜**（`vo_mode=storyteller` 且无角色 speaker）→ 中文 TTS + 中文字幕。

---

## 管线行为（`render_final`）

1. **TTS 文本** = `spoken_text_for_shot`：角色日文优先 `nar_ja` → `dialogue_ja` → `dialogue`；旁白用 `nar`/`narration`
2. **字幕文本** = `caption_text_for_shot`：永远优先 `nar`/`nar_zh`（中文）；**不要**把 `nar_ja` 当唯一 cue
3. **声线** = `voice_for_shot`：`cast_voices[speaker]`；角色默认 Nanami/Keita
4. 禁止：中文旁白 voice 读日文长句、或日文 voice 读中文（edge 会怪腔）

---

## Agent 纪律

- 写镜时：角色开口 **同时** 写 `nar`（中文）+ `nar_ja`（日文）+ `speaker`
- `write-spec`：`dialogue_spoken_lang=ja` 且角色镜缺 `nar_ja` → soft fail/报告，final 前补齐
- 用户显式「对白也要中文」→ 设 `dialogue_spoken_lang: "zh"` 并清日文 voice
- 与 [subs-always-burn-hard](lessons-2026-07-23-subs-always-burn-hard.md) 并存：**字幕语言 ≠ 对白 TTS 语言**

---

## 验收

- [ ] 角色近景对白听感为日文（Nanami/Keita 或用户锁声）
- [ ] 旁白镜仍为中文
- [ ] 主 mp4 抽帧可见 **中文**字幕
- [ ] `cast_voices` 一角一声，无跨镜随机
- [ ] 未把 `zh-CN-*` 名塞进 ElevenLabs / CosyVoice

---

## 相关

- [voices.md](voices.md) · [voice-tracks.md](voice-tracks.md)
- [lessons-2026-07-20-cut-silk-bilingual.md](lessons-2026-07-20-cut-silk-bilingual.md)（中英字幕轴；本课是 **对白日文音**）
- `scripts/render_final.py` · `spoken_text_for_shot` / `caption_text_for_shot` / `voice_for_shot`
