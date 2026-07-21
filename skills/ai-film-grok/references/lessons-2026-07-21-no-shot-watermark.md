# Lesson 2026-07-21 · 禁止画面烧 `shot` 字样（P0 可交付）

> **片例**：`velvet-stage-dual`（丝绒双姝）  
> **用户原话**：「上面的 shot 字样没有清干净 这个致命错误不要再犯 写入教训」  
> **症状**：成片 / 关键帧角落出现 `shot11`、`anime keyframe shot05`、`Production cast master v2` 等工程字  
> **映射**：**P0 可观测交付** · Visualize 层 · Select 验收  

## 根因

1. **Prompt 把工程 ID 当画面描述**：写了 `keyframe shot11` / `shot05 still` / `Production cast master v2` → 模型当可见文字画进图。  
2. **register-still 只看脸/运动**，**不查四角水印** → 脏 still 进 I2V → 成片必脏。  
3. **I2V 会继承** keyframe 上的字；后期字幕再叠 = 工程字 + 字幕双脏。  

## 硬规则（T1–T6 · 致命）

| # | 规则 |
|---|---|
| **T1** | **画面内禁止任何工程字**：`shot##` · `keyframe` · `cast master` · `v1/v2` · `lookbook` · `pilot` · `production` · 文件名 · 英文调试 caption |
| **T2** | **Prompt 禁写可被画出来的 ID**：不要写 `shot11 keyframe`；用「本镜」「this frame」「vertical 9:16 still」描述用途，**ID 只留在文件名/JSON** |
| **T3** | **每镜 still prompt 必含干净句**：`No text, no watermark, no caption, no labels, no logos, no shot numbers, clean production frame only.` |
| **T4** | **register-still 前硬检**：目视或 OCR 四角+底边；发现 `shot`/`keyframe`/版本字 → **identity/style fail**，禁 register、禁 I2V |
| **T5** | **脏了只修 still**：`image_edit`「Remove all corner/edge text watermarks; keep scene identical; no new text」→ 复检 → 再 I2V；**禁止**带着脏 keyframe 出 bulk |
| **T6** | **定妆/lookbook 同规**：cast master 上不得有 `Production cast master v2` 等字；有则先 scrub 再 lock-style |

## Agent 操作清单

```text
生成 still 前：
  - prompt 不出现 shot01/shot11/keyframe shotXX 等可印字串
  - 末尾固定 No text / no watermark 句

register-still 前：
  - 扫四角与底边
  - 命中工程字 → 不 register

成片前（pilot / final）：
  - 抽帧再扫一遍；成片有 shot 字 = 交付失败，回修 still+I2V
```

## 反例 / 正例

| 反例（会烧字） | 正例 |
|---|---|
| `Vertical 9:16 anime keyframe shot11. BOTH cast…` | `Vertical 9:16 anime production still. BOTH cast… No text, no watermark, no labels.` |
| `Production cast master v2 for Astra` | `Clean full-body cast master portrait of Astra. No text, no captions.` |
| 看见角落 `shot11` 仍 register | 先 scrub 再 register |

## 与双烧关系

- 字幕 / 片头是 **后期设计层**（VO 旁白、标题卡），合法。  
- **`shot##` 工程水印**不是字幕，**一律非法**。  
- plate-cards blank 管的是标题双烧，**管不掉** still 上已画死的 shot 字。  

## 关联

- [consistency.md](consistency.md) §1c 画面零工程字  
- [hard-defaults.md](hard-defaults.md)  
- [production-discipline.md](production-discipline.md)  
- P0 principles.md  
