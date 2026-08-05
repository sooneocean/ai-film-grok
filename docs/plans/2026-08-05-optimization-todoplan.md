# ai-film-grok 痛点分析 + 优化 TodoPlan（2026-08-05）

**Status:** ACTIVE · Wave 0 DONE (h3_primary 2.39.14) · Wave 2/3 partial landing  
**Full analysis:** session plan (same day). This file is the **repo single pointer**.

## 一句话

流程门禁已硬；主缺口是 **h3 until-empty 挂机**、**交付字幕契约机读**、**巨石/重复 I/O**。

## Waves

| Wave | Theme | Status |
|------|--------|--------|
| 0 | h3_primary 收口 → 2.39.14 | **DONE** |
| 1 | `h3 run-until-empty` + resume | TODO |
| 2 | post_route / caption-pixel / gate thrash 契约 | **IN PROGRESS** (2.39.15) |
| 3 | util read_json/run 去重 | partial (run_ffmpeg) |
| 4 | CLI audio/lipsync 按需抽 | optional |
| 5 | render_final / heat 有 churn 再拆 | optional |
| 6 | worktree/bak 卫生 | optional |

## 不做

自动批 pilot · 静默降 heat · 冲刺 monolith 1500 行 · 全自动毒镜 CV

## 默认 go

Wave 2 收口 commit → Wave 1 until-empty

See also: `2026-08-05-h3-primary-capacity.md` · closed ROI/workflow plans (do not re-open).
