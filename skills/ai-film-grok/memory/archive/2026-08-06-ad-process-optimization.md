# 副导演工序优化（2026-08-06 · 2.40.11）

**原话意图：** 当副导演盘点流程哪里可优化，三轴全做完。

## 三句

1. 真痛不在再贴 IRON，而在 **计划时长 vs H3 镜数**、**交付读回执肌肉**、**5090 真烧**。  
2. 本轮机读：density lift 回执、pilot 三看/debrief、shortlist 禁纯 mean、scale promote_ban、closeout 时长诚实。  
3. until-empty **OPEN_OPS**（无独占 GPU 不假绿）。

## 清单

- [x] A 时长 `finalize_duration_density` + adult-target-shot-lift  
- [x] B stages deliver/post 肌肉  
- [x] C pilot/shortlist/register  
- [x] D canary OPEN_OPS  
- [ ] 用户独占日真正 until-empty → queue_empty  

## 链

- plan: `docs/plans/2026-08-06-ad-process-optimization-todoplan.md`  
- hard-defaults 表行「副导演工序」  
- artifact: `artifacts/2026-08-06-ad-wave-d-ops-canary.json`  
