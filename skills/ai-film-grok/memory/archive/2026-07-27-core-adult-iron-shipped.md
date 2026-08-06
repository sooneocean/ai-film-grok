# Memory · 2026-07-27 核心三条 IRON 已入库

**用户目标（长期）**

1. **肉戏尺度最大化**
2. **高动态性爱**
3. **衣服不回穿**：能脱就脱；剧情后已脱不得回穿  
4. **尺度兜底阶梯**（2026-08-06）：真办事做不到→全裸诱惑；全裸也画崩→**模型极限勿硬上**；禁假办事/回穿；见 [2026-08-06 短卡](2026-08-06-wardrobe-no-redress-fullnude-fallback.md)

## 代码真相（plugin ≥2.8.3）

| 需求 | 入口 | 硬底 |
|------|------|------|
| 尺度 / 时长 / 露 | `edit_policy` + `film_spec` write-spec | act+climax ≥**50%**；亲密 ≥60%；setup ≤20%；act≥undressed；climax=**bare**；phase 只升；`challenge_max_scale` |
| 起承转合 | `lint_sex_arc` · `sex_arc_strict`（max 默认开） | **前戏 → 插入 → 射出**；码 `SEX_ARC_*` |
| 不回穿 | `apply_wardrobe_continuity` + `lint_sex_wardrobe` | rank 单调；`HEAT_WARDROBE_RE_DRESS`；clamp on max/hot |
| still 不回穿 | `lint_still_source_policy` · write-spec `still_source_strict` · `register-still` | undressed/bare **禁** sole-ref 全装 cast |
| 高动态 | `i2v_motion_gate.py` · CLI `aifilm i2v-motion-gate` | 平常 mean≥**18**；肉戏≥**20**（目标 24）；收据 audit + final-gate |

**逃生阀（仅显式）**：`heat_scale:soft` / `adult_max_iron:false` / 各 `*_strict:false`。

## 文档

- [adult-scale-max-sex-arc lesson](../references/lessons-2026-07-27-adult-scale-max-sex-arc.md) — 尺度第一优先 + 四拍弧  
- [high-motion-style-lock](../references/lessons-2026-07-27-high-motion-style-lock-final.md) — 动能 + MEDIUM  
- [hard-defaults](../references/hard-defaults.md) · SKILL §9  
- 记忆短页：[adult-scale-max-sex-arc](2026-07-27-adult-scale-max-sex-arc.md) · [high-motion](2026-07-27-high-motion-style-final.md)

## Agent 裁决

```text
成人片默认：尺度 MAX > 完整办事弧 > 高动 meat≥20 > 画风/装饰
禁止：静默降 heat；砍插入/射出；脱后穿回；弱 raw/KB 装片；peak still 从全装 cast 重开
final 桌面：仅 i2v-final-gate ok
```

## 相关 commit（本机 main）

- `e60ab6f` high-motion gate  
- `0b7e180` quality always-on + still_source write-spec + forbidden tokens  
- `50904e1` sex_arc + register-still still gate · 2.8.3  

## 未做（非本目标）

- 未接 final 自动拷桌面副作用（gate 可调用，拷贝仍按既有 final 流程）  
- 像素末帧回穿 CV 完整自动化仍为 lesson 操作门  
- scene-sound / headroom 等旁路草稿未并入本记忆主链  
