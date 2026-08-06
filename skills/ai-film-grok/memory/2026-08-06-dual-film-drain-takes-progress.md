# Memory · 2026-08-06 · 双片排水 · takes 认进度 · C1 外源复活

## 用户原话
> 继续推进到最后 要有成果才能来跟我回报  
> 能把教训回写吗 然后做完就可以收工 你看还有啥事情

## 三句话
1. **进度只认 `takes/` 非空文件**（+ `h3-run-*.json`），**不认** Comfy interrupt、也不认 pending 假高——Fill-Idle 因 `h3_below_floor` / multi-take 可 **一直 pending 却在狂出 take**。
2. **5090 一 owner 纪律**：`free-first` 不 cancel 外片，但 **双 cycle + 外源 C1 supervisor** 会抢空档；独占目标片时须 **停对方 cycle 并 neuter `artifacts/*c1-supervisor.sh`**（会被重写则再压）。
3. **门禁诚实**：`bulk-preflight` 在 `gpu_lease=LEASE_HELD` 时 fail 属预期；idle 时 `comfy free-memory --confirm` 解 VRAM/RAM floor；lease expire 可当 free，held 则等。

## 检查清单
- [ ] 双片同机：先定 **唯一 owner root**，再 `gpu-lease acquire`；另一片 cycle 不挂或只 capacity-wait
- [ ] 杀 cycle 时 **只 match** `cmd.startswith(pyenv) and aifilm_grok.py h3 cycle`——禁 `pgrep -f` 含脚本源码（会杀自己）
- [ ] C1/外源 supervisor：检查 `artifacts/2026-08-06-c1-supervisor.sh` 是否被复活；独占他片时 **neuter 为 exit 0**
- [ ] 验收写 `artifacts/*session-result.json`：recent takes mtime + bulk_ok + pending 解释
- [ ] pending 不降 ≠ 没进度；mean floor 重试要单独策略（轮转/封顶 take 数/人 promote）

## 片例
- canary：`0721/velvet-stage-dual`（C1，pending≈6 below_floor）
- 目标：`0805/suse-evolution-ep01`（bulk **True []**；until-empty 仍跑）
- 证据：`plugins/ai-film-grok/artifacts/2026-08-06-session-result.json` · `…-suse-bulk-now.json`

## 链
- capacity-wait IRON：[2026-08-06-c1-capacity-wait-iron](2026-08-06-c1-capacity-wait-iron.md)
- free-first 先例：[2026-08-05-s53-free-first-ops](2026-08-05-s53-free-first-ops.md)
- 代码：`media/h3_fill_idle.py`（free_first / capacity_wait / never cancel foreign）
- 框架 tip：plugin **2.39.87**（heat soft-queue · H3 meat cap · pilot 批准 phrases）
