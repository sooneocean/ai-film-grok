# ai-film-grok 内容创作质量优化计划（专家团诊断 · 2026-08-06）

> 主理人：司远（Soren）｜版本：基于 ai-film-grok `v2.39.95`  
> 说明：本计划由创意制片人整合**叙事/视觉/视频/后期/音频**五域诊断而成。各域结论均锚定项目真实子系统与既有踩坑 lesson（references 共 165 篇、lessons 77 个），目标是把"门绿但翻车"的已知坑位固化为自动硬门，并把 lesson 级经验晋升为默认策略。

---

## 执行状态（2026-08-06 已落地）

P0 五个自动硬门已全部实现并接入门禁/流水线，相关测试全绿（新增 56 用例，全量非 slow 套件 3153 passed）。详见 CHANGELOG。

> ⚠️ 双 checkout 并发：本会话（git 根 `/Users/dex/.grok/ai-film-grok`）与插件/其他 checkout 同推一个 `main`，远端多次 force-push。下列 P1 项由**另一条开发线**已先行落地（非本会话）：narrative 收尾重绑 + 发色锁 + 成人弧线（v2.40.6）、运动量化门 + 字幕 CJK + BGM 抗疲劳 + style NEG（v2.40.7）。本会话聚焦补齐**尚未覆盖**的 P1 项。

### P0（本会话落地）
| P0 | 门 | 落地文件 | 测试 |
|----|----|---------|------|
| 1 | 抗无聊硬门 | `gates/production_gates.py` `assert_anti_boring_variety` + `preflight` 接入 | `test_production_gates.py::AntiBoringGateTests` |
| 2 | 每镜脸身份 post_audit 门 | `gates/production_gates.py` `assert_face_identity_passed` + `preflight` + `cli_media.register_clip` 注入 | `test_production_gates.py::FaceIdentityGateTests` |
| 3 | 九项接戏程序化校验 | `assets/continuity_chain.py` 九项清单 + 字节复用 + **新增禁止掩盖检测** + `gates/production_gates.py` `assert_continuity_chain_passed` | `test_continuity_chain.py`（含 coverup 用例） |
| 4 | render_final 超时/假死防护 | `post/render_final.py` `_run_with_watchdog` + `--render-timeout`（默认 1800s，0 关闭）+ `final/errors.py` `RenderTimeoutError` | `test_render_watchdog.py` |
| 5 | TTS 语言乒乓校验 | `audio/voice_cast_profiles.py` `detect_language_pingpong` + `audio/audio_plan.py` 接入 | `test_tts_language_pingpong.py` |

### P1 进度（截至 v2.40.9）
| P1 项 | 状态 | 落地 |
|------|------|------|
| 发色锁 / 成人弧线 / narrative 收尾重绑 | ✅ 另一条线 | v2.40.6 |
| 运动量化门 / 字幕 CJK / BGM 抗疲劳 / style NEG | ✅ 另一条线 | v2.40.7 |
| **headroom 自动构图保护（时间线防裁头）** | ✅ **本会话** | v2.40.9 `headroom_report` + `assert_headroom_protected` + preflight 接入（`test_headroom.py` 12 用例） |
| 首帧毒化/静帧压缩 → style_lock 默认 | 🟡 部分（NEG token 在，未强制门） | 待补 |
| 5090 统一调度器 | 🟡 部分（h3_fill_idle free_first） | 待补/进行中 |
| lipsync 自动晋级 | ⛔ v2.40.0 已冻结，跳过 | — |
| HF 转场受控策略（spec 级校验） | ✅ **本会话** | v2.40.11 `transition_policy_report` + `assert_transition_policy` + preflight 接入（`test_transition_policy.py` 16 用例） |
| **HF 转场 export read-back 全量** | ✅ **本会话** | v2.40.12 `transition_export_readback_report` + `assert_transition_export_readback` + preflight 接入（`test_transition_export_readback.py` 19 用例）；校验 built transition_ops 全量覆盖 + 意图/风格/策略一致（continue→hard_cut/0.0s/no-overlay；soft→xfade+声明风格；chapter→soft fade/dissolve；scene cut→禁 whip/grid） |
| **visual_bible 自动生成（第一增量）** | ✅ **本会话** | v2.40.13 `derive_style_bible_from_spec` + `assert_style_bible_consistency` + preflight 接入（`test_style_bible_consistency.py` 12 用例）；spec 驱动派生 lighting_timeline（heat_phase）+ cast_masters，consistency 门校验缺失/hero 缺失/光照数不一致 —— 视觉语法自洽第一增量，像素 palette 抽取待补 | 
| **5090 no-hog 程序化校验（第一增量）** | ✅ **本会话** | v2.40.14 `gpu_no_hog_decision` + `gpu_no_hog_report` + `run_next_fill_idle` 显式守卫（`test_gpu_no_hog.py` 13 用例）；把"busy→零 submit 除非本会话独占 GPU"固化成纯函数+单测，补 submission_capacity 报 ready 却带 `COMFY_QUEUE_BUSY` 的漏判 —— 5090 统一调度器 / H3 Fill-Idle 第一增量 | 
| **H3 Fill-Idle 自动派单（dispatch-order 显式化）** | ✅ **本会话** | v2.40.15 `fill_idle_sort_key` 抽离为纯函数+单测（`test_fill_idle_dispatch_order.py` 8 用例）；P0→P1→P2 / dual-sticky 优先 / P1 最少 H3 takes / P2 最低 mean 派单序从 `build_fill_idle_queue` 内嵌闭包提升为可测不变量 | 
| **H3 Fill-Idle 模式/Lane 选取（R2V=能量位自动选取）** | ✅ **本会话** | v2.40.16 `select_fill_idle_mode` 抽离为纯函数+单测（`test_fill_idle_mode_select.py` 10 用例）；把 `classify_fill_idle_shot` 末尾的 R2V=能量位自动选取内联分支提升为可测不变量：primary dual second leg（r2v / flf-i2v）+ P2 soft challenge 优先 face-lock（flf/i2v）除非真实 on-cam-close 能量 | 
| **H3 Fill-Idle P2 空闲挑战自动派（γ3 低 ROI 跳过）** | ✅ **本会话** | v2.40.17 `decide_p2_challenge` 抽离为纯函数+单测（`test_fill_idle_p2_challenge.py` 9 用例）；把 `classify_fill_idle_shot` 的 `has_still and has_any` 分支（含 γ3 `best>=floor+6.0` 低 ROI 跳过）提升为可测不变量：H3 已 ok→done / H3 低于 floor→P1 retry / 无 H3 且基线强→skip_p2_baseline_strong / 否则 P2 fill_idle_challenge（有 grok 基线标 has_baseline_take） | 
| **介质自动路由（按角色稳定性选写实/漫剧）** | ✅ **本会话** | v2.40.18 `media/media_routing.py`：`route_character_medium`（unstable+photoreal→anime）/ `load_cast_stability`（spec `cast_stability` 覆盖，默认全 stable）/ `resolve_shot_medium` / `media_routing_report`；规划期定介质、不破运行时 medium lock；`test_media_routing.py` 15 用例。闭合 P2「介质自动路由」 |
| sung 自动生成 | ⬜ P2 | 未做（`audio_recipe` 已有 `musical_hybrid`+`sung_beat`+无 provider 降级；缺口仅在 HeartMuLa 实际生成后端，外部依赖阻塞；可建 `SungProvider` 接口+`LocalFallbackSungProvider` 闭环，不依赖外部） |

> 剩余真正开放的高 ROI P1/P2：首帧毒化·静帧压缩晋升 style_lock 默认硬锁、介质自动路由、H3 Fill-Idle 完整派单（R2V 能量位 + P2 空闲挑战自动派）、sung 自动生成（HeartMuLa⛔）、长片 SOP 固化。

---

## 0. 现状成熟度概览

| 维度     | 成熟度                                        | 一句话结论                                 |
| ------ | ------------------------------------------ | ------------------------------------- |
| 叙事/剧本  | 高（有 drama_graph + script-value-debrief 锁门） | 缺**自动抗无聊/弧线完整性**校验                    |
| 视觉一致性  | 高（style_lock + face pixel hash）            | 缺**每镜自动 post_audit 门**与发色/首帧毒化默认硬锁    |
| 视频/运镜  | 高（三级 fallback + continuity_chain）          | 缺**九项接戏程序化校验**与运动量化门                  |
| 后期/交付  | 中高（editorial-craft + delivery gates）       | **final 超时/假死**与字幕/headroom 偶发问题未自动防护 |
| 音频/本地化 | 高（5 配方 + 5 轨 + 多 TTS）                      | **TTS 语言乒乓**、sung 缺失、lipsync 晋级未全自动化  |

**核心思路**：项目不缺能力，缺的是"把已验证的 lesson 变成默认门禁 + 程序化校验"。本计划 80% 的工作是**固化与自动化**，而非从零新增。

---

## 1. 叙事 / 剧本（笔澜视角）

**现状强项**：`drama_graph` + `narrative_control` 推导、`script-value-debrief`（L0–L4 呈现价值锁门）、`dialogue-first` 中文主链、`edit_policy_heat` 尺度控制。

**最影响成片质量的短板**

1. **抗无聊未固化**：`shot-variety-anti-boring(P0)` 仍停留在 lesson——主戏≥4.5s、景别真变、motion 禁复制没有自动卡，导致"门绿但难看"。
2. **narrative 收尾重绑弱**：`closeout-gates(P0)` 要求收尾 narrative 重绑，但实现松散、易漏。
3. **成人弧线完整性无校验**：`adult-scale-max-sex-arc` 要求前戏→插入→射出全有，未自动检查 beat 齐备。
4. **多 POV / 角色立场**未与分镜自动绑定（`character-stance`）。

**优先级优化建议**

| 优先级    | 目标                | 具体动作                                        | 落地模块/文件                                                                 | 预期收益       |
| ------ | ----------------- | ------------------------------------------- | ----------------------------------------------------------------------- | ---------- |
| **P0** | 抗无聊自动硬门           | 在 production gate 加：主戏时长、景别序列去重、motion 描述去重 | `scripts/gates/production_gates.py` + 晋升 `shot-variety-anti-boring` 为硬门 | 直接消除最大观感问题 |
| P1     | narrative 收尾重绑自动化 | closeout 阶段强制 narrative 重绑检查并写 receipt      | `scripts/spine/advance.py` + `receipts/`                                | 收尾不丢叙事承诺   |
| P1     | 成人弧线完整性校验         | beat 序列校验前戏/插入/射出齐备                         | `scripts/narrative/edit_policy_heat.py`                                 | 尺度拉满且结构完整  |
| P2     | 多 POV 自动分镜标签      | character-stance 生成 shot 级 POV 标签供剪辑用       | `scripts/plan/*` + `scripts/assets/*`                                   | 剪辑可自动做立场切换 |

> **Top-1 ROI**：抗无聊自动硬门——成本最低、观感提升最直观。

---

## 2. 视觉一致性 / 画风锁定（珀西视角）

**现状强项**：`style_lock`（高动 MEDIUM LOCK cel）、`face_identity` 像素哈希 + `post_audit`、`keyframe-first` 状态照、`wardrobe_ladder`。

**最影响成片质量的短板**

1. **脸身份漂移**：`face-identity-pixel(P0)` 有哈希，但高动/换装后未强制每镜 `post_audit` 通过才 `register-clip`。
2. **发色/首帧毒化/静帧压缩**仍是 lesson 级（`hair-color-lock`、`keyframe-first-frame-poison`、`keyframe-no-compress`），未进 `style_lock` 默认。
3. **写实 vs 漫剧介质路由**稳定性未自动化（`photoreal-vs-manhua-stability`）。

**优先级优化建议**

| 优先级    | 目标                | 具体动作                                           | 落地模块/文件                                             | 预期收益      |
| ------ | ----------------- | ---------------------------------------------- | --------------------------------------------------- | --------- |
| **P0** | 每镜脸身份自动门          | `register-clip` 强制 face post_audit 不通过即 reject | `scripts/assets/face_identity.py` + post audit      | 一致性最大痛点根治 |
| P1     | lesson→默认硬锁       | 发色/静帧压缩/首帧毒化晋升 `style_lock` 默认硬 NEG/校验         | `scripts/assets/style_lock.py` + `hard-defaults.md` | 减少人工守门    |
| P1     | 介质自动路由            | 按 cast_state 稳定性评分选 I2V 路线（写实/漫剧）              | `scripts/media/*` 路由层                               | 降低出图漂移    |
| P2     | visual_bible 自动生成（第一增量） | spec 驱动派生 lighting_timeline（heat_phase）+ cast_masters，style-bible consistency 门（缺失/hero 缺失/光照数不一致） | `scripts/assets/visual_bible.py` + `gates/production_gates.py` | 全片视觉语法自洽（像素 palette 抽取待补） |

> **Top-1 ROI**：每镜脸身份自动门。

---

## 3. 视频生成 / 运镜 / 跨镜连续性（维欧视角）

**现状强项**：三级 fallback（FRW LTX 2.3→FRW API→Grok Video 1.5）、`keyframe-first`、`continuity_chain` 逐字节末帧复用、`H3 max effect` 锁脸/R2V。

**最影响成片质量的短板**

1. **九项接戏仍靠人工 md**：`continuity_chain` 禁止 dissolve/定格/倒放/插镜掩盖，但无程序化校验，长片最易崩。
2. **运动质量无量化门**：`action-fluency`/`meaningful-motion` 仍 lesson，register 仅靠队列粗判。
3. **5090 资源争抢**：`comfy-multifilm-contention-oom(P0)` 多片抢卡 + OOM 风险。
4. **FRW 403/502 退避**对长片不友好、canary 链路重。

**优先级优化建议**

| 优先级    | 目标                | 具体动作                                                                   | 落地模块/文件                             | 预期收益         |
| ------ | ----------------- | ---------------------------------------------------------------------- | ----------------------------------- | ------------ |
| **P0** | 九项接戏程序化校验         | 解析 receipts/continuity_chain，禁 dissolve/定格/倒放/插镜；末帧 hash 校验 continue 缝 | `scripts/media/` 或 `scripts/gates/` | 长片接戏最大崩点根治   |
| P1     | 运动量化门             | 光流/像素差阈值嵌入 register 验收                                                 | `media-queue` `complete` 判定         | 动作流畅可量化      |
| P1     | 5090 统一调度器        | free-first 空闲挑战 + 单 client 强制 + capacity 真窗口                           | `comfy-lan-control` / `media-queue` | 杜绝 OOM/抢卡    |
| P2     | H3 Fill-Idle 自动派单 | R2V=能量位自动选取 + P2 空闲挑战自动派                                               | `weapon-lane-matrix`                | GPU 利用率与质量兼顾 |

> **Top-1 ROI**：九项接戏程序化校验。

---

## 4. 后期剪辑 / 字幕 / 合成 / 交付（柯立视角）

**现状强项**：`editorial-craft` / `edit-strategy-voice-coupled`、`字幕硬烧`、`render_final`、`delivery gates`。

**最影响成片质量的短板**

1. **final 超时/sidechain 假死**：`evirus-ch04-bulk-final-iron(P0)` 无自动重试/拆分，长片易半路死。
2. **中文字幕偶发问题**：无空格或 PIL 渲染失败未自动检测修复。
3. **headroom 裁头**靠人工；quality 缓存/export 链在 closeout 弱。
4. **HF 转场受控策略**未全量铺开。

**优先级优化建议**

| 优先级    | 目标              | 具体动作                               | 落地模块/文件                                        | 预期收益     |
| ------ | --------------- | ---------------------------------- | ---------------------------------------------- | -------- |
| **P0** | final 交付可靠性防护   | render_final 加超时/假死自动防护（分片重试 + 心跳） | `scripts/post/render_final.py`                 | 交付最大风险消除 |
| P1     | 字幕硬烧自动校验        | 像素含中文 + 无空格检测 + PIL fallback       | `scripts/post/compose.py`                      | 字幕零事故    |
| P1     | headroom 自动构图保护 | 定器双锁/短 insert 自动插入防裁头              | `scripts/post/*`                               | 主戏不丢头    |
| P2     | HF 转场默认开启       | 受控策略全量 + export read-back 全量       | `hf-transition-policy` + `scripts/post/export` | 剪辑语言统一   |



> **Top-1 ROI**：render_final 超时/假死防护。

---

## 5. 音频 / 口型 / 本地化（艾达视角）

**现状强项**：`audio-recipe` 5 配方自动路由、5 轨母带、`loudnorm -16±2` 单一真相、TTS 适配器族、`lipsync` 5 后端挑战、`scene-sound-standard(P0)`。

**最影响成片质量的短板**

1. **TTS 语言乒乓**：`ep2-voice-heat-final(P0)` 口白中文/角色日文需人工守，禁乒乓未自动。
2. **sung 不自动生成**：`musical_hybrid` 降级（缺 HeartMuLa 适配器）。
3. **BGM 抗疲劳**长片强度不够；纯乐器兜底未自动触发。
4. **lipsync 后端晋级**未全自动化（5090 CUDA12.8 canary）。

**优先级优化建议**

| 优先级    | 目标                   | 具体动作                             | 落地模块/文件                            | 预期收益      |
| ------ | -------------------- | -------------------------------- | ---------------------------------- | --------- |
| **P0** | TTS 语言乒乓自动校验         | audio_plan 写语言标记 + final 检查禁中日乒乓 | `scripts/audio/audio_plan.py`      | 对白可信度最大痛点 |
| P1     | BGM 抗疲劳增强            | 长片重复检测 + 纯乐器兜底自动触发               | `scripts/audio/bgm-generation.py`  | 长片不腻      |
| P1     | lipsync 自动 canary 晋级 | Wav2Lip→LatentSync/MuseTalk 自动晋级 | `scripts/audio/lipsync_backend.py` | 口型质量阶梯提升  |
| P2     | sung 自动生成            | HeartMuLa 适配器补 musical_hybrid    | `scripts/audio/*`                  | 音乐剧能力闭环   |

> **Top-1 ROI**：TTS 语言乒乓自动校验。

---

## 6. 统一优先级路线图（执行顺序 & 依赖）

### P0 — 快速胜（约 1–2 周，5 个自动硬门，消除"门绿但翻车"）

1. 抗无聊硬门（`gates/production_gates.py`）
2. 每镜脸身份 post_audit 门（`assets/face_identity.py`）
3. 九项接戏程序化校验（`media/` 或 `gates/`）
4. render_final 超时/假死防护（`post/render_final.py`）
5. TTS 语言乒乓校验（`audio/audio_plan.py`）

> 这 5 项互相独立、风险低、收益高，建议并行开工。

### P1 — 深化（约 2–4 周，lesson→默认硬门 + 自动化）

- 发色/首帧毒化/静帧压缩晋升 `style_lock` 默认
- narrative 收尾重绑、成人弧线完整性校验
- 运动量化门、5090 统一调度器
- 字幕硬烧/headroom 自动、BGM 抗疲劳、lipsync 自动晋级

### P2 — 规模化（约 1–2 月，能力闭环）

- visual_bible 自动生成、介质自动路由
- H3 Fill-Idle 自动派单
- sung 自动生成（HeartMuLa）
- HF 转场全量 + 长片 SOP 固化（`short-drama-sop-bridge`）

---

## 7. 验收与验证

- **门禁真相**：`make check-all`（validate + ruff + doctor + `pytest -m 'not slow'`）全绿 + 相关 pytest 绿 + `plugin validate` 过。
- **doctor 探针**：为 5 个 P0 新门禁各加一个 doctor 探针，确保"能力缺失即红"。
- **人工 champion**：每完成一个 P0，挑一段历史易翻车片段重跑，盲测观感对比。
- **迭代纪律**：每个 lesson→硬门晋升后，把对应 lesson 标记为已归档，更新 `references/INDEX.md`。

---

## 8. 一句话总结

这个项目已经是工业级流水线，**质量提升的杠杆不在"加功能"，而在"把 77 个踩坑 lesson 固化成默认门禁 + 程序化校验"**。先打 5 个 P0 自动硬门，把"门绿但翻车"清零，再逐层深化。
