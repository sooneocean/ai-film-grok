# ai-film-grok 痛点分析 + 优化 TodoPlan（2026-08-05）

**Status:** ACTIVE · Waves 0–2 / until-empty / gate-slim **SHIPPED** (through **v2.39.20**)  
**Repo pointer** for optimization sequencing. Session plan has the full pain map.

## 一句话

流程门禁 + **h3_primary** + **until-empty 挂机** + **caption_path/pixel** 已落地；下一刀是 **真片过夜 canary**、material fidelity 实跑、巨石仅 churn 时再拆。

## 痛点（摘要）

| 类 | 曾卡 | 现状 |
|----|------|------|
| 产能 | 云配额 vs 5090 时间 | `h3_primary` + `h3 cycle --until-empty` |
| 交付 | 字幕双烧 / 假绿 | `post_route` + `caption-pixel-check` + soft no-SRT |
| 吞吐门 | gate thrash | machine-lane / gate slim |
| 工程 | 巨石 CLI / 重复 I/O | 部分抽离；按需继续 |
| 证据 | still≠prompt 返工 | Material Fidelity M0–M4 代码在仓 |

## Waves

| Wave | Theme | Status |
|------|--------|--------|
| 0 | h3_primary 收口 | **DONE** 2.39.14 |
| 1 | `h3 cycle --until-empty` + capacity-plan | **DONE** 2.39.16 |
| 2 | post_route / caption-pixel | **DONE** 2.39.15；soft SRT **2.39.20** |
| 3 | util run_ffmpeg / FilmError | partial |
| 4 | gate slim / pilot h3 modes | **DONE** 2.39.17 |
| 5 | cli_pilot extract | **DONE** 2.39.19 |
| M | Material Fidelity M3–M4 | **DONE** 2.39.18 |
| next | 真片 `until-empty` canary · worktree 卫生 | open |

## 不做

自动批 pilot · 静默降 heat · 冲刺 monolith 1500 行 · 全自动毒镜 CV

## 默认 go（真片）

```bash
export AIFILM_I2V_PROFILE=h3_primary
aifilm write-spec --root "<film>"
# pilot GO 后：
aifilm h3 capacity-plan --root "<film>"
aifilm h3 cycle --root "<film>" --until-empty --execute
```

See: `2026-08-05-h3-primary-capacity.md` · `2026-08-05-material-fidelity-loop.md` · closed ROI/workflow plans.
