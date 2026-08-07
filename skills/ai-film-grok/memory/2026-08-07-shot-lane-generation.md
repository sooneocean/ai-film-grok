# Memory · 镜头分型生成线（2026-08-07）

> **用户：** 分析链路各种镜头（对白镜、毒镜）· 依序优化生成逻辑  
> **板：** [shot-generation-lane-todoplan](../../../docs/plans/2026-08-07-shot-generation-lane-todoplan.md) · **2.40.60** Wave 0–6 **DONE**  
> **Canary：** [artifacts/2026-08-07-shot-lane-canary.json](../../../artifacts/2026-08-07-shot-lane-canary.json)

## 三句

1. **先分型再烧：** `aifilm shot-lane --root` → lane + mode + gates。  
2. **毒 / 满幅 / variety / 续镜：** poison 禁 I2V；首帧≥~75%；bulk variety；insert 禁 silent T2V；**毒/回穿 endframe 禁 continue 种子**。  
3. **对白：** still=speaker 脸 MCU · prompt 禁 no speech · `dialogue_audio_lane` XOR · cut_on mid_motion/vo。

## 清单

- [x] `shot_lane.resolve` + CLI  
- [x] poison 与 fill-idle 对齐  
- [x] Wave 2 对白全链  
- [x] Wave 3 composition_fill 闭环  
- [x] Wave 4 variety + insert  
- [x] Wave 5 continue + env  
- [x] Wave 6 canary 8 镜类 + 日课 T3 交叉

## 链

- [visual 分型](../references/stages/visual.md) · [weapon-lane](../references/weapon-lane-matrix.md) · [毒镜](2026-07-29-poison-shot-anatomy-iron.md)
