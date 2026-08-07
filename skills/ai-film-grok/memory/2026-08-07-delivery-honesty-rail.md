# Memory · 2026-08-07 · 出片诚实审计轨

**完整板**：[delivery-honesty-rail](../../../docs/plans/2026-08-07-delivery-honesty-rail-todoplan.md)

## 用户原话

> 1（开工 delivery-honesty-rail）

## 三句

1. **关警铃必须留牌子**：`AIFILM_SKIP_*` 经 `core.skip_audit.skip_flag` / closeout `sync` → `receipts/skip-usage.json`；IRON 无 `AIFILM_SKIP_REASON` → closeout PARTIAL。
2. **人证可回查**：`anatomy_safe=true` 写 `receipts/attestation-ledger.json`（reviewer/session/path/ts）；缺字段 = `pending_human_review`，不造假来源。
3. **双 checkout 只比 git**：`aifilm doctor` 带 `checkout_drift`；HEAD 不一致才 warn；**禁手拷** plugins↔dev。

## Checklist

- [ ] 出片前 `cat receipts/skip-usage.json`（应干净或有 reason）
- [ ] IRON 逃生：先 `export AIFILM_SKIP_REASON='…'`
- [ ] `anatomy_safe` 批 still 后查 attestation ledger
- [ ] 两树不同步 → git ff/merge，勿 cp

## 链

- hard-defaults 行：SKIP 运行期记账
- 测：`test_skip_audit` · `test_attestation_provenance` · `test_checkout_drift`
