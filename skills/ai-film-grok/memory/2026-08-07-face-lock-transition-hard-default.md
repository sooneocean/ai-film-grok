# 锁脸必要 + 剪辑转场默认 hard（2026-08-07）

**原话意图：** 锁脸是必要的；剪辑层转场还要优化。

## 三句

1. **有定妆就有刷脸**：`cast_masters` 存在时，缺 enroll/audit 或 enroll 缺口 → preflight **硬红**（不再只 soft）。  
2. **接戏缝永远 hard**；转场策略/export read-back **默认 hard**；soft 同风格连跑 = 粥（`HF_TRANSITION_SOFT_SOUP`）。  
3. **旧片逃生**：`face_identity_soft:true` / `transition_policy_soft:true`；或 env skip（须记账）。

## 清单

- [ ] 立项日 enroll-bible + audit → `verified`  
- [ ] continue 缝 intent=hard；soft 风格轮转  
- [ ] 旧片要 soft 时显式写 soft 字段，勿静默降门  

## 链

- plan: `docs/plans/2026-08-07-codebase-opt-face-transition-todoplan.md`  
- hard-defaults 表行 · `gates/production_gates.py` · partner/identity-gen memory  
