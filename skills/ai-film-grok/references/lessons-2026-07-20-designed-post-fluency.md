# 设计后期补流畅度（HyperFrames / Remotion · 2026-07-20）

**问题**：I2V 接戏 + hard match-cut 后，成片仍「分段感」——用户要的是观感丝滑，而不只是姿势对齐。  
**解法分层**：像素动能在 **I2V + visual_fit + mid-action cut**；**观感胶水** 用 HyperFrames / Remotion 做字幕/片头/轻叠层——**不能**用设计后期冒充 I2V 或 dissolve 盖断裂。

## 三层分工（硬边界）

| 层 | 工具 | 解决什么 | 禁止 |
|---|---|---|---|
| **A. 戏** | Grok still / I2V + continuity chain | 动作串接、字节首帧、切在动中 | Ken Burns 静图当戏 |
| **B. 拼** | FFmpeg `final`（`visual_fit: vo` + hard） | VO/BGM/板长、match-cut 时间轴 | soft 叠化盖接戏缝 |
| **C. 设计后期** | **HyperFrames** 或 **Remotion** | 字幕节奏、片头片尾、安全区、轻叠层「观感连续」 | 重排戏像素伪装流畅；**双烧字幕**；**双烧标题**（plate 有字 + 设计字） |

**标题双烧（2026-07-20 · 用户验收「效果很好」）**：designed-post 默认 `plate-cards blank` + `subs off`。专文：[lessons-2026-07-20-title-double-burn.md](lessons-2026-07-20-title-double-burn.md)。

```
I2V chain (byte promote + mid_motion)
  → final --post-engine ffmpeg  (visual_fit=vo, hard joins)  → plate
  → final --post-engine hyperframes|remotion                 → 设计成片
  → compose-preview → review-final
```

或一键（内部仍先 FFmpeg plate 再设计引擎）：

```bash
"$AIFILM" final --root "<root>" --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge \
  --compose-preset auto --require-preview
```

## HyperFrames 能补什么「顺」

改 HTML 前 load：`/hyperframes` + `/hyperframes-core`（+ animation 若加动效）。

| 可以 | 做法 | 不可以 |
|---|---|---|
| 字幕入出与 VO 对齐 | underlay + `caption_clock_offset=0` | 字比画面晚一整 title 段（multiclip 时钟错用） |
| 片头/片尾短而稳 | preset `ecchi-rnb` / `minimal`；title_dur 1.0–1.4s | 3s+ 黑场拖节奏 |
| 安全区 + 底部字幕条 | 统一 caption 样式，减少「字跳戏」 | 每镜换字体换位置 |
| 轻叠层（ vignette / 暖色 grade ） | 全片一致 CSS，跨缝连续 | 每缝换滤镜像换模 |
| Studio 预览调字幕 | `compose-preview` | 预览里 Ken Burns 静图当正片 |

**接戏缝上**：视频底轨保持 plate 的 hard cut；**不要**在 HF 里对 underlay 再套 xfade。

## Remotion 能补什么「顺」

改 `Film.tsx` 前 load：`/remotion-best-practices` + `/remotion-captions`。

| 可以 | 做法 | 不可以 |
|---|---|---|
| 帧级字幕 | `public/captions.json` + Caption 组件；与 package `film_timeline` 对齐 | 手写随机 start 与 plate 脱节 |
| 片头 Sequence 短 spring | 200–400ms 入场，不挡第一戏帧 | 长 spring 拖戏 |
| 多轨：video underlay + captions + grade | underlay 播整条 plate | Sequence 每镜重挂 clip 却丢掉 byte 链时间 |
| Studio 调参 | `compose-preview --engine remotion` | 未 npm install 却宣称已渲 |

```bash
"$AIFILM" final --root "<root>" --post-engine remotion --npm-install \
  --tts-backend edge --music-mood rnb --compose-preset auto
```

## 推荐产品路由（agent）

| 成片目标 | post-engine | 备注 |
|---|---|---|
| 最快技术验收 | `ffmpeg` | 烧录字幕；接戏检视用 |
| **默认设计交付（推荐）** | **`hyperframes`** | 字幕/片头最稳；Studio 快 |
| 字幕实验 / React 组件 | `remotion` | 首次 `--npm-install` |
| 双看 | `export-compose --engine both` 后分别 render | both 只自动渲 HF |

**continue-chain 片** 默认建议：

1. plate：`visual_fit: "vo"` + `transition_intents` 全 hard  
2. 设计：`--post-engine hyperframes --compose-preset auto`  
3. 先 `compose-preview` 再 render（可 `--require-preview`）

## package 字段（export 写入）

`compose/composition-package.json` 含 `fluency`：

```json
"fluency": {
  "visual_fit": "vo",
  "video_join_policy": "hard_match_cut",
  "continue_chain": true,
  "recommended_post_engine": "hyperframes",
  "designed_post_may": ["captions", "title_end", "grade_overlay", "studio_preview"],
  "designed_post_must_not": [
    "ken_burns_as_story",
    "dissolve_over_byte_identical_joins",
    "replace_i2v"
  ]
}
```

Agent 改 compose 时 **读此字段**，勿在 underlay 上加接戏缝 dissolve。

## 验收

- [ ] plate 接戏：hard + 动能（action-fluency）已过  
- [ ] 设计成片字幕不双烧、时钟 underlay=0  
- [ ] 无 Ken Burns 静图当戏  
- [ ] `review-final` 七维含 style/subs/dead-air  
- [ ] 未把 export-compose 成功当成交付  

## 相关

- [post-compose.md](post-compose.md)  
- [continuity_chain.md](continuity_chain.md)  
- [lessons-2026-07-20-action-fluency.md](lessons-2026-07-20-action-fluency.md)  
- [lessons-2026-07-20-audio-compose.md](lessons-2026-07-20-audio-compose.md)  
