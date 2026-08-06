# Memory · 2026-08-05 · h3 until-empty canary（dry）

## 用户原话
> go next

## 三句话
1. worktree prune 清掉 2 条 prunable 登记。
2. canary dry on h3-angles-runthrough：capacity-plan 2 job / ~18min · priority_ok · until-empty dry → dry_run_pass_execute。
3. 未真烧 GPU；真挂机需 pilot GO + --execute。

## 检查清单
- [x] capacity-plan 回执
- [x] fill-idle-until-empty dry 回执
- [x] canary 汇总 artifacts/2026-08-05-h3-until-empty-canary.json
- [x] 真片 --execute 跑过（AF7）：capacity_not_ready 诚实停
- [x] S5.3-ops `--free-first`（queue busy 不卸；见 s53-free-first canary）
- [x] S5.3-ops `--capacity-wait-sec`（2.39.66+；live 仍 capacity_not_ready PARTIAL）
- [ ] idle 后再跑到 queue_empty 真 takes 增量

## 链
- docs/plans/2026-08-05-optimization-todoplan.md
- docs/plans/2026-08-05-h3-primary-capacity.md
