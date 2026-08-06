# Memory · 2026-07-21 索引

Agent 开新片先扫本页 + [2026-07-20-session-index](2026-07-20-session-index.md) + **[2026-07-24-session-index](2026-07-24-session-index.md)**（声线分轨 / final 坑）。

| 主题 | 记忆 / 课 | 要点 |
|------|-----------|------|
| **口白中文·角色日文·禁乱切（P0）** | [2026-07-24-ep2-voice-heat-final](2026-07-24-ep2-voice-heat-final.md) | 成块切换；说书禁 nar_ja；sub_lead=0；长片直调 render_final |
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
| **成人办事三条硬底** | [sex-hard-floors](2026-07-21-sex-hard-floors.md) | 性爱时长≥20% · 卸甲脱衣 · 旁白荤梗 |
| 性爱时长 | [sex-duration-floor](../references/lessons-2026-07-21-sex-duration-floor.md) | act+climax duration 加权；`sex_floor_strict` |
| 办事卸甲 | [sex-undress-ladder](../references/lessons-2026-07-21-sex-undress-ladder.md) | full→undressed/bare；禁铠甲完整跨坐 |
| **卸装延续·不回穿** | 同上 · v1.4.2 | rank 单调；`apply_wardrobe_continuity`；`HEAT_WARDROBE_RE_DRESS` hard |
| 旁白荤梗 | [sex-vo-spice](../references/lessons-2026-07-21-sex-vo-spice.md) | 每镜 nar 荤梗；act 办事动词；`sex_vo_strict` |
| **声线默认 nar+BGM** | [voice-tracks](../references/voice-tracks.md) · v1.4.1 | `vocal_color` 娇喘轨默认关；成片旁白主导 |

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
成人max:   性爱时长≥20% + 卸甲脱衣(延续不回穿) + 旁白荤梗（三条 write-spec 默认 hard）
声线:      nar + BGM 主导；vocal_color 默认关（opt-in）
plugin:    ≥1.4.2（1.4.1 声线 / 1.4.2 卸装延续）
```
- [2026-07-21-continuity-strategy.md] 首尾幀與連貫性優化策略 (Intra-scene continue, Inter-scene cut)
- [2026-07-21-extreme-spice-strategy.md] 極限葷梗與大尺度敘事策略 (Hyper-sexualized premises, explicit VO, explicit action)

## 本会话交付（van / Astra）

- 成片桌面：`后座夜_旁白BGM.mp4`（~49.7s，无娇喘轨）
- film root：`~/AI FILM SPACE/0721/astra-van-nighthaul`
