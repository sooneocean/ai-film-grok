# HyperFrames / Remotion 能力盘点（ai-film-grok 适配）

> 2026-07-20 · 给 agent 的**能用 / 不用 / 谁来画**矩阵  
> 母法 **P5 分层表达**：设计后期补观感，不替代 I2V / 字节接戏。

## 一句话

| 引擎 | 在本 skill 里干什么 | 默认交付 |
|------|---------------------|----------|
| **HyperFrames** | underlay 整条 plate + 片头/片尾 + 字幕叠层 + Studio 预览 | **推荐** `final --post-engine hyperframes` |
| **Remotion** | React 帧级组件、逐词字幕、参数化 variant；首次需 npm | 明确选择时的替代 owner，不与 HF 同片叠加 |
| **FFmpeg plate** | VO/BGM/转场/空白 pad；**设计后期时不烧字不烧字幕** | 中间层，不是最终观感层 |

**归属规则**：FFmpeg 负责戏与声音；每集只由 HyperFrames 或 Remotion 其中之一负责正式设计叠层。
`engine=both` 仅双导出对照，不能产生两个正式 final。完整交接与门禁见
[post-compose.md](post-compose.md#后期引擎归属合约p0)。

---

## HyperFrames（能做什么）

来源：`/hyperframes` · `/hyperframes-core` · `/hyperframes-animation` · `/hyperframes-cli`

| 能力 | 本 skill 用法 | 状态 |
|------|---------------|------|
| HTML composition + `data-start/duration` | `export-compose` → `compose/hyperframes/index.html` | ✅ 已接 |
| underlay 整条 `film_final` | layout=underlay；与 SRT 同时钟 offset=0 | ✅ 已接 |
| multiclip 每镜 I2V | 无 plate 时 fallback | ✅ 已接 |
| 片头 / 片尾 card + GSAP 入场 | title/end section + gsap timeline | ✅ 已接 |
| 设计字幕条（圆角底 · preset） | `.caption-text`；ecchi-rnb / minimal | ✅ 已接 |
| **中英双字幕** | `caption_mode: zh_en` + `.cap-zh` / `.cap-en` | ✅ 2026-07-20 |
| plate-cards blank（无烧字 pad） | 防标题双烧 | ✅ 已接 |
| Studio 预览 | `compose-preview` | ✅ 已接 |
| check / render CLI | `compose-render --engine hyperframes` | ✅ 已接 |
| 统一 vignette / grade 叠层 | CSS overlay 全片一致 | ✅ 轻量 |
| 场景转场 catalog（push/blur/whip…） | **禁止**用在 continue 字节缝的 underlay 上 | ⚠️ 仅允许非接戏缝 / 纯 MG |
| Registry blocks / 3D / shader | 不默认进交付 | ❌ 非 hard path |
| 内嵌 TTS / 音乐生成 | 旁白仍 edge/voicebox；BGM 仍 aifilm | ❌ 不替代 |

### HF 转场目录（只读盘点 · 勿默认启用）

`hyperframes-animation/transitions/`：blur crossfade、push、whip、light leak、grid…  
**ai-film-grok 规则**：byte-identical continue 缝 **永远 hard match-cut**；这些 HF 转场只能装饰**场景硬切**或片头片尾，不能盖接戏。

---

## Remotion（能做什么）

来源：`/remotion-best-practices` · `/remotion-captions` · remotion-markup / render

| 能力 | 本 skill 用法 | 状态 |
|------|---------------|------|
| `OffthreadVideo` underlay | `Film.tsx` + media-copy-plan | ✅ 已接 |
| Sequence 片头/片尾 | titleFrames / endFrames | ✅ 已接 |
| `@remotion/captions` JSON | `public/captions.json` | ✅ 已接 |
| **双行中英字幕** | caption text `zh\nen` + `whiteSpace: pre-line` | ✅ 2026-07-20 |
| npm bootstrap | `--npm-install` | ✅ 已接 |
| Studio / preview | `compose-preview --engine remotion` | 部分 |
| 帧级组件 / 逐词字幕 / 数据驱动 variant | 明确选择 Remotion owner 时实现 | ⚠️ 高级；改前 load skill |
| Lambda / SaaS render | 不默认 | ❌ |
| 自动转写 Whisper | 旁白来自 film-spec nar，不自动 ASR | ❌ |

---

## 谁负责「丝滑」

| 问题感 | 正确层 | 错误做法 |
|--------|--------|----------|
| 动作跳 / 姿势断 | A：I2V + promote 字节 + mid_motion | dissolve 糊两帧 |
| 一镜一顿、VO 跟不上 | B：`visual_fit: vo` + hard plate | 拉 loop 视频 |
| 片头叠字、字幕双烧 | C：blank pad + designed captions | 有字 plate underlay |
| 镜间「像两段不同片」 | **剪辑语法 + 设计胶水**（见 cut-silk 课） | 在 continue 缝 xfade underlay |
| 国际观众看不懂 | C：`caption_mode: zh_en` + `nar_en` | 改 TTS 成英文（除非用户要求） |

---

## Agent 决策树

```
交付默认 → final --post-engine hyperframes
  plate: subs off + plate-cards blank
  captions: caption_mode zh | zh_en
  transitions: transition_fluency silk (auto)
  continue 缝: hard only
需要 React 特有组件 → remotion + --npm-install，并由它单独拥有正式设计层
只要技术验收 → ffmpeg（会烧字/烧字幕）
```

## 相关

- [lessons-2026-07-20-cut-silk-bilingual.md](lessons-2026-07-20-cut-silk-bilingual.md)  
- [lessons-2026-07-20-designed-post-fluency.md](lessons-2026-07-20-designed-post-fluency.md)  
- [lessons-2026-07-20-title-double-burn.md](lessons-2026-07-20-title-double-burn.md)  
- [post-compose.md](post-compose.md)  
