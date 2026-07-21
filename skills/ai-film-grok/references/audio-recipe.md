# 场景自适应声轨配方（audio_policy + audio_recipe）

> write-spec 自动按 `dramatic_function` 等为每镜写入 `audio_recipe`；**默认不自动唱、不自动口型**。

## 片级 `audio_policy`

```json
{
  "audio_policy": {
    "mode": "auto",
    "allow_sung": false,
    "allow_lipsync": false,
    "bed_source": "auto",
    "max_sung_shots": 1,
    "music_seed": 42
  }
}
```

| 字段 | 含义 |
|---|---|
| `mode` | `auto`（默认）· `storyteller_only` · `musical_hybrid` |
| `allow_sung` | 仅 `musical_hybrid` 可为 true；否则强制 false |
| `allow_lipsync` | 未开则不对口型（作者 `shot.lipsync=true` + 非 storyteller 可例外） |
| `bed_source` | `auto` 曲库池→程序 · `library_only` · `procedural_only` |
| `max_sung_shots` | hybrid 最多几镜 `sung_beat`（默认 1） |
| `music_seed` | 可选；与 final `--music-seed` 对齐 |

### mode 行为

| mode | 说书/床厚薄自适应 | 自动 sung | 自动 lipsync |
|---|---|---|---|
| `auto` | ✅ | ❌ | ❌ |
| `storyteller_only` | ✅ | ❌ | ❌ |
| `musical_hybrid` | ✅ | 最多 N 镜高潮近景 | 可 |

## 镜级 `audio_recipe`（5 种）

| recipe | 主声 | 床 | 口型 | 典型 beat |
|---|---|---|---|---|
| `narrate_bed` | 旁白 | full (gain≈1.0) | off | hook / approach / action |
| `narrate_thin` | 旁白 | thin (≈0.55) | off | bridge / reaction / 长 sensory |
| `bed_focus` | 无/极短 | focus (≈1.15) | off | 短 sensory / afterglow |
| `dialogue_lipsync` | 角色口白 | thin | **on**（近景） | hybrid + lipsync 旗标 |
| `sung_beat` | **唱=词** | thin | on | musical_hybrid 高潮 |

write-spec 写入完整对象：

```json
"audio_recipe": {
  "recipe": "narrate_thin",
  "primary_voice": "narration",
  "bed": "thin",
  "bed_gain": 0.55,
  "lipsync": false,
  "sfx_level": "minimal",
  "source": "auto",
  "reasons": ["beat=reaction", "policy.mode=auto"]
}
```

作者可强制：

```json
"audio_recipe": "bed_focus"
```

能力不足时降级并记 `degraded_from`（如 sung 无 provider → narrate_bed）。

## 路由摘要

write-spec 后：

- `film-spec.audio_policy`
- `film-spec._audio_routing`（counts / mean_bed_gain / 每镜 reasons）
- `sound_plan.bed_gain_hint`（供 final 调节床响度）

```bash
"$AIFILM" write-spec --root "<film>"
"$AIFILM" audio-plan --root "<film>"   # 含 audio_routing
```

## final 行为（当前）

- 读 `bed_gain_hint` / `mean_bed_gain` → 调节程序床 gen amp 与 music_volume  
- mix_report 记 `audio_routing_counts`、`audio_policy`  
- **sung 仍不自动生成**（需后续 HeartMuLa 适配器 + provider）；路由会先降级  

## 与其它文档

- BGM 抗疲劳：[bgm-generation.md](bgm-generation.md)  
- TTS 兜底：[audio-fallback.md](audio-fallback.md) · [voices.md](voices.md)  
- 口型：[lipsync.md](lipsync.md)  
