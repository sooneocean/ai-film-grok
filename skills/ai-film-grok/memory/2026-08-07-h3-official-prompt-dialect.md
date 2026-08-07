# H3 官方 prompt 方言（2026-08-07）

## 原话

> go next round and commit and push

## 三句

1. 官方 base 三字段 + Ref2VA 六段已对齐 GUIDE；T2VA 禁 Picture1；official 禁 2V/legacy 尾缀。  
2. **默认 auto**：对白→official；high→legacy（O3 mean）；其余 official。  
3. **P2**：media_pack 多 ref 写进 definitions/retention；detailed densify；二次 canary 仍待 idle。

## 清单

- [x] 编译器 + workflow fail-closed  
- [x] P0+P1 GUIDE 对齐（2.40.86）  
- [x] P2 multi-ref + densify（2.40.89）  
- [ ] P3 同 seed 二次 canary → 是否翻 high auto  
- [ ] 默认全 official（人审口型后）

## 链

- 优化板：`docs/plans/2026-08-07-h3-official-prompt-optimize-todoplan.md`  
- canary：`artifacts/2026-08-07-h3-official-ab-canary.json`  
