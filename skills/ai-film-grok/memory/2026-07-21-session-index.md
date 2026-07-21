# Memory · 2026-07-21 索引

Agent 开新片先扫本页 + [2026-07-20-session-index](2026-07-20-session-index.md)。

| 主题 | 记忆 / 课 | 要点 |
|------|-----------|------|
| 四层流水线主脊 | [pipeline-methodology](../references/pipeline-methodology.md) | Agent→视觉→语音→HF→FFmpeg |
| 生成式电影工序 | [generative-film-craft](../references/generative-film-craft.md) | Beat/Coverage/五锁 |
| FRW key 能力 | [frw-key-capability](../references/lessons-2026-07-21-frw-key-capability.md) · [frw-degrade-dispatch](../references/frw-degrade-dispatch.md) | **403≠502**；canary 回执 |
| 发色硬锁 | [hair-color-lock](../references/lessons-2026-07-21-hair-color-lock.md) | cast_locks + NEVER 禁色 |
| **capability 一页** | `aifilm capability` | TTS/BGM/lipsync/FRW；`--suggest-i2v` / `--apply` |
| **Grok Build / SDK** | [grok-build-sdk](../references/grok-build-sdk.md) | 推理·Imagine·Tools·记忆；会话优先原生工具 |
| **Grok OAuth** | [grok-oauth](../references/grok-oauth.md) | `grok login` → auth.json；`aifilm grok-oauth doctor` |
| **FRW LTX 环境床** | [ltx-env-plate](../references/ltx-env-plate.md) | `ltx-t2v` 文生视频 completed；`aifilm env-plate` |
| **工序八环** | [craft-spine](../references/craft-spine.md) | Idea→Verified · `aifilm craft` |
| **音频三阶梯** | [audio-fallback](../references/audio-fallback.md) | edge/Voicebox · BGM 库 · lipsync canary |
| **TTS 默认 vs 兜底** | [voices](../references/voices.md) | edge 默认；Voicebox 质量+opt-in FALLBACK；`tts-ab` |
| **BGM 抗重复 / 纯乐器** | [bgm-generation](../references/bgm-generation.md) · [bgm-anti-repeat](2026-07-21-bgm-anti-repeat.md) | 池≥3 纯乐器听感兜底；程序 v3 硬兜底；HeartMuLa 不当 BGM |
| **声轨自适应** | [audio-recipe](../references/audio-recipe.md) | audio_policy + 每镜 recipe；默认不自动唱 |

## 开场（自动调配）

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"
"$AIFILM" doctor
"$AIFILM" dispatch --root "<film>"   # 主入口：craft+机位+next_cmd
# 做完 next_cmd 再 dispatch，循环到 verified
```

## 硬默认（07-21 补）

```text
Craft:     Idea→Story→Beats→Shots→Media→Selects→Rough→Verified
Grok Build: 推理+Imagine 原生；OAuth auth.json
I2V:       grok_primary（Seedance 关）→ image_to_video bulk；恢复 seedance_first
TTS:       edge 默认；voicebox 质量/FALLBACK
BGM:       纯乐器池 seed 轮换 → 程序 v3 multi-style（硬兜底）
Audio:     audio_policy + audio_recipe（write-spec）
Lipsync:   默认 off
发色:      P1 hard
runtime:   改 scripts 后 lock-runtime
```
