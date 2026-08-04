# Memory · 2026-08-04 · H3 FLF 首尾帧

**矩阵**：[weapon-lane-matrix](../references/weapon-lane-matrix.md)

## 用户原话
> h3 i2v 优化为可以用 first frame and last frames 的参考图…多利用项目资源的 refer and image input

## 三句话
1. **H3 权重本就是 fl2va**；以前只接 first，现已可选 last_frame。
2. **有可信 end still 才 FLF**（`stills/<id>_end.png` / `--last-frame`）；禁 first 复制 last。
3. **续镜 ≠ FLF**：续镜=上镜 end→本镜 first；FLF=镜内 first→last；可组合。

## CLI
```bash
aifilm h3 plan --root "$ROOT" --shot-id s01 --last-frame stills/s01_end.png
aifilm h3 run  --root "$ROOT" --shot-id s01 --mode flf --last-frame stills/s01_end.png --register
```
