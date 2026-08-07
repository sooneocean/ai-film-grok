# MiniMax H3 官方 Skill 逻辑导入 · Todo Plan

**Status：** **O0–O3 SHIP · Round-2 auto 默认 · 2026-08-07**  
**Plugin：** 2.40.84  
**上游：** https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing  

## 实现快照

| 波次 | 状态 |
|------|------|
| O0 vendor pin | ✅ `references/vendor/minimax-h3/` |
| O1 编译器 | ✅ `scripts/media/h3_official_prompt.py` |
| O2 接线 | ✅ `h3_workflow` dialect 双轨 |
| O3 真烧 6/6 | ✅ seed 20260807 · canary DONE |
| Round-2 auto | ✅ 对白 official / high legacy / 其余 official |
| Round-2 高动 densify | ✅ official 路径半秒姿态 + 强运镜 |
| 默认翻全 official | ⬜ 人审口型后；机读 high 仍偏 legacy |

## O3 mean（absdiff）

| family | legacy | official | winner |
|--------|--------|----------|--------|
| dialogue_cu | 1.10 | 1.24 | tie |
| high_motion | 20.67 | 18.58 | legacy |
| soft_portrait | 4.13 | 1.47 | legacy |

## 开法

```bash
unset AIFILM_H3_PROMPT_DIALECT
export AIFILM_H3_PROMPT_DIALECT=official
export AIFILM_H3_PROMPT_DIALECT=legacy
```

## 非目标

- 8 个官方风格 skill 整包进 agent  
- 忙卡抢 submit  
