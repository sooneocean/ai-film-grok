# Memory · 镜头分型生成线（2026-08-07）

> **用户：** 分析链路各种镜头（对白镜、毒镜）· 依序优化生成逻辑  
> **板：** [shot-generation-lane-todoplan](../../../docs/plans/2026-08-07-shot-generation-lane-todoplan.md) · **2.40.56** Wave 0–4

## 三句

1. **先分型再烧：** `aifilm shot-lane --root` → lane + mode + gates。  
2. **毒镜 / 满幅 / variety：** poison 禁 I2V；首帧≥~75%；bulk variety 硬门；肉戏 insert 禁 silent T2V。  
3. **对白：** still=speaker 脸 MCU · prompt 禁 no speech · `dialogue_audio_lane` XOR · cut_on mid_motion/vo。

## 清单

- [x] `shot_lane.resolve` + CLI  
- [x] poison 与 fill-idle 对齐  
- [x] Wave 2 对白全链  
- [x] Wave 3 composition_fill 闭环  
- [x] Wave 4 variety + insert  
- [ ] Wave 5–6 见 plan  

## 链

- [visual 分型](../references/stages/visual.md) · [weapon-lane](../references/weapon-lane-matrix.md) · [毒镜](2026-07-29-poison-shot-anatomy-iron.md)
