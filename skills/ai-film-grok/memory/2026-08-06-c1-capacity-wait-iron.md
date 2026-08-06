# C1 capacity-wait IRON · 2026-08-06

## 原话
go c1 然后一路修完

## 三句
1. `--capacity-wait-sec 7200` 曾被 `_CAPACITY_WAIT_SEC_HARD_MAX=600` 静默钳死 → 抬到 **28800**（2.39.84）。
2. 等队列时若只剩 VRAM/RAM floor，须 **idle 后再 free-memory 一次**（2.39.86），禁止 cancel foreign。
3. until-empty 中途写 `stop_reason=capacity_waiting`（2.39.85），勿把旧 `run_failed` 当当前态。

## 清单
- [x] hard max 8h
- [x] free_first_when_idle
- [x] heartbeat receipt
- [ ] velvet queue_empty（共享 5090：savani/foreign 排队时诚实等）

## 链
- `media/h3_fill_idle.py` · `test_h3_until_empty.py`
- film: `velvet-stage-dual` · artifacts `2026-08-06-c1-*`
