# Memory · 2026-08-06 · 原声 XOR TTS（禁双重对白）

## 用户原话
> 生成的影片我发现好像除了主角讲话还有一个重复的旁白 … 不接受重复讲同样的对白 … 从根因修管线（原声 XOR TTS + 闸门）

## 三句话
1. 根因：`prefer_native` 保留 H3/Grok 原声时，Edge 仍全量合成同一句进 `narration` → 听感双轨。
2. 修法：每镜 `resolve_dialogue_audio_lane` → `native` \| `post_tts` \| `silence` 互斥；native 时 silent VO + 字幕仍烧。
3. 闸门：`DUPLICATE_DIALOGUE_AUDIO` + mix XOR fail-closed。

## 检查清单
- [x] 管线：`resolve_dialogue_audio_lane` + `render_final` silent VO on native（v2.40.18）
- [x] 闸门：`DUPLICATE_DIALOGUE_AUDIO` + mix XOR fail-closed
- [ ] final 后 `audio/mix_report.json` → `native_audio.shot_lanes` 无 `native`+`tts_mix_gain>0`（**片级重跑才验**）
- [ ] 人耳：对白镜只听一路声
- [ ] ADR 逃生：`audio_origin=post_vo` 或 `strip_native_use_tts_bgm`

## 链
- hard-defaults「原声 XOR TTS」· `final/native_audio.py` · `render_final` · `final_editorial_review`
