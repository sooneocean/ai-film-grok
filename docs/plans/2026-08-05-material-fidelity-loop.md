# Material Fidelity Loop — 2026-08-05

**Status:** M0–M2 SHIPPED (v2.39.15) · M3–M6 backlog  
**Goal:** 生成模型稳定吃对先验像素 → 素材质量上升

## Shipped

| Wave | Item |
|------|------|
| M0 | stages/visual 谁喂谁 · material-fidelity-loop 命名表 · hard-defaults 指针 |
| M1 | `still_source.py` · bulk-preflight still_source 审计 · peak 禁 cast master |
| M2 | `generation_request.py` · h3 plan 回执 · media-queue sha 校验 |

## Backlog

- M3 registry→prompt 加深（已有 location 注入骨架）
- M4 shot-evidence 反馈环 + still-challenge 挂钩
- M5 FLF/identity_refs 路径规范化
- M6 dispatch generation_ready 字段

## Escape

`AIFILM_SKIP_GENERATION_REQUEST=1`
