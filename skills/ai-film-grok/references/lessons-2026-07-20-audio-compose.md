# Lessons 2026-07-20 — 设计后期双引擎 + 听感全链路（A→H）

> 一次 session 把 **HyperFrames/Remotion 设计后期** 与 **旁白/BGM/SFX/响度/模板曲** 收成可交付默认。  
> 口令：**I2V 拍戏 · FFmpeg/HF 成片 · 听感靠 sound_plan · 交付靠 review-final**。

## 一句话

设计后期只做 titles/captions/overlays；音轨默认 **edge + rnb + auto_sfx + sidechain + loudnorm auto**；本地许可曲放 `audio/bgm.wav` 即用。

## 成片推荐命令（收工后默认）

```bash
SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"

# 可选：自备许可 rnb
# cp ~/Music/ok-to-use.wav "<root>/audio/bgm.wav"
# echo "许可说明…" > "<root>/audio/bgm.license.txt"

"$AIFILM" write-spec --root "<root>"   # auto→edge；rnb sidechain；auto_sfx
"$AIFILM" preflight --root "<root>"
"$AIFILM" write-spec --root "<root>"   # 也自动补 transition_styles / 更多 hard
"$AIFILM" final --root "<root>" \
  --tts-backend edge \
  --music-mood rnb \
  --music-seed 20260720 \
  --loudnorm auto \
  --music-template auto \
  --post-engine hyperframes \
  --compose-preset auto
"$AIFILM" status --root "<root>"       # 看 audio.* / compose.*
"$AIFILM" review-final --root "<root>" --approve …  # 七维
```

## Phase 对照表（已进代码）

| Phase | 能力 | 关键入口 |
|---|---|---|
| **A** | compose preset `ecchi-rnb` / `minimal`；underlay 字幕时钟 offset=0 | `export_composition` · `--compose-preset` |
| **B** | preview 回执 `receipts/compose-preview.json`；`--require-preview`；next 引导 | `compose_preview` · `next_actions` |
| **C** | Remotion `--npm-install`；未装 deps → next_steps 不 silent ok | `compose_render` |
| **D** | `sfx_accent` **真叠入**；`auto_sfx` 按 beat | `sound_plan` · `render_final` |
| **E** | 侧链可配（rnb release≈720ms）；Neural 禁塞 ElevenLabs（hard） | `resolve_sidechain` · `tts_backend` · preflight |
| **F** | write-spec 钉 edge + sidechain；status `audio`；LUFS 探测 | `film_spec` · `status` · `probe_mixed_loudness` |
| **G** | loudnorm **auto**（过响/过轻 → ~-16 LUFS） | `--loudnorm` · `resolve_loudnorm` |
| **H** | 本地 BGM 模板 `audio/bgm.wav` / `audio/templates/rnb.wav` | `resolve_music_template` · `--music-template` |
| **I** | BGM 抗疲劳：多套和声+分段；`--music-seed` | `rnb_bgm` · [bgm-anti-fatigue](lessons-2026-07-20-bgm-anti-fatigue.md) |
| **J** | 转场 `transition_styles` 每缝不同；运镜主轴防 push-in 三连 | [motion-transition](lessons-2026-07-20-motion-transition.md) |
| **K** | 设计后期音轨优先 `audio/mixed.wav`（禁近静音 I2V 原生轨） | `ensure_audio_mux` |
| **L** | 双烧 gate；Remotion pin 真版本；`final --post-engine remotion` | `compose_render` · post-compose |

## 硬规则（以后遇到 X 就做 Y）

1. **中文说书 TTS** → `write-spec` 把 `auto` 钉 `edge`；final 显式 `--tts-backend edge`。  
2. **`zh-CN-…Neural` + external/ElevenLabs** → preflight hard / synthesize 失败；换 edge 或真 provider id。  
3. **色气 BGM** → mood=`rnb`（禁 dark）；dark 仅 horror。听腻 → `--music-seed` 换 take。  
4. **SFX** → 默认 auto_sfx；手写 `sfx_accent` 会真叠 bed；关：`auto_sfx: false`。  
5. **侧链** → rnb 默认长 release；可 `sound_plan.sidechain` 或 `--sidechain-release`。  
6. **响度** → 默认 loudnorm auto；status 看 `audio.loudness`。  
7. **本地曲** → 放 `audio/bgm.wav` + `*.license.txt`；`--music-template off` 强制程序化。  
8. **设计后期** → 默认 HF；`final --post-engine remotion [--npm-install]`；**不能**替代 I2V；成片音轨 **mux mixed.wav**。  
9. **预览** → `compose-preview` 写回执；`--require-preview` 可强制。  
10. **交付** → 技术 final ≠ 完成；必须 `review-final` 七维。  
11. **转场没新意** → 写 `transition_intents` + `transition_styles`，**只 re-final**。  
12. **运镜没新意** → 改 `dsl.motion` 主轴后 **requeue I2V**（只改 spec 不会变像素）。

## 目录约定（音）

```
<root>/audio/
  bgm.wav | music.mp3          # Phase H 优先
  templates/rnb.wav
  templates/default.wav
  *.license.txt
  mix_report.json              # mood / sfx / sidechain / loudness / music_template
  mixed.wav / narration.wav / bgm_*.wav
```

## status 该看什么

```text
audio.tts_backend          # 期望 edge（说书）
audio.sound_plan_mood      # rnb
audio.sidechain            # release_ms ~720
audio.loudness             # integrated_lufs ~-16
audio.loudnorm_applied     # auto 是否动过刀
audio.local_music_available
compose.preview_receipt
compose.remotion.ready
```

## 测试（收工前回归）

```bash
cd ~/.grok/skills/ai-film-grok
python3 -m pytest \
  tests/test_music_template.py \
  tests/test_loudnorm_policy.py \
  tests/test_sfx_accent.py \
  tests/test_sidechain_and_tts_gate.py \
  tests/test_phase_f_audio_status.py \
  tests/test_export_composition.py \
  tests/test_compose_preview.py \
  tests/test_compose_render.py \
  -q
```

## 备份位置

`~/.grok/skills/ai-film-grok/backups/2026-07-20-*`  
（remotion-hf / compose-preset / compose-preview-gate / remotion-npm / audio-sfx / audio-phase-e / phase-f / phase-g-loudnorm / phase-h-music-template）

## 未做 / 下次

- 商用曲库托管（故意不做；只接本地许可文件）  
- loudnorm 双 pass 测量更准（当前单 pass 够 shortform）  
- VO 句间自动 spot duck 与 TTS 静音对齐（可 Phase I）  
- media-use 自动拉 BGM（禁止覆盖 rnb/声线锁）

## 相关文档

- [postproduction.md](postproduction.md) — 听感与 final  
- [post-compose.md](post-compose.md) — HF/Remotion  
- [voices.md](voices.md) — TTS  
- [SKILL.md](../SKILL.md) — 总入口  
