# Memory · 转场 + 运镜 v2（2026-07-20）

**User**: 转场跟运镜帮我优化 skill → 再把这些教训沉淀进 skill。

**Sample**: `nanniang-cafe-60s`（男娘咖啡厅）

## 产品结论

1. **continue 缝永远 hard**——作者写 soft/hold 也 `enforce_continue_hard_joins` 强改；记 `_transition_continue_hard_fixes`。
2. **运镜主轴 `dsl.camera_axis`** 六选一轮换；微动后缀**不再**默认绑 `push-in`。
3. lint：`CAMERA_AXIS_FLAT` · `STYLE_SOUP` · 加强 `SOFT_SOUP`。
4. **满 60s = 加镜**，不拉长 dissolve。
5. 假 continue（无 promote 字节）→ 改 `chain_mode: cut`，别硬叫接戏。
6. 改转场 → 只 re-final；改运镜 → re-I2V。

## Canonical

- `references/lessons-2026-07-20-transition-motion-v2.md`
- `scripts/edit_policy.py` · `film_spec.py` · `continuity.py`
- 交叉：`sediment-cn-codex` Opt8 · film-spec.md · production-discipline · schema

## P 码

P2 时空 · P3 动能 · P0 可观测
