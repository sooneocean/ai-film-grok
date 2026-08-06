# P0 · 构图防抢走 · multi-seed anti-hijack（2026-08-05 · 荒岛 ep02）

> **用户原话**：
> 1）第三个分镜 ok 但是前两个都不对啊 请优化重生  
> 2）**要避免抢走问题在犯 顺手优化掉**
>
> **片根**：`AI FILM SPACE/0804/huangdao-99-series/ep02`  
> **关联**：[speaker-frame](../memory/2026-08-04-speaker-frame-gate.md) · [shot-variety](lessons-2026-07-29-shot-variety-anti-boring.md) · [huangdao silk](lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md) · hard-defaults「构图防抢走 IRON」

## 现象（观众读到什么）

| 镜 | 台词/意图 | 错误赢家像素 | 正确 |
|---|---|---|---|
| sh01 | 澜汐对白开场「你醒了。」 | 沙俯视 + 脚印铺满 / 男头点缀 | 澜汐脸 CU 主读 |
| sh02 | 澜汐存在 + 林辰 | 男胸/躯干 CU 填满画面 | 女主可读 two-shot / MS |
| sh03 | （用户 OK） | — | 保留 |

门禁可绿：white0、native 音量、motion mean 都过 → **仍是错片**。绿灯 ≠ 主体对。

## 根因

| 层 | 发生了什么 |
|---|---|
| **选片尺子错** | multi-seed / shortlist 只比 mean_volume、white 底、motion mean，**不看构图主体** |
| **still / prompt 漏毒** | 开场 still 或 `framing: establishing environment` 把沙滩 env 喂进 I2V → 模型继续沙/脚印 |
| **dsl 与 shot_size 漂移** | 作者 `shot_size=close-up`，`dsl.camera.shot_size=medium` + env framing → 推理 want 类错、I2V 偏 env |
| **假阳性「干净」** | 早期 scorer 只标 sandish 米色；脚印纹理 `top_std` 偏高时 **漏标 hijack**（须兼 skin≈0 + 低中心对比） |

## 铁律（后面不要再犯）

1. **禁止** 只按 white0 / mean_volume / motion mean promote multi-seed 赢家。
2. **对白开场 / speaker 脸镜**：拒 **沙俯视、脚印铺满、纯 env 顶替脸**；中心须有可读肤色/脸对比。
3. **女主存在镜**：拒 **男胸/躯干 CU 填满**（torso_risk）；优先 two-shot 或女主主读。
4. **有干净备选时，hijack take 永不写入 manifest / narrative**。
5. **still 先对**：speaker 对白镜 still = 该角色脸 photoreal；禁 anime sheet / 俯视沙盘当 first frame。
6. **infer want 优先 `shot_size` 顶层**，勿让漂移的 `dsl.camera` 把 face 判成 env MS。

## 机读

| 入口 | 路径 |
|---|---|
| 模块 | `scripts/composition_anti_hijack.py` |
| CLI | `aifilm anti-hijack --root …`（`--shots` / `--promote`） |
| 自动 | `select-shortlist` demote + promote 拦截；`score_take_for_pk` 扣分 |
| 收据 | `receipts/anti-hijack-composition.json` · `receipts/anti-hijack-score.json` |
| 测 | `tests/test_composition_anti_hijack.py` |
| 逃生 | `AIFILM_SKIP_ANTI_HIJACK=1` |

打分要点：`sandish`（顶半高亮低色差）· `skin`（中心暖肤+对比）· `torso_risk`（中亮顶暗）· face 类 `skin<0.15` 硬 demote。

## 片例处置（ep02 v12）

- sh01 winner **seed 20260805**（alt 20260812）；拒 42 / 7777 / 99001  
- sh02 winner **seed 88001**  
- sample：`deliverables/ep02-narrative-sample.mp4` · 回执 `ep02-narrative-v12-anti-hijack.json`

## 一句话规则

> **以后 multi-seed 选 take：先 composition anti-hijack，再比 mean/音量；沙脚印与男胸抢女主 = 死 take，有备选绝不 promote。**
