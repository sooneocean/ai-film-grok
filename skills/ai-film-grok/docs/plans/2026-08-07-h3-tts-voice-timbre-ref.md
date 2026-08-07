# H3 TTS voice-timbre ref (path 2) · 2026-08-07

## Goal
Feed Edge TTS wav into MiniMax H3 as **audio input** so generation uses locked cast voice.

## How it works
1. Edge TTS (or any wav) → Comfy `LoadAudio`
2. Wired to `MiniMaxH3ReferenceToVideo.ref_audios.ref_audio_0`
3. Prompt clause: `<Audio 1>` = S1 voice-timbre reference
4. **Forces R2V** (I2V node has no audio slot)

## CLI
```bash
# auto Edge from cast_voices + shot dialogue
aifilm h3 run --root "$ROOT" --shot-id ep01_sc01_bt01_sh01 \
  --tts-ref --stage pilot --register

# explicit wav
aifilm h3 run --root "$ROOT" --shot-id ep01_sc01_bt01_sh01 \
  --audio-ref audio/tts/h3-ref/....wav --stage pilot --register

# voice override
aifilm h3 run ... --tts-ref --tts-voice zh-CN-XiaoyiNeural
```

Env: `AIFILM_H3_TTS_VOICE_REF=1` same as `--tts-ref`.

## Files touched
- `scripts/media/comfy_video.py` · `upload_audio`
- `scripts/media/comfy_armory.py` · optional LoadAudio inject + template match
- `registry/comfy-weapons.json` · minimax-h3-r2v-pilot `ref_audio_*` bindings
- `scripts/media/i2v_provider.py` · upload + pass input_audio_name; force r2v
- `scripts/media/h3_workflow.py` · ensure TTS + prompt + gen_kwargs
- `scripts/cli/cli_h3.py` · `--audio-ref` / `--tts-ref` / `--tts-voice`

## XOR note
H3 native output audio should already be the TTS-conditioned voice; do **not** also mix Edge TTS on the same line (DUPLICATE_DIALOGUE_AUDIO).

## Verify
```bash
python -c "from media.comfy_armory import compile_weapon_workflow, _matches_registered_template, _weapon
g=compile_weapon_workflow('minimax-h3-r2v-pilot', prompt='x', seed=1,
  input_image_name='aifilm_deadbeef0123456.png', input_audio_name='aifilm_cafebabe89abcdef.wav')
assert g['23']['class_type']=='LoadAudio'
assert _matches_registered_template(g, _weapon('minimax-h3-r2v-pilot'))"
```

Generated: 2026-08-07T09:57:21.365184+00:00
