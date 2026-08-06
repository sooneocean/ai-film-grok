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

## 2026-08-06 续 · execute PARTIAL（2.39.80）

- 已跑：`--until-empty --execute --free-first --capacity-wait-sec 7200`
- **capacity 最终 ready=true**（路径打通）
- 第 1 job `shot09` **run_failed**：`variety preflight L4_INSERT_LOW`（产品门禁，非 hang）
- `jobs_ran=0` · pending 仍 10 · **非 queue_empty**
- 回执：`artifacts/2026-08-06-c1-drain-closeout.json` · `artifacts/2026-08-06-c1-execute-run-next.json`
- 进程已停（避免同错误空转）；换绿 variety 片根或 `write-spec` 修 L4 后再 drain
