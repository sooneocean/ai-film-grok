# Memory · 2026-07-24 索引

Agent 开新片 / 改声线 / 出 final 前扫本页 + [2026-07-21-session-index](2026-07-21-session-index.md)。

| 主题 | 记忆 / 课 | 要点 |
|------|-----------|------|
| **声线分轨·禁中日乱切（P0）** | [ep2-voice-heat-final](2026-07-24-ep2-voice-heat-final.md) · [lesson](../references/lessons-2026-07-24-ep2-voice-heat-final.md) | 口白中文 · 角色日文 · 字幕中文 · 成块切换勿乒乓 · 禁赶片清 nar_ja |
| 人物对白日文（基线） | [character-dialogue-ja](2026-07-23-character-dialogue-ja.md) | Nanami/Keita；旁白 zh；字幕 zh |
| final SRT 重叠 | 同上 lesson §final | `sub_lead=0` + cue 钳制 |
| final 超时 | 同上 | 长片直调 `render_final.py`，勿 900s wrapper |
| review≠approved | 同上 | register-clip + sha 匹配 |
| 肉戏强度 / 审核 | 同上 · [sex-hard-floors](2026-07-21-sex-hard-floors.md) | I2V 高动态 edge；禁 genital 硬词；不降 heat_scale |
| 字幕硬烧 | [subs-always-burn](../references/lessons-2026-07-23-subs-always-burn-hard.md) | 像素内中文 |
| BGM rnb | [bgm-anti-repeat](2026-07-21-bgm-anti-repeat.md) | 色气 rnb 非 dark |
| **高动态常态 + 画风锁（P0 · 07-27）** | [2026-07-27-high-motion-style-final](2026-07-27-high-motion-style-final.md) · [lesson](../references/lessons-2026-07-27-high-motion-style-lock-final.md) | 平常≥18 肉戏≥20；MEDIUM LOCK cel；gate 才桌面；禁弱 raw/KB；禁高动漂半写实 |

## 开 final 前 10 秒

```text
1. 打印 speaker|voice|spoken_lang 表 → 检查禁乒乓
2. write-spec 绿
3. clips all approved + review sha match
4. render_final sub_lead=0 → burn_srt_pil 中文
5. 抽帧有中字 + 抽声角色日文/说书中文
6. i2v motion audit 平常≥18 肉戏≥20；style audit 无半写实漂移；gate ok 才桌面
```
