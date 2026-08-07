# H3 官方 Prompt 方言对齐 · 优化 Todo Plan

**Status：** **P0–P2.5 SHIP · P3 receipt ✅ / reburn OPEN_OPS · 2026-08-07**  
**Plugin：** 2.40.92  
**上游 base：** https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md  
**上游 ref：** https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md  
**基线 import 板：** [2026-08-07-h3-official-prompt-import-todoplan.md](2026-08-07-h3-official-prompt-import-todoplan.md)（O0–O3）  
**实现：** `skills/ai-film-grok/scripts/media/h3_official_prompt.py`  
**Vendor pin：** `skills/ai-film-grok/references/vendor/minimax-h3/`

---

## 结论

产线 IR → 官方 GUIDE 同构英文 rewrite。默认 **auto**（对白 official / high legacy / 其余 official）。  
本板在 O0–O3 MVP 上对齐官方结构：T2VA 禁 Picture、运镜词典、多说话人、FL/L 对齐、validate 硬门、official 禁 2V stage / legacy FLF·R2V 尾部拼接。

---

## 波次状态

| 波次 | 内容 | 状态 |
|------|------|------|
| **P0** | unpark 编译器 + T2VA bug + 禁 2V/legacy 尾缀 + tests | ✅ |
| **P1** | Base：align / shot 语法 / 运镜 / 对白 / sound+music / validate | ✅ 核心 |
| **P2** | Ref2VA 多 ref labels + media_pack 深合并 + detailed densify | ✅ |
| **P3** | combo family / receipt 字段 / 二次 canary | 🟡 receipt+compile ✅；reburn OPEN_OPS |
| **P4** | 本文档 + memory + hard-defaults 指针 | ✅ |
| **P5** | L2VA 产线入口 / 默认全 official | ⬜ 可选 |

---

## 开法

```bash
export AIFILM_H3_PROMPT_DIALECT=official   # 强制官方
export AIFILM_H3_PROMPT_DIALECT=legacy     # 旧 [0s-2s]
unset AIFILM_H3_PROMPT_DIALECT             # auto
# validate 软逃（仅调试）
export AIFILM_H3_OFFICIAL_SOFT=1
```

测：`pytest skills/ai-film-grok/tests/test_h3_official_prompt.py -q`

---

## 已修缺口（对照 GUIDE）

| ID | 修法 |
|----|------|
| A2 T2VA 误写 Picture1 | T2VA 无 align、无 `<Picture 1>`；validate 拦截 |
| A3 方言 | official 禁 legacy `[0s-2s]`；可选 `[Shot N] At MM:SS.mmm` |
| A4 运镜 | type+amplitude+speed 句式映射表 |
| A5 对白 | 多 cue → S1/S2；`<d>[Mandarin\|English]`；VO 固定句 |
| A9 music | dsl/score/bgm_style → 描述，否则 N/A |
| C2 尾缀污染 | official 跳过 flf/r2v free-text append；legacy 才 2V stage |
| C4 validate | dialect=official fail-closed（`AIFILM_H3_OFFICIAL_SOFT=1` 逃） |

---

## 仍开

- P2.5 ✅ Ref2VA detailed soft 350–500；base I2VA half-second densify  
- P3.5 同 seed 二次 canary reburn（queue busy → OPEN_OPS）→ 是否翻高动 auto；人审口型  
- P2.6 ✅ official definitions 已吸收 duty；legacy 路径仍可 append clause  

---

## 非目标

- 8 个官方风格 skill 整包  
- 忙卡抢 submit  
- 只比 mean promote  
