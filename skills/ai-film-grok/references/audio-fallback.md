# 音频三阶梯 · TTS / BGM / Lipsync 兜底

> 嵌在 craft **Media → Verified**；不替代八环主脊。  
> 默认：**说书 = edge TTS + rnb 床轨 + lipsync off**。
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

## Lipsync

```text
off（默认；storyteller 强制 off）
  → 用户要开口 + shot.lipsync=true + speaker/face target + 正脸/微侧近景
  → 默认 FRW LTX 2.3 `img2video-audio`（原生有声 I2V）
  → 抽帧确认无供应商字幕/乱码，且人审台词语义与口型
  → LTX 的原生声音来自提示词；当前 FRW CLI 不接收锁定 TTS 音频
  → 仅上述一项失败时先回退原 FRW `img2video`（同一批准关键帧）
  → 上镜对白的 FRW `img2video` 回退片与已锁定 TTS 再启用已批准 RTX LatentSync 1.6
  → 可分类技术失败才按显式策略回退 RTX MuseTalk 1.5
  → 旧流程保留已 lock 本机 MuseTalk/Wav2Lip/external
  → auto 未就绪或失败写回执；显式 backend/require 失败停 final
禁止：未过 fingerprint+canary+人工审片当 ready；质量差时静默换后端；全片默认对口型
```

```bash
# RTX 节点：
"$AIFILM" lipsync-node health
"$AIFILM" lipsync-canary --root "<film>" --shot shot03 --backend latentsync
"$AIFILM" lipsync-canary --root "<film>" --shot shot03 --backend musetalk

# 收编前的三镜近景试点：不会写入任何影片 manifest。
# 先注册正脸、微侧脸、轻微头动三条独立视频，统一使用最终日语对白。
# approval.json 必须有 approved=true；audio 的 language=ja、role=final_character_dialogue；
# 三个 videos 条目分别以 front_closeup/three_quarter_closeup/moving_closeup 为键，
# role=approved_character_reference，并绑定实际 SHA-256。
"$AIFILM" lipsync-pilot create --root "<pilot-root>" \
  --front-video "<front.mp4>" \
  --three-quarter-video "<three-quarter.mp4>" \
  --moving-video "<moving.mp4>" \
  --japanese-audio "<dialogue-ja.wav>" \
  --approval-receipt "<approval.json>"
# run 会先确认 ComfyUI 队列完全为空；否则只写 blocked_queue 收据，不触发 GPU。
"$AIFILM" lipsync-pilot run --root "<pilot-root>"
# 仅当收据将 LatentSync 标为结构化技术失败且 MuseTalk 已获批准，才由人显式重跑：
"$AIFILM" lipsync-pilot rerun-musetalk --root "<pilot-root>" --sample front_closeup
"$AIFILM" lipsync-pilot review-template --root "<pilot-root>"

# 旧本机后端仍须用户审权重（agent 不代 acknowledge）：
backend-lock inspect --backend wav2lip --root "$W2L"
backend-lock lock --backend wav2lip --root "$W2L" --acknowledge-trusted-weights
"$AIFILM" lipsync-canary --root "<film>" --shot shot03
"$AIFILM" final --root "<film>" --lipsync auto   # 仅标 true 的镜
```

## 场景自适应配方

按 `dramatic_function` 自动选 `narrate_bed` / `narrate_thin` / `bed_focus` 等；片级 `audio_policy`。  
见 [audio-recipe.md](audio-recipe.md)。

```bash
"$AIFILM" write-spec --root "<film>"
"$AIFILM" audio-plan --root "<film>"
```

## capability 字段

`aifilm capability` 含 `tts` · `music` · `lipsync` · `recommendations`。  
见 [craft-spine.md](craft-spine.md) · [voices.md](voices.md) · [lipsync.md](lipsync.md)
