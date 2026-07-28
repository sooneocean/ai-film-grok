# 量产纪律（season-scale / 多集）

与 `write-spec`、`media-queue` **代码门禁**对齐。Agent 不得只读本文而绕过 CLI。

## 先验后生 · 算力刀口（2026-07-22 · P0）

**验证完再生成**——图与视频同一逻辑；重复生成成本过高。

| 顺序 | 动作 | 禁 |
|---|---|---|
| 1 | still / image 落盘 | 未读图就当 keyframe |
| 2 | 几何+身份+结构过闸 | 缩水/横图/坏脸进库 |
| 3 | 才 I2V 或 bulk edit | 未验 30 still 开 30 I2V |
| 4 | 坏了只修上游再烧 | 对糊图盲重试 video |

权威课：[lessons-2026-07-22-verify-before-generate.md](lessons-2026-07-22-verify-before-generate.md) · 几何：[keyframe-no-compress](lessons-2026-07-22-keyframe-no-compress.md)。  
用户说「一路做完」= 不反复停问，**仍须每镜先验**。

## 叙事上游（Director’s Lens · 2026-07-20）

用户给文本/brief 时：**先** [directors-lens.md](directors-lens.md) 重构故事与 storyboard，**再** `film-spec` / `write-spec`。  
禁止原文插图化；可选收据 `receipts/directors-lens.md`。沉淀见 [lessons-2026-07-20-directors-lens.md](lessons-2026-07-20-directors-lens.md)。

## 规划 ≠ 剪辑（Editor’s Cut · 2026-07-20）

| 阶段 | 产出 | 完成判据 |
|---|---|---|
| A 生成规划 | still+clip 库存齐 | register 全过 |
| B 剪辑师过片 | `receipts/editor-cut.md` 四轴 | 再 final 才可称交付级 |

权威：[editor-cut-pass.md](editor-cut-pass.md)。  
成人漫剧默认 `heat_scale: max` + 双 KPI（看点+刺激点）：[ecchi-story.md](ecchi-story.md)。

## VO 预算与反 loop（硬门禁 · S1/S2）

| 规则 | 值 | 实现 |
|------|-----|------|
| **推荐（快节奏）** | **≤28 字** | `_vo_budget.recommended_nar_chars` + `shots_over_recommended` |
| **硬上限** | **≤55 字** | `validate_nar_budget` → `FilmSpecError` 含 `vo_budget` |
| 估算 | `est_vo_sec ≈ len(nar)/4` | 每镜 `est_vo_sec` |
| **S1 vo_pacing** | `est_vo_sec ≤ duration_sec + 0.5` | `write-spec` **失败**（`vo_pacing`）；默认 `duration_sec=6` |
| **S2 no-loop beats** | `hook` / `action` | `plan_stretch(forbid_loop)` → 永不 `stream_loop`；盖不住则 final 报错 |
| final 二次门 | `loop_risk_shots` 非空 | `assert_no_loop_risk` 挡 final |

**一镜一句一动作**。多情节 → 拆成多镜（新 still + 新 motion）。  
**禁止**用 `stream_loop` 把同一画面正放两遍来「撑时长」。  
**时长不够 → 加镜 / 升 10s / 砍字**，不要 loop。

## 口白·动作锁与防腻（soft · 2026-07-17）

| 规则 | 实现 |
|------|------|
| hook/approach/action 须有**主动词** | `_vo_motion_link` → `PRIMARY_MOTION_WEAK` |
| 连续 3 镜微动同构 | `MOTION_MONOTONY` |
| 连续 3 镜景别带不变 | `SIZE_FLAT` |
| ≥5 soft 且 0 hard | `SOFT_SOUP` |
| 硬拦（可选） | film-spec `vo_motion_strict: true` |

Agent 写 still/I2V prompt 时：**motion 字符串以主动作为首**，微动垫后。用户说「腻 / 对不上」→ 先改 spec 再重渲问题镜。

## 动态叙事意涵 Meaningful Motion（soft · 2026-07-20）

| 规则 | 实现 |
|------|------|
| 驱动镜禁止纯氛围 filler | `MOTION_NO_MEANING` |
| motion 须含 beat 语义族 | `BEAT_SEMANTICS_MISS` |
| 建议 `visible_change` / `story_beat` | `VISIBLE_CHANGE_MISSING` |
| 硬拦（可选） | `meaningful_motion_strict: true` |

每镜 I2V 须回答 beat 故事问题（登场/靠近/感官/反应/行动/余韵）。  
详解：[lessons-2026-07-20-meaningful-motion.md](lessons-2026-07-20-meaningful-motion.md)。

## Continuity Chain（硬 · 2026-07-20）

| 规则 | 实现 |
|------|------|
| 长片必须有 `continuity_chain.md` | preflight **hard** `continuity_chain_doc`；`continuity-chain init` |
| 下镜首帧逐字节 = 上镜已核准末帧 | `extract-frame --promote-keyframe`；`receipts/frame-chain.json` |
| 禁止从 cast/角色参考重起 continue 缝 | 政策 + check |
| 连接点九项核对 | pose·gaze·hands_props·travel·axis·hair·wardrobe·weather·lighting |
| 禁止掩盖 | dissolve 加长 / 定格 / 倒放 / 无关插镜 |
| end_pose→start_pose 文本 | `_frame_chain` soft `FRAME_CHAIN_GAP` |
| 硬拦字节/清单 | `continuity-chain check --strict`；`frame_chain_strict` |

详解：[continuity_chain.md](continuity_chain.md)、[lessons-2026-07-20-frame-chain.md](lessons-2026-07-20-frame-chain.md)。

## 设计后期 HyperFrames / Remotion（观感 · 2026-07-20）

| 规则 | 实现 |
|------|------|
| continue 链交付默认上设计后期 | plate 后 `final --post-engine hyperframes`（或 remotion） |
| 只做字幕/片头/统一 grade | underlay；`compose-preview` 再 render |
| **防字幕双烧** | designed-post 默认 `subs off`；burned_in plate 禁 underlay |
| **防标题双烧**（2026-07-20 用户验收） | designed-post 默认 **`plate-cards blank`**（pad 无字）；HF/Remotion 画唯一片名 |
| **转场丝滑 v2** | `transition_fluency: silk`；**continue 强制 hard**（作者 soft 也改）；styles 轮转；约每 2 soft 一 hard |
| **运镜防腻 v2** | 每镜 `dsl.camera_axis` 轮换；禁三连同轴 / 全 push-in；改运镜须 re-I2V |
| **中英双字幕** | `caption_mode: zh_en` + 每镜 `nar_en`；HF 双行 / Remotion pre-line |
| **满 60s** | **加镜** 或升 `duration_sec`；禁止用更长 dissolve 装时长 |
| 禁止 Ken Burns 当戏 | post-compose 硬边界 |
| 禁止接戏缝再 dissolve underlay | package.`fluency.designed_post_must_not` |
| 改 compose 前 load skill | HF: `/hyperframes`+core；Remotion: best-practices+captions |

详解：[post-compose.md](post-compose.md)、[hf-remotion-capability-matrix.md](hf-remotion-capability-matrix.md)、[lessons-2026-07-20-cut-silk-bilingual.md](lessons-2026-07-20-cut-silk-bilingual.md)、[lessons-2026-07-20-transition-motion-v2.md](lessons-2026-07-20-transition-motion-v2.md)、[lessons-2026-07-20-designed-post-fluency.md](lessons-2026-07-20-designed-post-fluency.md)、[lessons-2026-07-20-title-double-burn.md](lessons-2026-07-20-title-double-burn.md)。

## Pilot 硬门禁（S3）

| 状态 | 允许 `media-queue add` |
|------|------------------------|
| 无用户 pilot | 最多 **3** 个不同 `shot_id`（pilot 窗口） |
| `approved_by: user` | 不限 |
| `approved_by: agent` 等 | **拒绝**（禁止自批） |
| 紧急 | `--allow-without-pilot` 或 `AIFILM_SKIP_PILOT_GATE=1` |

路径：`receipts/pilot-approval.json`。

## Grok I2V 优先（FRW 技术备援）

| 规则 | 要求 |
|------|------|
| 默认 | `i2v_provider: grok`；`auto` 永远解析 Grok primary |
| Still | **Grok** `image_edit(cast)` 同源；禁止 FRW text2image 批量主角 |
| Still 卸装后 | peak 后 **只** `image_edit(undress-anchor/已脱 still)`；**禁**全装 cast 重起（回穿 P0） |
| 状态照索引 | `cast_state_masters` + keyframe-first；I2V 只吃 keyframe；坏了改 keyframe |
| bulk 2V | **Grok `image_to_video`**；FRW `newvideo` / `frw_seedance_i2v`（`seedance-2-fast-i2v`）仅 provider-switch 后执行 |
| 有尾帧 | FRW first-last 仅 fallback；保留 pair checksum 与 Contract checksum |
| 入组 | 下载 → ffprobe → 全解码 → perceptual/exact duplicate gate → 人工 review |
| **L1 人物** | Grok I2V → FRW Seedance/LTX fallback；`shot_role: hero` + cast still |
| **L2 合成** | Grok no-face motion；FRW `ltx-t2v` 仅 fallback；禁用 T2V 声称脸一致 |
| LTX 参数 | dims/duration/fps **string**；FRW `720p` 档位下竖屏原生 704×1280 |
| 禁止默认 | legacy img2video；T2V 当 A-roll 主角 |
| 记账 | seedance-blocked / LTX 502；恢复后重烤 |

详解：[layer-routing.md](lessons-2026-07-20-layer-routing.md)、[frw-degrade-dispatch.md](frw-degrade-dispatch.md)、[frw-ltx-probe.md](lessons-2026-07-20-frw-ltx-probe.md)。

## cn / codex 沉淀门禁（2026-07-20）

| 规则 | 实现 |
|------|------|
| 构图禁裁头词 | `framing_lint` → write-spec `_framing_lint`；preflight soft/hard；`framing_strict` |
| 镜库存一致 | `shot_inventory` → preflight hard `inventory_mismatch`；assemble/final assert |
| queue 无 ghost shot | `media-queue add` 要求 shot_id ∈ film-spec |
| 时长 fail-loud | `media_duration.probe_duration_sec`；render/compose/`aifilm.media_duration` |
| TTS 预演 + 实测时长门 | `tts-rehearse` → receipt；preflight/final **优先 measured**；超 plate hard；`tts_rehearsal_required` / `--strict-tts-rehearsal` |
| Edge 空流重试 | `tts_edge` min 500B × 3 attempts |
| VO atempo 三轴 | slot 默认：视频定 plate + `vo_atempo`；上限 1.5；`--vo-fit` |
| `next` 路由 | clips 齐 → `tts-rehearse`；framing 风险 → fix-framing |
| 证据分层 | `status.evidence` intent ≠ executed ≠ human_review |

详解：[lessons-2026-07-20-sediment-cn-codex.md](lessons-2026-07-20-sediment-cn-codex.md)。  
**非 port**：5090 IP-Adapter 必经、Studio/OpenCut 必交付、Director Contract v2 硬依赖、**Grok I2V ≠ first-last-frame**、平台 FRW zip 覆盖本机 frwclaw。

### FRW 降级（用户授权时 · 2026-07-20）

| 规则 | 实现 |
|------|------|
| 官方 CLI | `frw_dispatch` / `dispatch.py`；stdout JSON protocol 1.0 |
| 分镜 I2V | 优先 `first-last-frame`；禁错 poll batch FLF |
| 入 Grok 控制台 | `reencode-clips` → `register-clip`（`provider=frw model=…`） |
| 同源 | 禁止半片 Grok + 半片 FRW 混角色 |

详解：[frw-degrade-dispatch.md](frw-degrade-dispatch.md)、[consistency.md](consistency.md) §3。

### Pilot 一键辅助（2026-07-17）

```bash
aifilm pilot pick|report|score|approve --root <root>
```

- `score` 三维 fail 时**默认**写入 `director_notes.json` 重拍项（可用 `--no-notes-on-fail` 关闭）。
- `approve` 必须用户原话，且默认要求 scorecard 全 pass。
- **批准词扩展（2026-07-17）**：`pilot 过` / `可以批量` / 短确认 `可以` / `ok` / `好的` / `行`；含 `生成完成`/`做完`/`直接进行` → `run_to_completion: true`（批准后一路到 final，勿再停问）。**不算批准**：`可以改` / `不行` / `重做`。
- 第 4 镜 `media-queue add` 被拦时，错误信息会提示 `pilot report → score → approve`。
- `aifilm status` 输出 `next_actions` / `next_cmd` 路由下一步。

## I2V 串行 + pilot 门禁（代码）

- `media-queue` `max_concurrency=1`。
- Agent 侧也**禁止**并行多个 `image_to_video`（429 `rate_limit`）。
- continue 链 **串行**：`clip[i]` → `extract-frame --promote-keyframe` → I2V[i+1]（首帧字节复用末帧）。
- 每次：`claim` → 一次工具调用 → `complete` 或 `fail`。
- **`media-queue add` 门禁**（`production_gates.assert_pilot_allows_add`）：
  - 无用户 pilot 批准 → **最多 3 个不同 shot_id**（pilot 窗口）
  - 第 4 个起必须 `receipts/pilot-approval.json` 含 `approved: true` + `approved_by: user`
  - 应急：`--allow-without-pilot` 或 `AIFILM_SKIP_PILOT_GATE=1`（仅测试/急救）
- **`final` 门禁**：`assert_no_loop_risk`；应急 `--allow-loop-risk`
- `rate_limit` 默认退避 **90s**。

## 失败分类与 requeue

| `--reason` | 含义 | 默认行为 |
|------------|------|----------|
| `moderation` | Imagine 内容审核 | **failed**（不自动空转）；换 soft still 后 `requeue --reset-attempts` |
| `motion` | motion_score / 静帧 | 可退避 pending |
| `rate_limit` | 429 / 503 / resource-exhausted | 退避 **90s** pending |
| `decode` | 损坏/无法解码 | 可退避 |
| `other` | 其余 | 可退避 |

```bash
media-queue fail --root ROOT --job-id ID --claim-token TOK \
  --error "…" --reason moderation
media-queue requeue --root ROOT --job-id ID --reset-attempts
```

**禁止**手改 `receipts/media-queue.json`。



## 色气 BGM（R&B / Soul · 硬默认）

| mood | 何时用 |
|------|--------|
| **`rnb`** / `soul` / `sensual` | **色气、里番、同人、诱惑** 默认（late-night Rhodes） |
| `warm` / `playful` | 日常、轻快 |
| `dark` | **仅**恐怖/惊悚 — **禁止**当里番默认 |

- `write-spec`：缺 `sound_plan` → 自动注入 `mood=rnb`（storyteller/色气 tone）。
- tone 含 色气/里番/后宫 等却写了 `dark` → **自动改 rnb** 并记 `_sound_plan_notes`。
- `final`：`sound_plan.mood` **覆盖** `--music-mood`；CLI 默认也是 `rnb`。
- 别名：`soul` / `seductive` / `ecchi` → `rnb`。

## TTS（中文）

- 成片旁白默认：`--tts-backend edge` + `zh-CN-YunxiNeural` / `zh-CN-XiaoxiaoNeural`。  
- `write-spec`：storyteller/hybrid 且 `tts_backend=auto` → **自动钉 edge**。  
- 若环境 `AIFILM_TTS_ARGV` 指向 ElevenLabs 等 external：**禁止**把 edge 的 Neural 名当 provider voice id（preflight hard / synthesize 失败）。  
- 一角一声仍成立：显式 edge 后端时整片锁同一 `vo_voice`。

## 听感默认（2026-07-20 A–H · 见 lessons-2026-07-20-audio-compose.md）

- BGM：`rnb` + 侧链 release≈720ms；loudnorm **auto**（过响/过轻 → ~-16 LUFS）。  
- SFX：`auto_sfx` 按 beat 叠入；关：`sound_plan.auto_sfx=false`。  
- 本地曲：`audio/bgm.wav` 或 `audio/templates/rnb.wav` + `*.license.txt`；`--music-template off` 强制程序化。  
- `status` → `audio.*`；`audio/mix_report.json` 可审计。

## I2V 静戏 motion

- 静戏（倾听、对视、坐）也必须写 **可测微动**：blink / breath / hair / push-in。  
- `register-clip` motion 失败：`fail --reason motion` → 加强 motion 文案后 `requeue --reset-attempts`，**不要**用静帧蒙混。

## 系列续作

- 同角色：**复制 cast master**，新 root + 新 film-spec。  
- 用户明确说「整集生产 / 新版本」：pilot-approval 可记 `user_phrase`；禁止无用户意图空批。  

## 审核安全视觉（soft ladder）

色气优先靠 **VO + 距离/湿/眼神/崩溃脸**，不要连撞 explicit 构图。

建议阶梯（仍全员成人）：

1. 对视 / 耳语距离  
2. 贴身拥抱、湿发、蒸汽  
3. 锁骨/颈线、服装失序暗示  
4. 震惊 / 泪崩 / ahegao-despair **表情**（非露点硬核）

`explicit` 构图若 moderated：**同一 beat 改 clothed suggestive**，`nar` 可保留荤点（storyteller）。

## 微动 + 构图 + 丝滑接缝

- `sensory` / `reaction` / `afterglow` / `hook`：缺 blink/breath/tremble/hair/push-in 时 **注入**微动。
- 缺 `camera.shot_size` / `angle` / `framing` 时按 beat 补 **竖屏构图**。
- 默认 `transition_sec=0.28` soft dissolve；未写 `transition_intents` 时按 beat 自动 soft/hard/hold。
- I2V motion 偏好 **continuous / smooth / 单轴**（详见 [shot-motion.md](shot-motion.md)）。
- 旁白默认略增益、`vo_rate≈-3%`，BGM 略让路。

## lock-style 同源

`--canonical` 指向已是 `canonical/style-v1.*` 时 short-circuit，只更新 hash + `locked=true`，不 `SameFileError`。

## 画风 / 身份一致性（硬纪律）

详见 [consistency.md](consistency.md)、[style-bible.md](style-bible.md)。摘要：

1. **定妆双件套**：`style-v1`（介质）+ `cast/<id>-v1`（脸服）；转面设定图不得直接当 style 锁定。  
2. **Pilot 3 镜批准**后才批量 still / I2V；写 `receipts/pilot-approval.json`。  
3. 主角镜只用 **edit / img2img**，cast 为第一参考；禁止纯文生主角。  
4. 降级 FRW 时：**固定 model + 固定分辨率 + 全程 img2image**；禁止半片 Grok 半片 FRW 混角色。  
5. 终审 scorecard 必须含 **`style`**；style fail 不得交付。  
6. 每镜 prompt 前缀强制 `signature_block` + `identity_lock`。  
7. **画面零工程字（致命）**：prompt **禁止**写 `shot11`/`keyframe shotXX`；必写 `No text/watermark/labels`；register 前扫四角。见 [lessons-2026-07-21-no-shot-watermark.md](lessons-2026-07-21-no-shot-watermark.md)。  
8. **首帧结构（致命）**：I2V 首帧=keyframe；手指数/融合/破面 fail → **禁 I2V**；register-clip 前抽 t=0。见 [lessons-2026-07-21-keyframe-first-frame-poison.md](lessons-2026-07-21-keyframe-first-frame-poison.md)。

### 教训 [2026-07-16]（完整表见 [lessons-2026-07-16-kei.md](lessons-2026-07-16-kei.md)）

追加（同日 v3/v4 收工）：

- 现象：漏光环 / EL 中文差 / 有 srt 无画面字 / 60s 变 30s。  
- 规则：签名配件写进 lock；中文用 Edge 女声；**必须烧录字幕**；时长用槽位堆；续集新 root+复用 cast。

- 画风漂：无锚批量 / 混 provider / 设定图当 style → 双 master + 单 provider + pilot。  
- 重播无聊：长 VO → loop → **nar≤28 + 一镜一句**。  
- final 炸：并发 final、脏编码、sha 不同步 → 串行 final、re-encode、re-register。  
- pilot 自批无效：必须用户明确「pilot 过」。
