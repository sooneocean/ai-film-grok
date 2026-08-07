# Visual 阶段卡

先验后生：静帧/身份/状态/几何未过闸 → 禁 I2V。  
**H3 日课**：[h3-core-day.md](h3-core-day.md) · 铁律正文：[hard-defaults.md](../hard-defaults.md)

## 本阶段必做

| 纪律 | 命令 / 红线 |
|------|-------------|
| 素材链 | L0 style → L1 cast → L2 state → L3 still → L4 clip → L5 endframe |
| 领料单 | `generation_request` → `receipts/prompts/<id>.request.json`（restricted 缺 = hard） |
| 毒镜人证 | `register-still --anatomy-safe`；毒 still 禁 H3/I2V |
| **镜头分型** | `aifilm shot-lane --root` → setup/dialogue/meat/env/continue/`poison_blocked` + mode |
| **对白 still** | on_camera：speaker 脸 MCU/CU；禁 WS/fullbody 挂台词（register + preflight） |
| **首帧满幅** | h3 run / queue 硬拦 composition-fill（可 auto-remedy）；plan 显示 advisory |
| **静帧喂料否决（E1）** | fill/face/source 红 → dispatch **禁** `h3-run-next`；先 still-challenge / ensure_fill |
| **效果记分卡（E3）** | `ship-prep` → `receipts/effect-scorecard.json` + weak reburn；禁 pure-mean promote |
| **续镜 endframe** | poison/回穿/满幅失败 → `safe_for_continue=false`；禁当下一镜 first |
| **分型 canary** | 8 镜类合成绿：`artifacts/2026-08-07-shot-lane-canary.json` · `test_shot_lane_canary_wave6` |
| 主武器 | 默认 `h3_primary`；`h3 run-next --max 5`；until-empty 须 `--i-own-the-gpu` |
| pilot | 用户批准后才 bulk；`pilot pack` three_look |
| 选片 | `select-shortlist` + anti-hijack；禁只比 mean |
| variety | 字段 + `variety_pixel`；改 pose 须 re-I2V |
| true-video | still 不进 timeline；hero=真 I2V/H3 |
| 高动 | mean≥18 / 肉戏≥20；MEDIUM LOCK cel |
| 末帧 | 卸装镜 endframe 不回穿；continue 字节 promote（smash 勿盲） |

## 谁喂谁（一行）

`still_source` + `generation_request` → Grok/H3 I2V·FLF·R2V；T2V 仅无脸 env。

## 毒镜 SOP（5 行）

① still/clip 见毒或 `anatomy_safe=false` → ② archive → ③ Qwen/still-challenge 修 → ④ `register-still --anatomy-safe` → ⑤ 才 `h3 run`。

深入：[weapon-lane-matrix](../weapon-lane-matrix.md)（含 **lane id**）· [shot-lane plan](../../../../docs/plans/2026-08-07-shot-generation-lane-todoplan.md) · [material-fidelity-loop](../material-fidelity-loop.md) · [h3-max-effect](../lessons-2026-08-04-h3-max-effect.md) · [anti-hijack memory](../../memory/2026-08-05-composition-anti-hijack.md)
