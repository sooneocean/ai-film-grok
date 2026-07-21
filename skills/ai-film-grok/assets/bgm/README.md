# Shared BGM library（纯乐器 · 用户自放）

技能**不附带**版权曲。这里只放 **无人声 / 纯乐器** bed，供 final 按 mood + seed **池轮换**。

## 规则

1. **纯乐器**：有唱、有说唱的不要进默认 `rnb/`（会抢旁白）  
2. 多首：`01.wav` `02.wav` …（≥3 首抗重复效果最好）  
3. 旁注：`同名.license.txt` 写来源与授权  
4. 无文件时 → **程序化 rnb v3**（工程硬兜底，永不假静音）

## 布局

```text
assets/bgm/
  rnb/           # 色气 / 说书默认 · 只放 instrumental
  sensual/
  warm/
  playful/
  dark/          # 仅恐怖
  default/
```

## 抗重复

- 池内 `music_seed % pool_size`  
- 或 `--music-seed` / `audio_policy.music_seed`  
- 详见 [bgm-generation.md](../../references/bgm-generation.md)
