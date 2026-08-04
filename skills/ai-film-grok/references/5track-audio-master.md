# 5-Track 影院级混音主轨架构（2026-08-04）

> **目标架构（Target architecture · 2026-08-04）**  
> 下列 DX/FX/BG/MX/SUB 轨定义与响度目标为产品方向。  
> **当前真路径**：`aifilm final` 的 VO+BGM sidechain + 可选 post-audit 响度检查（**尚无** `aifilm audio mix --tracks …` 全轨 CLI）。  
> Delivery Truth 2.36.4 先保证运动/零旁白门诚实；5-Track 硬接线另开 sprint。

## 一、5 轨定义

```text
Track 1 DX  — Dialogue & VO
Track 2 FX  — Spot Foley & Impact Effects
Track 3 BG  — Ambience & Room Tone (Continuous Bed)
Track 4 MX  — Music / Score (Auto-Ducked)
Track 5 SUB — LFE Sub-bass Pulse (Dramatic Beats)
```

| 轨道 | 职责 | 规格 | 禁止 |
|---|---|---|---|
| **DX** | 角色对白、TTS 配音 | 居中声道 (C)；峰值不超 -3dBFS；整体 -16 LUFS ±1.5dB | 旁白与对白混入同轨无分离 |
| **FX** | Foley（服装摩擦、脚步、道具碰撞）、点缀音效 | 立体声 L/R 空间定位；单次不超 -6dBFS | 超过 -3dBFS 爆音、过度密集 |
| **BG** | 场景环境底噪（Room Tone / 雨声 / 风声 / 人群底噪）| 低电平持续立体声；-30 至 -24dBFS；**禁止连续静音 >200ms** | 零值段切断（BG 轨全片贯穿） |
| **MX** | BGM / Score | 默认 rnb；DX 出现自动 sidechain -4dB~-6dB；DX 结束 200ms 内恢复 | 过于响亮盖过 DX；BGM 直接硬切 |
| **SUB** | LFE 低频脉冲（地鸣感）| 仅在剧情转折/高潮拍点状触发；≤80Hz；peak ≤-6dBFS | 全片持续低频轰鸣 |

## 二、混音顺序

**已接线：**

```bash
aifilm final --root "$ROOT" --tts-backend edge --music-mood rnb --lipsync off
```

**规划中（下列 CLI 尚未实现，勿当 shipped）：**

```bash
# aifilm audio add-sfx / add-ambience / bgm --sidechain-dx / add-lfe
# aifilm audio mix --tracks dx,fx,bg,mx,sub --target-lufs -16
```

## 三、验收标准

| 检查项 | 通过标准 |
|---|---|
| 响度 | 整体 **-16 LUFS ±1.5dB**；peak ≤ -1dBTP |
| BG 连续性 | 全片 BG 轨任意 200ms 窗口内电平 > -50dBFS |
| DX 清晰度 | 对白信噪比 (SNR) ≥ 20dB；无爆音 (clipping) |
| MX Sidechain | DX 出现后 ≤50ms 内 MX 衰减到位 |
| FX 空间感 | 主要 Foley 点均有 L/R 定位差（非 mono 居中） |

## 四、与既有管线的关系

- 现有 `aifilm final --post-engine hyperframes` 走 `audio/mixed.wav`：**此文件由 5-Track 流程输出**，命名保持兼容。
- `sidechain 混音失败 → amix 降级 → PARTIAL receipt`（与 longform 规则一致）。
- BGM seed 锁定沿用 `audio_policy.music_seed`；rnb 库池兜底不变。
- Foley 自动 SFX 池：`assets/sfx/foley/`（cloth / footstep / door / breath）。

## 五、与 zero_narration_strict 的联动

启用 `zero_narration_strict:true` 时：
- DX 轨不会出现第三人称说书 TTS（旁白零预算）。
- BG 轨承担原来「旁白静默时的空气感」——**靠 Room Tone 而非旁白填充静音感**。
- FX 轨在旁白替代段（道具/Foley 叙事）自动强化事件点缀。
