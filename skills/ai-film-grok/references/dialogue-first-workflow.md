# 对白驱动剧情片主链

剧情类输入默认走一条主链，不再以常驻旁白补齐故事：

```text
story.receive
→ dialogue_screenplay 候选
→ 用户审核
→ narrative lock
→ drama-graph 投影
→ performance-state I2I
→ 日文 TTS
→ 双路线候选
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
- 禁止连续讲话大头镜；相邻镜必须改变景别、视点、眼神轴、动作或反应功能。
- 旁白只补 `time_jump`、`location_context`、`offscreen_fact`、`inner_context` 等画面和对白无法承载的信息。必须记录理由、信息缺口和时长；目标占比为 0，硬上限 15%。
- 相同身份、衣着、情绪、视线、姿态、道具、光线与机位共享 `performance_state`；真实变化才拆新状态。批准 I2I receipt 必须绑定输入、输出、模型与 SHA-256。

## 讲话镜竞赛

同一讲话镜的两个候选必须共享批准状态图、最终日文 TTS 和表演意图：

1. 保真链：Qwen I2I → Wan 2.2 I2V → LatentSync 1.6。
2. 生成链：同状态图与音频 → 已通过实时 canary 的 InfiniteTalk/FantasyTalking。

执行 DAG 固定为：

```text
state_i2i → tts → candidate_preservation → candidate_generative
→ qa → provisional_select → human_approve → promote
```

RTX 5090 单队列串行；队列、GPU 或能力证据未知/过期即阻断。实验武器只可进入 pilot。自动评分只产生 provisional winner；完整观看人工批准前不得 promote，败选素材不得进入 final。

## 声音与交付

- 角色对白日文、字幕中文、旁白中文；动作描述不进入 TTS。
- 对白、旁白、呼吸表演、Foley、SFX、环境声和 BGM 独立成轨；对白处 BGM 自动 duck。
- Edge 是稳定默认；其他 TTS、ACE-Step、MMAudio 都服从能力、许可和人工试听/晋升门禁。
- 最终完成仍需逐镜观看、完整解码、FFprobe、字幕与声轨审计；生成成功或 provisional winner 都不等于成片批准。
