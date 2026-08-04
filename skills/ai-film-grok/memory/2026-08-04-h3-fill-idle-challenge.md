# Memory · 2026-08-04 · H3 Fill-Idle 挑战（Grok 主轴 + 本地 PK）

**运营矩阵**：[weapon-lane-matrix.md](../references/weapon-lane-matrix.md)（节 Fill-Idle）  
**模式课**：[lessons-2026-08-04-h3-max-effect.md](../references/lessons-2026-08-04-h3-max-effect.md) · [h3-max-effect 短卡](2026-08-04-h3-max-effect.md)

## 用户原话
> 尽可能多使用 r2v 然后可以用 i2v 去排队挑战其他生成的片段 主轴还是倚靠 grok video … 透过我本地生成去 PK 若效果比较好就可以替换  
> （定策）soft 能烧就烧 · R2V 能量位优先 · 机读建议 + 人最终拍板

## 三句话
1. **Grok 铺 soft baseline**；**restricted 主轨 H3**；5090 **P0→P1→P2 填空**（空闲挑战 Grok，禁抢 P0）。
2. **R2V 占满能量位**（大嘴/高难/I2V 静）；锁脸与续镜 **I2V**；不是全片默认 R2V。
3. **PK**：`h3 next`/`pk-compare` 机读建议 → **人** `select-shortlist --promote`；final **不**等 P2 烧完。

## 补定策（用户 agree all · 2026-08-04）
1. **P2 排序**：同级填空按 **mean 最低优先**（最弱 Grok 先挑战）；并列再按时间轴。
2. **Ship 门**：允许 **P2 未完成** 直接 ship；高光镜 **不** 强制必须挑战过（质量上限 ≠ 发布阻塞）。
3. **跨集**：R2V/I2V 胜率 **不** 自动跨集复用；人记 / 片级 dailies 即可。

## 检查清单
- [ ] `aifilm h3 next --root` / `h3 list --challenge` 看 P0→P2
- [ ] 空闲：`aifilm h3 run-next --root --execute [--max 5]`（产能绿才跑；P2=pilot；非 daemon；看 `next_after`）
- [ ] climax/对白CU 肉戏：I2V 后自动排 **R2V 第二腿**（或 `h3_prefer: dual`）
- [ ] 人审后：`h3 pk-ledger --append` 记 dailies（不跨片自动）
- [ ] 成片前：`aifilm ship-prep --root` 看 `pk_compare` / `human_pk_required`（v2.37.10）
- [ ] `h3 next` 的 `capacity_ready`（offline 也可仍给 command）
- [ ] baseline 在 **takes/** 或 **manifest.clips** 都能解锁 P2（v2.37.7）
- [ ] `aifilm h3 pk-compare --root` 只建议，禁静默 promote
- [ ] 非 restricted：Grok 先有 baseline；H3 作挑战（P2）
- [ ] restricted：`h3 list` P0 先于任何 P2
- [ ] 续镜只 I2V 末帧；能量镜跟 list 的 r2v/alt
- [ ] P2 优先 mean 最低的 Grok 镜
- [ ] `select-shortlist` 看建议 → 人一眼 → 才 `--promote`
- [ ] 禁 mean 静默换片；毒/换人一票否决
- [ ] final 可不 tip 完 P2；跨集不靠自动胜率表

## 片例
（下一片实跑 Fill-Idle 后补路径）
