# H3 官方 prompt 方言（2026-08-07）

## 原话

> 做 P3.5 真烧 canary

## 三句

1. P3.5 seed 202608074 **6/6 真烧 DONE**；high official mean 28.9 > legacy 26.9（早轮 live 实测 mean 24.86 > legacy 20.67）。
2. **auto 默认 high→official** densify；逃生 `AIFILM_H3_HIGH_MOTION_OFFICIAL=0`（可退 legacy）。
3. 对白/软 mean 仍偏 legacy，但结构保 official（`<d>`/三字段）；口型须人审。

## 清单

- [x] live + P3.5 镜 reburn + score
- [x] high auto 翻 official
- [x] 证据 JSON
- [ ] 对白口型人审 shortlist / 画质人审

## 链

- `artifacts/2026-08-07-h3-official-p35-canary.json` · `2026-08-07-h3-official-live-canary.json`
- eval：`artifacts/5090-evaluation/h3-official-ab-20260807/`
- plan：`docs/plans/2026-08-07-h3-official-prompt-optimize-todoplan.md`