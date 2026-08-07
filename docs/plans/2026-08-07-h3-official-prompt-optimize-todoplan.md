# H3 官方 Prompt 方言对齐 · 优化 Todo Plan

**Status：** **P0–P3 code R5 SHIP · reburn OPEN_OPS · 2026-08-07**  
**Plugin：** 2.40.94  
**上游 base：** https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md  
**上游 ref：** https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md  
**基线 import 板：** [2026-08-07-h3-official-prompt-import-todoplan.md](2026-08-07-h3-official-prompt-import-todoplan.md)（O0–O3）  
**实现：** `skills/ai-film-grok/scripts/media/h3_official_prompt.py`  
**Vendor pin：** `skills/ai-film-grok/references/vendor/minimax-h3/`

---

## 结论

产线 IR → 官方 GUIDE 同构英文 rewrite。默认 **auto**（对白/R2V/多 ref → official；high → legacy，除非 `AIFILM_H3_HIGH_MOTION_OFFICIAL=1`）。  
R5：combo official families + plan dry-run preview + on-screen text / `<scenetrans>`。

---

## 波次状态

| 波次 | 内容 | 状态 |
|------|------|------|
| **P0** | unpark 编译器 + T2VA bug + 禁 2V/legacy 尾缀 + tests | ✅ |
| **P1** | Base：align / shot 语法 / 运镜 / 对白 / sound+music / validate | ✅ |
| **P2** | Ref2VA 多 ref + densify | ✅ |
| **P3** | receipt + plan preview + combo R5 official families | ✅ 2.40.94 |
| **P3.5** | 同 seed 二次 canary reburn | ⬜ OPEN_OPS（5090 idle + 人审） |
| **P4** | 文档 / memory / hard-defaults | ✅ |
| **P5** | L2VA 产线入口 / 默认全 official | ⬜ 可选 |

---

## 开法

```bash
export AIFILM_H3_PROMPT_DIALECT=official   # 强制官方
export AIFILM_H3_PROMPT_DIALECT=legacy     # 旧 [0s-2s]
unset AIFILM_H3_PROMPT_DIALECT             # auto
export AIFILM_H3_HIGH_MOTION_OFFICIAL=1    # high 也走 official densify（实验）
export AIFILM_H3_OFFICIAL_SOFT=1           # validate 软逃（仅调试）

# combo R5 compile-only A/B
python3 -c "from h3_combo_eval import compile_family_author_prompt; print(compile_family_author_prompt('dialogue_mouth_official')[:200])"
```

测：

```bash
pytest skills/ai-film-grok/tests/test_h3_official_prompt.py skills/ai-film-grok/tests/test_h3_combo_eval.py -q
```

---

## R5 本轮交付（2.40.94）

| 项 | 说明 |
|----|------|
| combo families | `*_official` + `R5_OFFICIAL_COMBO_ORDER` / `round=5` |
| compile route | `prompt_format=official` → `compile_official_h3_prompt` |
| auto dialect | R2V / multi-ref → official；high opt-in env |
| GUIDE | onscreen `"text"` · multi-cue `<scenetrans>` |
| plan | `prompt_preview` + `receipts/prompts/<id>.h3.preview.txt` |
| preview API | `preview_official_h3_prompt()` |

---

## 仍开

- P3.5 同 seed reburn（mean + 人审口型）→ 是否默认 high→official  
- P5 L2VA 产线 mode 入口  

---

## 非目标

- 8 个官方风格 skill 整包  
- 忙卡抢 submit  
- 只比 mean promote  
