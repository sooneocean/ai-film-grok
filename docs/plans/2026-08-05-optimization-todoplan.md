# ai-film-grok 痛点分析 + 优化 TodoPlan（2026-08-05）

**Status:** ACTIVE · Waves 0–2 / until-empty / gate-slim **SHIPPED** · canary dry **PARTIAL** (2026-08-05)  
**Repo pointer** for **ops throughput waves** (this file).  
**Strategy pointer (director + engineer residual):** [2026-08-05-strategy-director-engineer-upgrade.md](2026-08-05-strategy-director-engineer-upgrade.md)  
**Structure residual (大石 internal peels):** [2026-08-05-residual-monolith-w4-todo.md](2026-08-05-residual-monolith-w4-todo.md) · owner [project-module-refactor](2026-08-05-project-module-refactor.md) (W0–W5 package SHIPPED · internal peels optional)

## 一句话

流程门禁 + **h3_primary** + **until-empty 挂机** + **caption_path/pixel** 已落地；**dry canary 已过**；真烧 GPU 过夜仍待人确认 5090 idle。后续双镜头升级与 OPEN 队列见 strategy 档，勿把本档 SHIPPED 波次当绿野重开。

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
| next | 真片 `until-empty` canary · worktree 卫生 | **PARTIAL** execute path ran · stop=`capacity_not_ready` · full drain open until 5090 free · `artifacts/2026-08-05-s53-until-empty-canary.json` |

## Canary log

- **2026-08-05 AF7 final**: real execute s_cu i2v · takes 14→16 · drain PARTIAL · 

- **2026-08-05 dry**: film `skills/.../h3-angles-runthrough` · pending=2 · ETA≈18m · `priority_ok` · until-empty stop=`dry_run_pass_execute`  
  - receipt: `artifacts/2026-08-05-h3-until-empty-canary.json`  
  - memory: `memory/2026-08-05-h3-until-empty-canary.md`  
  - worktree: pruned 2 prunable entries
- **2026-08-05 AF7 execute**: same film · capacity blocked · stop=`capacity_not_ready` · jobs_ran=0 · takes 14→14  
  - receipt: `docs/reports/2026-08-05-h3-until-empty-canary-af7.json`  
  - memory: `memory/2026-08-05-af7-until-empty-execute-canary.md`  

## 不做

自动批 pilot · 静默降 heat · 冲刺 monolith 1500 行 · 全自动毒镜 CV

## 默认 go（真片过夜）

```bash
export AIFILM_I2V_PROFILE=h3_primary
aifilm write-spec --root "<film>"
# pilot GO + 5090 idle 后：
aifilm h3 capacity-plan --root "<film>"
aifilm h3 cycle --root "<film>" --until-empty --execute
```

See: `2026-08-05-h3-primary-capacity.md` · `2026-08-05-material-fidelity-loop.md` · closed ROI/workflow plans.
