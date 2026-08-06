# C1 capacity-wait IRON · 2026-08-06

## 原话
go c1 然后一路修完

## 三句
1. `--capacity-wait-sec 7200` 曾被 hard max=600 静默钳死 → **28800**（2.39.84）。
2. 队列空但仍 VRAM floor → wait 中 **idle free 一次**（2.39.86）；中途写 `capacity_waiting`（2.39.85）。
3. P1 按 **H3 take 最少优先** 轮转（2.39.87），避免 shot09 独占 5090。

## 清单
- [x] hard max 8h · idle free · heartbeat · P1 rotate · L4 fix · contention map · safe upload
- [x] 实跑：pending 8→7 · 704 takes 9→20 · shot16 过 floor；shot10/11 逼近 20
- [ ] `queue_empty`（余 6×P1 below_floor + shot01 P2；共享 5090 与 suse 竞合；shot09 mean~1.5 难清）

## 链
- `media/h3_fill_idle.py` · tests `test_h3_until_empty` 18p
- film `velvet-stage-dual` · artifacts `2026-08-06-c1-*`
- versions 2.39.84–2.39.87 pushed
