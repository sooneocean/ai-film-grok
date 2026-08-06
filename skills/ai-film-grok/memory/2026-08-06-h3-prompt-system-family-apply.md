# Memory · 2026-08-06 · H3 prompt 系统设定接线（family → 生产）

**计划**：session plan `h3 prompt logic` · 审计 `docs/plans/2026-08-06-h3-prompt-system-audit.md`  
**registry**：`h3-combo-winners.json` · `h3-prompt-system.json`

## 用户原话
> 思考如何因为你跑的参数经验 导致你后面生成效果变更好 开始规划如何测试优化h3 prompt logic in system setting

## 三句话
1. **断点**：winners 的 `prompt_family` 以前只写 plan 标注，**不进** `_prompt_for_shot` 编译。
2. **已修（2.39.89）**：5090 `h3_primary`/`hybrid_h3` 默认 **补洞**应用 family DSL；系统句进 `h3-prompt-system.json`；关：`AIFILM_H3_FAMILY_APPLY=0`。
3. **下一步**：5090 idle 跑 R5 combo-eval（soft 微动 / 高动段数 / 嘴型）→ 写 winners → 真片 2 镜 canary。

## 检查清单
- [x] family apply + 单测
- [x] 系统句表 + spine 读表
- [x] dialogue winner.family 对齐 max
- [ ] R5 GPU 矩阵（idle）
- [ ] 真片 soft+meat canary

## 链
- lesson h3-max · weapon-lane · combo-eval CLI
