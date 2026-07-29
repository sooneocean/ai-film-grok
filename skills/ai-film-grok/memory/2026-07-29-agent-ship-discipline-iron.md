# Memory · 2026-07-29 · Agent 出货纪律 IRON（后面不要再犯）

> 本 session 反复卡 push / 测红 的工程纪律沉淀。  
> 全文课：[lessons-2026-07-29-agent-ship-skill-budget-push.md](../references/lessons-2026-07-29-agent-ship-skill-budget-push.md)

## 三句话

1. **`SKILL.md` ≤6000 字节**（`test_dispatch_compact`）；加 P0 必须**压**旧字，且**保留**文档测试锚点（lens/frw/cut-silk/title-double-burn/`plate-cards blank`）。  
2. **改 scripts 必刷 `runtime-lock.json`**；push 前 **工作区干净**；并行会话脏档会把 pre-push 打死。  
3. **成人 max 分层**：**queue 硬 A**、**final/export 硬 S（final_ok）**；`dialogue_drama` 字幕在 `caption_text` 不塞说书 `nar`；卸装走 **wardrobe ladder + approve-state**。

## 出货前 30 秒

```text
ruff + 相关 pytest
PYTHONPATH=scripts 重建 runtime-lock 并 verify ok
wc -c SKILL.md  # ≤6000
git status 干净
git push  # 等 release-check 全量绿（数分钟）
```

## 逃生（诚实写回执）

- heat queue：`AIFILM_SKIP_HEAT_QUEUE_GATE=1`
- heat final：`--skip-heat-gate` / `AIFILM_SKIP_HEAT_FINAL_GATE=1`
- pilot：`--allow-without-pilot`（**不**绕 heat）
