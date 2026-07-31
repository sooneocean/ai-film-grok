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
- 旁白只补 `time_jump`、`location_context`、`offscreen_fact`、`inner_context` 等画面和对白无法承载的信息。必须记录理由、信息缺口和时长；目标占比为 0，硬上限 15%。
- 状态键是「角色 × 场景 × 衣着 × 情绪 × 姿态 × 视线 × 道具 × 光线 × 空间位置」。角色母版先经 Qwen I2I 生成状态照；状态照再生成每句关键帧；已批准的上镜末帧可 promote 为下一镜候选。批准 I2I receipt 必须绑定输入、输出、模型与 SHA-256。
- `dialogue-scene-package.json` 用 `line_id` 把台词、TTS 哈希/时长、状态照、关键帧、口型、字幕和人工审核绑在一起。`on_camera` 只允许短句、近景/微侧脸、遮挡少，且必须有状态照、TTS 与逐镜人工口型审核。
- TTS 排练完成后会锁回每一条对白镜的 `duration_sec`（实音频 + 明确前后停顿），禁止再用估算秒数硬塞进既有 I2V 片长。
- `aifilm dialogue-production-plan --root <film>` 会把每个 `line_id` 编译为无消费责任链：TTS → Qwen 状态照 → Qwen 关键帧 → FRW 上传（keyframe SHA-256 + `img-url` receipt）→ FRW LTX 2.3 原生有声 I2V → 无烧字/口型/语义审查 →（被拒绝时才）原 FRW Seedance I2V →（仍需上镜口型时）LatentSync → Foley/MMAudio → post。每一步列出依赖与必须回执；生成计划本身不会提交 5090 队列。

## 讲话镜动态路由

同一讲话镜的两个选项必须共享批准状态图、最终日文 TTS 和表演意图：

1. **首选**：Qwen I2I 状态图/关键帧 → FRW 上传取得 `img-url` → FRW `img2video-audio`（此子命令选择 LTX 2.3）。提示词强制含「无可见文字、无字幕、无水印」，但提示词不是门禁：必须解码抽帧，人审确认没有供应商烧字、听到的台词符合预期、口型与声音一致。
2. **第一回退**：仅在 LTX 原生音画被明确拒绝（台词不符、口型不符、供应商烧字或解码失败）时，才使用原 FRW `seedance-2-fast-i2v`；它复用同一批准关键帧。LTX 的 `img2video-audio` 会按提示词自行生成声音，当前 FRW CLI **不接收外部 TTS 音频**，因此不能把它误记成已锁定 TTS 的口型结果。
3. **口型后处理**：若第一回退用于上镜对白，才将该 FRW I2V 与已锁定 TTS 交给 RTX LatentSync 1.6；它不再占用默认 5090 容量。

条件 DAG 固定为：

```text
state_i2i → tts rehearsal → keyframe_i2i → FRW keyframe upload → FRW LTX 2.3 native-audio I2V
  → native-text gate → post
  └→ only on rejection: FRW Seedance I2V → LatentSync 1.6 (on-camera dialogue only)
                                                     ↘ MuseTalk 1.5 (classified failure only)
                                              → full human review → promote
```

`dialogue_motion_route=auto` 只在 FRW 原生有声音画 canary 已通过且可审查时选择 LTX 2.3；它生成的声音必须逐镜确认台词语义、口型和无烧字。质量拒绝、身份漂移和未知错误都不构成静默换路理由。只有被记录为 LTX 拒绝原因的对白失败才可先切到原 FRW Seedance I2V，并在需要时进入 LatentSync 1.6。InfiniteTalk 与 FantasyTalking 会重生成整张画面，只可作为明确标记的实验 pilot，绝不作为默认对白生产线。

RTX 5090 单队列串行；队列、GPU 或能力证据未知/过期即阻断。尚未晋升的 InfiniteTalk
只可进入 pilot；架构首选不等于伪造生产就绪。自动评分只产生 provisional winner；
完整观看人工批准前不得 promote，败选素材不得进入 final。

## 30–60 秒武器样片

批量生产前，以同一组有真实 TTS 哈希的 `line_id` 做 30–60 秒样片。无消费的
`aifilm dialogue-benchmark --root <film>` 会写出 Qwen 状态照、FRW LTX 2.3 原生有声 I2V、无烧字审查与按需 LatentSync 1.6
三臂的共同输入与人工选择门；它不是生成或批准的替代品。每一臂有实际产物与完整看片后，
才可记录稳定参数并进入 bulk。

若 5090 正忙，可执行 `aifilm dialogue-benchmark-queue enqueue --root <film>`，把三臂
保存为项目内可审计的本地待办；它**绝不**提交 ComfyUI prompt。worker 使用 `claim` 时才
重新检查 Comfy 队列、RAM 与 VRAM 门槛；不达标就保持 `pending`。每臂仍必须先由
`dialogue-benchmark-review` 写入实际产物和人工审看，才可用 `complete` 关闭队列任务。

依序用 `aifilm dialogue-benchmark-review` 记录三臂的实际产物、人工意见与参数，再用
`aifilm dialogue-benchmark-approve` 锁定整条链。批准会以使用者本机环境中的
`AIFILM_AUDIO_RECEIPT_KEY`（或既有 `AIFILM_AUDIO_NODE_TOKEN`）签名；任何一臂改写都会
撤销批准与签名，必须重新完整审看。密钥不写进项目档或命令列。

## 声音与交付

- 角色对白日文、字幕中文、旁白中文；动作描述不进入 TTS。
- 对白、旁白、呼吸表演、Foley、SFX、环境声和 BGM 独立成轨；对白处 BGM 自动 duck。
- Edge 是稳定默认；其他 TTS、ACE-Step、MMAudio 都服从能力、许可和人工试听/晋升门禁。
- 最终完成仍需逐镜观看、完整解码、FFprobe、字幕与声轨审计；生成成功或 provisional winner 都不等于成片批准。
