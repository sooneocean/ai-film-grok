# Memory · 2026-08-05 · h3_primary 无限主产线

**定策（实现 SHIPPED）**：[docs/plans/archive/2026-08-05-h3-primary-capacity.md](../../../docs/plans/archive/2026-08-05-h3-primary-capacity.md)  
**日课续板（ACTIVE）**：[docs/plans/2026-08-06-h3-core-workflow-todoplan.md](../../../docs/plans/2026-08-06-h3-core-workflow-todoplan.md) · [h3-core-workflow memory](2026-08-06-h3-core-workflow.md)  
**矩阵**：[weapon-lane-matrix.md](../references/weapon-lane-matrix.md)

## 用户原话
> local 5090 的 h3 虽然要花时间运算但是只要花时间就可以无限生成 — 摆成主要生成手段，按场景 t2v i2v r2v  
> 从 p0 推进

## 三句话
1. **`AIFILM_I2V_PROFILE=h3_primary`** → auto `comfy-h3`；setup/meat/对白/env 全本地。
2. **模式**：env→T2V · 单 still→I2V · 有 last→FLF · 高动→R2V；云 bulk 默认硬拦。
3. **dispatch**：clips 未齐 + pilot GO → **`h3-run-next`** 优先，不是 media-queue。

## 检查清单
- [ ] `export AIFILM_I2V_PROFILE=h3_primary`（或 config.env）
- [ ] `aifilm write-spec` 后 `_i2v_profile=h3_primary` · `i2v_provider=comfy-h3`
- [ ] `aifilm h3 capacity-plan` 看 ETA
- [ ] `aifilm h3 cycle --until-empty --execute` 挂机吃光队列
- [ ] media-queue 推 Grok 应 QueueError（escape: `AIFILM_ALLOW_CLOUD_RESTRICTED=1`）
- [ ] hybrid 片：setup 仍 Grok（回归）；P0 永不被 P2 挤

## 作战序
```text
write-spec (h3_primary) → pilot 人批
→ capacity-plan → cycle --until-empty --execute
→ ship-prep / pk 人 promote → gate-auto → final
```
