# Lessons 2026-07-20 — 运镜防腻 + 转场有节奏

> 承接 [lessons-2026-07-17-vo-motion-link.md](lessons-2026-07-17-vo-motion-link.md)、[shot-motion.md](shot-motion.md)。  
> 口令：**转场 re-final 立刻见效；运镜改 I2V 才变画面。**

## 一句话

60s 竖片最容易死在「全 soft fade」和「三连 slow push-in + blink + breath」——转场用 hard 断点 + 每缝不同 xfade；运镜每镜只押一条主轴。

## 现象 → 规则

| # | 现象 | 根因 | 以后做 |
|---|------|------|--------|
| 1 | 转场没新意 / soft soup | 全 soft + 单一 `fade` | `transition_intents` 混 hard/soft/hold；**`transition_styles` 每缝不同**（不写则 write-spec 自动轮转） |
| 1b | **接戏了仍糊/不顺** | continue 已 **byte 复用末帧** 却仍 soft dissolve | **hard match-cut**；叠化会双影。见 [continuity_chain.md](continuity_chain.md)「转场与 match-cut」 |
| 2 | 运镜没新意 | 每镜都 push-in + blink + breath | 连续 3 镜 ≥2 维变化；机位轴：dolly / pan / locked / ECU / pull-back 轮换 |
| 3 | 改了 motion 画面没变 | 只改 film-spec | **转场** re-`final` 即可；**运镜像素** 必须 requeue I2V |
| 4 | hard 切也像 dissolve | 全局一个 style | `transition_styles[i]` 对齐 soft/hold 缝；hard 位占位，ffmpeg 走 concat |

## film-spec 推荐形

```json
{
  "transition_sec": 0.30,
  "transition_default": "soft",
  "transition_style": "dissolve",
  "transition_intents": ["hard", "soft", "hard", "soft", "hard", "soft", "hard", "hold", "hold"],
  "transition_styles": [
    "fade", "smoothleft", "hblur", "dissolve", "smoothup",
    "hblur", "smoothright", "dissolve", "fadeblack"
  ]
}
```

- `transition_intents` / `transition_styles` 长度 **= n_shots − 1**  
- hard 位的 style 字符串只是占位（不进 xfade）  
- write-spec：不写 styles → `suggest_transition_styles`；不写 intents → `suggest_transition_intents`（含更多 hard 断点）

## 运镜主轴菜单（`dsl.camera_axis` + motion）

| `camera_axis` | 适用 beat | 文案关键词 |
|------|-----------|------------|
| `dolly_in` | hook, sensory | continuous slow dolly-in on subject |
| `pan_with` | approach, reaction | horizontal pan-with-subject, no push-in |
| `locked` | action 细节 | camera static locked-off, only body/prop moves |
| `ecu_hold` | sensory | tight hold, micro-tremble only, no push-in |
| `low_lean` | action 压迫 | low angle lean-in then stop |
| `pull_back` | afterglow | gentle pull-back then hold |

write-spec **自动轮换**轴（避开最近 2 轴）；lint：`CAMERA_AXIS_FLAT`。  
**禁止**任意连续 3 镜都以 `slow push-in` + `soft blink` + `breath` 开头。  
**禁止** continue 缝 soft（`enforce_continue_hard_joins` 强改 hard）。  
升级复盘：[lessons-2026-07-20-transition-motion-v2.md](lessons-2026-07-20-transition-motion-v2.md)。

## 代码入口

| 能力 | 文件 |
|------|------|
| per-join xfade styles | `edit_policy.build_xfade_filter_graph(join_styles=…)` |
| auto styles | `suggest_transition_styles` · film_spec write-spec |
| 硬/hold 建议 | `suggest_join_intent`（hook→action hard 等） |
| soft lint | `lint_vo_motion_link` → MOTION_MONOTONY / SIZE_FLAT / SOFT_SOUP |

## Agent 清单

- [ ] write-spec 后看 `_vo_motion_link` / `transition_styles`  
- [ ] 每条镜间缝都有 `transition_ops[i]`：hard cut 也必须是明确的剪辑操作，不是缺省值
- [ ] `transition_ops[i].continuity_class == continue` 时：`picture.base=hard_cut`、`duration_sec=0`、HF overlay 保持 `none`
- [ ] final 日志出现 `styles=[…]` 且不全是 fade  
- [ ] 用户抱怨运镜没变 → 说明须 re-I2V；先交付转场新版  
- [ ] 色气 60s：约每 2 soft 至少一个 hard；尾 1–2 hold  

## 实战样例

`yixuan-hot-chamber-60s`：9 缝 hard/soft 交替 + hold 尾；styles 混 smoothleft/hblur/dissolve/fadeblack；final 已 re-render。
