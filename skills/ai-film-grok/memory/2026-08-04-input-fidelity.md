# Memory · 2026-08-04 · Input Fidelity（产出与 input 相关性尺子）

## 用户原话
> 帮我针对此项目提出链路优化计划 让这个流程更顺 产出的效果跟input的内容相关性更高

## 三句话
1. **先立尺子**：`aifilm fidelity check|status --root` → `receipts/input-fidelity.json`（score + codes）。
2. **相关性=可机读引用**，不是自觉：污染旁白 / 实体覆盖 / 保护台词 / must_keep 映射 / debrief。
3. **默认 soft**；`heat=max` + `user_source_fidelity_strict` + debrief 已确认 或 `AIFILM_FIDELITY_STRICT=1` 才 hard。

## 检查清单
- [ ] plan 后跑 `fidelity check`，score≥0.75
- [ ] 无 `USER_SOURCE_NAR_POLLUTED` / 保护台词掉线
- [ ] must_keep 有 beat→shot 映射（debrief `beat_shot_map`）
- [ ] 下一步 F1：shot `source_quote` 默认锚点

## 链
- 代码：`scripts/input_fidelity.py` · CLI：`cli_workflow` `fidelity`
- 旧闸：`lint_user_source_fidelity` · lesson `lessons-2026-07-22-user-source-fidelity.md`
- 上游：`script-value-debrief` · `story-reception`
