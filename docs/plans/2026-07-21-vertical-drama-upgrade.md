# 竖屏漫剧 Plugins + Skills 升级蓝图

> **状态**：Phase 0–4 已落地（**v1.5.0**；Phase 4 细分实现记录见 v1.4.8）  
> **日期**：2026-07-21（Phase1–4：2026-07-22）  
> **主对象**：`ai-film-grok` plugin v1.4.2  
> **关联**：`frw-manju`、`ai-film-pipeline`、`frwclaw-pro`、`hyperframes*`、`media-use`、`imagine`  
> **原则**：不全面重写；在现有八环 + film-spec + dispatch 上**增量**长成 Vertical Drama 系统  
> **最终验收一句话**：用户输入故事后，Agent 经可验证、可重跑、可追踪的 Plugins + Skills，产出含叙事/一致性/动态/声音/字幕/节奏的 9:16 漫剧 MP4

---

## 0. 执行摘要（结论先行）

| 维度 | 判断 |
|------|------|
| 能否做出 9:16 成片 | **Already Supported**（ai-film-grok 主路径已通） |
| 是否已是「竖屏漫剧系统」 | **Partially**——成片强、图模型弱、Skill 边界糊 |
| 最大结构债 | 单 Skill 巨无 prompt + CLI 命令混装；无正式 Skill Registry / Execution Graph / Episode·Beat 一等公民 |
| 改造策略 | **保留执行内核**（dispatch / media-queue / write-spec / final），**外挂 Graph + Registry + 契约**，按 Phase 1→9 增量迁移 |
| 不要做的 | 先写多 Agent 自治；先全面重写 film-spec；把 frw-manju TG 流水线硬并进 Grok 主路径 |

**建议 P0 工程顺序（用户确认后再改码）**：

1. **Skill Registry 清单 + 契约壳**（把现有 CLI 映射为 `skill_id`，不拆实现）  
2. **Vertical Drama Graph v0**（在 film-spec 旁增加 `drama-graph.json`，Episode/Beat 一等公民，Shot 仍兼容 film-spec）  
3. **Execution Graph 最小版**（dispatch 输出 `jobs[]` + dependencies，仍可一步一 `next_cmd`）  
4. **竖屏安全区 + productionMode 分流**（panel-animation vs I2V）  
5. 再扩 image.rank / motion.validate / multi-episode  

与并行中的 [codebase-optimization](./2026-07-21-codebase-optimization.md) **正交**：那份拆 CLI 单体；本份长产品能力。两者可同仓推进，避免同一文件大冲突。

---

# 1. Existing Plugin Architecture Audit

## 1.1 现有 Plugins（Grok Build）

| Plugin | 版本 | 角色 | 是否竖屏漫剧主路径 |
|--------|------|------|-------------------|
| **ai-film-grok** | 1.4.2 | 工作流容器：film-root 状态、八环 craft、media-queue、TTS/BGM、final/export | **是（主）** |
| grok-build-hud（installed） | — | 状态条 / quota | 辅 |
| 其它 | — | 非影音 | 否 |

## 1.2 相关 Skills（非 Grok plugin，但 Agent 会路由到）

| Skill | 路径 | 与主路径关系 |
|-------|------|--------------|
| **ai-film-grok** | `~/.grok/plugins/ai-film-grok/skills/ai-film-grok`（symlink `~/.grok/skills/ai-film-grok`） | **本体** |
| **imagine** | `~/.grok/skills/imagine` | 静帧/edit 规范 |
| **hyperframes*** | `~/.agents/skills/hyperframes*` | 设计后期 / 合成 |
| **media-use** | `~/.agents/skills/media-use` | BGM/SFX/TTS 解析 |
| **video-use** | `~/.agents/skills/video-use` | 已有片剪辑（非生成主路径） |
| **frwclaw-pro** | `~/.agents/skills/frwclaw-pro` | FRW 图/视频 API |
| **frw-manju** | `frwclaw-pro/frw-manju` | TG 漫剧 FSM（剧本→选角→配音→生图→合成），**另一栈** |
| **ai-film-pipeline** | `~/.agents/skills/ai-film-pipeline` | SOP 编排文档（偏 brief→spec），与 aifilm CLI 有概念重叠 |

## 1.3 Plugin 实际承担的职责（对照你 §3.1）

| 职责 | 现况 | 证据 |
|------|------|------|
| 专案状态 | ✅ film-root + receipts | `init` / `status` / `receipts/*` |
| Story Graph | ⚠️ 弱 | `film-spec.scenes[].shots[]` + director_intent；无 Episode/Beat 实体 |
| Asset Registry | ⚠️ 半 | style-bible / cast masters / state-index / register-still\|clip |
| Skill Registry | ❌ | 无；只有 CLI 子命令 + 巨型 SKILL.md |
| Provider 管理 | ⚠️ 半 | adapters/ + capability + i2v_provider + tts_backend |
| 任务编排 | ✅ 弱 DAG | `dispatch` 输出 next_cmd（线性） |
| Job Queue | ✅ | `media-queue` claim/complete/fail/requeue |
| 依赖关系 | ⚠️ | craft 环顺序 + hard_gates；非 JobDependency 表 |
| 版本控制 | ⚠️ | runtime-lock / style previous_versions；无 Revision 图 |
| 错误恢复 | ✅ 局部 | queue requeue、frw degrade、TTS fallback 策略 |
| 人工审核 | ✅ | pilot approve、review-final 七维 |
| 时间线 | ✅ | timeline.json + assemble + final |
| 最终渲染 | ✅ | FFmpeg plate + HyperFrames/Remotion |
| 汇出发布 | ⚠️ | export-desktop；无平台元数据包 |

## 1.4 架构形态（当前）

```text
User / Agent
    │
    ▼
SKILL.md（路由+硬门禁，~300 行主脊 + 60+ references）
    │
    ▼
aifilm CLI（aifilm_grok.py ~4622 行单体 + 模块）
    │
    ├─ dispatch / craft / next     → 工序状态机（八环）
    ├─ write-spec / film_spec      → 规格门禁
    ├─ bible / lock-style          → 视觉圣经
    ├─ media-queue + adapters      → 静帧/I2V 作业
    ├─ tts / audio-plan / sfx      → 声轨
    ├─ final / compose / review    → 成片与 QA
    └─ receipts/*.json             → 可追踪回执
```

**不是**「Planner Agent + 多 Specialist Skill 进程」；是 **「单 Agent + 强制 dispatch 读 next_cmd + 本地 CLI 门禁」**。对当前单机 Grok Build **足够且更稳**；目标态应在此之上加 Graph/Registry，而不是换成复杂多 Agent 运行时。

## 1.5 可保留 / 必须重构

| 类别 | 模块 |
|------|------|
| **Can Reuse（内核）** | dispatch、craft_spine、media_queue、write-spec 门禁、continuity/wardrobe/state-index、register-clip 链、final/review-final、adapters/grok_oauth*、edge TTS、audio_recipe |
| **Must Refactor（边界）** | 巨型 SKILL 能力清单 → Skill Registry；film-spec 兼做 Graph；next_cmd 线性调度 → Execution Graph 视图 |
| **Can Defer** | 多 Agent 自治、团队协作 UI、4K、长篇连载 CMS |
| **Do Not Merge Now** | frw-manju TG FSM（保留为可选 Provider/通道适配器） |

---

# 2. Existing Skills Inventory

> 说明：现状 **没有** 独立 skill 包（无 `script.normalize/SKILL.md` 这种）。下表是 **逻辑能力单元**，映射到现有命令/文档/脚本。

## 2.1 逻辑 Skill 清单（现状）

| 逻辑 skill_id | 现实现 | 输入（实质） | 输出（实质） | 验证 |
|---------------|--------|--------------|--------------|------|
| `story.intake`（弱） | Agent 读用户话 + init | 自然语言 | film-root + theme | 人工 |
| `story.normalize` | ❌ 无结构化 | — | — | — |
| `episode.structure` | ❌ 无多集 | — | 单片 film-spec | — |
| `scene.segment` | Agent 手写 scenes[] | brief | film-spec.scenes | write-spec |
| `beat.extract` | 文档/Lens；`dramatic_function` 近似 | Lens md | 镜级字段 | 软 |
| `character.extract` | Agent + bible | 文本/图 | style-bible.characters | bible lock |
| `character.bible.build` | `bible` / lock-style | 角色描述+cast | style-bible + masters | lock |
| `character.state.update` | wardrobe_state + state-index | 前镜状态 | cast-states/* | state-index check |
| `location.bible.build` | style-bible.locations（字符串级） | 文本 | 弱结构 | 弱 |
| `prop.track` | style-bible.props 字符串 | — | 弱 | 弱 |
| `shot.plan` | Agent + write-spec 注入 coverage | scenes | shots[] | write-spec lint |
| `panel.layout` | ❌ 无 Panel 实体；有 prompts/*.txt | — | prompt 文件 | — |
| `keyframe.plan` | state-index plan + first-last lesson | shots | keyframes 计划 | state-index |
| `keyframe.generate` | image_gen/edit + register-still | ref+prompt | still/keyframe | pilot/人审 |
| `continuity.check` | lint-continuity / continuity-chain / preflight | film-spec | lint json | hard/soft |
| `image.rank` | pilot scorecard（半自动） | 候选 | score | 人批 |
| `image.repair` | image_edit 手工 | 坏 still | 修图 | 人审 |
| `camera.motion.plan` | dsl.camera_axis / motion 字符串 | shot | 文本 | 软 |
| `image.animate` | media-queue + I2V（grok/frw） | keyframe | clip.mp4 | register + media_qa |
| `motion.validate` | media_qa / meaningful_motion 部分 | clip | 指标 | 部分硬 |
| `dialogue.adapt` | Agent 改 nar；VO 预算 | nar | nar≤55 字 | write-spec |
| `voice.cast` | vo_voice + voices.md | 角色 | 声线 id | 弱 |
| `voice.synthesize` | tts-rehearse / final TTS | nar | wav | 实测时长 |
| `subtitle.generate` | final 烧字 / caption_mode | nar | burn-in | review audio/subs |
| `sound.design` | sound_plan + make_sfx_bed | recipe | sfx | 软 |
| `music.plan` | audio_recipe + BGM mood | policy | bed | 软 |
| `timeline.compose` | write-spec seed + assemble | shots+clips | timeline | 时长 |
| `rhythm.evaluate` | edit_strategy / editorial-craft / heat arc | film-spec | 建议 | 软+部分 hard |
| `video.render` | final / compose-render | root | mp4 | doctor+ffprobe |
| `quality.inspect` | review-final 七维 + media_qa | final | scorecard | 人审 |
| `export.package` | export-desktop | final | Desktop 拷贝 | 文件存在 |

## 2.2 Agent 如何选择 Skill（现状）

```text
每回合 → aifilm dispatch --root
       → 读 craft_stage + next_cmd + agent_instruction + hard_gates
       → 只执行 next_cmd
       → 完成再 dispatch
```

- **有**：工序路由（八环）、机位路由（TTS/I2V/FRW）、硬门禁。  
- **无**：按 Skill 契约选实现、并行 Job 调度、Skill 失败自动换 Provider（仅有文档级 fallback）。

## 2.3 Skill Registry / Execution Graph（现状）

| 项 | 状态 |
|----|------|
| Skill Registry | **不存在** |
| Execution Graph（DAG） | **不存在**；仅有 craft 环 + next_cmd 线性建议 |
| Job 记录 | media-queue + receipts/*（按操作类型，非 skill_id） |

## 2.4 现有漫画/漫剧数据模型

```text
film-root/
  film-spec.json          # title, director_intent, scenes[{shots[{id,nar,dsl,...}]}]
  style-bible.json        # characters, locations, props, wardrobe
  timeline.json           # fps, w/h, shots[{id,duration}]
  prompts/<shot>.txt
  keyframes/ clips/ canonical/
  receipts/               # dispatch, pilot, tts, final, ...
  continuity_chain.md     # 长片可选
```

**关系**：`Scene → Shot` 扁平。  
**缺失一等公民**：Episode、Beat、Panel、MotionClip 结构化、DialogueLine 与 VoiceClip 分轨图、ProvenanceRecord、ExportManifest 完整包。

**Shot 已有强字段（可复用）**：`dramatic_function`、`duration_sec`、`wardrobe_state`、`heat_phase`、`dsl.*`（motion/camera_axis/chain_mode/viewpoint）、`shot_role`、`lipsync`。

## 2.5 Provider 与渲染

| 能力 | Provider | 备注 |
|------|----------|------|
| 静帧 | Grok Imagine（image_gen/edit / OAuth） | 主 |
| I2V | `grok_primary` 默认；FRW Seedance/LTX 可选 | Seedance 运营上暂关 |
| T2V 环境床 | FRW ltx-t2v | 无脸 |
| TTS | edge 默认；grok/voicebox/external/cosyvoice | |
| BGM | 库 rnb + 程序化；外部 music adapter | |
| SFX | 程序 bed + recipe | |
| 合成 | FFmpeg + HyperFrames + Remotion 可选 | |
| 分辨率 | 默认 720×1280 级；目标 1080×1920 需显式/升级 | timeline example 720×1280 |

## 2.6 失败重试 / 资产 / 一致性 / 版本 / UI

| 项 | 现况 |
|----|------|
| 失败重试 | media-queue fail/requeue；OAuth 429 仍需 hardening（见 optimization 计划） |
| 资产保存 | film-root 文件系统 + register 回执 |
| 一致性 | cast master、continue 末帧=下镜首帧、wardrobe 单调、发色锁、state photos |
| 版本 | style previous_versions；runtime-lock；无 Revision 树 |
| UI | HUD dispatch 短行；无完整执行图可视化 |

---

# 3. Plugin / Skill Responsibility Problems

1. **Skill 边界糊**：一切挤在 `ai-film-grok` 一个 skill + 一个 CLI；references 60+ 文件是「隐式 skill 库」，Agent 难机械发现。  
2. **Plugin 未做 Registry**：Plugin 有工作流，但没有「可枚举、可契约、可测」的 Skill 表。  
3. **数据模型以成片为中心，不以图为中心**：film-spec 强、Graph 弱；难以局部重跑「只重 beat 3 的 panel.layout」。  
4. **Panel 未一等公民**：漫画 panel 只存在于 prompt 字符串，无法 rank/repair 挂资产 ID。  
5. **Beat 未一等公民**：只有 `dramatic_function` / `story_beat` 字符串，节奏 Agent 难按 Beat 聚合。  
6. **生产模式未显式**：I2V 与静态运镜混在实践中，缺 `productionMode` 字段驱动路由。  
7. **Provider 泄漏风险**：film-spec 含大量 `frw_*` 字段（可用但违反你「核心模型禁止 provider-specific」的目标态）。  
8. **叙事入口弱**：无 `story.normalize` / 小说切集；依赖 Agent 临场拆。  
9. **多集/连载缺**：单 film-root = 单片。  
10. **Provenance 碎片化**：receipts 多文件，无统一 ExportManifest。  
11. **验证不统一**：有的 hard（write-spec）、有的人审（pilot）、有的软（节奏）；缺 Skill 级 `validate()` 契约。  
12. **与 frw-manju / ai-film-pipeline 概念重叠**：三套「漫剧/短片」SOP，Agent 易混路由。

---

# 4. Vertical Drama Gap Analysis

以最终 9:16 漫剧验收为准：

| 能力 | 分类 | 说明 |
|------|------|------|
| 接受一句创意 → 成片 | Partially | 能；但规范化弱 |
| 小说/剧本 intake | Missing | 无 normalize/FDX |
| 自动规划竖屏短集 | Partially | 单集；无 Episode 切分 |
| Scene/Beat/Shot 拆解 | Partially | Scene/Shot 有；Beat 弱 |
| 角色/场景 Bible | Partially | 角色强；场景/道具弱 |
| Shot 生产路线选择 | Partially | 实践有；字段/路由不全 |
| 9:16 Keyframe | Supported | aspect 默认竖屏 |
| 角色服装场景一致性 | Supported | 卸装/continue/state-index |
| I2V 重点镜 | Supported | grok_primary |
| 低动态漫画运镜 | Partially | compose/KenBurns 有限；非系统化 |
| 对白/旁白/字幕/SFX/BGM | Supported | 旁白主导；角色对白多轨弱 |
| 多轨 Timeline | Partially | 实为 shot 序列 + 混音轨 |
| Hook/节奏/高潮分析 | Partially | heat arc + editorial；非 rhythm.evaluate skill |
| 失败 Shot 局部重跑 | Supported | queue requeue + 单镜 regenerate |
| UI 执行状态 | Partially | HUD；无 Graph UI |
| 1080×1920 发布级 | Partially | 默认 720p 级；可升但非默认 |
| Story Graph + Provenance 包 | Partially / Missing | receipts 有；统一包无 |
| Panel 作为中间资产 | Missing | |
| Vertical 安全区强制 | Partially | framing/字幕；平台 UI 区不全 |
| Skill 执行记录（skill_id） | Missing | |
| Execution Graph 可视化 | Missing | |

### 漫画流程 → Shot 视频流程

- **可以转**：已是 Shot-based，不是纯 Panel 编辑器。  
- **缺的是**：Panel 挂在 Shot 下、静态运镜与 I2V 的显式分流、Beat 级节奏验收。

---

# 5. Target Vertical Drama Graph

## 5.1 原则

- **兼容优先**：`drama-graph.json` 为新真相；`film-spec.json` 继续作为「可执行成片投影」，由 `graph.project_to_film_spec` 生成/校验。  
- **ID 稳定**：所有节点 UUID 或 `ep01_sc03_bt02_sh01` 稳定 slug。  
- **锁定层**：`lockedDecisions` / human lock 禁止 Skill 静默改写。

## 5.2 目标实体（v1 必达 / v2 可延）

| 实体 | v1 | 映射现有 |
|------|----|----------|
| Project | 必 | film-root |
| Episode | 必（可 1 集） | 新；单集时 episode=film |
| Character / CharacterState | 必 | style-bible + cast-states |
| Location | 必（可薄） | style-bible.locations 结构化 |
| Prop | 可薄 | style-bible.props |
| Scene | 必 | film-spec.scenes |
| Beat | 必 | 新；从 dramatic_function 组升 |
| Shot | 必 | film-spec shots |
| Panel | 必（可 1 panel/shot） | prompts + still 元数据 |
| Keyframe | 必 | keyframes/ |
| MotionClip | 必 | clips/ |
| DialogueLine / VoiceClip | 必（旁白先行） | nar + tts |
| SubtitleCue | 必 | final 字幕轨 |
| SoundCue / MusicCue | 必 | sound_plan / BGM |
| Transition | 必 | transition_intents/styles |
| TimelineTrack | 可延 | timeline + 混音 |
| Revision / Approval | 必 | pilot/review receipts |
| ProvenanceRecord | 必 | 统一 receipts 索引 |
| ExportManifest | 必 | export 包 |

## 5.3 层级

```text
Project
└── Episode[]                    # v1 默认 1
    ├── CharacterState snapshots
    ├── Scene[]
    │   ├── Beat[]
    │   │   └── Shot[]
    │   │       ├── Panel[]      # layout 计划
    │   │       ├── Keyframe[]
    │   │       ├── MotionClip[]
    │   │       ├── DialogueLine[] → VoiceClip[]
    │   │       ├── SubtitleCue[]
    │   │       └── SoundCue[]
    │   └── Transition → next Scene
    ├── TimelineTrack[]
    └── ExportManifest
```

## 5.4 关键字段（Shot 增补，不破坏现有）

```typescript
// 在现有 shot 上 additive
productionMode: "panel-animation" | "single-keyframe-i2v" | "first-last-frame-i2v" | "text-to-video" | "composite";
verticalComposition: "top-subject" | "center-subject" | "bottom-subject" | "foreground-background" | "two-character-stack" | "three-layer-depth";
beatId: string;
panelIds: string[];
safeZoneProfile: "douyin" | "reels" | "generic"; // 默认 generic
```

## 5.5 竖屏安全区（默认 generic 1080×1920）

```text
Canvas: 1080 × 1920（导出目标；生产可 720×1280 再升）
Face band:     y = 20%–70%
Subtitle band: y = 68%–88%
Bottom UI:     ≥ 220 px
Side margin:   ≥ 72 px
```

实现：`schemas/safe-zone.schema.json` + framing_lint 扩展。

---

# 6. Target Agent Execution Graph

## 6.1 模型

保留 **单 Planner（Agent + dispatch）**，不引入多进程 Multi-Agent 运行时。

```text
User brief
  → Planner（Agent 读 Skill Registry + drama-graph 状态）
  → ExecutionPlan { jobs, dependencies, approvalGates, fallbacks }
  → dispatch 选择 READY 的 job（默认可并行标记，v1 仍串行执行）
  → Skill runner（CLI 或 python 函数）
  → Validator（skill 自带 + 全局 gate）
  → PASS → mark done；FAIL → requeue / 降级 / 人工
  → Assemble → Final QA → Render → ExportManifest
```

## 6.2 ExecutionPlan（v1 最小）

```json
{
  "projectId": "film-root-id",
  "targetAspectRatio": "9:16",
  "targetResolution": "1080x1920",
  "targetFps": 30,
  "targetDuration": 45,
  "jobs": [
    {
      "id": "job_shot03_i2v",
      "skillId": "image.animate",
      "nodeRef": "shot:shot03",
      "status": "ready|running|done|failed|blocked",
      "dependsOn": ["job_shot03_keyframe", "job_bible_lock"],
      "provider": "grok",
      "attempts": 0,
      "receiptPath": "receipts/skills/job_shot03_i2v.json"
    }
  ],
  "approvalGates": ["pilot", "review_final"],
  "fallbackPolicies": [
    { "skillId": "image.animate", "on": "429|timeout", "then": "requeue_backoff" },
    { "skillId": "voice.synthesize", "on": "backend_fail", "then": "edge" }
  ]
}
```

## 6.3 与现有 dispatch 关系

| 现有 | 目标 |
|------|------|
| `craft_stage` | 保留，作为 Graph 的粗粒度阶段视图 |
| `next_cmd` | = 当前 READY 中优先级最高 job 的 CLI 投影 |
| `receipts/dispatch.json` | 增补 `execution_plan_digest` + `jobs_summary` |

---

# 7. Skill Registry Design

## 7.1 位置

```text
plugins/ai-film-grok/skills/ai-film-grok/
  registry/
    skills.json              # 索引
    contracts/
      story.normalize.json
      shot.plan.json
      keyframe.generate.json
      image.animate.json
      ...
  scripts/
    skill_registry.py        # load / validate / list
    skill_runner.py          # run by skill_id → 现有 CLI
```

## 7.2 skills.json 条目

```json
{
  "id": "image.animate",
  "version": "1.0.0",
  "summary": "Keyframe → motion clip (I2V or panel motion)",
  "inputs": "contracts/image.animate.in.schema.json",
  "outputs": "contracts/image.animate.out.schema.json",
  "produces": ["MotionClip"],
  "dependsOnAssets": ["Keyframe", "CharacterState"],
  "providers": ["grok", "frw"],
  "capabilities": ["i2v"],
  "cli": {
    "run": "media-queue add + claim + register-clip",
    "validate": "media_qa"
  },
  "retry": { "max": 3, "backoff": "exp" },
  "locks": ["must_not_mutate_human_locked"]
}
```

## 7.3 选择规则（Planner）

1. 读 drama-graph 缺口（缺 Beat？缺 Keyframe？）  
2. 过滤 Registry 中 `produces` 匹配且依赖满足  
3. 应用 hard_gates / approvalGates  
4. 估 cost（可选）→ 输出 next job  

---

# 8. Skill Input / Output Contract

## 8.1 统一信封

```typescript
interface SkillRequest {
  skillId: string;
  projectRoot: string;
  nodeRef: string;          // e.g. shot:shot03
  input: object;            // skill-specific
  dryRun?: boolean;
  force?: boolean;          // 仅人工
}

interface SkillResult {
  ok: boolean;
  skillId: string;
  nodeRef: string;
  assets: { type: string; id: string; path: string }[];
  warnings: string[];
  errors: string[];
  provenance: {
    model?: string;
    provider?: string;
    promptHash?: string;
    costHint?: string;
    startedAt: string;
    finishedAt: string;
  };
  nextSuggested?: string[];
}
```

## 8.2 优先落地的 12 个契约（Phase 2–3）

| skill_id | 输入核心 | 输出核心 |
|----------|----------|----------|
| story.normalize | raw_text / files | NormalizedStory + candidates |
| episode.structure | NormalizedStory + targetDuration | Episode[] |
| scene.segment | Episode | Scene[] |
| beat.extract | Scene | Beat[] |
| character.bible.build | candidates + refs | Character bible + masters |
| shot.plan | Beat[] | Shot[] + productionMode |
| panel.layout | Shot | Panel[]（结构化，非纯 prompt） |
| keyframe.generate | Panel + refs | Keyframe candidates |
| image.rank | candidates | ranked + scores |
| image.animate | Keyframe + mode | MotionClip |
| voice.synthesize | DialogueLine | VoiceClip |
| video.render | Timeline | ExportManifest candidate |

现有命令 **wrap** 为 runner，先不重写算法。

---

# 9. Provider Adapter Design

## 9.1 原则

- **核心 Graph 禁止** `frw_*` / 模型名进入节点必填字段。  
- Provider 配置进 `project.providers.json` 或 `runtime_policy`。  
- Adapter 统一接口：

```text
ImageProvider.generate | edit | rank
VideoProvider.image_to_video | first_last | t2v
TtsProvider.synthesize | list_voices
MusicProvider.resolve_bed
RenderProvider.compose | export
```

## 9.2 现有 adapters/ 映射

| Adapter 文件 | 接口角色 |
|--------------|----------|
| grok_oauth_image*.py | ImageProvider |
| grok_oauth_video.py | VideoProvider |
| grok_oauth_tts.py / edge / voicebox / cosyvoice | TtsProvider |
| music_external.py | MusicProvider |
| frw_dispatch / env_plate | VideoProvider（frw） |

## 9.3 film-spec 中 frw_* 迁移

- v1：保留 film-spec 字段但标记 `provider_binding`  
- v2：移到 `providers.bindings.i2v = { backend: frw, model: ... }`  
- Graph Shot 只保留 `productionMode` + `duration` + 语义字段  

---

# 10. Asset and Revision Model

## 10.1 Asset 类型

```text
ReferenceAsset | GeneratedAsset
  id, type, path, sha256, createdBySkill, createdAt,
  parentIds[], locked: boolean, labels[]
```

## 10.2 Revision

```text
Revision {
  id, parentRevisionId?,
  summary, author: "agent"|"user",
  changedNodeIds[],
  receiptPaths[]
}
```

- pilot approve / review-final → 创建 Approval 挂 Revision  
- 重跑 Shot 不删历史：新 GeneratedAsset + 指针切换 `currentMotionClipId`

## 10.3 与 receipts 关系

```text
receipts/
  skills/<job_id>.json      # 新
  dispatch.json
  index.json                # Provenance 索引（新）
```

---

# 11. Timeline and Render Architecture

## 11.1 现状保留

```text
clips + VO + BGM + SFX + subs
  → final --post-engine hyperframes|ffmpeg|remotion
  → review-final 七维
  → export-desktop
```

## 11.2 目标增强

| 轨 | 内容 |
|----|------|
| V1 画面 | MotionClip 序列 + Transition |
| A1 旁白/对白 | VoiceClip |
| A2 BGM | MusicCue |
| A3 SFX | SoundCue |
| T1 字幕 | SubtitleCue（安全区） |
| M 元数据 | 片头/片尾/发布信息 |

## 11.3 生产模式 → 渲染路由

| productionMode | 路径 |
|----------------|------|
| single-keyframe-i2v | media-queue I2V |
| first-last-frame-i2v | 双关键帧 + I2V/FLF |
| panel-animation | 静帧 + camera.motion JSON → FFmpeg/HF 运镜 |
| text-to-video | env-plate / T2V（禁身份） |
| composite | 多层合成 |

## 11.4 默认分辨率策略

- 生成：720×1280（成本/速度，现状）  
- 交付目标：1080×1920（final 升或原生）；Graph 记 `targetResolution`，render 负责对齐  

---

# 12. UI Workflow Graph

## 12.1 v0（本机，低成本）

- 扩展 HUD：`jobs done/total`、`blocked_gate`、当前 skill_id  
- `aifilm graph status --root` → ASCII / JSON  

## 12.2 v1（可选 Web）

- 只读页：Episode → Scene → Beat → Shot 树  
- 节点色：planned / ready / running / failed / approved  
- 点 Shot 看 Panel/Keyframe/Clip/Receipt  

## 12.3 不做（本阶段）

- 在线协作编辑器、完整漫画 Panel 拖拽编辑器  

---

# 13. Incremental Migration Plan

## 13.1 兼容策略

| 阶段 | film-spec | drama-graph | 行为 |
|------|-----------|-------------|------|
| 现在 | 真源 | 无 | 现状 |
| M1 | 真源 | 从 film-spec **派生**只读 | 新命令 `graph derive` |
| M2 | 双写 | graph 可编辑，投影回 film-spec | write-spec 读写两侧 |
| M3 | 投影 | **graph 真源** | 旧 CLI 仍工作 |

## 13.2 命令兼容

- 所有现有 `aifilm *` 保留  
- 新命令加前缀：`aifilm skill list|run`、`aifilm graph *`、`aifilm plan *`  
- SKILL.md 主脊保持短；Registry 详情外置  

## 13.3 路由清理

| 用户意图 | 路由 |
|----------|------|
| Grok 竖屏漫剧/短片成片 | **ai-film-grok**（唯一主路径） |
| TG + aiaiartist 选角流水线 | frw-manju（标注 external channel） |
| 仅 HTML 动效 | hyperframes |
| 已有片剪辑 | video-use |

`ai-film-pipeline`：逐步声明 **deprecated 为文档 SOP**，逻辑并入 ai-film-grok references，避免双 SOP。

---

# 14. Phased Engineering Plan

> 每个 Phase：目标 · 改哪些 · 新 skill · 模型 · API · UI · 迁移 · 测试 · 风险 · DoD

### Phase 0 — Audit（本文件）  
**DoD**：16 交付物落地；用户确认优先 Phase。 ✅

### Phase 1 — Vertical Drama Graph v0 ✅ (2026-07-22 / v1.4.6)
- **目标**：`drama-graph.json` schema + derive/project  
- **文件**：`schemas/drama-graph.schema.json`、`scripts/drama_graph.py`  
- **模型**：Episode(1)、Scene、Beat、Shot 链接；Panel 从 dsl 派生  
- **API**：`aifilm graph derive|validate|status`  
- **Migration**：从现有 film-spec 单向 derive  
- **测试**：`tests/test_drama_graph.py`  
- **风险**：双源漂移 → 仅 derive 只读  
- **DoD**：任意现有 film-root derive 成功 + validate ✅

### Phase 2 — Skill Registry + Execution Graph 壳 ✅ (2026-07-22 / v1.4.6)
- **目标**：skills.json + 契约壳 + dispatch 暴露 jobs_summary  
- **文件**：`registry/`、`skill_registry.py`、`dispatch.py`  
- **API**：`aifilm skill list|show`；dispatch `schema_version=2`  
- **测试**：`tests/test_skill_registry.py` + dispatch 字段断言  
- **风险**：文档漂移 → registry 为能力清单真源  
- **DoD**：Agent 可只靠 `skill list` 知道能力边界 ✅  

### Phase 3 — Episode / Scene / Beat / Shot Planning ✅ (2026-07-22 / v1.4.7)
- **目标**：`story.normalize`、`beat.extract`、`shot.plan` 写 graph  
- **文件**：`scripts/story_plan.py` · CLI `aifilm plan *` · registry 更新  
- **测试**：`tests/test_story_plan.py` — 一句话 → ≥1 ep ≥3 beats + film-spec + write-spec 绿  
- **风险**：确定性规划文案偏模板 → Agent 精修 nar/dsl 后再 write-spec  
- **DoD**：一句话创意可生成可 validate 的 graph + film-spec 投影 ✅  

### Phase 4 — 角色 / 场景 / 一致性资产 ✅ (2026-07-22 / v1.4.8)
- **目标**：Location/Prop 结构化；CharacterState 与 state-index 对齐  
- **复用**：bible、wardrobe、state-index、continuity  
- **文件**：`scripts/asset_registry.py` · CLI `aifilm assets *` · schemas  
- **DoD**：state-index check 与 graph CharacterState 一致 ✅（`assets check` + timeline re-dress）  

### Phase 5 — Keyframe + Panel  
- **目标**：Panel 实体 + keyframe.generate/rank/repair 契约  
- **API**：panel 写入 graph；prompt 从 panel 生成  
- **DoD**：禁止「只有无法拆解的 prompt」作为唯一资产  

### Phase 6 — 静态 Motion + I2V  
- **目标**：productionMode 路由；camera.motion.plan JSON；panel-animation 路径  
- **DoD**：低动态镜可不走 I2V 仍进 timeline  

### Phase 7 — Voice / Subtitle / SFX / BGM  
- **目标**：DialogueLine 图；字幕安全区校验  
- **复用**：tts、audio_recipe、sound_plan  
- **DoD**：graph 可列出每镜 VO/字幕/SFX 资产 ID  

### Phase 8 — Timeline / Rhythm / Recut  
- **目标**：rhythm.evaluate skill；Hook/高潮/结尾检查  
- **DoD**：缺 hook 或单镜过长 → soft/hard 可配  

### Phase 9 — Render / QA / Provenance  
- **目标**：ExportManifest + provenance index；默认 1080×1920 交付选项  
- **DoD**：export 包含 mp4 + graph + timeline + srt + provenance  

### Phase 10 — 长篇 / 多集 / 协作  
- **Defer**：多 Episode 流水线、团队 Comment、完整 UI  

### 与 codebase-optimization 并行

| Wave（优化） | 与本升级 |
|--------------|----------|
| CLI 拆分 / util I/O | 利于 Phase 2 runner |
| I2V retry | Phase 6 前完成更佳 |
| 全量 CI | 每 Phase 必挂测试 |

---

# 15. Test and Acceptance Plan

## 15.1 自动化

| 层级 | 内容 |
|------|------|
| Unit | schema validate、derive、registry load、safe-zone math |
| Integration | 迷你 film-root fixture：normalize→plan→fake assets→render dry |
| 回归 | 现有 pytest（~62 文件）必须绿 |
| Contract | 每个新 skill：golden input → output schema |

## 15.2 人工验收剧本（金样）

1. **一句创意**（非成人）：30–45s 竖屏，3 scene，明确 hook/结尾钩子  
2. **短剧本**（含对白）：旁白+一句角色对白  
3. **失败重跑**：故意坏一镜 keyframe → repair → 只重该镜 I2V  
4. **一致性**：continue 链 3 镜，末帧=下首帧  
5. **交付包**：MP4 + graph + srt + provenance index  

## 15.3 最终验收清单（对照你 §25）

- [ ] 故事/小说/梗概/剧本入口（至少 md/txt）  
- [ ] 自动规划竖屏短集（单集先）  
- [ ] Scene / Beat / Shot  
- [ ] 角色与场景 Bible  
- [ ] Shot 生产路线（productionMode）  
- [ ] 9:16 keyframe  
- [ ] 一致性（角色/服装/场景/道具）  
- [ ] I2V + 漫画运镜分流  
- [ ] 对白旁白字幕音效 BGM  
- [ ] 多轨 timeline（逻辑轨）  
- [ ] Hook/节奏检查  
- [ ] 失败 Shot 局部重跑  
- [ ] 执行状态可查（CLI/HUD）  
- [ ] 可发布 1080×1920 MP4（或明确 upscale 路径）  
- [ ] 制作包 + Provenance  

---

# 16. Risk Register

| ID | 风险 | 等级 | 缓解 |
|----|------|------|------|
| R1 | 双真源 film-spec vs graph 漂移 | 高 | Phase1 只读 derive；M2 单写入口 |
| R2 | 范围膨胀成重写 | 高 | 禁止 Phase10 前 Multi-Agent；契约 wrap CLI |
| R3 | Registry 与 SKILL.md 双维护 | 中 | CI：registry 为能力清单真源，SKILL 只链 |
| R4 | Token/成本暴涨（多候选 rank） | 中 | pilot 预算；默认候选数=2 |
| R5 | 720→1080 质量假象 | 中 | 关键镜原生高分辨率选项 |
| R6 | Provider 字段污染 Graph | 中 | schema additionalProperties 收紧 + lint |
| R7 | 与 frw-manju 用户心智混淆 | 中 | 路由表写进 SKILL 与 AGENTS |
| R8 | 成人内容规则过拟合主路径 | 低 | heat 规则保持 soft/gated；通用竖屏规则独立 |
| R9 | CLI 单体与新模块冲突 | 中 | 先做 optimization Wave 拆分或只加新文件 |
| R10 | 自动化节奏评价误杀艺术 | 低 | rhythm 默认 soft |

---

## 附录 A · 目标 Skill 全表 vs 现状（速查）

| 目标 skill | 现状 | 优先级 |
|------------|------|--------|
| story.normalize | 缺 | P0 |
| episode.structure | 缺 | P1 |
| scene.segment | 半 | P0 |
| beat.extract | 半 | P0 |
| character.extract / bible.build | 半/有 | P0 |
| character.state.update | 有 | 复用 |
| location.bible.build | 弱 | P1 |
| prop.track | 弱 | P2 |
| shot.plan | 半 | P0 |
| panel.layout | 缺 | P0 |
| keyframe.plan/generate | 半/有 | P0 |
| continuity.check | 有 | 复用 |
| image.rank/repair | 半 | P1 |
| camera.motion.plan | 弱 | P1 |
| image.animate | 有 | 契约化 |
| motion.validate | 半 | P1 |
| dialogue.adapt | 半 | P1 |
| voice.cast/synthesize | 半/有 | 契约化 |
| subtitle.generate | 有 | 安全区增强 |
| sound.design / music.plan | 有 | 契约化 |
| timeline.compose | 有 | 增强 |
| rhythm.evaluate | 半 | P1 |
| video.render / quality.inspect / export.package | 有 | Provenance |

## 附录 B · 建议立即落地的文件树（未创建，待确认）

```text
skills/ai-film-grok/
  schemas/
    drama-graph.schema.json
    safe-zone.schema.json
    skill-result.schema.json
  registry/
    skills.json
    contracts/*.json
  scripts/
    drama_graph.py
    skill_registry.py
    skill_runner.py
  docs/plans/
    2026-07-21-vertical-drama-upgrade.md  ← 本文件
```

## 附录 C · 一句话迁移哲学

> **不要换发动机，要给发动机装仪表盘、油路图和可拆零件标签。**  
> dispatch / media-queue / write-spec / final 是发动机；  
> Vertical Drama Graph + Skill Registry + ExecutionPlan 是仪表盘与零件标签。

---

## 下一步（等人确认）

请选择推进方式（回复编号即可）：

1. **`go Phase1`** — 落地 drama-graph schema + `aifilm graph derive|validate|status`（只读派生，零破坏）  
2. **`go Phase1+2`** — 同时加 Skill Registry 壳 + dispatch jobs_summary  
3. **`go P0 skills only`** — 先写 12 个 contract JSON + skills.json，不改运行时  
4. **调整范围** — 说明要 defer/提前的 Phase  

**默认推荐**：`2`（Phase1+2），投入小、立刻让 Agent 可枚举能力与 Graph，且不打断现有成片。
