# Lesson 2026-07-24 · Adult max IRON（肉戏/脱衣/露点铁律）

> **用户原话**：「强制把肉戏比例拉到最高 尺度拉到最高 能脱衣就要脱衣 能露点就要露点 这是铁律 请写进插件逻辑」
> **P 码**：P0 产品 · 叙事刺激
> **互补**：sex-duration-floor · sex-undress-ladder · adult-max-playbook · hard-defaults

## 一句话

**秒数 ≥50% + 亲密 ≥60% + act 脱光 + climax bare + spice extreme + 自动抬升卸装 + 持续加压不泄火** = 铁律；不是建议。

## 持续挑战尺度最大（用户补强）

| 禁 | 必 |
|---|---|
| 中途 heat_phase 回退（act→foreplay/setup） | phase 只升：setup→foreplay→act→climax |
| act 后再写 setup 回避身体 | 进入 act 后只加压/换姿/加深 |
| climax 前 afterglow 收火 | 先 climax bare 再 afterglow |
| foreplay 连拖 >2 镜不升 act | 前戏短促，尽快进办事 |
| 只有 act 没有 climax | 必须办穿峰值 |
| 审核软化时降 heat_scale | 画面顶格 suggestive + VO/SFX 双轨补 |

码：`HEAT_ESCALATION_REGRESSION` · `HEAT_ESCALATION_STALL` · `HEAT_ESCALATION_NO_PEAK`  
字段：`challenge_max_scale`（max 默认 true）· 合入 `heat_arc_strict`

## 机器码

| 码 | 含义 |
|---|---|
| `HEAT_SEX_DURATION_LOW` | act+climax 时长 < 50%（hardcore 55%） |
| `HEAT_INTIMACY_RATIO_LOW` | 亲密镜比 < 60% |
| `HEAT_SETUP_RATIO_HIGH` | setup > 20% |
| `HEAT_SEX_WARDROBE_WEAK` | act 仅 partial |
| `HEAT_BARE_PEAK_MISSING` | 全片无 bare / climax 非 bare |
| `HEAT_WARDROBE_RE_DRESS` | 回穿 |
| `HEAT_ESCALATION_REGRESSION` | 中途泄火 / phase 回退 |
| `HEAT_ESCALATION_STALL` | 前戏/铺垫平台过长不加压 |
| `HEAT_ESCALATION_NO_PEAK` | 有 act 无 climax |

## 默认字段（max）

`sex_floor_strict` · `sex_wardrobe_strict` · `sex_vo_strict` · `heat_arc_strict` · `spice_level=extreme` · `sex_min_duration_ratio=0.50`

## 逃生阀

- 显式 `heat_scale: soft|medium|hot`
- `adult_max_iron: false` / `heat_arc_strict: false` / `sex_*_strict: false`（须用户同意，agent 禁私关）

## 验收

```bash
python -m pytest tests/test_adult_max_iron.py tests/test_hard_defaults.py -q
"$AIFILM" heat check --root "<film>"
```
