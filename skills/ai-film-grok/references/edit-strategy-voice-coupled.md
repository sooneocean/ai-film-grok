# 剪辑策略迭代 · Voice-Coupled Editorial（2026-07-21）

> **问题**：final 常变成「每镜 6s + 全 hard 切 + 旁白拖满板」的幻灯片，呆板。  
> **策略**：把 **热度相位 + 多轨声线（nar / vocal_color / sound_cues / tone_tags）** 接进剪辑语法。

## 一句话

**剪辑不再用同一把尺量所有镜**——办事段 snap 切 + 短叠；余韵 mood_hold 长叠；语助轨有落点；画面 `visual_fit` 跟声线走。

## 呆板根因 → 对策

| 呆板现象 | 根因 | 本迭代 |
|---|---|---|
| 镜镜 6 秒幻灯片 | `visual_fit=slot` 一律填满 | act/climax 默认 **`visual_fit=vo`** |
| 全 hard 同一刀感 | 作者/默认 `transition_intents` 全 hard + 固定 `transition_sec` | **`edit_craft` 热度重写** + **`join_transition_secs` 每缝不同** |
| 旁白完立刻硬切 | 不关心 vocal_color | color **offset 落在板中后段**；afterglow **slot 留尾巴** |
| 无物件插镜 | craft 全 cut_on_action | `sound_cues` → 倾向 **insert_cut** |
| 高潮不砸、余韵不放 | 无 heat 感知 | act→act **montage/smash**；climax→afterglow **mood_hold** |

## film-spec

```json
{
  "edit_strategy": {
    "mode": "voice_coupled",
    "lock_craft": false,
    "prefer_vo_fit_on_act": true,
    "hard_join_sec": 0.06,
    "soft_join_sec": 0.26,
    "hold_join_sec": 0.40,
    "whip_join_sec": 0.18,
    "color_tail_sec": 0.55
  }
}
```

| mode | 行为 |
|---|---|
| `off` | 不改 craft |
| `auto` | heat max/hot → voice_coupled；soft → silk |
| `voice_coupled` | **默认成人策略**（本迭代主推） |
| `punchy` / `silk` | 偏硬 / 偏软 fluency |

`lock_craft: true` + 作者 `edit_craft` → 只改 visual_fit/offset，不重写 craft。

write-spec 后可读：

- `edit_craft` / `transition_intents` / `transition_styles`
- **`join_transition_secs`**（每缝秒数）
- `_edit_strategy_plan`

## 节奏表（voice_coupled）

| 相位缝 | craft 倾向 | join 秒 |
|---|---|---|
| setup → foreplay | whip_soft | ~0.18 |
| foreplay → act | smash / cut_on_action | ~0.06 |
| act → act | montage_jump | ~0.06 |
| → climax | smash_cut | ~0.06 |
| climax → afterglow | mood_hold | ~0.40 |
| sound_cues 物件 | insert_cut | hard micro |
| continue 字节缝 | 永 hard 族 | ≤0.04 |

## 与声线层的契约

| 声线 | 剪辑响应 |
|---|---|
| `nar` 办事动词 | act `visual_fit=vo`，少死静 |
| `vocal_color` 娇喘 | offset≈板 52%；afterglow 留 slot |
| `tone_tags` moan/hungry | 倾 smash |
| `tone_tags` afterglow/shy | 倾 soft_glue / mood_hold |
| `sound_cues` leather/impact | insert_cut |

## final

`render_final` 读 `join_transition_secs` → 展开为 title/end 边缝 + 镜间缝的 **`join_use_ts`**，传入 xfade（硬缝可微叠 0.06，余韵 0.40）。

## 代码

- `scripts/edit_strategy.py`
- `film_spec.validate` 在 audio/voice 之后调用 `apply_edit_strategy_to_spec`
- `render_final.concat_videos(..., join_use_ts=…)`

## 验收

1. write-spec 后 `len(set(edit_craft)) ≥ 4`（60s 成人）  
2. act 镜 `visual_fit == vo`  
3. final log 出现 `join_use_ts=[...]` 且非全等  
4. 观感：办事段更脆，余韵更拖得住，语助听得到落点  

## 相关

- [voice-tracks.md](voice-tracks.md) · [editor-cut-pass.md](editor-cut-pass.md) · [editorial-craft.md](editorial-craft.md)
