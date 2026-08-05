# Memory · 2026-08-05 · Material Fidelity Loop

## 用户原话
> 分析 codebase … 让生成模型使用生成素材资源 … 质量更高 … todo plan

## 三句话
1. 瓶颈是**领料不统一**，不是再加门禁：StillSource + GenerationRequest。
2. peak 镜禁 full cast master 当 I2V 首帧；h3 plan 写 `receipts/prompts/<id>.request.json`。
3. queue 有回执则校验 first-input sha；逃生 `AIFILM_SKIP_GENERATION_REQUEST=1`。

## 检查清单
- [x] M0 文档（谁喂谁 + 命名表）
- [x] still_source + 测
- [x] generation_request + h3 plan + queue
- [ ] M3–M6 backlog

## 链
- `scripts/still_source.py` · `generation_request.py`
- `references/material-fidelity-loop.md` · `docs/plans/2026-08-05-material-fidelity-loop.md`
