# Memory · 2026-08-03 · Workflow merge-all wrap (v2.31.20–23)

**Plan：** `docs/plans/2026-08-03-workflow-optimize-todo.md` → **Wave A–F SHIPPED**  
**plugin：** `2.31.23`（Wave F）· 另有本机后续 commit 可能领先 origin（见 git log）

## 三句话

1. **吞吐 CLI 齐**：closeout · pilot GO · bulk-preflight · variety · shortlist · gpu-lease · tunnel · queue-progress。  
2. **Final 工程齐**：超时地板 1200/1800 · sidechain→amix PARTIAL · SRT 空格稳路径 · genre spine 自动发现。  
3. **Agent 回路齐（Wave F）**：dispatch/next_actions/advance 接 preflight·variety·closeout；**不要**再静默降 heat / 自批 pilot。

## 命令速查

```text
aifilm pilot pack --root …
aifilm bulk-preflight --root …
aifilm variety-precheck --root …
aifilm select-shortlist --root …
aifilm gpu-lease acquire|heartbeat|release --root …
aifilm tunnel-probe
aifilm queue-progress --root …
aifilm final --root …              # 超时/PARTIAL 见 Wave D
aifilm closeout status|run --root …
aifilm dispatch --root …           # next 会推 throughput 门
```

## 检查清单

- [x] 2.31.20 Wave A closeout + pilot pack  
- [x] 2.31.21 Wave B–C preflight/variety/lease/tunnel/progress  
- [x] 2.31.22 Wave D final engineering + genre spine  
- [x] 2.31.23 Wave F agent-loop glue  
- [x] Wave G–H bulk 硬门 + preflight 收据复用 + shortlist inject  
- [x] e2e 冒烟跑通 → [2026-08-03-throughput-e2e-run.md](./2026-08-03-throughput-e2e-run.md)  
- [ ] 真片 root 同一路径（用户点名）  
- [ ] `grok plugin update` 收工后若本地 installed 落后  

## 下一刀 ROI（未开）

| ID | 题 | 何时开 |
|----|----|--------|
| W8 | Autopilot 扩 allowlist 接 throughput 命令 | 实拍验证 F 稳定后 |
| W7 | 毒 still 自动化加深 | 有启发式/CV 才开 |
| 实片 | 用 `dispatch` 在真实 film root 走一轮 GO | **用户点片名即可** |

## 关联

- Changelog `[2.31.20]`–`[2.31.23]`  
- Closeout IRON · Bulk→final IRON（2026-07-29 memory）
