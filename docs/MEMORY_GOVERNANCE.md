# Memory / docs governance · ai-film-grok

Prevent context bloat and dual-truth docs. Authority order is fixed.

## Authority stack (read top-down)

1. **`references/hard-defaults.md`** — hard product rules (edit + tests).
2. **`references/stages/*`** — per-stage agent cards (dispatch context).
3. **`memory/*`** — short session cards only (quote + 3 lines + checklist + lesson link).
4. **`references/lessons-*`** — long postmortems; **do not** paste whole files into agent context.
5. **`docs/plans/*`** — execution boards; status headers must stay 账实一致.

**Single execution board:** [CTO plan](plans/2026-08-06-cto-optimization-todoplan.md).  
**Iron → code internalization:** [2026-08-07-iron-internalization-todoplan.md](plans/2026-08-07-iron-internalization-todoplan.md).  
**Nutrient ledger:** [2026-08-06-nutrient-matrix.md](plans/2026-08-06-nutrient-matrix.md) (L3/L4/L5).

## memory/ retention

| Rule | Detail |
|------|--------|
| Shape | Dated `YYYY-MM-DD-topic.md`; max ~80 lines preferred（skill README 约 60） |
| Content | User quote + 3 bullets + checklist + optional lesson pointer |
| No secrets | Never paste tokens, `url.user:pass@host`, or `config.env` |
| Soft cap | Prefer **≤ 40** active P0 pointer cards; archive rest to `memory/archive/` |
| Age | Cards **> 60 days** with no hard-defaults pointer → archive candidate |
| Index | `memory/README.md` lists active P0 cards only |

## Change order (law → prose)

When a rule changes:

1. **Code + `hard-defaults.md` row** (and error codes / env escapes).
2. **pytest** (contract or focused test).
3. **`references/lessons-*`** only if postmortem needed.
4. **`memory/*`** — three lines + checklist only; **never** dual-write the full iron table.
5. **stages/** — one-line pointer if stage action changed.
6. **L5** — if already L4 default path, archive or shrink memory to pointer.

**Forbidden:** memory-only “law updates”; claiming SHIPPED while plan header still OPEN.

---

## Iron internalization（铁律如何进系统逻辑）

> 类比：规章上墙不够，要让走错路径的闸门自动喷水。

### 事故 → 飞轮（永久 · 2026-08-07 F0）

```text
用户原话 / 掉片
  → 五问卡（A/B/C · L阶 · 挂载层 · 证据 · 人判）
  → 只 C 进队列（CTO OPEN 或 error-internalization plan）
  → 代码 gate + hard-defaults 一行 + pytest
  → iron_status 登记 + nutrient 行
  → memory 三句指针（禁双写全表；禁缺链）
  → stages 一行（若阶段动作变）
  → L5：已 L4 则 archive / 瘦卡
  → 周 reconcile：header vs plugin.json
```

**禁：** 只改 memory/AGENTS 当 Done；假 CV 当 Done；默认 `AIFILM_SKIP_*=1`。  
**对账：** [nutrient-matrix](plans/2026-08-06-nutrient-matrix.md) §2b（E1–E4）；CTO 主执行板。

### 五问卡（出 todo 前必答；只 C 类进队列）

| # | 问 | 答案形态 |
|---|-----|----------|
| 1 | **A / B / C？** | A 法条已定性 · B 工程已 ship · C 仍 OPEN |
| 2 | **L 阶？** | L3 能拦 · L4 默认必走 · L5 可废文 |
| 3 | **挂哪一层？** | validate / dispatch / queue / promote / render / closeout |
| 4 | **证据？** | receipt 字段 + pytest +（可选）真片 canary |
| 5 | **人判边界？** | 机读拦假绿；人签 pilot / PK / review-final |

### Todo 卡片模板

```text
ID: IRON-xx
主题: <一句话>
现状: L? / 有码否 / 挂载点
缺口: <可测一句>
做法: 改 <file:fn> + 常量 + 测
验收: pytest 名 · receipt 字段 · 逃生 env
非目标: 不写新 memory 全文 / 不做不可靠 CV 幻觉
```

### 优先级（文科可用）

`掉片频率 × 假绿伤害 × 可机读程度`  
→ 可 ffmpeg/字段证明的先做；「好看/解剖」先 **缺 attestation = hard**，真视觉模型后置。

### 完成定义

- 相关 pytest 绿；指纹变则 `lock-runtime`
- hard-defaults 有一行；memory 最多三句指针
- 默认 fail-closed；`AIFILM_SKIP_*` 须写 receipt
- **永不**机器代签 pilot / PK / review-final

### 明确不要做

- 从 `hard-defaults.md` 写全量 markdown parser 当唯一机读源（脆、贵）
- 用假 CV 声称「已识别毒镜」当 Done
- 再贴标语代替 gate

---

## What agents must not do

- Paste entire `lessons-*` into every turn.
- Rewrite hard-defaults by only editing memory (memory is index, not law).
- Claim OPEN items already SHIPPED in plan headers.
- Re-open A1–A5 / package-boundary waves already marked SHIPPED.
- Soften IRON via default `AIFILM_SKIP_*=1`.

## Related

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [REVIEW_CHECKLIST.md](./REVIEW_CHECKLIST.md)
- skill `memory/README.md`
- [CTO plan](plans/2026-08-06-cto-optimization-todoplan.md)
- [Iron internalization](plans/2026-08-07-iron-internalization-todoplan.md)
