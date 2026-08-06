# Memory · 2026-08-05 · 构图防抢走（anti-hijack）

**完整课**：[lessons-2026-08-05-composition-anti-hijack.md](../references/lessons-2026-08-05-composition-anti-hijack.md)

## 用户原话
> 要避免抢走问题在犯 顺手优化掉  
> （前因：sh01 沙俯视+脚印被 multi-seed 当赢家；sh02 男胸 CU 抢走澜汐）

## 三句话
1. **母题抢走** = 音量/白底/mean 绿，但画面不是本镜要的主体（沙滩俯视顶替女脸对白；男躯干顶替女主存在）。
2. multi-seed **必须** 过 composition gate 再 promote；**禁止** 只比 white0 / mean_volume / motion mean。
3. 机读：`scripts/composition_anti_hijack.py` → `aifilm anti-hijack --root`；已挂进 `select-shortlist` 与 `pk-compare`。

## 一句话规则
> **以后 multi-seed 选 take：先 composition anti-hijack，再比 mean/音量；沙脚印与男胸抢女主 = 死 take，有备选绝不 promote。**

## 检查清单
- [x] `composition_anti_hijack.py`（sandish / skin / torso_risk）
- [x] `select-shortlist` demote hijack + 不 promote 脏 take
- [x] `score_take_for_pk` 扣分
- [x] CLI `aifilm anti-hijack`
- [x] hard-defaults + stages/visual + Agents.md 指针
- [x] 长课 lessons-2026-08-05
- [x] 单测合成帧 5 passed
- [x] ep02 实机：42/7777/99001 hijack；20260805 / 88001 ok

## 拒什么
| 类 | 症状 | 处置 |
|---|---|---|
| 沙俯视/脚印 | top 高亮低方差 / 中心无肤色 | hijack → 永不 promote（有干净备选时） |
| 男胸躯干 CU | mid 高亮、顶区暗、无女脸 | torso_risk → demote |
| 纯 env 顶替对白脸 | skin≈0 + 低 cstd | face 类 hard demote |

## 命令
```bash
aifilm anti-hijack --root "$ROOT"
aifilm anti-hijack --root "$ROOT" --shots ep02_sc01_sh01,ep02_sc01_sh02 --promote
aifilm select-shortlist --root "$ROOT"   # 自动带 anti-hijack
```

## 逃生
`AIFILM_SKIP_ANTI_HIJACK=1`

## 片例
`huangdao-99-series/ep02` · winners sh01=`20260805` · sh02=`88001` · receipt `receipts/anti-hijack-composition.json` · sample `deliverables/ep02-narrative-sample.mp4`
