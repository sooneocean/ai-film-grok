# Memory · C1 until-empty OPEN_OPS（2026-08-06）

**片根探针**：`AI FILM SPACE/0721/velvet-stage-dual`  
**回执**：`artifacts/2026-08-06-c1-until-empty-dry-open-ops.json`

## 三句话

1. Comfy 隧道 **18188 可达**，但 **RAM/VRAM 低于提交地板** + **COMFY_QUEUE_BUSY**。
2. `h3 cycle --until-empty --free-first` dry：`stop_reason=dry_run_pass_execute`；free_first **skipped_queue_busy**（禁杀 foreign）。
3. pending=10 · jobs_ran=0 · **全 drain queue_empty 仍 OPEN_OPS** 直到 5090 idle。

## 再烧条件

```bash
aifilm h3 capacity-plan --root "<film>"
# ready 后：
aifilm h3 cycle --root "<film>" --until-empty --execute --free-first --capacity-wait-sec 120
```
