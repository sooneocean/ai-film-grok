# 对白驱动剧情片主链

剧情类输入默认走一条主链，不再以常驻旁白补齐故事：

```text
story.receive
→ dialogue_screenplay 候选
→ 用户审核
→ narrative lock
→ drama-graph 投影
→ performance-state I2I
→ 日文 TTS 排练（实音频、时长、停顿、情绪版本）
→ 按实测时长编排覆盖与镜头
→ QA provisional winner
→ 完整观看人工批准
→ promote / final
```

## 故事与对白合同

- `drama-graph.json` 是唯一故事真相；`dialogue_screenplay` 是其中的一等合同。
- 散文只可自动形成 `candidate_only` 对白候选。场景目标、冲突、转折、时空、说话人、对象、来源、翻译和审核齐全后才能锁故事。
- 原文事实、保护台词和结局不可改；新增影视化内容标记 `creative_suggestion`，未知项保持待确认。禁止用固定录音、门口、证据等模板代替来源。
- `documentary`、用户明确的 `monologue` 或实验形式才可显式改用其他模式。

## 画面、旁白与状态

- 以对白回合设计 A-roll、正反打、过肩、反应、动作覆盖与信息插镜；长台词可切画面，声音和字幕时钟不断。
- 禁止连续讲话大头镜；相邻镜必须改变景别、视点、眼神轴、动作或反应功能。每个 `beat_id` 含讲话镜时，必须有同一 `beat_id` 的 `reaction`、`action_cover` 或 `silence` 承接；同一节拍可含多句短对白，不会被强迫一行一条视频。
- 旁白只补 gap 信息；目标占比 0，硬上限默认 **5%**。**禁止**第三人称说书填钟。**（v2.34 起场景级硬闸）** 每个 scene（嵌套 shots）必须有 ≥1 条 `on_camera`/`off_camera` 对白（`spoken_text`+dialogue voice cue）；每场纯 `silence`/`action_cover`/纯 `nar` 硬拒收。逃生=scene `{"silent_scene": true, "narration_reason": "…"}`，或 spec `allow_silent_scenes:true`；默认绝不产「全旁白/全静默」场景。
- 状态键是「角色 × 场景 × 衣着 × 情绪 × 姿态 × 视线 × 道具 × 光线 × 空间位置」。角色母版先经 Qwen I2I 生成状态照；状态照再生成每句关键帧；已批准的上镜末帧可 promote 为下一镜候选。批准 I2I receipt 必须绑定输入、输出、模型与 SHA-256。
- `dialogue-scene-package.json` 用 `line_id` 把台词、TTS 哈希/时长、状态照、关键帧、口型、字幕和人工审核绑在一起。`on_camera` 只允许短句、近景/微侧脸、遮挡少，且必须有状态照、TTS 与逐镜人工口型审核。
- TTS 排练完成后会锁回每一条对白镜的 `duration_sec`（实音频 + 明确前后停顿），禁止再用估算秒数硬塞进既有 I2V 片长。
- `aifilm dialogue-production-plan --root <film>` 把每个 `line_id` 编成责任链：**状态照 → Grok Video 或 5090 H3 原音 I2V/R2V → 人审（语义/原声/无烧字）→ promote → post**。Edge TTS 只服务字幕时钟与可选 ADR，**不**驱动后期对嘴。计划本身不提交 5090 队列。

## 讲话镜动态路由（2026-08-05 · 原音 IRON）

**用户新规**：有语音的部分用 **Grok Video + 5090 H3** 生成；原先对嘴工具效果差，**全部先冻结**；直接用模型 **原音** 优化混音。

| 场景 | 路由 | 音频要点 |
|---|---|---|
| 非敏感对白近景 | `cloud_dialogue_grok`（Grok Imagine Video I2V） | 模型原声；`audio_policy=prefer_native` / `use_clip_audio` |
| **restricted 对白近景**（heat/bare/高难 + on_camera） | `local_dialogue_h3`（5090 `minimax-h3-i2v`；状态链/能量 → `r2v`） | H3 prompt 注入中文台词 + 口型可见；`prefer_native` |
| `h3_primary` 全片 | 对白也走 H3 | 同上 |
| 无台词覆盖镜 | Grok / H3 / env 车道 | 不能占满一整场（v2.34 场景级规） |

**冻结（勿 bulk）**：LatentSync · MuseTalk · InfiniteTalk · FantasyTalking · FRW lipsync · Wav2Lip · LTX 对白棚默认路径。

条件 DAG（`dialogue_competition` policy `native_audio_grok_h3_v1`）：

```text
state_i2i
  → primary_grok_native（auto / 安全对白）
  → alt_h3_native（restricted / 显式 local_h3 / Grok 可分类技术失败）
  → qa → provisional_select → human_approve → promote
```

1. **首选**：批准状态 still → Grok Imagine Video（prompt 含中文台词 + 嘴型清晰 + 无字幕烧字）→ 保留 clip 原声。
2. **restricted / h3_primary / Grok 技术失败**：同一 still → `aifilm h3 plan|run --register`（I2V/R2V）→ `prefer_native`。
3. **禁**：把 final TTS 灌进 LatentSync/MuseTalk 做后期对嘴；`final --lipsync off`。

自动评分只产生 provisional winner；完整观看人工批准前不得 promote。

## 30–60 秒武器样片

批量前用同一组 `line_id` 做 30–60 秒样片：Grok 原音臂 + H3 原音臂（可选）人审择优；**不再**默认跑 LatentSync 臂。`aifilm dialogue-benchmark` 若仍输出旧三臂文案，以本页生产路由为准，败选/旧臂不得 promote。


若 5090 正忙，可执行 `aifilm dialogue-benchmark-queue enqueue --root <film>`，把三臂
保存为项目内可审计的本地待办；它**绝不**提交 ComfyUI prompt。worker 使用 `claim` 时才
重新检查 Comfy 队列、RAM 与 VRAM 门槛；不达标就保持 `pending`。每臂仍必须先由
`dialogue-benchmark-review` 写入实际产物和人工审看，才可用 `complete` 关闭队列任务。

依序用 `aifilm dialogue-benchmark-review` 记录三臂的实际产物、人工意见与参数，再用
`aifilm dialogue-benchmark-approve` 锁定整条链。批准会以使用者本机环境中的
`AIFILM_AUDIO_RECEIPT_KEY`（或既有 `AIFILM_AUDIO_NODE_TOKEN`）签名；任何一臂改写都会
撤销批准与签名，必须重新完整审看。密钥不写进项目档或命令列。

## 声音与交付

- **角色对白默认中文**、字幕中文（HyperFrames 唯一烧字）、旁白中文 gap-only；日文仅显式 `ja`。动作描述不进入 TTS。
- 对白、旁白、呼吸表演、Foley、SFX、环境声和 BGM 独立成轨；对白处 BGM 自动 duck。
- Edge 是稳定默认；其他 TTS、ACE-Step、MMAudio 都服从能力、许可和人工试听/晋升门禁。
- 最终完成仍需逐镜观看、完整解码、FFprobe、字幕与声轨审计；生成成功或 provisional winner 都不等于成片批准。
