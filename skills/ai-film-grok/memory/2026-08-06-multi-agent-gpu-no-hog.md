# Memory · 2026-08-06 · 多 agent 共用 5090 · 禁抢闲占满

## 用户原话
> 有其他人在用吗 你只能在没人在用的时候去跑啊 你讲这个有搞清楚逻辑吗 你现在占满 我其他agent真的要用 没得用啊  
> 写入记忆 不准再犯

## 三句话
1. **`free-first` 不 cancel 外片 ≠ 可以 until-empty 长驻抢空档**：队列一空就 submit = **占满 5090**，别的 agent/片 **插不进来**。
2. **多 agent / 多片共用机默认：不挂 `--until-empty`、不挂 c1-supervisor 自动重启**；只在用户 **点名独占**（如「今夜只烧这片」「go 独占」）才允许排水长驻。
3. **submit 前必须确认 Comfy idle**（`queue_running+pending=0` 且 capacity ready）；忙则 **完全不 submit、不 capacity_wait 死缠**，回报 PARTIAL 等用户批。

## 检查清单
- [ ] 起 H3 / Comfy 前：`curl :18188/queue` → running+pending 必须为 0（除非用户已批「可排队」）
- [ ] **禁默认** `h3 cycle --until-empty --execute` 当多会话/多 agent 可能并存
- [ ] **禁** 未批准就写 supervisor 自动 restart drain
- [ ] 用户抱怨占满 / 说「别人要用」→ **立刻杀本片 until-empty + neuter supervisor**，不争辩
- [ ] 用户说「写入记忆」→ 当轮落档（本卡 + Agents 指针 + hard-defaults 行）
- [ ] 独占一夜：用户圣旨后才 `--until-empty`；结束或用户喊停 → 杀干净

## 错因（本次）
- 把 C1 overnight「能烧就烧」用在 **多 agent 共用 5090** 场景
- free-first 只保证不杀别人，**空档仍被我们抢光**

## 链
- 双片排水（相关）：[2026-08-06-dual-film-drain-takes-progress](2026-08-06-dual-film-drain-takes-progress.md)
- capacity-wait：[2026-08-06-c1-capacity-wait-iron](2026-08-06-c1-capacity-wait-iron.md)
- 5090 pilot 独占：[2026-07-29-comfy-gpu-priority-pilot-i2v](2026-07-29-comfy-gpu-priority-pilot-i2v.md)
- hard-defaults 表行：**多 agent 5090 禁抢闲占满**
