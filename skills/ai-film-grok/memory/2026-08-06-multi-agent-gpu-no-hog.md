# Memory · 2026-08-06 · 多 agent 共用 5090 · 禁抢闲占满

## 用户原话
> 有其他人在用吗 你只能在没人在用的时候去跑啊 你讲这个有搞清楚逻辑吗 你现在占满 我其他agent真的要用 没得用啊  
> 写入记忆 不准再犯

## 三句话
1. **`free-first` 不 cancel 外片 ≠ 可 until-empty 长驻抢空档**。
2. **机读（2.39.98+）**：`h3 cycle --until-empty --execute` **拒绝**除非 `--i-own-the-gpu` 或 `AIFILM_I_OWN_THE_GPU=1`；dry-run 仍可。默认 dispatch = **`run-next --max 5`**。
3. **进度只认 takes 文件数**（回执 `takes_count_delta`）；pending 因 mean floor 可假高。

## 检查清单
- [ ] 多会话默认：`h3 run-next` / `cycle --max` 单批，不挂 until-empty
- [ ] 独占一夜：用户点名 + `--i-own-the-gpu`
- [ ] 用户喊占满 → 立刻杀 drain + neuter supervisor
- [ ] busy → 零 submit，PARTIAL

## 链
- hard-defaults 表行 · dual-film-drain · c1-capacity-wait  
- 外片 ACTIVE lock 时 Grok 逃逸（勿对杀 guardian）：[one-outfit-mouth-min60-gpu-escape](2026-08-07-one-outfit-mouth-min60-gpu-escape.md)  
- 码：`h3_fill_idle.fill_idle_until_empty` · `cli_h3 --i-own-the-gpu` · `next_actions`
