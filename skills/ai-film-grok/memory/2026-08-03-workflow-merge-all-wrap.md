# Memory · 2026-08-03 · Workflow merge-all wrap

**Plan：** `docs/plans/2026-08-03-workflow-optimize-todo.md` → **Wave A–H + W8 SHIPPED**  
**plugin：** `2.31.35`（W8 autopilot local throughput）

## 三句话

1. **吞吐 CLI 齐**：closeout · pilot GO · bulk-preflight · variety · shortlist · gpu-lease · tunnel · queue-progress。  
2. **Agent 回路齐（F/G/H）+ W8**：dispatch/next/advance 接 preflight·variety·closeout；autopilot 本地只走 `ADVANCE_ACTIONS`，dry-run 不 shell。  
3. **下一项**：真片 root（用户点名）；勿静默降 heat / 自批 pilot。

## 命令速查

```text
aifilm pilot pack --root …
aifilm bulk-preflight --root …
aifilm variety-precheck --root …
aifilm select-shortlist --root …
aifilm gpu-lease acquire|heartbeat|release --root …
aifilm tunnel-probe
aifilm queue-progress --root …
aifilm final --root …
aifilm closeout status|run --root …
aifilm dispatch --root …
aifilm autopilot --root …              # W8：本地吞吐 + 预算技能；人审/付费停
```

## 检查清单

- [x] 2.31.20 Wave A closeout + pilot pack  
- [x] 2.31.21 Wave B–C preflight/variety/lease/tunnel/progress  
- [x] 2.31.22 Wave D final engineering  
- [x] 2.31.23–26 Wave F–H agent glue / bulk 硬门 / shortlist  
- [x] 2.31.35 Wave W8 autopilot local throughput allowlist  
- [x] e2e 冒烟 → [2026-08-03-throughput-e2e-run.md](./2026-08-03-throughput-e2e-run.md)  
- [ ] 真片 root 同一路径（用户点名）  
- [ ] push origin（需授权时）· `grok plugin update`

## 下一刀 ROI（未开）

| ID | 题 | 何时开 |
|----|----|--------|
| W7 | 毒 still 自动化加深 | 有启发式/CV 才开 |
| 实片 | 用 `dispatch` 在真实 film root 走一轮 GO | **用户点片名即可** |

## 关联

- Changelog `[2.31.20]`–`[2.31.35]`  
- Closeout IRON · Bulk→final IRON（2026-07-29 memory）
