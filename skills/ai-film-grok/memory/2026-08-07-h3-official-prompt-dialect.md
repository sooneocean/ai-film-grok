# H3 官方 prompt 方言（2026-08-07）

## 原话

> 依照两份官方文件要求帮我优化代码 · 再进行一轮升级迭代

## 三句

1. 官方 base 三字段 + Ref2VA 六段已编译；T2VA **禁**误写 Picture1；official 禁 2V stage。  
2. **默认 auto**：对白/R2V/多 ref→official；high→legacy（`AIFILM_H3_HIGH_MOTION_OFFICIAL=1` 可翻）。  
3. R5：combo official families + plan `prompt_preview`；真烧 canary 仍待 5090。

## 清单

- [x] 编译器 + vendor pin + validate  
- [x] densify + run receipt + plan preview  
- [x] combo R5 official families  
- [x] onscreen text + scenetrans  
- [ ] 高动二次 canary → 是否默认翻 official  

## 链

- 优化板：`docs/plans/2026-08-07-h3-official-prompt-optimize-todoplan.md`  
- canary：`artifacts/2026-08-07-h3-official-ab-canary.json`  
