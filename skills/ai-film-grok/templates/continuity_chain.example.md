# Continuity Chain — {{TITLE}}

> 本文件是长片动作串接的**唯一清单**。continue 缝：下镜首帧 SHA 必须等于上镜已核准末帧 SHA。  
> 规则见 skill `references/continuity_chain.md`。

- **film root**: `{{ROOT}}`
- **updated**: {{DATE}}
- **long_form**: true
- **shot_count**: {{N}}

## 动作脊柱（一句话）

{{SPINE}}

## 全局轴线 / 天气 / 主光

| 项 | 锁定值 |
|---|---|
| 屏幕主行进方向 | e.g. left→right / into depth |
| 180° 轴线 | e.g. character screen-left of door |
| 天气 | e.g. clear night / light rain |
| 主光 | e.g. warm vanity key + cool corridor rim |

## 连接点

对每个 **continue** 缝复制一表；**cut** 缝只写理由 + join=hard。

### Join: shot01 → shot02

| 字段 | 值 |
|---|---|
| chain_mode | continue |
| last_frame path | `clips/shot01.mp4` → extract last |
| last_frame sha256 | _fill after register-clip_ |
| first_frame path | `keyframes/shot02.png` |
| first_frame sha256 | _must equal last_ |
| byte_identical | YES / NO |

**九项核对**（全部 pass 才 I2V 下镜）：

| # | 维度 | pass/fail | 备注 |
|---|---|---|---|
| 1 | 姿势 pose | | |
| 2 | 视线 gaze | | |
| 3 | 手与道具归属 hands_props | | |
| 4 | 行进方向 travel | | |
| 5 | 镜头轴线 axis | | |
| 6 | 发型 hair | | |
| 7 | 服装 wardrobe | | |
| 8 | 天气 weather | | |
| 9 | 光线 lighting | | |

**禁止掩盖**：未使用加长 dissolve / 定格 / 倒放 / 无关插镜挡跳切。□ 确认

### Join: shot02 → shot03

（同上表复制）

## Cut 缝（故意断开）

| from → to | 叙事理由 | transition |
|---|---|---|
| e.g. shot03→shot04 | 时间跳跃 / 主观闪回 | hard |

## 生成顺序（打勾）

- [ ] continuity_chain.md 已写脊柱 + 全部 join 表头
- [ ] 仅链首（或 cut 后首镜）从 cast 起 still
- [ ] 每 continue 缝：`extract-frame --promote-keyframe` 后再 I2V
- [ ] `aifilm continuity-chain check --root .` 通过
- [ ] final 前未用后期掩盖断裂
