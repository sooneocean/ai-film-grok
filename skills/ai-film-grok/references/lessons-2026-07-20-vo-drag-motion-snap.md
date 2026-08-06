# 旁白不拖腔 · 动态有速度感（星声·谢幕后）

> 2026-07-20 · 片源：`astra-private-encore-60s`《星声·谢幕后》  
> 用户反馈：**「语音太卡」「动态速度感太差」** → 声画双改后通过  
> 映射：**P2 时空连续（时间轴真相）** · **P3 动能连续** · **P4 语义绑定**

## 失败现场

| 现象 | 根因 | 错误「救法」 |
|---|---|---|
| 旁白拖腔、发腻、「卡」 | `visual_fit: slot` + 短 `nar`（VO≈3.5–5s）硬贴 6s plate → **atempo 0.67–0.88 拉慢语速**；再叠 `vo_rate: -3%` | 再降 rate / 再拉长 plate |
| 动态慢、像定妆微动 | I2V prompt 只有 soft lean / breath / blink；motion_score 低（≈3–4） | 只 re-final 不 re-I2V |
| 想硬凑满 60s | 用 slot 垫静音或拖腔 | 加镜 / 加字，而不是拖语音 |

## 正确做法

### A. 语音（防拖腔）

1. **禁止**为填满 plate 把旁白 atempo 降到 **&lt; 0.92**（代码 `pad_natural` / drag guard）。  
2. 短 VO + 长 plate：  
   - **优先** `visual_fit: "vo"`（说书短片默认体感）→ 语速自然、节奏紧、总片略短于「镜数×6」。  
   - 或 **加长 nar / 加镜** 真满 60s。  
   - slot 路径：代码 **静音 pad**，不拖腔（可能死气，preflight soft `VO_DRAG_OR_DEAD_AIR`）。  
3. TTS：默认 `vo_rate: "+0%"`；色气快节奏可用 **`+5%`～`+8%`**；**禁止**「-3% + 重度 atempo 拉慢」叠用。  
4. `vo_gain` 默认约 **1.32**；侧链可略紧（rnb threshold≈0.06）让人声贴前。

### B. 动态（速度感）

1. I2V motion **主动词要狠**：`snap / yank / clamp / shrug hard / decisive / rhythmic pulse` —— 禁止整片 `soft lean + blink + breath`。  
2. motion QA 低（&lt;5）的镜：**必须 re-I2V**，只 re-final 无效。  
3. `visual_fit: vo` 时 plate 跟 VO 压缩 → 画面略加速，常有利于「速度感」（与自然语速同向）。  
4. 主动作仍绑定 `nar`/`action`（P4）；狠动词 ≠ 乱加 mouth-speaking。

### C. 满 60s 的合法路径

| 合法 | 非法 |
|---|---|
| 加镜（+2～3 个 beat） | atempo≪1 拖旁白 |
| 每镜 nar 加到实测 ≈ plate±0.5s | 长 dissolve / 冻帧凑时长 |
| `visual_fit: vo` 接受 ~45–55s 完播优先 | 声称 60s 却只有拖腔 |

## 代码与门禁

| 位置 | 行为 |
|---|---|
| `scripts/vo_atempo.py` | `DEFAULT_MIN_NATURAL_ATEMPO=0.92`；`mode=pad_natural` + `drag_guard` |
| `scripts/preflight.py` | soft `VO_DRAG_OR_DEAD_AIR`（slot + vo/plate&lt;0.92） |
| `scripts/render_final.py` | 默认 `vo_rate=+0%`、`vo_gain=1.32` |
| `tests/test_vo_atempo.py` | pad_natural / mild slow / opt-in drag |

应急：`plan_vo_atempo(..., allow_speech_drag=True)` 或旧片显式需要拖腔时再开（默认关）。

## Agent 决策树

```text
用户要 60s 说书短片
  ├─ 口白已满（每镜实测 ≈ duration_sec）→ slot 或 vo 皆可
  ├─ 口白偏短 + 要听感利落 → visual_fit: vo + vo_rate +5%~+8% + 强 motion re-I2V
  └─ 口白偏短 + 硬要 60s → 加镜/加字；禁止拖腔凑秒
用户说「语音卡 / 拖」
  → 查 final log 是否 atempo&lt;0.92 或 vo_rate 负；改 vo 路径 + re-final
用户说「动态慢」
  → 查 motion_score；重写 motion 主动词 + re-I2V + re-final
```

## 相关

- [lessons-2026-07-20-vo-atempo-three-axis.md](lessons-2026-07-20-vo-atempo-three-axis.md)（三轴；本课补 drag 下限）  
- [lessons-2026-07-20-meaningful-motion.md](lessons-2026-07-20-meaningful-motion.md) · [shot-motion.md](shot-motion.md)  
- [lessons-2026-07-17-vo-motion-link.md](lessons-2026-07-17-vo-motion-link.md)  
- [ecchi-story.md](ecchi-story.md)（色气审核：荤在 VO，画面可软）
