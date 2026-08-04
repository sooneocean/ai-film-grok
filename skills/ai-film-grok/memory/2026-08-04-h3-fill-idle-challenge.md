# Memory · 2026-08-04 · H3 Fill-Idle 挑战（Grok 主轴 + 本地 PK）

**运营矩阵**：[weapon-lane-matrix.md](../references/weapon-lane-matrix.md)（节 Fill-Idle）  
**模式课**：[lessons-2026-08-04-h3-max-effect.md](../references/lessons-2026-08-04-h3-max-effect.md) · [h3-max-effect 短卡](2026-08-04-h3-max-effect.md)

## 用户原话
> 尽可能多使用 r2v … i2v 排队挑战 … 主轴 grok … 本地 PK 更好就替换  
> agree all · 推进全部 Wave αβγ

## 三句话
1. **Grok 铺 soft**；**restricted 主轨 H3**；P0→P1→P2 填空（能烧就烧，禁抢 P0）。
2. **PK 复合分**（motion−身份罚）+ 人 promote；`h3 evidence` 记账。
3. **5090**：dual 粘连 · 够动可停盲 R2V · 换模 free-memory · Grok take 打 `grok_*` 标。

## 补定策
- P2=mean 最低优先；ship 允许 P2 未完；跨集胜率不自动。
- 自动 dual 若 I2V 已够强可跳过 R2V；**显式 `h3_prefer: dual` 仍双烧**。
- baseline mean ≥ floor+6 → 可不进 P2（省队列）。

## 检查清单
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

## 片例（Wave α · 填路径）
- 证据收据：`<film>/receipts/fill-idle-evidence.json`
- 记账五项：P0 数 / P2 挑战数 / 人换 H3 比例 / mean 提升 / 重做次数  
- （跑完真片后把 root 写这里）
