# References 索引

> **165** 个 reference Markdown 的分类导航（含 stages / lessons）。agent 按需加载时先查此表，再读目标文件。  
> 踩坑 lessons **76** 个，见末节按日期归档；新规则须标 P 码 + 层。  
> **文档分层（2026-08-03）**：`hard-defaults`（机读）→ `stages/*`（回合默认）→ `memory/*`（短卡）→ `lessons-*`（按需复盘）。勿在 Agents 复写 IRON 正文。  
> **用户主进度只有 7 步**（SKILL）；八环 / Professional 11-stage 为内部投影。

---

## 每回合阶段卡（Token 精简入口 · dispatch 默认）

| 文件 | 主题 |
|---|---|
| [stages/agent.md](stages/agent.md) | Brief、Lens、Graph、locks、projection |
| [stages/visual.md](stages/visual.md) | 身份、状态、几何、pilot、媒体 |
| [stages/voice.md](stages/voice.md) | 对白、旁白、BGM/SFX、mix |
| [stages/post.md](stages/post.md) | 剪辑、设计后期、字幕、post audit |
| [stages/deliver.md](stages/deliver.md) | screening、Master、export read-back |
| [stages/approval.md](stages/approval.md) | 人审、付费与外部动作暂停边界 |

机器路由：`registry/context-routing.json`。`dispatch` 默认只返回当前回合最多三份
`context_refs`；完整审计包仍写 `receipts/dispatch.json`。

## 工序与主脊（Craft Spine）

| 文件 | 主题 |
|---|---|
| [craft-spine.md](craft-spine.md) | 八环工序主脊 Idea→Verified |
| [generative-film-craft.md](generative-film-craft.md) | 生成式电影工序（Beat/Coverage/五锁） |
| [directors-lens.md](directors-lens.md) | Director's Lens 文本→故事→Storyboard→film-spec |
| [beat-spines.md](beat-spines.md) | 多类型节拍骨架总纲 |
| [pipeline-methodology.md](pipeline-methodology.md) | 工具层 + 工序层方法论 |
| [longform-workflow.md](longform-workflow.md) | 8–15 分钟竖屏长片合约、单元与恢复 |
| [principles.md](principles.md) | 底层泛化能力 P0–P5 |
| [hard-defaults.md](hard-defaults.md) | 默认与跨层决策（硬门禁完整表） |
| [production-discipline.md](production-discipline.md) | 量产纪律 season-scale |
| [short-drama-sop-bridge.md](short-drama-sop-bridge.md) | 短剧量产 SOP 的运营层桥接：G0–G11、运行卡、返工分流与三遍终检 |
| [director-self-scorecard.md](director-self-scorecard.md) | 导演自评卡 |
| [genre-migration-test.md](genre-migration-test.md) | 题材迁移测试 |

## 专业导演系统（v1.15+）

| 文件 | 主题 |
|---|---|
| [professional-director-system.md](professional-director-system.md) | Production Book / 部门合同 / 审批 ledger / stale 传播 |
| [director-methodology.md](director-methodology.md) | 40 年导演方法论注入总纲（前期/制作/后期三阶段 + 考验矩阵） |

## 规格与契约

| 文件 | 主题 |
|---|---|
| [film-spec.md](film-spec.md) | Film Spec 契约 |
| [style-bible.md](style-bible.md) | Style Bible 全片视觉语法 |
| [config-schema.md](config-schema.md) | config_loader.py 配置 schema |
| [production-routing-control-plane.md](production-routing-control-plane.md) | 镜头意图 × 有时效能力快照 × 只读路线解释 |
| [dialogue-first-workflow.md](dialogue-first-workflow.md) | 对白剧本、状态 I2I、双路线竞赛与人工晋升主链 |

## 工具栈 · Grok Build

| 文件 | 主题 |
|---|---|
| [grok-build-sdk.md](grok-build-sdk.md) | SDK 能力矩阵 |
| [grok-oauth.md](grok-oauth.md) | OAuth Pack chat/image/edit/video/tts |
| [grok-media-pipeline.md](grok-media-pipeline.md) | Grok 媒体管线 + FRW 2V 优先 |
| [generation-usage-accounting.md](generation-usage-accounting.md) | T2I/I2V/TTS 逐次次数、token 与真实费用账本 |
| [auto-dispatch.md](auto-dispatch.md) | aifilm dispatch 自动调配 |

## 工具栈 · I2V / FRW

| 文件 | 主题 |
|---|---|
| [i2v-grok-primary.md](i2v-grok-primary.md) | 旧项目显式 Grok-first 兼容模式 |
| [comfy-lan-control.md](comfy-lan-control.md) | 私有区网 ComfyUI 5090 控制、API 工作流与安全门禁 |
| [local-omni-review.md](local-omni-review.md) | 私网多模态影格审片：hash-bound、candidate-only、无云端回退 |
| [speech-preview.md](speech-preview.md) | 私有 5090 Speech-to-Speech 互动对白预演：loopback、容量门、候选回执 |
| [frw-degrade-dispatch.md](frw-degrade-dispatch.md) | FRW Seedance/LTX/经典 dispatch |
| [frw-ab-workflow.md](frw-ab-workflow.md) | FRW 全模型 pilot fan-out、机器排名、人审 champion＋challenger |
| [ltx-env-plate.md](ltx-env-plate.md) | FRW LTX T2V 无角色环境床 |
| [frw-lipsync.md](frw-lipsync.md) | FRW 口型音画同步 |
| [seedance-camera-vocab.md](seedance-camera-vocab.md) | Seedance 运镜/视觉词库 |
| [dialogue-i2i-frw-priority-and-5090-readdress](lessons-2026-07-29-dialogue-i2i-frw-priority-and-5090-readdress.md) | 历史 FRW i2i 事故与 5090 重地址恢复；现行政策为 Qwen 主路由、FRW 明确回退 |

## 工具栈 · 音频

| 文件 | 主题 |
|---|---|
| [audio-fallback.md](audio-fallback.md) | 音频三阶梯 TTS/BGM/Lipsync |
| [loudnorm-policy.md](loudnorm-policy.md) | 响度标准 LUFS -16±2（单一真相） |
| [audio-recipe.md](audio-recipe.md) | 场景自适应声轨配方 |
| [scene-sound-standard.md](scene-sound-standard.md) | **P0** 每次运行场景声音检查、环境音/拟音契约与交付门 |
| [bgm-generation.md](bgm-generation.md) | BGM 生成与抗疲劳 |
| [voice-tracks.md](voice-tracks.md) | 多轨声线（娇喘轨 opt-in） |
| [voices.md](voices.md) | 旁白与声线一致性 |
| [vo-modes.md](vo-modes.md) | VO Modes 口白策略 |
| [opensource-tts.md](opensource-tts.md) | 开源 TTS 与一角一声 |
| [lipsync.md](lipsync.md) | Lip-sync 后端政策 |
| [lipsync-challenge.md](lipsync-challenge.md) | 五后端开源唇同步挑战赛、盲测与晋级规则 |

## 工具栈 · 后期

| 文件 | 主题 |
|---|---|
| [post-compose.md](post-compose.md) | 设计后期桥 HF/Remotion |
| [postproduction.md](postproduction.md) | 正式后期与交付 |
| [hf-remotion-capability-matrix.md](hf-remotion-capability-matrix.md) | HF/Remotion 能力盘点 |
| [hf-transition-policy.md](hf-transition-policy.md) | HF 转场受控启用策略 |

## 一致性与接戏

| 文件 | 主题 |
|---|---|
| [consistency.md](consistency.md) | 画风/身份/画质一致性硬门禁 |
| [continuity_chain.md](continuity_chain.md) | 长片动作串接 |
| [keyframe-first-state-index.md](keyframe-first-state-index.md) | Keyframe-First 状态照索引 |
| [shot-motion.md](shot-motion.md) | 运镜/动态/过场/构图 |
| [character-stance.md](character-stance.md) | 角色立场/多 POV 剪辑 |

## 剪辑工艺

| 文件 | 主题 |
|---|---|
| [editor-cut-pass.md](editor-cut-pass.md) | Editor's Cut Pass |
| [editorial-craft.md](editorial-craft.md) | 资深剪辑语法 |
| [edit-strategy-voice-coupled.md](edit-strategy-voice-coupled.md) | Voice-Coupled Editorial |

## 色气 / 成人

| 文件 | 主题 |
|---|---|
| [ecchi-story.md](ecchi-story.md) | 色气叙事规范 |
| [adult-max-playbook.md](adult-max-playbook.md) | 办事剧单入口 sex≥30% |
| **[anatomy-milk-futa-comfy-batch](lessons-2026-07-29-anatomy-milk-futa-comfy-batch.md)** | **P0 毒镜解剖**：禁 futa/喷奶/霓虹器；尺度≠畸形 |
| **[evirus-ch04-bulk-final-iron](lessons-2026-07-29-evirus-ch04-bulk-final-iron.md)** | **P0 bulk→final**：moderated bare I2V / 高动 / evidence 双轮 / final 混音字幕坑 |
| **[comfy-multifilm-contention-oom](lessons-2026-07-29-comfy-multifilm-contention-oom.md)** | **P0 多片抢 5090 + 本机 OOM**：单 client；禁邻镜 meat 静默顶替 |
| **[comfy-tunnel-8188-not-8189](lessons-2026-07-29-comfy-tunnel-8188-not-8189.md)** | **P0 隧道端口**：18188→**8188** only；→8189=401；idle 立刻 submit；bare 霓虹结合符禁 register |

---

## 踩坑 Lessons（按日期）

> 新规则须标 P 码 + 层。验证稳定后可晋升到上方稳定 references。

### 2026-07-29

| 文件 | 主题 |
|---|---|
| **[agent-ship-skill-budget-push](lessons-2026-07-29-agent-ship-skill-budget-push.md)** | **P0 出货纪律**：SKILL≤6k+锚点；runtime-lock；干净树 push；heat A/S；dialogue_drama；wardrobe ladder |
| **[shot-variety-anti-boring](lessons-2026-07-29-shot-variety-anti-boring.md)** | **P0 抗重复·抗无聊**：门绿≠好看；motion 禁复制；camera 景别真变；主戏≥4.5s；contact 可读差（ch04 观感案） |
| **[closeout-gates-chaebol](lessons-2026-07-29-closeout-gates-chaebol.md)** | **P0 收尾门禁**：plate≠完；heat codes / partner_wardrobe；sensory；truth_contract；字幕真钟；quality 缓存；narrative 重绑；export 链（财阀案） |
| **[evirus-ch04-bulk-final-iron](lessons-2026-07-29-evirus-ch04-bulk-final-iron.md)** | **P0 bulk→final**：Imagine bare 拦 → undress 续接+高动；evidence 双轮；final 超时/sidechain 假死；字幕无空格或 PIL |
| **[anatomy-milk-futa-comfy-batch](lessons-2026-07-29-anatomy-milk-futa-comfy-batch.md)** | **P0 毒镜**：禁 futa/女体阴茎、喷奶乳汁、霓虹生殖器；中英硬 NEG；毒 still 禁 I2V；+ Comfy 5090 批跑资源塔 |
| **[comfy-multifilm-contention-oom](lessons-2026-07-29-comfy-multifilm-contention-oom.md)** | **P0 多片抢 5090 + 本机 OOM**：单 client；禁 pgrep 自杀；禁 09 八进制；capacity 假窗口；邻镜 meat 禁静默顶替（night-lock 案） |

### 2026-07-28

| 文件 | 主题 |
|---|---|
| **[rtx5090-lipsync-routing](lessons-2026-07-28-rtx5090-lipsync-routing.md)** | **P0 Voice→Post**：Wav2Lip 只作基线；LatentSync/MuseTalk 目标梯队；5090 CUDA 12.8 与实片 canary 门 |

### 2026-07-24

| 文件 | 主题 |
|---|---|
| **[ep2-voice-heat-final](lessons-2026-07-24-ep2-voice-heat-final.md)** | **P0**：口白中文 / 角色日文 / 禁中日乒乓；final SRT·timeout·register；肉戏 2× 动态路径（ep2 全量复盘） |
| **[high-motion-style-lock-final](lessons-2026-07-27-high-motion-style-lock-final.md)** | **P0**：高动态常态（平常≥18 肉戏≥20）；MEDIUM LOCK cel；gate 才桌面；禁弱 raw/半写实漂移（ep3 案） |
| **[adult-scale-max-sex-arc](lessons-2026-07-27-adult-scale-max-sex-arc.md)** | **P0 最重要**：成人尺度拉满优先；肉戏起承转合 **前戏→插入→射出** 全有 |
| **[headroom-no-crop-heads](lessons-2026-07-27-headroom-no-crop-heads.md)** | **P0 禁裁头**：主戏 full head；定器同镜双锁或短 insert；裁脚>裁头；打包防切顶 |
| [director-methodology-activation](lessons-2026-07-24-director-methodology-activation.md) | 导演方法论激活（若存在） |

### 2026-07-23

| 文件 | 主题 |
|---|---|
| [character-dialogue-ja](lessons-2026-07-23-character-dialogue-ja.md) | 角色日文 TTS · 旁白/字幕中文（P0；07-24 强化禁乱切） |
| [style-lock-from-ref](lessons-2026-07-23-style-lock-from-ref.md) | 输入图画风锁 medium/cast_locks（P0） |
| [face-identity-pixel](lessons-2026-07-23-face-identity-pixel.md) | 像素 face-identity 哈希 + post_audit（P0） |
| [photoreal-vs-manhua-stability](lessons-2026-07-23-photoreal-vs-manhua-stability.md) | 写实不稳 vs 漫剧质感·介质路由（P0） |
| [subs-always-burn-hard](lessons-2026-07-23-subs-always-burn-hard.md) | 字幕必烧硬门（若存在） |

### 2026-07-22

| 文件 | 主题 |
|---|---|
| [i2v-endframe-no-redress](lessons-2026-07-22-i2v-endframe-no-redress.md) | I2V 末帧不回穿 + promote 门 |
| [keyframe-no-compress](lessons-2026-07-22-keyframe-no-compress.md) | 静帧禁压缩/错幅 |
| [shaofu-cast-subs-bgm-final](lessons-2026-07-22-shaofu-cast-subs-bgm-final.md) | 少婦案 脸锁/字幕/BGM/final |
| [user-source-fidelity](lessons-2026-07-22-user-source-fidelity.md) | 用户原文保真 |
| [verify-before-generate](lessons-2026-07-22-verify-before-generate.md) | 先验后生·算力刀口 |

### 2026-07-21

| 文件 | 主题 |
|---|---|
| [audio-recipe-routing](lessons-2026-07-21-audio-recipe-routing.md) | 音频配方路由 |
| [bgm-instrumental-fallback](lessons-2026-07-21-bgm-instrumental-fallback.md) | BGM 纯乐器兜底 |
| [bgm-multi-style](lessons-2026-07-21-bgm-multi-style.md) | BGM multi-style |
| [ecchi-climax-ratio-multi](lessons-2026-07-21-ecchi-climax-ratio-multi.md) | 色气高潮比例 |
| [first-last-gen](lessons-2026-07-21-first-last-gen.md) | 生成 first/last 接戏 |
| [frw-key-capability](lessons-2026-07-21-frw-key-capability.md) | FRW key 能力 / 403·502 |
| [hair-color-lock](lessons-2026-07-21-hair-color-lock.md) | 发色硬锁 |
| [intercourse-impact-benchmark](lessons-2026-07-21-intercourse-impact-benchmark.md) | 性交冲击力标竿 |
| [keyframe-first-frame-poison](lessons-2026-07-21-keyframe-first-frame-poison.md) | 首帧毒化 |
| [montage-hardcore-male](lessons-2026-07-21-montage-hardcore-male.md) | 蒙太奇+重口男向 |
| [no-shot-watermark](lessons-2026-07-21-no-shot-watermark.md) | 禁 shot 水印 |
| [sex-duration-floor](lessons-2026-07-21-sex-duration-floor.md) | 性爱时长硬底 ≥30% |
| [sex-undress-ladder](lessons-2026-07-21-sex-undress-ladder.md) | 办事卸甲阶梯·不回穿 |
| [sex-vo-spice](lessons-2026-07-21-sex-vo-spice.md) | 旁白荤梗硬底 |
| [size-ladder-hardcore-stack](lessons-2026-07-21-size-ladder-hardcore-stack.md) | 景别情绪堆叠 |
| [tts-shengwang-eval](lessons-2026-07-21-tts-shengwang-eval.md) | TTS 声网评测 |
| [wardrobe-no-redress-still](lessons-2026-07-21-wardrobe-no-redress-still.md) | 卸装后 still 源链 |

### 2026-07-20

| 文件 | 主题 |
|---|---|
| [action-fluency](lessons-2026-07-20-action-fluency.md) | 动作流畅 |
| [audio-compose](lessons-2026-07-20-audio-compose.md) | 音频混音 |
| [bgm-anti-fatigue](lessons-2026-07-20-bgm-anti-fatigue.md) | BGM 抗疲劳 |
| [character-stance](lessons-2026-07-20-character-stance.md) | 角色立场 |
| [cut-silk-bilingual](lessons-2026-07-20-cut-silk-bilingual.md) | 剪辑丝滑/双语字 |
| [designed-post-fluency](lessons-2026-07-20-designed-post-fluency.md) | 设计后期流畅 |
| [directors-lens](lessons-2026-07-20-directors-lens.md) | Director's Lens 上游 |
| [editor-cut-ecchi-scale](lessons-2026-07-20-editor-cut-ecchi-scale.md) | 剪辑色气尺度 |
| [editorial-craft](lessons-2026-07-20-editorial-craft.md) | 剪辑工艺 |
| [frame-chain](lessons-2026-07-20-frame-chain.md) | 帧链 |
| [frw-2v-first](lessons-2026-07-20-frw-2v-first.md) | FRW 2V 优先 |
| [frw-ltx-probe](lessons-2026-07-20-frw-ltx-probe.md) | FRW LTX 探测 |
| [layer-routing](lessons-2026-07-20-layer-routing.md) | 分层路由 |
| [meaningful-motion](lessons-2026-07-20-meaningful-motion.md) | 有意义运动 |
| [motion-transition](lessons-2026-07-20-motion-transition.md) | 运动转场 |
| [sediment-cn-codex](lessons-2026-07-20-sediment-cn-codex.md) | 沉淀 |
| [seedance-quality](lessons-2026-07-20-seedance-quality.md) | Seedance 质量 |
| [title-double-burn](lessons-2026-07-20-title-double-burn.md) | 标题双烧 |
| [transition-motion-v2](lessons-2026-07-20-transition-motion-v2.md) | 转场运动 v2 |
| [vo-atempo-three-axis](lessons-2026-07-20-vo-atempo-three-axis.md) | VO atempo 三轴 |
| [vo-drag-motion-snap](lessons-2026-07-20-vo-drag-motion-snap.md) | VO 拖拽运动 snap |

### 2026-07-16 ~ 17

| 文件 | 主题 |
|---|---|
| [kei](lessons-2026-07-16-kei.md) | kei 案 |
| [compose-pilot](lessons-2026-07-17-compose-pilot.md) | compose pilot |
| [run-to-completion](lessons-2026-07-17-run-to-completion.md) | 一路做完 |
| [vo-motion-link](lessons-2026-07-17-vo-motion-link.md) | VO 运动链接 |
