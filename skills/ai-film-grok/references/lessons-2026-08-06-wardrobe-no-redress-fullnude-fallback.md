# Lesson · 卸装不回穿 + 尺度兜底阶梯（勿硬上防崩）（2026-08-06）

## 背景

`suse-evolution-ep01` 用户复盘三句：

1. 衣服脱了又出现 → **逻辑不对，不回穿**  
2. 大尺度做不到 → **全裸诱惑**  
3. **全裸诱惑 MAX 也做不到 → 以模型极限就好，不要硬上，否则画面崩坏**

本课把三条钉成 **P0 产品阶梯**，禁止「假办事」与「硬冲 bare 把画面冲烂」。

## 规则 A · 衣服不回穿（HARD）

类比：卸甲后不能又穿回盔甲再打。

1. **rank 单调不降**：dressed → partial → undressed → bare，只升不降。  
2. **后镜继承**：`start_pose` / `wardrobe_state` 从上一镜 **已脱** 开场。  
3. **still 源**：peak 后 sole-ref = undress-anchor 或 bare 状态照，禁止全装 cast master。  
4. **I2V 首帧**锁衣着；**末帧**过不回穿门；毒末帧禁 promote。  

码：`HEAT_WARDROBE_RE_DRESS` · `HEAT_WARDROBE_TEXT_CONFLICT` · promote rank 硬拦。

## 规则 B · 大尺度做不到 → 全裸诱惑

类比：正餐做不出来就上最高档冷盘，**不许端半生的假牛排**。

| 情况 | 正确 | 错误 |
|------|------|------|
| 拦插入/结合 | bare 诱惑：pose·距离·感官；**PARTIAL** | 内衣/半脱假插入装绿 |
| 合拍失败 | 保持已脱；改角度再挑战 | 穿回衣 |

## 规则 C · 全裸诱惑也做不到 → 模型极限（HARD 防崩）

类比：厨房炉子只能烧到某温度——**不要把火拧爆把锅烧穿**。

| 信号 | 正确 | 错误 |
|------|------|------|
| 供应商/模型硬拦 bare | 用 **该模型能稳出的最高色气**（侧影、遮挡、implied bare、undressed 极致） | 连刷 bare 词硬上 |
| 连出崩坏/畸形/毒镜 | **立刻停**；降构图难度；换可画方案；记 PARTIAL | 同一失败 take 硬 promote |
| 「名义 MAX」vs「可看稳帧」 | **稳帧优先**；delivery 写清实际档 | 为标签牺牲画面 |

**尺度意图仍 MAX**，但 **交付以可看为准**：能到 bare 到 bare；不能则模型极限 + 诚实 PARTIAL，**永不硬上致崩**。

与毒镜 IRON 同向：崩坏/畸形镜禁 register / I2V / final。

## Agent 裁决卡

```text
IF 上一镜已 undressed|bare:
  禁止下一镜 dressed / 整穿已脱衣
IF 真办事/结合做不到:
  TRY 全裸诱惑 MAX + PARTIAL
IF bare 也拦 / 出崩 / 畸形:
  DO 模型极限内最高可画色气（稳帧）
  DON'T 硬 prompt 冲 bare/结合
  DON'T 假办事 / 回穿 / 毒镜 promote
  LABEL delivery PARTIAL + 实际 wardrobe 档
```

## 检查清单（出片前）

- [ ] wardrobe rank 无下降  
- [ ] 无末帧回穿 promote  
- [ ] 无「脱后又穿」像素  
- [ ] 无真 coitus 时：tempt 或模型极限链 + PARTIAL  
- [ ] **无硬上崩坏 take 装片**  

## 链

- memory：`memory/2026-08-06-wardrobe-no-redress-fullnude-fallback.md`  
- hard-defaults：不回穿 · 全裸诱惑 · **模型极限勿硬上**  
- 旧课：wardrobe-no-redress-still · i2v-endframe-no-redress · adult-scale-max · poison-shot-anatomy  
