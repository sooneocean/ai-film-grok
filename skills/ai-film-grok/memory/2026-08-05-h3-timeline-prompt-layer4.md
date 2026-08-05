# Memory · 2026-08-05 · H3 Layer-4 时间轴 Prompt（5090）

**完整课**：[lessons-2026-08-04-h3-max-effect.md](../references/lessons-2026-08-04-h3-max-effect.md) §H3 Layer-4

## 用户原话（要旨）
> 把自然语言需求转成 MiniMax H3 能理解的「时间轴动作脚本」——时间码约束、动作优先、镜头+环境运动、声音由可见事件暗示；补连续性/每段主动作数/单镜头模式/结尾态。

## 三句话
1. **Layer 4 only**：Shot → `[0s-2s]…` 时间轴；不是剧本/分镜系统。
2. **5090 路径自动**：`h3_primary`/`hybrid_h3` 用 `build_h3_temporal_prompt`；Grok 仍 flat spine。
3. **控乱序靠时间分解**：连续覆盖 + 1 primary/段 + continuity + ending pose + env motion。

## 检查清单
- [x] `aifilm h3 plan|run` 产出 prompt 含 `[0s-`
- [x] 首段有 Continuity / Primary action；末段 Resolves ending pose
- [x] 对白镜仍有 `line:「…」` + lip sync
- [x] 非 5090 profile 仍是 `Vertical 9:16` flat spine
- [x] combo families 默认 Layer-4 compile；`--round 3` flat vs timeline A/B
- [ ] GPU 空闲时：`combo-eval --round 3 --execute`（prep：`artifacts/.../h3-timeline-ab-20260805`）
- [ ] 可选：`dsl.camera_cut_mode=multi` / `timeline_events` / `environment`

## 代码
- `scripts/h3_timeline_prompt.py`
- `scripts/motion_prompt_spine.py` → `build_h3_temporal_prompt`
- `scripts/media/h3_workflow.py` → `_prompt_for_shot`
