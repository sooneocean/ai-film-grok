# H3 官方 Prompt 方言对齐 · 优化 Todo Plan

**Status：** **P0–P3.5 SHIP · 2026-08-07**  
**Plugin：** 2.40.95（pending bump）  
**上游 base/ref：** MiniMax HF VIDEO_PROMPT_WRITING_GUIDE_{base,ref}_en.md  
**实现：** `scripts/media/h3_official_prompt.py`  
**P3.5 证据：** `skills/ai-film-grok/artifacts/2026-08-07-h3-official-p35-canary.json`

---

## 结论

产线 IR → 官方 GUIDE 同构 rewrite。**auto 默认**：对白 / R2V / 多 ref / **high densify → official**；逃生 `AIFILM_H3_HIGH_MOTION_OFFICIAL=0` 回 high→legacy。

---

## P3.5 真烧结果（seed 202608074 · 6/6）

| family | legacy mean | official mean | winner |
|--------|-------------|---------------|--------|
| dialogue_cu | 10.23 | 0.83 | legacy（mean；结构仍用 official） |
| high_motion | 26.92 | **28.92** | **official**（Δ+2.0） |
| soft_portrait | 8.59 | 1.28 | legacy（mean；结构仍用 official） |

**政策：** high auto **翻 official**；对白/软保持 official 结构（不因 mean 回退 timeline）。人审口型仍要求。

Eval root：`artifacts/5090-evaluation/h3-official-ab-20260807/`

---

## 波次

| 波次 | 状态 |
|------|------|
| P0–P2 densify | ✅ |
| P3 R5 combo/preview | ✅ |
| **P3.5 真烧 canary** | ✅ 6/6 seed 202608074 |
| P5 L2VA 产线 | ⬜ 可选 |

---

## 开法

```bash
unset AIFILM_H3_PROMPT_DIALECT          # auto（含 high official）
export AIFILM_H3_HIGH_MOTION_OFFICIAL=0 # 逃生：high 回 legacy timeline
export AIFILM_H3_PROMPT_DIALECT=official|legacy  # 强制
```
