# Memory · 2026-08-05 · S5.3-ops until-empty execute (capacity_not_ready PARTIAL)

## 用户原话
> GO

## 三句话
1. 真片 canary `h3-angles-runthrough` 跑 `h3 cycle --until-empty --execute --free-first --capacity-wait-sec 15` → live 回执 **stop_reason=capacity_not_ready** · ok=true · jobs_ran=0 · **pending_after=2**。
2. **不是** queue_empty；未假报过夜 drain 成功。execute 路径 fail-closed 诚实停机。
3. 真 `queue_empty` 仍 OPEN_OPS：需 5090 idle + Comfy 队列空 + 有 pending 时能 jobs_ran>0。

## 检查清单
- [x] free-first + capacity-wait CLI 真跑
- [x] stop_reason=capacity_not_ready（与 `receipts/fill-idle-until-empty.json` 一致）
- [x] canary `artifacts/2026-08-05-s53-until-empty-queue-empty.json`（内容已校正；文件名历史保留）
- [ ] 有 pending 的 film 上 overnight drain 到 stop_reason=queue_empty 且 jobs_ran>0

## 链
- live: `artifacts/5090-evaluation/h3-angles-runthrough/receipts/fill-idle-until-empty.json`
- memory/2026-08-05-s53-free-first-ops.md
- docs/plans/2026-08-05-strategy-director-engineer-upgrade.md (R-ops PARTIAL)
