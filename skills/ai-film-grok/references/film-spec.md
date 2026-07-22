# Film Spec 契约

`film-spec.json` 保存**导演意图**、故事事实、声音决策、运镜与时长。视觉稳定的风格语法保存在 `style-bible.json`。

**叙事上游（写本文件之前）**：用户文本必须先走 [directors-lens.md](directors-lens.md)（故事重构 → 场景 → storyboard 面板），再落到下列字段。禁止原文插图化。

完整模板：[../templates/film-spec.example.json](../templates/film-spec.example.json)。机器可读契约：[../schemas/film-spec.schema.json](../schemas/film-spec.schema.json)。

## 最小有效结构

```json
{
  "title": "雨夜后座",
  "aspect_ratio": "9:16",
  "vo_mode": "storyteller",
  "vo_voice": "zh-CN-YunxiNeural",
  "tts_backend": "auto",
  "i2v_provider": "frw",
  "frw_video_model": "seedance-2-fast-i2v",
  "frw_aspect_ratio": "9:16",
  "frw_resolution": "720p",
  "frw_duration": "5",
  "tts_allow_network_fallback": false,
  "native_audio_volume": 0.16,
  "transition_sec": 0.2,
  "director_intent": {
    "logline": "雨夜出租车后座，说书人陪你靠近一位湿透的女司机。",
    "tone": "色气·雨夜·压迫感",
    "emotional_arc": ["好奇登场", "空间变窄", "感官贴近", "未完成邀请"]
  },
  "scenes": [{
    "title": "Ride",
    "shots": [{
      "id": "shot01",
      "dramatic_function": "hook",
      "duration_sec": 6,
      "nar": "话说那晚雨下得很急。",
      "lipsync": false,
      "dsl": {
        "subject": "adult anime woman taxi driver",
        "action": "opens the rear door",
        "environment": "rainy neon street",
        "camera": {"shot_size": "medium full", "angle": "eye level"},
        "motion": "slow push-in, rain splash, soft blink, breathing, idle not speaking"
      }
    }]
  }]
}
```

## I2V / FRW Seedance（顶层字段 · 2026-07-20 质量版）

| 字段 | 默认 | 说明 |
|------|------|------|
| `i2v_provider` | `frw` | `auto`→`frw`；显式 `grok` 才走 Imagine I2V |
| `frw_video_model` | **`seedance-2-fast-i2v`** | bulk 质量默认；`legacy-img2video` 仅显式（write-spec WARN） |
| `frw_aspect_ratio` | 跟 `aspect_ratio` 或 `9:16` | 传给 `frw newvideo --aspect-ratio` |
| `frw_resolution` | **`720p`** | **原生**；禁止 576 生成再放大 |
| `frw_duration` | `"5"` | Seedance duration 字符串 |

CLI 配方与入组纪律：[frw-degrade-dispatch.md](frw-degrade-dispatch.md)、[lessons-2026-07-20-seedance-quality.md](lessons-2026-07-20-seedance-quality.md)。

**分层 + Fallback（2026-07-20）**——细表 [layer-routing.md](lessons-2026-07-20-layer-routing.md)：

| 层 | 字段 | 主力 → Fallback |
|----|------|-----------------|
| 人物 A-roll | `frw_video_model` + `shot_role: hero` | Seedance i2v → LTX i2v → Grok 720p；**禁** T2V 锁脸 |
| 合成/空镜 | `frw_env_model` + `env\|bridge\|insert` | **LTX T2V** → Seedance t2v → classic t2v |
| 身份静帧 | — | **Grok cast** |

LTX 参数必须 **string** 宽高；竖屏 `720`×`1280`。[frw-ltx-probe.md](lessons-2026-07-20-frw-ltx-probe.md)。

## 内容通道与场内触发（v1.11.1）

`nar` 是旁白/音频文本，**不是**动作 prompt。`dialogue` 是角色台词；只有 `voice.on_camera=true` 且 `lipsync=true` 时才允许驱动嘴型。人物表演与动态必须来自可见动作，并由场内事件触发。

```json
"content_channels": {
  "voice": {"kind": "narration", "on_camera": false},
  "performance": {
    "playable_action": "她的手停在门锁上",
    "reaction_trigger": "门把自己转动",
    "body_state": "肩膀绷紧，视线钉住门缝"
  },
  "motion": {
    "action": "她后退半步，手仍悬在锁前",
    "scene_trigger": "门把自己转动"
  }
}
```

开 `content_channels_strict: true` 后，以下会阻断 write-spec：把 `nar` 原样复制为 `dsl.action`、镜内台词却关 lipsync、开 lipsync 却没有 dialogue、或以“旁白/台词”作为反应触发器。空镜/建立镜可只用旁白与镜头运动，不强造角色表演。

## 表演事实审片（v1.11.3）

`review-shot --approve` 会把当前 clip 的 hash、首/中/末联系表和人类观察时间点绑在一起。只要该镜使用 `content_channels`（或全片开了 `content_channels_strict`），审片人还要提供与编导意图相符的 `--performance-evidence kind@seconds:note`：声明的 `scene_trigger` 对应 `trigger_visible`；`playable_action` 对应其后的 `action_visible`；`reaction_trigger` 对应其后的 `reaction_visible`；镜内 lipsync 台词对应 `dialogue_delivery`；镜内人物配画外旁白且关闭 lipsync 时，对应 `mouth_still`。

每条表演证据还会抽出该秒的独立 frame，并与 clip hash 一并收据化。它是导演的人工事实记录，不是自动嘴型、脸部或演技识别；它能证明谁在何秒看到了什么，并防止旁白或“她很惊讶”被误当成已发生的动态表演。是否真正成立仍需完整观看 clip。

`aifilm performance-timeline --root <film>` 会把所有已批准镜头的这些证据转换为全片绝对时间轴。`review-final` 对启用 content channels 的项目自动调用它：缺少镜头收据、证据 frame 损坏、或动作/反应早于其场内触发，都会阻止最终批准。

## 台词、嘴型与反应留白（v1.11.5）

镜内 lipsync 台词必须先有同一 `dialogue` 文本的实测 TTS rehearsal，再以 `dialogue_delivery@秒数:note` 记录**最后一个可听见音节结束**的人工观察。`aifilm speech-performance-timing --root <film>` 会拒绝：旁白音频冒充台词、rehearsal 文本与 canonical dialogue 不同、交付时间早于实测音频结束，或交付后不足 0.2 秒就切镜。旁白不驱动此门禁，也不允许借此要求嘴型。

`aifilm audio-provenance --root <film>` 进一步记录台词 rehearsal 音频、voice carrier 与最终 MP4 的 hash。它阻止审过后换音频或换交付文件；但 hash 只能证明文件未被替换，最终听感、台词含义和嘴型仍须人类完整审片。

## 字幕跨镜例外（v1.11.9）

硬切与 Continue 默认不允许字幕跨镜。电话声、悬念句等确实需要 L-cut 时，顶层 `subtitle_carryovers` 必须逐项声明 `from_shot_id`、`to_shot_id`、实际 cue 起止秒数、具体原因，并设 `human_approved: true`；范围以外或未批准的字幕仍会阻断 final。

## 转场 / 运镜（顶层 + 每镜 · v2）

| 字段 | 默认 / 位置 | 说明 |
|------|-------------|------|
| `transition_fluency` | `auto`→silk | silk / **cinematic**（craft 丰富）/ punchy；惊悚 tone→punchy |
| `edit_craft` | 长度 n−1 | 资深剪辑 craft；不写则 write-spec 建议；见 [editorial-craft.md](editorial-craft.md) |
| `transition_sec` | `0.28` | soft/hold 基础叠化；**满 60s 靠加镜**不靠拉长 |
| `transition_intents` | beat 建议或作者 | 长度 n−1；**continue 入缝 write-spec 强制 hard** |
| `transition_styles` | 自动轮转 | soft/hold 勿全 dissolve（`STYLE_SOUP`） |
| `dsl.camera_axis` | 每镜自动轮换 | `dolly_in\|pan_with\|locked\|ecu_hold\|low_lean\|pull_back` |
| `dsl.focal_character` | 共情归属 | `hero` / `partner` / cast id；见 [character-stance.md](character-stance.md) |
| `dsl.viewpoint` | 机位语法 | `objective\|ots\|reverse\|reaction_to\|subjective_pov\|dual\|insert_object` |
| `dsl.look_axis` | 180° 轴线 | `left\|right\|center`；reverse 对翻 |
| `dsl.chain_mode` | 作者 | `continue`→真接戏须 promote 字节；假接戏改 `cut` |
| `dsl.cut_on` | 建议 mid_motion | continue 动能切 |

lint 码：`CAMERA_AXIS_FLAT` · `SOFT_SOUP` · `STYLE_SOUP` · `MOTION_MONOTONY`。  
权威：[lessons-2026-07-20-transition-motion-v2.md](lessons-2026-07-20-transition-motion-v2.md)、[shot-motion.md](shot-motion.md)。

## 导演意图（`director_intent` · 必填）

开拍 / `media-queue add` 之前必须写清片子承诺。来源：Director’s Lens Phase A。

| 字段 | 规则 |
|---|---|
| `logline` | 非空，≥8 字；一句话卖点 |
| `tone` | 非空；语气/气质 |
| `emotional_arc` | 字符串数组，**≥3** 个情绪节拍标签 |
| `audience` | 可选 |
| `taboos` | 可选字符串数组（禁止卖点/收尾方式） |
| `theme` | 可选；主题句（Lens 提炼） |
| `act_structure` | 可选；`{setup, confrontation, resolution}` 或五幕扩展 |
| `pace_chart` | 可选；节奏标签数组（慢燃→爆发→释放） |
| `visual_motifs` | 可选；视觉象征字符串数组 |

`theme` / `act_structure` / `pace_chart` / `visual_motifs` **不**被 write-spec 硬校验，但写了可帮 agent 与用户对齐；schema 允许 `additionalProperties`。

## 每镜戏剧功能（`dramatic_function` · 必填）

镜头在剧情脊柱里的角色，不是「好看帧」标签：

| 值 | 含义（对照 ecchi-story 六镜骨架） |
|---|---|
| `hook` | 登场/压迫感 |
| `approach` | 靠近、空间变窄 |
| `sensory` | 感官特写 |
| `reaction` | 对方/代入反应 |
| `action` | 身体行动推进 |
| `afterglow` | 余韵/钩子 |
| `bridge` | 过渡/连接 |

## 强制规则

- `title`、`vo_mode`、**`director_intent`**、`scenes` 和至少一镜必须存在。
- `vo_mode` 只能是 `storyteller | character | hybrid`。
- 每镜 `id` 必须唯一且符合 `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`；缺失时 `write-spec` 可依序指派。
- 每镜 **`dramatic_function`** 必须是上表枚举之一。
- 每镜 `nar` 必须非空；说书人模式使用第三人称旁白。
- **VO 预算**：每镜 `nar` 长度 **≤55**（推荐 ≤42）；超限 `FilmSpecError` 含 `vo_budget`。校验通过后写入 `est_vo_sec` 与 `spec._vo_budget`。
- 每镜 `dsl` 和 `dsl.motion` 必须非空。motion 应同时给相机与身体/环境线索，禁止 mouth-speaking-primary。
- **微动注入**：`sensory`/`reaction`/`afterglow`/`hook` 若 motion 缺 blink/breath/tremble 等，追加**微动**后缀（**不再**默认绑死 push-in）。**主动作仍须作者写在前**。
- **运镜主轴**：write-spec 写入 `dsl.camera_axis` 并轮换；必要时注入 motion 关键词。三连同轴 → `CAMERA_AXIS_FLAT`。
- **口白·动作 / 防腻 soft lint**：`_vo_motion_link`（`PRIMARY_MOTION_WEAK` / `MOTION_MONOTONY` / `SIZE_FLAT` / `SOFT_SOUP` / `CAMERA_AXIS_FLAT` / `STYLE_SOUP`）。默认不拦；`vo_motion_strict: true` 可升 hard。
- **构图默认**：缺省时补 `camera.shot_size` / `camera.angle` / `dsl.framing`。
- **转场**：默认 `transition_sec=0.28`；intents 按 beat 建议；**continue 缝强制 hard**（`enforce_continue_hard_joins`，fixes 写入 `_transition_continue_hard_fixes`）；styles 自动轮转。
- `duration_sec` 必须大于 0 且不超过 60。
- `transition_sec` 为 0–0.6；0 表示硬切。
- `native_audio_volume` 为 0–1，默认 0.16。
- `tts_backend` 只能是 `auto | external | minimax | fish | voicebox | edge`。
- `tts_allow_network_fallback` 默认 `false`。开启后只允许 `auto` 在已选 provider 运行失败时走 **voicebox（若就绪）→ Edge**；显式 `fish | minimax | external | voicebox` 仍然闭锁报错（除非另开 `AIFILM_TTS_VOICEBOX_FALLBACK=1`）。

## 分镜转场意图（P2）

| 字段 | 含义 |
|---|---|
| `transition_sec` | soft/hold 的基础叠化秒数（0=全局硬切） |
| `transition_default` | `hard\|soft\|hold`，未写 intents 时的默认 |
| `transition_intents` | 故事镜间接缝，长度 **= n_shots−1** |
| `transition_style` | 全局默认 xfade 名（title/end 边缝也用） |
| `transition_styles` | **每缝** xfade 名，长度 **= n_shots−1**；不写则 write-spec 自动建议 |

`hard` = concat 不叠化；`soft`/`hold` = xfade（hold 更长）。片头/片尾接缝默认跟 `transition_default` + `transition_style`。  
**continue 入缝永远 hard**（作者 soft 也会被改掉）。改 intents/styles 后 **只 re-final**；改 `camera_axis`/motion 像素须 **re-I2V**。见 [lessons-2026-07-20-transition-motion-v2.md](lessons-2026-07-20-transition-motion-v2.md)。

## 声音 spotting（P2）

```json
"sound_plan": {
  "mood": "rnb",
  "bed": true,
  "events": [
    { "type": "mute", "shot_id": "shot02", "duration_sec": 1.0 },
    { "type": "sfx_accent", "shot_id": "shot03", "kind": "heartbeat" },
    { "type": "duck", "shot_id": "shot01", "depth": 0.35 }
  ]
}
```

`final` 写入 `audio/mix_report.json`（`applied_events` + 是否应用 bed）。

## 场景自适应声轨（P2 · audio_policy + audio_recipe）

片级策略 + 每镜配方；**write-spec 自动填写**。默认 `mode=auto`：只调说书/床厚薄，**不自动唱、不自动口型**。

```json
"audio_policy": {
  "mode": "auto",
  "allow_sung": false,
  "allow_lipsync": false,
  "bed_source": "auto",
  "max_sung_shots": 1
}
```

每镜（自动或作者强制字符串）：

```json
"audio_recipe": "narrate_thin"
```

完整表与降级规则见 [audio-recipe.md](audio-recipe.md)。write-spec 摘要在 `_audio_routing`；`sound_plan.bed_gain_hint` 供 final 调节床响度。

## 连续性 lint（P2）

`write-spec` 产出 `continuity_lint.json`；稳定 reason code：

- `CAST_FLIP` / `SCREEN_DIRECTION_FLIP`（默认 blocking）
- `COVERAGE_JUMP` / `PROP_DROP`（warning）

```bash
"$AIFILM" lint-continuity --root <root>
"$AIFILM" lint-continuity --root <root> --strict   # 有 blocking 则失败
```

`continuity_strict: true` 时 write-spec 直接失败。

## Beat → 覆盖默认（B1）

`write-spec` 会按 `dramatic_function` 自动补全**缺失**的：

| dramatic_function | 默认 shot_size | 默认 motion 气质 |
|---|---|---|
| hook | medium full | 登场 push-in |
| approach | medium | dolly-in / 靠近 |
| sensory | close-up | 极慢推近 |
| reaction | close-up | 微反应 |
| action | medium full | 身体行动 |
| afterglow | medium | 余韵 hold |
| bridge | medium | 过渡 pan |

作者已写的 `dsl.motion` / `camera.shot_size` **优先**，不会被覆盖。实现：`edit_policy.coverage_defaults_for_beat`。

## Storyboard 字段速查（Lens → JSON）

| Storyboard 面板 | film-spec |
|---|---|
| 幕/主题/节奏 | `director_intent.*` |
| 场景目的 | `scenes[].title` / `summary` |
| 景别 / 角度 | `dsl.camera.shot_size` / `angle` |
| 运镜+表演 | `dsl.motion`（主动词在前） |
| 世界变化 | `dsl.visible_change` |
| 戏剧一句 | `dsl.story_beat` + `dramatic_function` |
| 旁白 | `nar`（≤55）· 可选 `nar_en` |
| 转场 | `transition_intents` / `transition_styles` |
| 音效 | `sound_plan.events` |

详表见 [directors-lens.md](directors-lens.md)。

## Agent 生产门禁

0. 文本输入已完成 Director’s Lens（至少 detailed shot 可填）；禁止跳过弧线重构。  
1. `write-spec` 通过（含 intent + dramatic_function；可缺 motion 由 beat 补全）。
2. **未锁 intent / beat 前，不得** `media-queue add` 烧 I2V。
3. 风格锁与定妆仍按 [style-bible.md](style-bible.md) / [consistency.md](consistency.md)。
4. 成片审批必须带六维评分卡全 pass（见 [postproduction.md](postproduction.md)）。

## 连续性检查

- 同一角色的脸、发型、服装和固定声线一致。
- 屏幕方向稳定，除非有意轴线反转。
- 道具库存和场景地理可读。
- 旁白长度与镜头时长相符。说书人中文通常 28–42 字/镜，超过时先拆镜。
