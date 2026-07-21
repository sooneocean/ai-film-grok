# VO Modes — 口白策略（产品决策）

## Why mouth rarely “keeps up”

| Layer | Reality |
|---|---|
| Grok `image_to_video` | Silent I2V; mouth motion from text is **approximate**, not phoneme-locked to TTS |
| Free Wav2Lip | Often **warps anime faces**; detector fails on stylized art |
| MuseTalk | Better, needs NVIDIA + weights — not default on Apple Silicon |

So if the viewer **expects the character to be speaking** the line on screen, free tools usually disappoint.

## Three modes (pick in film-spec)

Set top-level:

```json
{
  "vo_mode": "storyteller",
  "title": "...",
  "scenes": []
}
```

| `vo_mode` | Expectation | Lip-sync | `nar` writing | Default when |
|---|---|---|---|---|
| **`storyteller`（默认推荐）** | 说书人讲故事；角色在「演」不在「念」 | **Always off** | 第三人称 / 「话说…」 | 色气短片、完播优先 |
| **`character`** | 角色本人在说话 | Need MuseTalk / careful CU Wav2Lip | 第一人称对白 | 用户明确要「她在讲」且接受嘴型风险 |
| **`hybrid`** | 说书人主导；1–2 镜角色金句 | Only shots with `"lipsync": true` | 说书句 + 少量对白 | 偶尔要「亲口说」的钩子 |

## Storyteller rules (default for 色气成片)

1. **Never** set `lipsync: true` unless user forces character mode.
2. I2V motion = **visible story action first**, then idle sensual filler (blink, breath, hair) — **not** “mouth speaking”.  
   旁白说「落锁 / 解扣 / 俯身」时，画面必须先动门闩/金扣/身体俯压，**不能**只播 push-in+眨眼。
3. `nar` uses storyteller voice（**默认中文女声，旁白优先于 BGM**）:
   - 推荐：`zh-CN-XiaoxiaoNeural`（晓晓 · 温暖旁白）· 详见 [voices.md](voices.md)
   - 备选甜：`zh-CN-XiaoyiNeural`；台湾：`zh-TW-HsiaoChenNeural`；男声仅用户指定
   - **中段句式（动作新闻）**：「门一落锁…」「金扣一松…」「她俯身逼近…」
   - **余韵句式（诗）**：「灯还亮着…」「故事却刚好开始。」
4. Subtitles = storyteller lines (same as `nar`), not “dialogue balloons” only.
5. Visuals carry 色气；voice carries **which action** — **decouple mouth from audio**, **couple verb to body**.  
   口白·动作锁细则：[lessons-2026-07-17-vo-motion-link.md](lessons-2026-07-17-vo-motion-link.md)。

## Character mode rules (opt-in)

1. Prefer **close-up only** for spoken lines.
2. I2V may add mild mouth motion; true sync only via MuseTalk when ready.
3. Wide / full-body shots remain storyteller or silent action.
4. Report honestly if lipsync skipped/failed.

## Decision tree (agent must follow)

```
用户要色气短片 / 没提对口型?
  → vo_mode = storyteller, lipsync off

用户坚持「角色亲口说」「嘴型必须对」?
  → vo_mode = character or hybrid
  → 仅大脸近景 + MuseTalk if ready, else 明确告知做不到真·对口型

嘴型再次失败 / 毁脸?
  → 回退 storyteller，不要硬贴 Wav2Lip
```

## Film-spec fields

```json
{
  "vo_mode": "storyteller",
  "vo_voice": "zh-CN-YunxiNeural",
  "scenes": [{
    "shots": [{
      "id": "shot01",
      "nar": "话说闭馆前的图书馆，助教推着小车，把规矩说得很软、很湿。",
      "lipsync": false,
      "dsl": { "motion": "soft blink, breath, hair sway — idle, not speaking" }
    }]
  }]
}
```
