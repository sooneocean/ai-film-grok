# Lessons · 片头标题双烧（FFmpeg + HyperFrames）

> 2026-07-20 · 映射 **P5 分层表达**（设计后期只叠一次）  
> 样本：`xixifu-playful-night` 片头「戏服玩心夜」叠影  
> **用户验收（2026-07-20）**：修后「效果很好」→ 本条升为 skill 默认纪律，不是可选补丁。

## 一句话

**字幕双烧已挡，标题双烧也曾漏。**  
设计后期（HyperFrames / Remotion）时：plate 只留 **空白 pad**（`plate-cards blank`），**字只由设计引擎画一次**。

## 现象

片头同时出现：

1. **底层**：FFmpeg `mkcard_video` 烧进 plate 的整行标题  
2. **上层**：HyperFrames / Remotion 设计片头（半透明 gradient + 动效字）  

观感像「戏服玩心 / 夜」叠在半透明的「戏服玩心夜」上（用户截图确认）。

## 根因

| 层 | 行为 |
|----|------|
| `final --post-engine hyperframes` | 已默认 `--subs off`（防**字幕**双烧） |
| 但 plate 仍默认 `title_dur=1.5` **带字** | 与 HF 片头同窗叠放 |
| underlay | 整条 plate 作底，半透明设计层盖不住底层烧字 |
| 大字号 CSS | 短中文标题偶发换行（`戏服玩心` / `夜`）加重「像两套字」 |

字幕双烧有 gate（`burned_in` → 禁 underlay）；**标题双烧原先没有对称策略**。

## 正确分层（P5）

| 层 | 职责 |
|----|------|
| FFmpeg plate（designed-post） | VO / BGM / 转场 + **空白片头/片尾 pad**（保留时长给 SRT 时钟，**不烧字**） |
| HyperFrames / Remotion | **唯一**可读片头/片尾 + 用户认可的字幕样式（圆角底条 / ecchi-rnb 等） |
| `ffmpeg` 纯交付 | 仍可 `plate-cards text` 烧字（无设计后期时） |

```
final --post-engine hyperframes
  → render_final: subs=off, plate_cards=blank  （pad 有时长、无 glyph）
  → export-compose underlay + 设计 title/end/captions
  → HF render → register film_final
```

## 落点（代码 / 文档）

| 资产 | 行为 |
|------|------|
| `render_final --plate-cards blank\|text` | blank = 渐变 pad 无字 |
| `aifilm final --post-engine hyperframes\|remotion` | 默认 **`plate_cards=blank`** + **`subs=off`** |
| `aifilm final --post-engine ffmpeg` | 默认 `plate_cards=text` |
| HF CSS `.card h1` | `white-space: nowrap`（短 CJK 标题不拆行） |
| Remotion `Film.tsx` title | `whiteSpace: "nowrap"` |
| 本文 + [post-compose.md](post-compose.md) | 硬纪律 |

## 重渲（已验证样本）

```bash
"$AIFILM" final --root "…/xixifu-playful-night" --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge --compose-preset auto
# log 须含: plate_cards=blank, subs=off
# underlay 片头 pad：纯渐变无字；成片片头：单层清晰标题；字幕样式保留
```

## 验收清单

- [ ] underlay 在 t≈0.5s **无**烧录标题字  
- [ ] 成片片头只有 **一层** 清晰片名（无叠影）  
- [ ] 设计字幕样式仍在（圆角底条 / preset）  
- [ ] 旧有字 plate 不可「只改 HTML」冒充修好 → 必须 **re-final**

## 不可宣称

- 旧 `film_final` 若在有字 plate 上 underlay → 必须 **re-final**，不能只改 compose HTML。  
- `plate-cards blank` ≠ 去掉 title pad 时长（时钟仍可保留 1.5s 静场）。  
- 仅修标题 ≠ 可跳过 `review-final`。

## 相关

- [post-compose.md](post-compose.md)  
- [lessons-2026-07-20-designed-post-fluency.md](lessons-2026-07-20-designed-post-fluency.md)  
- [postproduction.md](postproduction.md)  
