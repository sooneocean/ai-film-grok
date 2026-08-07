# 音频阶梯 · TTS / BGM（Lipsync 已退役）

> 嵌在 craft **Media → Verified**；不替代八环主脊。  
> 默认：**Edge 中文 TTS + rnb 床轨**；对白有声镜 **prefer_native**（Grok/H3 原音）。  
> **后期 lipsync 已 v2.40 移除**（`final --lipsync` 仅 off）— 见 [lipsync.md](lipsync.md)。  
> 响度标准（LUFS -16±2）：[loudnorm-policy.md](loudnorm-policy.md)（单一真相，禁止多套阈值）。

## TTS

```text
edge（默认 · 零依赖）
  → Voicebox（质量/克隆 · 固定 VOICEBOX_PROFILE）
  → AIFILM_TTS_VOICEBOX_FALLBACK=1 时 edge 失败再试 Voicebox
  → 仅 tts_allow_network_fallback 时 MiniMax/Fish（固定 voice_id）
禁止：zh-CN-*Neural 塞 ElevenLabs；静默换声
```

```bash
"$AIFILM" capability
"$AIFILM" tts-ab --root "<film>" --shot shot01 --backends edge,voicebox
"$AIFILM" tts-rehearse --root "<film>" --backend edge
```

## BGM（纯乐器优先 · 抗重复）

```text
听感兜底：纯乐器曲库池 assets/bgm/rnb/* 或 audio/templates/rnb/*（seed 轮换）
  → --music 用户文件
  → AIFILM_MUSIC_ARGV（可选现生成；失败回落）
工程硬兜底：程序化 rnb v3 multi-style（永远有声；换 music-seed 换 style）
禁止：把 HeartMuLa 成歌当默认 BGM；有人声轨进 rnb 池
music_template=on 且全无文件 → hard fail
```

```bash
"$AIFILM" audio-plan --root "<film>"
# 听腻：--music-seed N  或  池内放 ≥3 首纯乐器
# 详：references/bgm-generation.md · audio-recipe.md
```

## Lipsync（墓碑 · v2.40）

```text
生产：final --lipsync 仅 off
对白有声：Grok / H3 prefer_native（禁后期对嘴叠 TTS）
历史 CLI / 节点：tombstone（route-catalog status=tombstone）
政策：references/lipsync.md
```

```bash
"$AIFILM" final --root "<film>" --lipsync off
```

## 场景自适应配方

按 `dramatic_function` 自动选 `narrate_bed` / `narrate_thin` / `bed_focus` 等；片级 `audio_policy`。  
见 [audio-recipe.md](audio-recipe.md)。

```bash
"$AIFILM" write-spec --root "<film>"
"$AIFILM" audio-plan --root "<film>"
```

## capability 字段

`aifilm capability` 含 `tts` · `music` · `recommendations`（lipsync 字段若仍有 = 墓碑说明）。  
见 [craft-spine.md](craft-spine.md) · [voices.md](voices.md) · [lipsync.md](lipsync.md)
