# Memory · 2026-08-04 · H3 FLF + multi-ref 全链路

**矩阵**：[weapon-lane-matrix](../references/weapon-lane-matrix.md)

## 用户原话
> h3 i2v 优化为可以用 first/last frames…多利用 refer and image input  
> 计划里的后续推进到最后再 commit and push 收工

## 三句话
1. **FLF**：有 `stills/<id>_end.png` 或 `--last-frame` → `mode=flf`（同 I2V 武器 + last_frame）。
2. **媒体包**：first/last + cast bible identity refs 自动进 plan；缺 last 有 `missing_last_hint`。
3. **R2V multi-ref**：最多 2 额外槽（21/22）+ `<Picture n>` 职责；promote `--as end` 产 end still。

## CLI
```bash
aifilm h3 plan --root "$ROOT" --shot-id s01
aifilm h3 run  --root "$ROOT" --shot-id s01 --mode flf --last-frame stills/s01_end.png --register
aifilm still-challenge promote --root "$ROOT" --shot-id s01 --as end \
  --identity-approved --anatomy-safe --review-note "end pose"
aifilm h3 run --root "$ROOT" --shot-id s01 --mode r2v --ref cast/hero.png --register
```

## Phase 0
`artifacts/5090-evaluation/h3-flf-ab-scaffold/` — GPU 忙时挂起；空闲按 README 跑 I2V vs FLF A/B。
