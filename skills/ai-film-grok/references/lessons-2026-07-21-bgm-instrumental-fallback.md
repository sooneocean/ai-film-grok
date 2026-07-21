# Lessons · 2026-07-21 · 重复 BGM + 纯乐器兜底（收工沉淀）

**层**：voice · **P**：硬兜底有声；听感用纯乐器池；不静默换商

## 问题

程序床听腻；歌模型（HeartMuLa）带人声不适合说书 BGM。

## 定稿阶梯

1. **听感**：`assets/bgm/rnb/*.wav` 纯乐器多文件 + seed 轮换  
2. **工程硬兜底**：程序 rnb **v3 multi-style**（换 seed 换 style 族）  
3. **灌库可选**：ACE-Step `[inst]` / Stable Audio Open /（MusicGen 常 NC）→ 听审无人声 → 入池  
4. **不当 BGM 硬兜底**：HeartMuLa 成歌  

## 已实现

| 项 | 位置 |
|---|---|
| multi-style 程序床 | `make_sfx_bed.rnb_bgm` |
| 曲库池 seed 轮换 | `sound_plan.resolve_music_template` |
| 场景 bed 厚薄 | `audio_recipe` + `bed_gain_hint` |
| seed 优先级 | CLI → `audio_policy.music_seed` → hash(+recipe counts) |
| 文档 | [bgm-generation.md](bgm-generation.md) |

## 操作口令

```bash
# 换 take
"$AIFILM" final --root <r> --music-seed 99 --tts-backend edge --music-mood rnb
# 灌池后自然抗重复
ls ~/.grok/skills/ai-film-grok/assets/bgm/rnb/
```

## 勿做

- 默认 final 热路径跑重型 AI 生乐  
- 有唱轨进 rnb 默认池  
- MusicGen NC 权重当商用默认  
