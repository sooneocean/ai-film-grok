# Shot motion & transitions（运镜 / 动态 / 过场 / 构图）

目标：**动作丝滑、接缝不跳、构图稳定、旁白贴耳**。

## Why films felt static, jumpy, or random

| Problem | Cause | Skill fix |
|---|---|---|
| 硬切像幻灯片 | `concat` 不用 xfade | `final` 默认 **xfade 0.28s soft** + VO **acrossfade** |
| 长口白画面僵 | VO>I2V 时慢放/冻帧 | **loop 更早**（ratio>1.15）；冻帧 ≤0.25s；禁止超长 nar |
| 嘴在动却对不上 | I2V 写 mouth speaking | **`dsl.motion` 必填**；禁 mouth-speaking 主动态 |
| 静戏 motion_score 挂 | 只有「站着」 | 微动注入 blink/breath/push-in |
| **动态速度感差 / 发肉** | I2V 全是 soft lean·breath·blink | **主动词要狠**（snap/yank/decisive）；motion_score&lt;5 → **re-I2V**（见 §1c） |
| 镜间跳切乱 | 无 join 策略 | **edit_craft** + beat suggest（[editorial-craft.md](editorial-craft.md)） |
| **剪辑呆板线性** | 全 soft dissolve 或全 hard | craft 菜单：smash/insert/montage/hold 轮换；soft≤3 连跑 |
| **用户批「剪辑/运镜/动态太差」** | 顺序拼板 + 弱 motion + 无 insert | **资深蒙太奇强制**：见 [lessons-2026-07-21-montage-hardcore-male.md](lessons-2026-07-21-montage-hardcore-male.md) R-M |
| **动作不串 / 像摆拍拼盘** | 每镜 still 只锚 cast；无 end→start pose | **Frame chain**：last-frame seed + `start_pose`/`end_pose`（见下 §1b） |
| 构图每镜乱飞 | 无景别/角度默认 | beat → shot_size + angle + framing |
| **旁白拖腔「卡」** | slot 短 VO 被 atempo 拉慢 | drag guard pad；说书优先 `visual_fit:vo`（[vo-drag](lessons-2026-07-20-vo-drag-motion-snap.md)） |

## Production recipe（单页照做）

### 0) 导演意图 + beat

**上游**：文本先走 [directors-lens.md](directors-lens.md)（故事弧 → scene → shot 面板），再填本页字段。  
`director_intent` + 每镜 `dramatic_function` 通过 `write-spec` 后才能 `media-queue add`。  
缺 motion / shot_size / angle / framing 时按 beat 补全（作者手写优先）。

### 1) 每镜 `dsl.motion` + `dsl.camera_axis`（连续、单轴 + 口白绑定）

必须同时有 **镜头主轴** + **身体/环境**，并写 **idle not speaking**。

**顺序**：**主动作（与 `nar`/`action` 同一事件）→ camera_axis → 再微动 filler**。  
微动 alone 过 motion QA ≠ 戏好看（见 [lessons-2026-07-17-vo-motion-link.md](lessons-2026-07-17-vo-motion-link.md)）。

| `camera_axis` | 注入关键词 |
|---|---|
| `dolly_in` | continuous slow dolly-in |
| `pan_with` | pan-with-subject, no push-in |
| `locked` | camera static locked-off |
| `ecu_hold` | tight hold, no push-in |
| `low_lean` | low angle lean-in then stop |
| `pull_back` | gentle pull-back then hold |

write-spec 轮换轴；三连同轴 → soft lint `CAMERA_AXIS_FLAT`。  
v2 纪律：[lessons-2026-07-20-transition-motion-v2.md](lessons-2026-07-20-transition-motion-v2.md)。

### 1a) 动态必须有叙事意涵（Meaningful Motion）

权威：[lessons-2026-07-20-meaningful-motion.md](lessons-2026-07-20-meaningful-motion.md)。

| 原则 | 做法 |
|---|---|
| 一镜一世界变化 | 写 `dsl.visible_change`（状态 A→B） |
| 一镜一戏剧功能 | 写 `dsl.story_beat`；对齐 `dramatic_function` |
| 动态 = 答案 | motion 须回答 beat 问题（登场/靠近/感官/反应/行动/余韵） |
| 微动是配菜 | hook/approach/action **禁止**只有 blink+breath+push-in |

| beat | 故事问题 | 动态必须让人看见 |
|---|---|---|
| hook | 谁占场？ | 入场/掀帘/现身 |
| approach | 空间怎么窄？ | 走近/落锁/关距 |
| sensory | 身体哪在说话？ | 呼吸/汗/指尖（可绑微动） |
| reaction | 她怎么应？ | 眼神/手势/一怔 |

### 1c) I2V 速度感词表（星声 lesson · 2026-07-20）

hook / approach / action 的 **motion 字符串必须带至少一个狠动词**；micro 只能垫后。

| 弱（禁当主句） | 强（优先） |
|---|---|
| soft lean, gentle sway | lean hard, lunge forward, decisive lean |
| fingers slowly… | fingers snap / clamp / yank |
| soft breath only | chest heaves, sharp breath **after** primary action |
| hair drifts | hair whips / swings hard |
| continuous slow…（alone） | continuous **decisive** motion + camera_axis |

- register 后看 `qa.motion_score`：**< 5** 的 hook/approach/action → **requeue re-I2V**，禁止只 re-final。  
- 审核拦截时：换 clothed/suggestive still，**VO 可保留荤点**（[ecchi-story.md](ecchi-story.md)）；motion 仍用狠动词但去露点词。  
- 完整决策树：[lessons-2026-07-20-vo-drag-motion-snap.md](lessons-2026-07-20-vo-drag-motion-snap.md)。
| action | 局势怎变？ | 撑台/解扣/俯压… |
| afterglow | 余韵邀请？ | 停距/一眨眼收钩 |

**禁止**：`mouth speaking` / multi-action thrash（扭腰+转头+挥手同时）。  
**禁止**：连续 3 镜全是 slow push-in + blink + breath（`MOTION_MONOTONY` soft）。  
**禁止**：空审美动态（`MOTION_NO_MEANING` / `BEAT_SEMANTICS_MISS` soft）。

### 1b) Continuity Chain（长片动作串接 · 优先于 xfade）

权威：[continuity_chain.md](continuity_chain.md)。摘要：

1. **长片**必须有 film-root `continuity_chain.md`（`continuity-chain init|check`）  
2. continue：`extract-frame --promote-keyframe next` → 下镜 keyframe **逐字节 =** 上镜末帧；**禁止 cast 重起**  
3. 连接点九项：pose / gaze / hands_props / travel / axis / hair / wardrobe / weather / lighting  
4. **禁止** dissolve·定格·倒放·无关插镜掩盖断裂  

操作复盘：[lessons-2026-07-20-frame-chain.md](lessons-2026-07-20-frame-chain.md)。  
Lint：`FRAME_CHAIN_*` + preflight hard `continuity_chain_doc` / byte mismatch。

### 2) 构图（coverage 默认）

| beat | shot_size | angle | framing 要点 |
|---|---|---|---|
| hook | medium full | eye level | 中心+headroom，注视方向留白 |
| approach | medium | eye level | 更紧，眼在上三分 |
| sensory | close-up | eye level | 细节占满，浅景深 |
| reaction | close-up | eye level | 脸优先，情绪可读 |
| action | medium full | slight low | 肢体完整，轴线稳定 |
| afterglow | medium | eye level | 余韵中景，软虚化 |
| bridge | medium | eye level | 过渡方向明确 |

竖屏 **9:16**：脸与重要道具避开底部字幕带与极顶裁切。

#### 2b) 景别情绪堆叠（2026-07-21 · 成人片强制）

> 用户嫌「尺度小 / 没压迫感」时，**单镜 beat 表不够**——必须设计 **WS→MF→M→CU→局部** 加压链。  
> 权威：[lessons-2026-07-21-size-ladder-hardcore-stack.md](lessons-2026-07-21-size-ladder-hardcore-stack.md)。

| 级 | size | 成人用途 |
|---|---|---|
| L0/L1 | wide / medium full | 空间·双人关系 |
| L2 | medium | 贴身·失序 |
| L3 | close-up（头肩 headroom） | 喘·反应·完成脸 |
| L4 | close-up 物件/肢体 | 闩/手/腿/布 insert（禁填脸裁头） |

**60s selects 配额**：L0/L1≥1 · L2≥2 · L3≥2 · L4≥2；**act→climax 禁止无故退回全景**；连续 3 镜同 size = fail。

### 3) 旁白 vs 6s I2V

| 每镜 nar | 约 VO | 画面策略 |
|---|---|---|
| 28–42 字 | 6–9s | 轻慢 + 短循环 |
| ≤55 字 | ≤11s | 循环（硬上限 write-spec） |
| 更长 | — | **拆镜** |

默认说书：`vo_rate: +0%`，`vo_gain: ~1.32`，BGM 略让路；快节奏色气可用 `+5%~+8%`（禁 `-3%` 叠 atempo 拖腔，见 vo-drag lesson）。

### 4) 过场（有节奏 · 防 soft soup）

```json
"transition_sec": 0.30,
"transition_style": "dissolve",
"transition_default": "soft",
"transition_intents": ["hard", "soft", "hard", "soft", "hard", "soft", "hard", "hold", "hold"],
"transition_styles": [
  "fade", "smoothleft", "hblur", "dissolve", "smoothup",
  "hblur", "smoothright", "dissolve", "fadeblack"
]
```

| 字段 | 含义 |
|---|---|
| `transition_sec` | soft/hold 基础叠化秒（默认 **0.28–0.30**；0=全局硬切） |
| `transition_intents` | 故事镜间接缝，长度 **n_shots−1**；`hard\|soft\|hold`；**continue 缝强 hard** |
| `transition_style` | 全局默认 xfade 名（边接 title/end 也用它） |
| `transition_styles` | **每缝** xfade 名，长度 **n_shots−1**；不写则 write-spec 按 beat 自动轮转 |
| `transition_fluency` | `silk` 非 continue 偏 soft；`punchy` 更多 hard |

**硬纪律**：`dsl.chain_mode: continue` 的入缝永远 **hard match-cut**（作者写 soft 也会被 write-spec 改掉）。  
**时长**：`成片秒 ≈ Σplate − Σsoft_xfade`；要满 60s 就 **加镜**，不要把 dissolve 拉长装时长。

不写 `transition_intents` 时，write-spec **按 beat 自动建议**：

| 相邻 beat | join |
|---|---|
| action→reaction / sensory→reaction | **hard**（震惊） |
| hook→approach/action · action→action/sensory | **hard**（节奏断点） |
| *→afterglow · afterglow→afterglow | **hold**（余韵） |
| 其他连续升温 | **soft** |

**可用 xfade 名**：`fade` · `fadeblack` · `fadewhite` · `smoothleft` · `smoothright` · `smoothup` · `smoothdown` · `hblur` · `dissolve`。  
hard 位的 style 字符串只是占位（ffmpeg 走 concat）。

60s 片：**约每 2 soft 至少一个 hard**；全 soft → `SOFT_SOUP` soft 警告。

```bash
"$AIFILM" final --root <root> --lipsync off \
  --tts-backend edge --music-mood rnb --music-seed 20260720
```

改 intents/styles 后 **只需 re-final**，不必重 I2V。见 [lessons-2026-07-20-motion-transition.md](lessons-2026-07-20-motion-transition.md)。

### 5) 一角一声

固定 `vo_voice` / provider voice ID。Fish 无 ID 则拒绝。

### 6) Final 模板

```bash
"$SKILL_DIR/scripts/aifilm" final \
  --root <root> \
  --lipsync off \
  --tts-backend edge \
  --voice zh-CN-XiaoxiaoNeural \
  --transition-sec 0.28 \
  --music-mood rnb \
  --music-volume 0.48
```

## Agent 纪律

1. 一镜 **一个** 主运动方向（推或跟或摇，别全上）。  
2. I2V **串行**；失败 `fail --reason` + `requeue`。  
3. 色气硬核被审核 → soft 构图，荤点留给 VO。  
4. 量产总纪律：[production-discipline.md](production-discipline.md)。
