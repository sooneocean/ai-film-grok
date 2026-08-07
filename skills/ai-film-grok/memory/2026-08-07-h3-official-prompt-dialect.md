# H3 官方 prompt 方言（2026-08-07）

## 原话

> 依照两份官方文件要求帮我优化代码 · 提出优化 todo plan

## 三句

1. 官方 base 三字段 + Ref2VA 六段已编译；T2VA **禁**误写 Picture1；official 禁 2V stage / legacy 尾缀。  
2. **默认 auto**：对白→official；high→legacy（O3 mean）；其余 official。  
3. 优化板 P0+P1 已合；二次 canary / 默认全 official 仍待人审。

## 清单

- [x] 编译器 `h3_official_prompt` + vendor pin  
- [x] T2VA / FL2VA / L2VA / I2VA / Ref2VA 结构 + validate  
- [x] workflow dialect + official fail-closed  
- [ ] 高动二次 canary → 是否翻 auto  
- [ ] Ref2VA 350–500 词密度

## 链

- 优化板：`docs/plans/2026-08-07-h3-official-prompt-optimize-todoplan.md`  
- import 基线：`docs/plans/2026-08-07-h3-official-prompt-import-todoplan.md`  
- canary：`artifacts/2026-08-07-h3-official-ab-canary.json`  
- HF base/ref：MiniMax-H3 VIDEO_PROMPT_WRITING_GUIDE_{base,ref}_en.md  
