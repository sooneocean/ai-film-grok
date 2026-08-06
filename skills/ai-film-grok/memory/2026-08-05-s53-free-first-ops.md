# Memory · 2026-08-05 · S5.3-ops free-first

## 用户原话
> go next round

## 三句话
1. `h3 cycle --free-first`：队列空闲且**仅** RAM/VRAM floor 挡时卸模一次；`COMFY_QUEUE_BUSY` **永不** free/cancel 外来 prompt。
2. 单元测 11 绿；live dry = `queue_busy_never_cancel_foreign`；live execute free_prep=`already_ready` 后仍 `capacity_not_ready`（争用竞态）。
3. 过夜 `queue_empty` 真 drain 仍 OPEN_OPS，需 5090 真正 idle。

## 检查清单
- [x] `prepare_capacity_free_first` + report `free_prep`
- [x] CLI `--free-first` on cycle/until-empty
- [x] tests: disabled / queue_busy / dry would_free / free once / until_empty free_prep
- [x] canary `artifacts/2026-08-05-s53-free-first-canary.json`
- [ ] idle 后再跑到 `queue_empty` 真 takes 增量

## 链
- docs/plans/2026-08-05-strategy-director-engineer-upgrade.md (rev 2026-08-05e)
- docs/plans/2026-08-05-optimization-todoplan.md
- memory/2026-08-05-h3-until-empty-canary.md
