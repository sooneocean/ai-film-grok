# Lesson 2026-07-21 · 首帧坏 = 整段坏（Keyframe First-Frame Poison）

> **片例**：`velvet-stage-dual` 成片 ~33s  
> **用户原话**：「33秒那个首帧坏了 导致整个片段都坏了 请记取教训修正此问题 以后不要再犯」  
> **定位**：`shot13`（锁腿 insert · ~29.6–35.7s）  
> **P 码**：**P0 可交付** · P1 身份/结构 · Visualize → Generate  

## 现象

- 成片约 33s 进入 insert 蒙太奇后，**整段**画面结构崩（多指、肢体融合、中间「长出」不合理形体）。  
- 不是字幕问题、不是转场 xfade 糊接——**毒源在 I2V 的第 0 帧 = keyframe still**。  

## 根因（铁律）

```text
I2V 首帧 ≈ keyframe 静帧
静帧解剖学/构图坏 → 模型把坏结构「演」满 6s → 整 clip 不可救
```

| 失败链 | 本片证据 |
|---|---|
| still 手指数/关节已怪 | shot13 静帧双手按腿，指过长、关节糊 |
| 复杂交叠身体（双人无头 insert） | 两躯干+四腿+多手，模型易融合 |
| register-still 只看「像 cast / 有运动」 | **未做解剖学 QA** |
| I2V 后 motion_score 仍可能过门 | 结构坏但像素在动 → **QA 漏检** |
| 直接进 Editor selects | 33s 整段炸给观众 |

**抽象**：`motion_ok` ≠ `structure_ok`。能动但多指/融合 = **仍 fail**。

---

## 硬规则（F1–F7 · 首帧门禁）

| # | 规则 |
|---|---|
| **F1** | **首帧 = 交付帧**：register-still 前必须当「成片冻帧」审，不是草图 |
| **F2** | **解剖学清单**（全勾才 register）：双手 **5 指**清晰；无多余肢体；无躯干/腿融合；头/肩若入画比例正常；无破面/糊成一团的「第三物体」 |
| **F3** | **高风险构图降级**：双人无头 insert、多手交叠、腿缠死 → 优先改成 **单主体清晰 insert**（一只手+一截腿 / 门闩 / 指节攥布）或半身可辨双人 |
| **F4** | **I2V 前硬停**：静帧 F2 fail → **禁止** `image_to_video` / queue；先 `image_edit` 修结构或重抽 still |
| **F5** | **I2V 后复检首帧**：抽 clip `t=0` 与 `t=0.5s`；若相对 still 出现多指/融合/崩坏 → `fail --reason other` 或 re-I2V，**禁** register-clip approved |
| **F6** | **成片抽帧门**：final 后对每镜起点 ±0.3s 抽帧；任一段首帧结构坏 → 该 shot **必换**，不得只靠 re-final 蒙混 |
| **F7** | **insert 不等于可以脏**：蒙太奇 insert 更要干净——观众只看 1–2 秒局部，错指更扎眼 |

## Agent 操作清单

```text
register-still 前：
  [ ] 读图：手数、指、腿数、有无融合/破面
  [ ] 高风险构图？→ 简化再生成
  [ ] No text / 发色锁 仍执行

I2V 后 / register-clip 前：
  [ ] ffmpeg 抽 first frame + 0.5s
  [ ] 对比 keyframe：结构是否继承且未崩
  [ ] motion_score 与 structure 双过才 approved

final 后：
  [ ] 按 timeline 每镜起点抽帧（含 ~33s 类中段）
  [ ] 坏 → 修 still → re-I2V → re-register → re-final
```

## 反例 / 正例

| 反例 | 正例 |
|---|---|
| 双人无头、四手抓腿的 insert 直接 I2V | 单手攥丝绒特写 / 清晰单腿锁 + 一只正常手 |
| 手指 6–7 根仍 register | 修到 5 指再 register |
| motion_score=3 但「能动」就过 | 结构 fail 一票否决 |
| 用户指出 33s 坏了才回头 | final 自检每镜起点 |

## 与既有规则关系

- 不替代 [发色硬锁](lessons-2026-07-21-hair-color-lock.md) / [禁 shot 水印](lessons-2026-07-21-no-shot-watermark.md)  
- 与 [consistency.md](consistency.md) 定妆验收并列：**结构 QA 是 P0**  
- motion 狠动词见 [shot-motion.md](shot-motion.md)；**先结构正确再加狠动作**  

## 本片修复动作

1. 废弃毒化 `shot13` clip  
2. 重做 **结构干净** 的锁腿/攥布 insert still（简化构图）  
3. re-I2V + 首帧复检 + 替换 selects + re-final  
