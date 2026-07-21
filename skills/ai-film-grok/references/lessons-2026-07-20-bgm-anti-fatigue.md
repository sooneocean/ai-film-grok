# 实战复盘：BGM 听腻 + 设计后期音轨（2026-07-20）

## 一句话

程序 R&B 床不能 60 秒单循环；设计后期成片不能继承「近静音镜头原生轨」当最终混音。

## 现象对照

| # | 现象 | 根因 | 规则 |
|---|------|------|------|
| 1 | Remotion 成片几乎听不见 | `ensure_audio_mux` 见有 audio stream 就 passthrough；I2V 原生轨 mean≈-56dB | **优先 `audio/mixed.wav` / film_final 音轨**；过静才用原生 |
| 2 | 同一 rnb 听很多遍腻 | `rnb_bgm` 固定 Am9→Dm→G→C + 恒定 kick/clap | 多套和声 + 分段编曲 + kit 密度 + seed |
| 3 | 想换 take 无法控 | 无 seed | `--music-seed`；默认 hash(title+mood) |
| 4 | burned final + underlay 双烧 | 旧 plate burned_in | underlay hard gate；auto 可降 multiclip |
| 5 | remotion npm `4.0.0` 不存在 | 假 pin | 用 npm 真实版（现 4.0.494） |

## 听感优化（rnb v2 → v3）

**v2（2026-07-20）**

- 4 套 progression 轮转（am / em / fm / gm）
- section：sparse → full → pad bridge → half-time → soft return → outro
- half-time 段减少踩点；ghost kick / 句末 fill 少量
- 轻微 BPM 抖动 + seed 可复现

**v3（2026-07-21）—— 听腻同音色族**

- seed 映射 **style**：velvet / pulse / ambient / lofi / glitter（听感差一档，不只重排）
- 6 套 progression；曲库池 `seed % n` 轮换
- 可选 `AIFILM_MUSIC_ARGV` → ACE-Step 等外部 AI
- 文档：[bgm-generation.md](bgm-generation.md)

```bash
"$AIFILM" final --root "<root>" --tts-backend edge --music-mood rnb --music-seed 20260720
# 再换 take（会换 style）：
"$AIFILM" final --root "<root>" --tts-backend edge --music-mood rnb --music-seed 42
# 预听：
python3 "$HOME/.grok/skills/ai-film-grok/scripts/make_sfx_bed.py" \
  --duration 24 --shot-starts 0 --mood rnb --seed 42 --out /tmp/bgm.wav
```

## 代码入口

- `scripts/make_sfx_bed.py` — `rnb_bgm(..., seed=)` multi-style
- `scripts/sound_plan.py` — 曲库池轮换
- `scripts/render_final.py` — `--music-seed` + external music hook
- `scripts/adapters/music_external.py` — AI HTTP
- `scripts/compose_render.py` — `ensure_audio_mux` 优先 mixed.wav
