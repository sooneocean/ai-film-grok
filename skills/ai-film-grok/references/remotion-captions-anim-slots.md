# Remotion 字幕 + video-use 动画槽集成

> 2026-07-23 · ai-film-grok × remotion-captions × video-use  
> 母法 **P5 分层**：设计后期补观感，不替代 I2V / 字节接戏。

## D3 · Remotion TikTok 逐词字幕

`export_composition.py:1638` 已写 `public/captions.json`（`@remotion/captions` shape）。
当前默认双行中英（`caption_mode: zh_en`）。TikTok 逐词高亮是可选增强。

### 启用 TikTok 逐词高亮

在 `Film.tsx` 的字幕渲染部分，用 `@remotion/captions` 的 `createTikTokStyleCaptions`：

```tsx
import { createTikTokStyleCaptions, Caption } from "@remotion/captions";

// captions.json 已是 Caption[] shape（含 startMs/endMs）
const pages = createTikTokStyleCaptions({ captions, combineTokensWithinMilliseconds: 800 });

// 每个 page 渲染为一个 <Sequence>，逐词高亮用 page.tokens + useCurrentFrame()
```

**字幕后烧（video-use Hard Rule 1）**：字幕永远是 filter chain 最后一层。
ai-film-grok 的 `subtitle_cut_boundaries.py` + `subtitle_typesetter.py` 已保证这一点；
Remotion 路径由 `compose_render.py` 的 `plate_subtitles_burned_in` 门禁守卫。

### 字幕三维度

| 维度 | 选项 | 用途 |
|------|------|------|
| chunking | 1/2/3词/句 | 短视频快切 vs 叙事长句 |
| case | UPPER/Title/Natural | 风格 |
| placement | MarginV 35/60/80 | 快切贴底 vs 叙事留白 |

ai-film-grok 默认：`caption_mode: zh_en` + `subtitle_typesetter.py` 的 ASS 风格。
Remotion 路径可覆盖为 TikTok 风格（需手改 Film.tsx 或加 preset）。

---

## D4 · video-use 动画槽 → designed-post overlay 对接

video-use 的 `animations/slot_<id>/` 并行子 agent 产出 overlay clip，对接到
designed-post（HyperFrames/Remotion）的 overlay 入口。

### 路由规则

| overlay 来源 | 落位 | 守卫 |
|-------------|------|------|
| video-use 动画槽 | `overlays[].file` → `compose/<engine>/public/` | PTS-shifted（Hard Rule 4） |
| HyperFrames 内置动画 | composition HTML 内 `<div class="clip">` | seek-safe runtime |
| Remotion 内置动画 | `<Sequence>` / `<TransitionSeries>` | 帧级 deterministic |

### 防标题双烧（lessons-2026-07-20-title-double-burn）

- video-use 动画槽的 overlay clip **不带字幕**（字幕由 designed-post 统一烧）
- `compose_render.py:assert_underlay_not_double_burn` 守卫 underlay 不双烧
- 若 overlay 自带字幕：在 `merge_edls` 时标 `subtitle_conflict: true`，人工裁定

### 动画槽产物对接

video-use 子 agent 产出 `slot_<id>/render.mp4`（含 alpha 用 webm）。
对接方式：
1. `auto-cut` 的 EDL `overlays[].file` 指向 `render.mp4` 绝对路径
2. `merge_edls` 合并到主 EDL
3. `compose_render` 的 HyperFrames underlay / Remotion `<OffthreadVideo>` 引用

### 并行规则（video-use Hard Rule 10）

多动画槽必须并行（`Agent` 工具 spawn N 个子 agent），不是顺序。
ai-film-grok 的 `media_queue.py` 已是单并发队列——动画槽生成不走 media_queue，
直接子 agent 并行，产物落 `animations/slot_<id>/`。

## 相关

- [hf-remotion-capability-matrix.md](hf-remotion-capability-matrix.md)
- [hf-transition-policy.md](hf-transition-policy.md)
- [lessons-2026-07-20-title-double-burn.md](lessons-2026-07-20-title-double-burn.md)
