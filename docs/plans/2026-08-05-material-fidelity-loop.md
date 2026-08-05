# Material Fidelity Loop — 2026-08-05

**Status:** M0–M4 SHIPPED (v2.39.17) · M5–M6 backlog  
**Goal:** 生成模型稳定吃对先验像素 → 素材质量上升

## Shipped

| Wave | Item |
|------|------|
| M0 | stages/visual 谁喂谁 · material-fidelity-loop 命名表 · hard-defaults 指针 |
| M1 | `still_source.py` · bulk-preflight still_source 审计 · peak 禁 cast master |
| M2 | `generation_request.py` · h3 plan 回执 · media-queue sha 校验 |
| M3 | `build_asset_prompt_hints` location/prop/time/rules → GenerationRequest |
| M4 | `shot_evidence` · mean/register 写回执 · PRIOR_EVIDENCE · still-challenge next · pk identity 加重 |

## Backlog

- M5 FLF/identity_refs 路径规范化
- M6 dispatch generation_ready 字段

## Escape

`AIFILM_SKIP_GENERATION_REQUEST=1`
