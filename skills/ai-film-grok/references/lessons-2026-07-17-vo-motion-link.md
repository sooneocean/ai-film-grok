# 实战：动态与口白脱节 / 看两三镜就腻（2026-07-17 · 仪玄·密室余温）

## 用户反馈（原话意译）

- 影片**动态跟口白的连结度低**
- **大概看两三个片段就腻**
- **没有连贯的优势**（不像一条戏往前走，像色气幻灯片）

## 现象对照

| # | 现象 | 根因 | 规则 |
|---|---|---|---|
| 1 | 旁白说「门落锁 / 金扣松 / 勒皮带」，画面却是通用 blink+breath+push-in | 微动注入与 motion QA 把「能过 gate」当成「戏」；**主动作被 filler 淹没** | **口白·动作锁**：`nar` 的动词/物件 = `dsl.action` 的主动词 = `dsl.motion` 的**首要**可见运动 |
| 2 | 2–3 镜后腻 | 景别全是 CU/半身、运镜全是 slow push-in、身体全是 idle 微动 | **三镜防腻**：任意连续 3 镜，至少在 2 维上变化（景别带 / 主动词 / 机位轴） |
| 3 | 无连贯优势 | 距离阶梯只写在 `emotional_arc` 文案，画面未按远→中→贴阶梯走；道具不回访 | **视觉阶梯 + 母题回访**：shot_size 序列可读；≥1 道具/签名件跨 ≥3 镜 |
| 4 | soft 叠化汤 | 几乎全 soft join，没有硬切标点 | 60s 片至少 **1 hard / 5 soft** 节奏点 |
| 5 | 说书人变成「氛围诗」 | `nar` 只写感觉不写「这一秒看见什么在动」 | 中段镜 `nar` = **动作新闻**；余韵镜才写诗 |

## 口白·动作锁（一句话）

> 观众闭着眼听旁白，应能猜到这一镜画面在动什么；睁开眼应立刻对上。

### 写法公式

```
nar:    「[物件] + [动词] + [一句后果/色气]」
action: 英文主动词 + 物件（与 nar 同事件）
motion: **先写主动词可见过程**，再写 blink/breath 等 filler（静戏除外）
```

| 弱（密室余温式） | 强 |
|---|---|
| nar 门一落锁 + motion soft blink, hair, push-in | nar 门一落锁 + action hand turns latch shut + motion **latch turn, hand leave metal**, then blink |
| nar 金扣一松 + motion breath blink | action **unhooks gold buckle, coat slips shoulder** + motion buckle fingers, coat slide |
| 连续 4 镜 CU 脸 soft smile | MF 全身门 → CU 侧脸转头 → MS 解扣 → ECU 锁骨呼吸 → 低机位俯压 |

### 谁可以以微动为主

| beat | 主运动可以是微动？ |
|---|---|
| sensory / reaction / afterglow | **可以**（仍建议绑定 nar 感官词：呼吸/指尖/泪） |
| hook / approach / action | **不可以**；微动只能垫在主动作后 |

## 三镜防腻（agent 自检）

任意 `shot[i..i+2]` 至少满足 **2/3**：

1. **景别带**变化（full/medium/close 三档里换档，不只 medium↔medium full）
2. **主动词**不同（turn latch ≠ head turn ≠ unhook ≠ lean-in ≠ belt pull）
3. **机位轴**不同（eye / low / high / profile / POV）

连续 3 镜全是「慢推 + 眨眼 + 呼吸」→ 视为 **MOTION_MONOTONY**（write-spec soft / preflight soft）。

## 连贯优势（不是多加镜）

连贯 = 观众感到「上一秒的后果在这一秒还在」：

1. **距离阶梯可见**：shot_size rank 大致远→近（允许 1 次拉远呼吸）
2. **服装状态可递进**：外套扣→松→肩滑→半脱（写在 action，不靠换服）
3. **签名道具回访**：玄鸦 / 金蝶扣 / 门闩 至少 3 镜出现
4. **轴线稳定**：无故不左右跳轴

## 与既有规则的关系

- **不推翻**「禁止 mouth-speaking」「短旁白」「微动过 motion gate」
- **修正优先级**：主动作可见性 **>** 微动凑分 **>** 氛围诗
- motion QA 失败时：先加强**主动作幅度**，再堆 blink（见 lessons kei §12）

## Agent 改稿清单（用户说「腻 / 不连贯 / 口白对不上」）

1. 打印每镜：`nar | action | motion 首 12 词 | shot_size`
2. 标出无主动词的镜 → 重写 action/motion
3. 标出连续同构 3 镜 → 改景别或机位或动词
4. 重 still + I2V **只动问题镜**，不必整片重渲
5. final 再审：听旁白能否指认画面动作

## 本片索引

工程：`…/yixuan-hot-chamber-60s`  
成片技术成功但叙事体验失败 → 本 lesson；skill 补 VO-bind + monotony soft lint。
