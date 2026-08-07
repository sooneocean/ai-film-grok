# Memory · 2026-08-04 · H3 Fill-Idle 挑战（队列优先级）

**运营矩阵**：[weapon-lane-matrix.md](../references/weapon-lane-matrix.md)（节 Fill-Idle · **2026-08-06 语义澄清**）  
**日课续板**：[h3-core-workflow](2026-08-06-h3-core-workflow.md) · [h3-core-day](../references/stages/h3-core-day.md)  
**模式课**：[lessons-2026-08-04-h3-max-effect.md](../references/lessons-2026-08-04-h3-max-effect.md) · [h3-max-effect 短卡](2026-08-04-h3-max-effect.md)

## 用户原话
> 尽可能多使用 r2v … i2v 排队挑战 … 主轴 grok … 本地 PK 更好就替换  
> agree all · 推进全部 Wave αβγ

## 三句话
1. **默认 `h3_primary`**：P0=缺 clip 主烧 H3；P1=弱 take 补烧；**无「Grok 铺底」**。P2 挑战 Grok **仅 `hybrid_h3`**。
2. **PK 复合分**（motion−身份罚）+ 人 promote；`h3 evidence` 记账。
3. **5090**：平日 `run-next --max 5` · dual 粘连 · 够动停盲 R2V · 换模 free-memory。

## 补定策
- P2=mean 最低优先；ship 允许 P2 未完；跨集胜率不自动。
- 自动 dual 若 I2V 已够强可跳过 R2V；**显式 `h3_prefer: dual` 仍双烧**。
- baseline mean ≥ floor+6 → 可不进 P2（省队列）。

## 检查清单
- [ ] `aifilm h3 cycle --root --execute --max 5`（2.38.2 一循环）
- [ ] multi-take 时 ship-prep **不**静默 promote
- [ ] `aifilm h3 evidence --root` 写 metrics
- [ ] `h3 run-next --execute --max 5`（P2=pilot；换模 free-memory）
- [ ] `h3 pk-compare` 看 `pk_score` + `dailies_md`
- [ ] `ship-prep` → `human_pk_required` → 人 promote / `pk-ledger --append`
- [ ] dual 第二腿先于其他同级；续镜只 I2V

## 作战序
```text
Grok bulk → still 先验 → run-next --max 5 → evidence
→ ship-prep → pk-compare → 人 promote → final（可 P2 未完）
```

## 片例（Wave α · 2026-08-04 GO 实跑）
- **片根**：`/Users/dex/Desktop/e-virus-ch04-shelter/简报`（第4章：避难所的建立 · heat=max）
- 证据：`receipts/fill-idle-evidence.json` · 摘要：`receipts/fill-idle-alpha-run-2026-08-04.json`
- 插件副本：`artifacts/fill-idle-alpha-evirus-ch04/alpha-run-summary.json`
- **五项**：P0=**13** · P2=**1** · 人换 H3 比例=**n/a（尚无 multi-take）** · mean 提升=**n/a（clips 未测 mean）** · 重做=**0**
- **next 作业**：`ep01_s02_sh01` P0a I2V（`capacity_ready=false` 故未 --execute）
- **发现**：12×P0c 续链等首镜 I2V；多镜 grok clip 对 still 有 `identity_l1_high`；成片已有 film_final 但仍可 H3 挑战重做
