# Lessons · 资深剪辑语法（反呆板线性）

> 2026-07-20 · 用户要求：剪辑区块像资深电影剪辑，不被呆板线性限制  
> 映射 **P2 P3 P4 P5** · 权威全文 [editorial-craft.md](editorial-craft.md)

## 一句话

**接缝有句法，不是只有 soft dissolve。**  
write-spec 生成 `edit_craft[]` → intents/styles；continue 仍 hard；soft 连跑自动砸 `contrast_cut`。

## 代码入口

| 函数 / 字段 | 作用 |
|---|---|
| `suggest_edit_craft` / `suggest_edit_crafts` | beat×chain×scene → craft |
| `edit_crafts_to_intents` / `edit_crafts_to_styles` | craft → FFmpeg 层 |
| `_punctuate_soft_run` | 防 soft 汤 |
| `film-spec.edit_craft` · `_edit_craft_plan` | 可审计剪辑计划 |
| `transition_fluency: cinematic` | 新 fluency |

## 不可宣称

- 写了 soft 全片 = 电影感  
- dissolve 盖 continue = 丝滑接戏  
- 只改 craft 不 re-final = 剪辑已更新  
- craft = 真·闪回时间轴（闪回要在 Lens 阶段改镜序）
