# 多轨声线（Voice Tracks）

> 2026-07-21 · 分层语义：旁白 / 画面语气 / 声景。  
> **2026-07-22 v1.10**：非成人仍默认关娇喘轨；**hardcore / spice=extreme** 建议开 + act 自动肉体 SFX。

## 默认成片声线

| 轨 | 非成人默认 | 重口 hardcore / extreme |
|---|---|---|
| **旁白 `nar`** | ✅ 主叙事 | ✅ 更直白办事动词 |
| **BGM** | ✅ rnb / sidechain | ✅ rnb |
| native clip 环境音 | 低增益可选 | 同左 |
| **vocal_color 娇喘轨** | ❌ 关（鸡肋） | ✅ **建议开** auto + gain≈0.52 |
| tone_tags | 只进画面 prompt | act 自动 breathy/moan |
| sound_cues | 可进 SFX | act/climax **自动** impact/breath/leather |

## 为什么还留字段

| 内容类型 | 层 |
|---|---|
| 叙事办事动词 | **`nar`** |
| 角色表演语气（喘息脸、媚眼） | **`tone_tags`** → 静帧/I2V |
| 皮座/心跳等 | **`sound_cues`** → SFX |
| 娇喘语助（可选实验） | `vocal_color` 须 `voice_tracks.enabled=true` |

## 片级 `voice_tracks`

```json
{
  "voice_tracks": {
    "enabled": false,
    "nar_gain": 1.32,
    "vocal_color_gain": 0.0,
    "native_audio_volume": 0.72,
    "sfx_bed_gain": 0.55,
    "auto_vocal_color": false
  }
}
```

| 字段 | 含义 | 默认 |
|---|---|---|
| `enabled` | 是否启用语助轨 | **false** |
| `nar_gain` | 主旁白增益 | 跟 `vo_gain` |
| `vocal_color_gain` | 语助轨 | **0** |
| `auto_vocal_color` | 自动补嗯啊 | **false** |

Opt-in 实验（不推荐默认）：`enabled=true` + `vocal_color_gain=0.5~0.7` + 每镜 `vocal_color`。

## 镜级字段

```json
{
  "id": "shot06",
  "nar": "一坐到底。沉腰吃进，整根吞满。",
  "vocal_color": "嗯…啊…",
  "vocal_color_offset_sec": 1.4,
  "vocal_color_gain": 0.7,
  "tone_tags": ["breathy", "needy", "moan"],
  "sound_cues": ["leather", "breath", "impact"]
}
```

| 字段 | 进哪条轨 | 说明 |
|---|---|---|
| `nar` | 旁白 TTS | 字要听得懂、办事动词清楚 |
| `vocal_color` | **独立 TTS** | 极短；自动也可：`嗯…` / `哈啊…` |
| `vocal_color_offset_sec` | 时间轴 | ≥0 绝对偏移；缺省 ≈ 板长 55% 或 VO 中后段 |
| `tone_tags` | **画面 prompt** | breathy / teasing / dominant / needy / whisper / moan / afterglow / shy / hungry |
| `sound_cues` | **SFX accent** | breath / heartbeat / whoosh / impact / leather… |

## final 混音图（默认）

```
[narration.wav]  × nar_gain  ──┐
[bgm]            × music_vol ─┬─ sidechain(duck by VO) ─┐
[native_track]   × native_vol ─┘                        ├─ amix + alimiter → mixed.wav
```

`mix_inputs` 默认：`["narration", "bgm", "native"]`。  
**仅** opt-in（`voice_tracks.enabled=true` 且 gain>0 且有 stem）才多一路 `vocal_color`。

产物：

- `audio/narration.wav` — 主旁白
- `audio/mix_report.json` → `voice_tracks` / `vocal_color_shots` / `mix_inputs`
- （opt-in）`audio/*_color.wav` · `audio/vocal_color_track.wav`

## write-spec

`apply_audio_recipes_to_spec` 末尾调用 `apply_voice_tracks_to_spec`：

- 规范化 `tone_tags` / `sound_cues`
- `auto_vocal_color` 时按 `heat_phase` 填短语助
- 写 `spec._voice_tracks_routing`

## 写作纪律

1. **nar 不写娇喘串**（「嗯啊嗯啊她沉腰…」）→ 语助进 `vocal_color`
2. **tone 不进 TTS**（「用喘息的语气说」）→ `tone_tags`
3. **物件声不念**（「皮座发出吱呀」）→ `sound_cues`
4. 语助 **≤ 8 字**，避免 loop_risk / 盖旁白

## 相关

- [audio-recipe.md](audio-recipe.md) · [audio-fallback.md](audio-fallback.md) · [voices.md](voices.md)
- 代码：`scripts/voice_tracks.py` · `render_final.py` · `prompt_injector.py`
