# Memory · 卸装不回穿 + 尺度兜底阶梯（P0 · 2026-08-06）

**片例**：`AI FILM SPACE/0805/suse-evolution-ep01`（宿色进化 EP01 正牌 final 链）  
**完整课**：[lessons-2026-08-06-wardrobe-no-redress-fullnude-fallback.md](../references/lessons-2026-08-06-wardrobe-no-redress-fullnude-fallback.md)

## 用户原话（圣旨级）

> 里面的衣服脱了又出现 这个逻辑不对 需要衣服不回穿  
> 然后大尺度如果做不到 直接做全裸诱惑就好  
> **全裸诱惑 MAX 如果做不到 以模型的极限就好 不要硬上 不然画面会崩坏**

## 三句话

1. **已脱不得回穿**：film-spec / still / I2V 首末帧 / promote，衣着 rank **只升不降**；脱后下一镜禁止整穿已脱衣物。
2. **尺度兜底阶梯**：真办事做不到 → 全裸诱惑 MAX；**全裸诱惑也做不到 → 模型安全极限内的最高可画**（半裸/侧影/遮挡诱惑等），诚实 PARTIAL。
3. **禁止硬上**：供应商/模型拦、连出崩坏/毒镜/畸形 → **停手换可画方案**，禁反复硬 prompt 冲 bare/结合导致画面崩。

## 一句话规则

> **衣服脱了就不能再穿回来；插不进就全裸诱惑；全裸也画崩就按模型极限能稳出的最色，不要硬上。**

## 裁决顺序（冲突时）

1. 不回穿（continuity HARD）  
2. 尺度 MAX（能真办事就真办事）  
3. **真办事做不到 → bare 诱惑 MAX**（禁止 clothed/underwear “假肉戏”）  
4. **bare 诱惑也做不到 / 出崩 → 模型极限内最高可画色气**（禁硬上）  
5. 画风 / 其它  

## 执行检查清单

| 层 | 做什么 | 禁止 |
|---|---|---|
| plan / film-spec | `wardrobe_state` 单调；act≥undressed；climax 目标 bare | 后镜 dressed 回退 |
| still | undress-anchor / bare state 源 | peak 后 image_edit 全装 cast |
| I2V | first-frame 锁已脱；register 前 last-frame 过 W8 | 末帧肩胸整穿已脱衣 |
| promote / dailies | 回穿 rank 硬拦；崩坏/毒镜拒 | 毒末帧装片 |
| 大尺度失败 | 先 bare tease + PARTIAL | 内裤/军裤/半脱当 penetration |
| bare 也失败/崩坏 | **降到模型能稳出的极限**；换角/遮挡/侧影/暗示；记 PARTIAL | 硬刷 bare 词导致崩坏/畸形仍 promote |

## 硬上禁令（防崩坏）

- 同一 take 连出解剖崩 / 肢体熔 / 毒镜 → **立刻停**，改可画构图，不「再加一倍 bare 词」  
- 交付须 **可看稳帧** 优先于名义 scale 标签  
- delivery 诚实：`PARTIAL` + 实际达到的 wardrobe 档（undressed / implied-bare / soft-max 等）

## 机读码（已有，必须当真）

- `HEAT_WARDROBE_RE_DRESS` / `HEAT_WARDROBE_TEXT_CONFLICT`  
- `HEAT_SEX_WARDROBE_*` / `HEAT_BARE_PEAK_MISSING`  
- promote 回穿 rank 硬拦（Wave 2）  
- still_source_strict · i2v-endframe-no-redress  
- 毒镜解剖 IRON（崩坏/畸形禁 register）

## 与旧记忆叠乘

- [core-adult-iron](2026-07-27-core-adult-iron-shipped.md) · [adult-scale-max](2026-07-27-adult-scale-max-sex-arc.md)  
- hard-defaults：**卸装不回穿** · **全裸诱惑兜底** · **模型极限勿硬上** · 毒镜 IRON  
- lessons：wardrobe-no-redress-still · i2v-endframe-no-redress  

## 本片触发

宿色 EP01：用户先钉不回穿 + 全裸诱惑；再钉 **全裸也做不到勿硬上、按模型极限防崩坏**。此后 agent 默认按本卡阶梯裁决。
