# Memory · 2026-07-27 高动态常态 + 画风锁 + 交付（深入版）

**完整课**：[lessons-2026-07-27-high-motion-style-lock-final.md](../references/lessons-2026-07-27-high-motion-style-lock-final.md)（v2 四层漏斗 / 双闸 / 连戏决策树）

## 不可压缩结论

1. **生成成功 ≠ 可交付** —— 用户只看桌面成片像素。  
2. **Motion 与 Medium 正交** —— 两闸都过才装片。  
3. **库内 takes 是资产** —— 先 `argmax(mean|时长)` 再烧。  
4. **高动不得换画风** —— MEDIUM LOCK cel；style-relock 从 still 重跑。  
5. **连戏不得泄动态** —— chain 仅 mean≥旧×0.85 且 ≥肉戏门。  
6. **桌面只认 gate** —— `i2v-final-gate.json` ok。  
7. **vocal_color never**（本用户永久默认，除非显式恢复）。

## 数字

| tier | mean 硬底 |
|------|-----------|
| 平常 | ≥ 18 |
| 肉戏 | ≥ 20（目标 24） |
| 包络 1:00→尾 | ≥ 18 |

## 开 I2V / final 前 15 秒

```text
1. style-v1 在场；still medium 先验
2. prompt = MEDIUM LOCK + 高动动词
3. 串行 I2V；肉戏 6s×2 可选
4. pick max mean takes
5. audit + style 抽帧
6. package after_60
7. gate ok → 桌面；用户重开播放器
```

## 假绿警报

- 「24/24 ok」但桌面 mtime 旧  
- mean 用 2 当门  
- exports 有新片桌面仍是 nocolor/KB  
- 高动后半写实、脸模换人  
