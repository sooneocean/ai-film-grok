# HyperFrames 转场受控启用策略

> 2026-07-23 · ai-film-grok × hyperframes-animation  
> **母法**：continue 接戏缝永远 hard match-cut；HF 转场只能装饰场景硬切或片头片尾。  
> 来源规则：`hf-remotion-capability-matrix.md:36-39`

## 一句话

| 缝类型 | 允许的转场 | 禁止的转场 |
|--------|-----------|-----------|
| **continue 接戏缝**（字节续接） | `hard`（match-cut） | blur / push / whip / dissolve 等**全部禁止** |
| **场景硬切**（cut, 新场景入口） | `hard` / `match` / `fade` | whip（太快）/ grid（太花） |
| **段落转场**（章/幕之间） | `fade` / `dissolve` | — |
| **片头 / 片尾** | `fade` / `push` / `light leak` | — |
| **纯 MG 段**（无接戏） | 全目录放开（blur/push/whip/grid…） | — |

## 为什么

continue 接戏缝的 underlay 是 byte-identical 续接——镜头必须像同一个动作的延续。
任何 xfade（dissolve/blur）都会在两帧上糊出「重影」，观众读成「跳了一个动作」，
破坏字节接戏的连贯性（见 `lessons-2026-07-20-designed-post-fluency.md`）。

HF 转场目录（`hyperframes-animation/transitions/`）：blur crossfade、push、whip、
light leak、grid… 这些是**视觉糖衣**，不是接戏语言。

## HF 转场目录（只读盘点）

| 转场 | 风格 | 允许位置 |
|------|------|---------|
| `blur crossfade` | 两镜模糊交叠 | 段落转场 / 片头片尾 / 纯 MG |
| `push` | 新镜把旧镜推出 | 片头 / 场景硬切（非接戏） |
| `whip` | 快甩过渡 | 纯 MG / 音乐节拍点 |
| `light leak` | 光斑扫过 | 段落 / 片头片尾 |
| `grid` | 网格切片 | 纯 MG（勿用于剧情） |

## Agent 决策树

```
两个 shot 的 chain_mode == "continue" 且同一 beat？
  ├─ 是 → hard match-cut（零转场），禁止任何 HF xfade
  └─ 否 → 看 cut_on
       ├─ "fresh"（新场景入口）→ 可 fade / match / push
       ├─ 幕间 / 章间 → fade / dissolve
       └─ 片头片尾 → 放开 HF 转场目录
```

## 落地

转场判断在 `edit_policy.py` 的 `build_xfade_filter_graph`：
- `chain_mode == "continue"` → 强制 `intent="hard"`（concat，零 xfade）
- 场景硬切 → `intent="soft"` 可选 `DEFAULT_XFADE_STYLE` 轮转
- HF 的 CSS/JS 转场只作用在 **designed-post 层**（片头/片尾/字幕条），不盖接戏 plate

## 相关

- [hf-remotion-capability-matrix.md](hf-remotion-capability-matrix.md) — HF/Remotion 能力矩阵
- [lessons-2026-07-20-designed-post-fluency.md](lessons-2026-07-20-designed-post-fluency.md) — 接戏缝规则
- [lessons-2026-07-20-cut-silk-bilingual.md](lessons-2026-07-20-cut-silk-bilingual.md) — 剪辑语法
- [lessons-2026-07-20-title-double-burn.md](lessons-2026-07-20-title-double-burn.md) — 片头叠字
