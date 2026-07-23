# P0 · 剪辑双播 / 怪断点（2026-07-23 · E病毒案）

## 现象
成片部分片段「跑了两遍」，或断在僵住、重复的末帧上。

## 根因
1. **I2V 源长固定 6s**，film-spec `duration_sec=7–8` + `visual_fit=slot` → stretch 目标 > 源。
2. `plan_stretch` 在 `target/src > 1.15` 时升级 **`stream_loop`** → 整段重播 = 「跑两遍」。
3. hook/action 禁 loop 时 **`MAX_FREEZE_PAD_NO_LOOP=1.25s`** 末帧克隆 → 像卡死/怪断点。
4. **软转场 0.26s xfade** + first-last promote 首尾同帧 → 转场叠影像双帧。
5. VO 实测 4–5.5s 却被 slot 拉到 8s + atempo，声画都空。

## 修复（代码）
| 项 | 改动 |
|----|------|
| `edit_policy.plan_stretch` | 短板 overshoot **钳制为一次播完**；禁 loop 默认扩到常见 dramatic_function；freeze cap 0.40s |
| `render_final.stretch_clip` | 尊重 `target_clamped`，同步 VO 时钟 |
| `render_final` visual_fit | `voice_coupled` 默认 **vo** 而非 slot |
| `edit_strategy` | soft_join 0.26→**0.12**；setup 也 prefer vo |

## Agent 规则
- I2V 6s 片：`duration_sec` 优先 **6**（或 ≤ clip），`visual_fit=vo`
- 禁止为「填满旁白空档」而 loop 画面
- continue / first-last 链：硬切微叠（≤0.06s），勿长 dissolve
- 出片前看 stretch 日志：`mode=loop` 在短片上 = 红灯

## 验收
`plan_stretch(6.04, 8.0)` → `setpts_pad` + clamp，**loops=0**  
`plan_stretch(6.04, 5.5)` → `setpts` 一次，无 freeze 长尾
