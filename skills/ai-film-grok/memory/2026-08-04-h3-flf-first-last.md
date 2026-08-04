# Memory · 2026-08-04 · H3 first/last 全面主链

**矩阵**：[weapon-lane-matrix](../references/weapon-lane-matrix.md)

## 用户原话
> 我项目当中使用 h3 的 i2v r2v 全面升级为 first frames last frames 的 input 逻辑让生成的质量大幅度提高

## 三句话
1. **有 end still → FLF 主轨**（I2V 武器 + `last_frame`）；能量/对白 CU 只作 `alt_mode=r2v`。
2. **R2V 也吃 first/last**：first=主 still；last 优先 pose land ref + land prompt（`force_r2v` 仍走 R2V）。
3. **Fill-Idle 接 FLF**：`has_last` 进选型；dual 认 flf；command 带 `--last-frame`。

## CLI
```bash
aifilm h3 plan --root "$ROOT" --shot-id s01
aifilm h3 run  --root "$ROOT" --shot-id s01 --mode flf --last-frame stills/s01_end.png --register
aifilm still-challenge promote --root "$ROOT" --shot-id s01 --as end \
  --identity-approved --anatomy-safe --review-note "end pose"
# 强制能量：仍可 R2V，last 作 pose ref
aifilm h3 run --root "$ROOT" --shot-id s01 --mode r2v --last-frame stills/s01_end.png --register
```

## 逃生
- 单首帧：`force_i2v_single` / `h3_prefer=i2v`
- 强制 R2V：`force_r2v` / `h3_prefer=r2v`（不因 last 升 FLF）
