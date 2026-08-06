# 2026-08-06 · shortform S5 OPEN_OPS（板末）

## 三句话
1. **S5.1 GPU drain**：本机 `18188→Comfy` **timeout**，未执行 until-empty（遵守 no-hog + 须 `--i-own-the-gpu`）。
2. **S5.2 duration**：savani ep01/02 目标已对齐媒体 ~211.8s / 41 镜 → **duration hard 绿**；suse 仅 overlong soft。
3. Canary：`artifacts/2026-08-06-shortform-s5-open-ops-canary.json`。

## 有 GPU 时
```bash
aifilm h3 capacity-plan --root "<film>"
aifilm h3 cycle --until-empty --execute --free-first --i-own-the-gpu
# stop ∈ {queue_empty, max_cycles}
```

## 链
- board: `docs/plans/2026-08-06-shortform-optimization-todoplan.md` CODE CLOSED + S5
