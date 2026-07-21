# 设计后期桥：HyperFrames / Remotion（双引擎闭环）

> **一句话**：Grok Imagine 拍戏（I2V + continuity chain）→ FFmpeg plate（`visual_fit: vo` + hard match-cut；非 continue 可 soft）→ **设计后期** HyperFrames / Remotion（字幕/片头/统一 grade/双字幕，补**观感**流畅）→ 仍须 `review-final` 七维。  
> **不能**用 HF/Remotion 替代 I2V，也**不能**在 underlay 接戏缝上再 dissolve 盖断裂。  
> 能力盘点：[hf-remotion-capability-matrix.md](hf-remotion-capability-matrix.md) · 丝滑剪辑+双字幕：[lessons-2026-07-20-cut-silk-bilingual.md](lessons-2026-07-20-cut-silk-bilingual.md) · 观感：[lessons-2026-07-20-designed-post-fluency.md](lessons-2026-07-20-designed-post-fluency.md)。

## 分工（硬边界）

| 层 | 谁做 | 工具 | 可否宣称成片 |
|---|---|---|---|
| 定妆 / still / I2V | ai-film-grok + agent | Grok `image_edit` / `image_to_video` | 否（只是素材） |
| 默认后期 | `aifilm final`（`--post-engine ffmpeg`） | FFmpeg + PIL 烧录字幕 | 技术渲染成功；正式交付还要 review-final |
| 设计后期（一键 · 推荐） | `aifilm final --post-engine hyperframes` | FFmpeg VO/BGM（**`subs off` + `plate-cards blank`**）→ export underlay → HF 唯一片头/字幕 → 注册 | 同上 |
| 设计后期（分步 HF） | `export-compose` → `compose-render --engine hyperframes` | HyperFrames CLI | 同上 |
| 设计后期（Remotion · 一键） | `aifilm final --post-engine remotion [--npm-install]` | 同上：plate **空白 pad** + 设计引擎画字 | 同上 |
| 设计后期（Remotion · 分步） | `export-compose --engine remotion\|both` → `compose-render --engine remotion` | 有 `node_modules` 则 auto render；否则 **`rendered: false` + next_steps** | 同上 |
| 外部/已渲 MP4 | `register-final --source … --post-engine remotion\|external` | 任意已混好的 MP4 | 同上 |
| 片头片尾纯 MG、无角色戏 | 可单独开 HF/Remotion 工程 | 见下方 skill load | 与本 skill 角色戏无关 |

### 禁止

- 用 HyperFrames/Remotion **Ken Burns 静图**冒充 I2V 成片。
- 跳过 pilot / cast master，直接在 compose 里「拼成片」。
- 未 `review-final` 七维 pass 就 `export-desktop`。
- 半片 Grok clip + 半片随机 FRW still 混进同一角色轨道。
- 声称 `export-compose` 成功 = 正式交付。
- 在 **byte_identical continue 缝** 的 underlay 视频轨上再套 xfade/dissolve「抹平」——会双影更糊；接戏用 plate hard cut。
- 设计字幕与 FFmpeg burned-in **字幕双烧**（`hyperframes|remotion` 时 FFmpeg 必须 `subs off`）。
- 设计片头与 FFmpeg burned-in **标题双烧**（`hyperframes|remotion` 时 FFmpeg 必须 **`plate-cards blank`**：pad 有时长、无字；字只由 HF/Remotion 画）。见 [lessons-2026-07-20-title-double-burn.md](lessons-2026-07-20-title-double-burn.md)。

## 流畅度：何时上 HyperFrames / Remotion

| 阶段 | 命令 | 作用 |
|---|---|---|
| 1 戏+链 | I2V + `extract-frame --promote-keyframe` | 像素接戏（见 continuity_chain） |
| 2 动能 | `final --post-engine ffmpeg` + `visual_fit: vo` + hard | 板长跟 VO、match-cut |
| 3 **设计后期（推荐默认）** | `final --post-engine hyperframes` | 字幕/片头/轻 grade → 观感连续 |
| 3b 实验 | `final --post-engine remotion --npm-install` | 帧级字幕组件 |
| 4 预览 | `compose-preview`（HF 或 `--engine remotion`） | 调字不调戏 |

**continue-chain 片默认路由**：plate 用 ffmpeg → 交付用 **hyperframes underlay**（不要停在裸 ffmpeg 烧录字幕）。  
package 内 `fluency` 字段声明 `recommended_post_engine` / `designed_post_must_not`——改 compose 前必读。

### HyperFrames 可做 / 不可做

| ✓ | ✗ |
|---|---|
| underlay 字幕与 plate 同时钟（offset=0） | multiclip 时钟错用导致字飘 |
| 短 title/end（~1–1.4s）；plate **blank pad** 上叠唯一设计字 | 长黑场拖节奏；plate 已烧字再 underlay |
| 全片统一 caption 样式 / vignette（用户喜好的圆角底条） | 每缝换滤镜换模感；FFmpeg 烧字 + 设计字双轨 |
| **中英双字幕** `caption_mode: zh_en` + `nar_en` | 把 TTS 改成英文冒充双字幕；缺 EN 硬 fail 交付 |
| Studio 调字幕 | Ken Burns 静图当戏；接戏缝 xfade underlay |

Load：`/hyperframes` + `/hyperframes-core`（+ `/hyperframes-animation` 若动效）。

### Remotion 可做 / 不可做

| ✓ | ✗ |
|---|---|
| 帧级 Caption + `public/captions.json` | 手写 start 与 film_timeline 脱节 |
| underlay 播整条 plate + 叠字幕轨 | 每镜重挂 clip 打乱 byte 链时间 |
| 短 spring 片头 | 长动画挡第一戏帧；未 npm 却宣称已渲 |

Load：`/remotion-best-practices` + `/remotion-captions`。

## Agent 技能加载矩阵（改 compose 前必读）

| 任务 | 加载 skill | 路径提示 |
|---|---|---|
| HyperFrames 总入口 | `/hyperframes` | `~/.agents/skills/hyperframes` 或宿主 hyperframes skill |
| 改 HF HTML / data-* 时序 | `/hyperframes-core` | composition contract、clip tracks |
| HF 动效 / GSAP | `/hyperframes-animation` | |
| HF CLI（check/preview/render） | `/hyperframes-cli` | |
| Remotion 总入口 | `/remotion-best-practices` | `~/.agents/skills/remotion-best-practices` |
| Remotion 字幕 | `/remotion-captions` | Caption JSON、TikTok-style |
| Remotion 组件 markup | remotion-markup | 在 remotion-best-practices 下 |
| Remotion render CLI | remotion-render | `npx remotion render` |
| 新建 Remotion 工程 | remotion-create | 仅当本包 npm install 不够用时 |
| 素材检索（可选） | `/media-use` | **不**覆盖 aifilm 声线锁 / rnb 默认 BGM |

**不要**在 agent 回复里现编 HyperFrames/Remotion 规范；先 load 上表 skill。

## 推荐命令（闭环）

### A. 一键设计成片（HyperFrames · 推荐）

```bash
"$AIFILM" final --root "<root>" \
  --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge
# 内部：
#   FFmpeg VO+BGM + SRT（subs=off，避免与 HF 字幕双烧）
#   → export-compose layout=underlay
#   → hyperframes check + render
#   → 无音轨时从 film_final 抽音轨混入
#   → register final_film (post_engine=hyperframes)
#   → final_complete 仍为 false，须 review-final
```

### B. 分步（先稳妥 FFmpeg，再设计）

```bash
"$AIFILM" final --root "<root>" --post-engine ffmpeg --tts-backend edge --music-mood rnb
"$AIFILM" export-compose --root "<root>" --engine both --layout underlay --force
"$AIFILM" compose-render --root "<root>" --engine hyperframes --layout underlay --quality standard
"$AIFILM" review-final --root "<root>" --approve ...
```

### C. Remotion（一键对称 HF + 分步）

```bash
# 一键（推荐 Remotion 路径）：与 hyperframes 对称，subs off 防双烧
"$AIFILM" final --root "<root>" --post-engine remotion --npm-install \
  --lipsync off --music-mood rnb --tts-backend edge --compose-preset auto
# → FFmpeg plate → export remotion → media-copy → npm install →
#   remotion render src/index.ts Film → audio mux → register (post_engine=remotion)

# 已装 deps：
"$AIFILM" final --root "<root>" --post-engine remotion --tts-backend edge --music-mood rnb

# 分步：
"$AIFILM" export-compose --root "<root>" --engine remotion --force
"$AIFILM" compose-render --root "<root>" --engine remotion --npm-install
# 未 bootstrap：{ "ok": false, "rendered": false, "next_steps": [...] }

# 手动：
cd "<root>/compose/remotion" && npm install
npx remotion render src/index.ts Film out/film_remotion.mp4
"$AIFILM" register-final --root "<root>" \
  --source "<root>/compose/remotion/out/film_remotion.mp4" \
  --post-engine remotion
```

**时间轴（与 HF 对齐）**：multiclip I2V 从 t=0 pack；underlay caption offset=0；export 写 `caption_clock_offset` 进 captions。  
**engine=both**：只 export 双引擎 + remotion media-copy + **渲 HF**；Remotion 不自动渲（见 steps.remotion_render.skipped）。  
**字幕实验（agent）**：改 `Film.tsx` 前 load `/remotion-captions`；主路径仍推荐 HyperFrames。

### D. 注册任意外部成片

```bash
"$AIFILM" register-final --root "<root>" --source "./out/custom.mp4" --post-engine external
```

## CLI 速查

| 命令 | 作用 |
|---|---|
| `final --post-engine ffmpeg` | 默认：烧录字幕成片 |
| `final --post-engine hyperframes` | 设计字幕闭环（FFmpeg subs off + HF） |
| `final --post-engine remotion` | 同上，走 Remotion（首次加 `--npm-install`） |
| `export-compose --engine hyperframes\|remotion\|both` | 写出 `compose/hyperframes` 与/或 `compose/remotion` |
| `compose-preview` | HF Studio（默认）；`--engine remotion` 起 Remotion Studio（需 npm install）；URL 未观测时 **ok=false** |
| `compose-render --engine hyperframes` | HF check→render→混音→register |
| `compose-render --engine remotion` | media-copy + auto-render **或** actionable next_steps |
| `register-final --post-engine remotion\|external\|…` | 外部/Remotion MP4 进 final_film 门禁 |

## Layout

| layout | 画面 | 何时 |
|---|---|---|
| `multiclip` | 每镜 I2V clip 拼时间轴 + 设计字幕 | 尚无 film_final，或要从 clip 重排 |
| `underlay` | 整条 film_final 作底 + 设计标题/字幕 | 已有 FFmpeg 成片（auto 默认） |
| `auto` | 有 final → underlay，否则 multiclip | 默认 |

## Compose preset（片头/字幕观感）

只影响 **标题卡 + 字幕条 + 轻动效**，不改 I2V、不改 BGM/TTS。

| preset | 观感 | 何时 |
|---|---|---|
| `auto` | 按 `sound_plan.mood` / `director_intent.tone` 推断 | **默认** |
| `ecchi-rnb` | 暖玫瑰叠层、字幕轻 blush 边、略大字 | mood=`rnb`/`soul`/`sensual` 或 tone 含色气/暧昧 |
| `minimal` | 干净黑底、细边字幕 | 非色气默认 / 显式指定 |

```bash
# 一键（推荐色气片）
"$AIFILM" final --root "<root>" --post-engine hyperframes \
  --compose-preset auto --tts-backend edge --music-mood rnb

# 显式
"$AIFILM" export-compose --root "<root>" --engine both --compose-preset ecchi-rnb --force
"$AIFILM" compose-render --root "<root>" --engine hyperframes --compose-preset minimal
```

HTML 根节点会写：`data-compose-preset`、`data-caption-clock-offset`。

### Caption 时钟（防字飘戏后）

| layout | offset | 原因 |
|---|---|---|
| `underlay` | **0** | 与 `film_final` / `out/final.srt` **同一绝对时间轴**；禁止再减 title pad |
| `multiclip` | `title_dur` | I2V 从 t=0 叠，package cue 仍按含 title 的 film_timeline |

## 产出目录

```
<root>/compose/
  package.json                 # export manifest (kind=ai-film-grok-compose-export)
  composition-package.json
  hyperframes/
    index.html                 # seekable data-* timing + media
    composition-data.json
    README.md
  remotion/
    package.json               # real npm package (remotion deps)
    remotion.config.ts
    tsconfig.json
    media-copy-plan.json
    src/Film.tsx + Root.tsx + index.ts
    public/captions.json + composition-data.json
    public/clips/              # after media-copy / compose-render
<root>/out/
  film_final.mp4               # 正式候选（register 后）
  film_hyperframes.mp4
  film_remotion.mp4            # remotion auto-render 时
  final.srt
  final-delivery.json
```

## 门禁

1. `export-compose` / `compose-render` 需要 **`clips_complete`**。
2. `register-final` / compose-render 注册会跑 **decode + motion + audio** 技术 QA。
3. 替换 final 会 **作废** 旧 `final_review`（写入 `final_review_stale`）。
4. `final_complete` 只在 `review-final --approve` 七维全 pass 后为 true。
5. 无音频时：compose-render 会从既有 `film_final` 或 VO/BGM stems 混轨；都没有则失败并提示先 `final`。
6. **双烧字幕**：`final --post-engine hyperframes|remotion` 时 FFmpeg 默认 `--subs off`。  
   另：**hard gate**——`out/final-delivery.json` 若 `subtitles.burned_in=true` 且 layout=underlay，`compose-render` **拒绝**（防 burn final + 设计字幕叠字）。覆盖：`--allow-burned-underlay`。
7. Remotion 未 bootstrap 时 **不得** 以 ok=true 假装已渲；必须 `rendered: false` + `next_steps`。
8. remotion media-copy **fail-closed**（计划条数不全则 error，不 silent ok）。

## Studio 预览（一键 + 回执）

```bash
"$AIFILM" compose-preview --root "<root>"
# → 缺 compose 时自动 export-compose；background Studio；打开浏览器
# → 写 receipts/compose-preview.json（+ compose/preview.json 指针）
# JSON: { "url": "http://localhost:3002", "receipt": "…/compose-preview.json", … }

"$AIFILM" compose-preview --root "<root>" --engine remotion --no-open
# → 需 compose/remotion/node_modules（先 compose-render --npm-install）
# → 默认端口 3003；写同一 receipt（engine=remotion）

"$AIFILM" compose-preview --root "<root>" --status
"$AIFILM" compose-preview --root "<root>" --stop
"$AIFILM" compose-preview --root "<root>" --no-open   # 只返回 URL + 仍写 receipt
```

### next / preflight

- `aifilm next`：clips 齐且无 final 时 **优先** `compose-preview`；有 receipt 后优先 `final --post-engine hyperframes`。
- `preflight` soft：`compose_preview_recommended`（未预览）、`remotion_not_ready`（已 export remotion 但未 npm install）。

### 强制先预览再渲

```bash
"$AIFILM" final --root "<root>" --post-engine hyperframes --require-preview
"$AIFILM" compose-render --root "<root>" --engine hyperframes --require-preview
# 缺 receipts/compose-preview.json → 失败并提示先 compose-preview
```

用户看过 Studio 后再 `compose-render` / `final --post-engine hyperframes`（默认不强制；要强制加 `--require-preview`）。

## 体验优化（默认行为）

| 点 | 行为 |
|---|---|
| doctor | `designed_post` 字段报告 npx/hyperframes；缺了**不**拦 ffmpeg final |
| status | 显示 `post_engine`、compose 是否已导出、final 摘要 |
| pilot | `pilot pick/report/score/approve` 三镜 scorecard 辅助（禁 agent 自批） |
| preflight / next | 教训体检 + 下一步唯一命令 |
| compose-preview | Studio URL + 系统浏览器自动打开 |
| final hyperframes | 先 preflight tooling；stdout **单一 JSON**（含 ffmpeg + compose）；subs off |
| Remotion render | node_modules 齐 → auto render+register；否则 ok=false + next_steps |
| 渲染进度 | hyperframes render **实时打到 stderr** |
| 磁盘 | 默认删除 `film_hyperframes_raw.mp4`（`--keep-raw` 保留） |
| multiclip 时间轴 | 镜头从 t=0 叠 I2V，片头/片尾半透明叠层（过 motion continuity） |
| 失败提示 | QA 失败时提示 composed MP4 仍在，可修后 register-final |

## 相关实现

- `scripts/export_composition.py` — 导出 HF HTML + Remotion 完整 package
- `scripts/compose_render.py` — HF/Remotion 渲染 + 混音 + 注册；`probe_remotion_readiness`
- CLI：`export-compose` / `compose-render` / `compose-preview` / `register-final` / `final --post-engine`
- 默认后期：`references/postproduction.md`
