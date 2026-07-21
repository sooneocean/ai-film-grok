# Sediment crosswalk: ai-film-cn + ai-film-codex → ai-film-grok

> 2026-07-20 · 优势目录，不是双栈合并。  
> 来源只读：`~/.hermes/skills/creative/ai-film-cn` · `~/.codex/skills/ai-film-codex`（或 `~/YDEX/INPORTANT WORK/aifilm-codex`）  
> 目标 live skill：`~/.grok/skills/ai-film-grok`  
> 每条「保留」须挂 [principles.md](principles.md) **P0–P5**，并落到可测 gate / 字段 / 命令。

## 一句话

从 cn / codex **吸取可迁移纪律**（构图铁律、库存一致、时长真相、TTS 预演、证据分层），**不**把 5090、Studio/OpenCut、Director Contract v2 整套搬进 Grok。

---

## Kept advantages（可迁移 · ≥6）

| # | 来源 | 优势 | P 码 | Grok 落点 |
|---|------|------|------|-----------|
| 1 | **cn** | 构图铁律：禁裁头景别词；`full head + headroom + subject stays framed` | **P0** 可观测 + **P4** 语义绑定 | `scripts/framing_lint.py` · `write-spec` → `film-spec._framing_lint` · `framing_strict` hard |
| 2 | **cn** | 景别 / framing 默认注入安全词（非 ECU 填满） | **P0** | `edit_policy.BEAT_COVERAGE_DEFAULTS` framing 文案 |
| 3 | **cn** | 三轴 / 真 duration：禁静默假默认导致字幕窗漂移 | **P2** 时空连续（时间轴真相） | `scripts/media_duration.probe_duration_sec` · `render_final.pdur` / `compose_render.pdur` fail-loud |
| 4 | **cn** | 空 / 过长 nar 不进量产 | **P4** | 既有 `vo_budget` + `vo_pacing`（保留强化） |
| 5 | **codex** | TTS rehearsal：bulk 前真测 VO 秒数；有回执时 timing gate 用 measured | **P4** | `aifilm tts-rehearse` · `bind_receipt_to_spec_timing` · preflight hard `tts_rehearsal_over_plate` · final `--strict-tts-rehearsal` · `production_gates.assert_tts_rehearsal_timing` |
| 6 | **codex** | 镜库存一致：shot set = approved clips（= VO stems when present） | **P2** | `scripts/shot_inventory.py` · preflight hard `inventory_mismatch` · assemble/final `assert_inventory_for_final` · `status.inventory` |
| 7 | **codex** | 证据分层：intent ≠ executed ≠ human_review | **P5** 分层 + 验收横跨 P0–P5 | `scripts/evidence_status.py` · `status.evidence` · preflight soft impersonation risks |
| 8 | **codex** | technical 过 ≠ creative 人审过 | 验收 | 既有 pilot / review-final；status 分栏不混 plan |

### 实现入口（agent 速查）

```bash
"$AIFILM" write-spec --root "<root>"          # 发出 framing_lint（软）；framing_strict 可硬
"$AIFILM" tts-rehearse --root "<root>" \
  --register-json measurements.json           # 离线绑定实测时长；或真 TTS 合成
"$AIFILM" preflight --root "<root>"           # inventory_mismatch hard；evidence soft
"$AIFILM" status --root "<root>"              # .inventory + .evidence
"$AIFILM" assemble|final --root "<root>"      # 库存不全直接失败
```

| 纯函数 / 模块 | 测什么 |
|---------------|--------|
| `framing_lint.lint_framing_iron` | crop-prone 词 |
| `shot_inventory.check_shot_inventory` | N shots ≠ M clips |
| `media_duration.probe_duration_sec` | missing path → raise |
| `tts_rehearsal.register_measured_durations` | receipt 按 shot_id 绑定 measured_duration_sec |
| `evidence_status.classify_evidence` | sound_plan 不能冒充 mix |

---

## Explicit non-ports（禁止当硬依赖）

下列 **不得** 写成 Grok 默认必经路径或「没它不算交付」：

1. **5090 ComfyUI + IP-Adapter FaceID 为必经路径**（cn 锁脸栈）— Grok 用 style-bible + cast master + Imagine。
2. **Studio / OpenCut 为必交付通道**（codex finishing）— Grok 正式交付是 `final` + `review-final`；HF Studio preview 可选。
3. **Director Contract v2 全 schema 硬依赖**（codex lock/compile 全家桶）— 只吸证据分层思想进既有 receipts。
4. **声称 Grok `image_to_video` = first-last-frame** — **禁止**。Grok 主路径是 **frame-1 I2V**；接戏靠 promote last→next keyframe（continuity_chain），不是 FLF 通道。
5. Hunyuan I2V（缺 CLIP 死路）当主视频后端。
6. 把 FRW / LTX 内部 template ID 或未白名单 route 当默认。
7. Agent 伪造 `human_observation` / `user_phrase` / pilot 自批。
8. 复制 cn 70k+ 坑位散文或 codex 整本 SKILL 进 grok SKILL.md（只保本 crosswalk + 指针）。

---

## Gap → shipped（本沉淀回合）

| 缺口（沉淀前） | 行为结果 |
|----------------|----------|
| 无裁头景别 lint | write-spec soft `_framing_lint`；`framing_strict` hard |
| 部分 clip 仍可能被索引 | preflight hard + assemble/final assert |
| pdur / 缺文件假默认风险 | `media_duration` fail-loud |
| 仅 `len(nar)/4` 估时 | 有 `tts-rehearsal.json` 时 preflight/final **优先 measured**；超 plate hard fail |
| receipts 混 intent/执行/人审 | `status.evidence` 三分 + soft 假冒风险 |

---

## 与既有 lessons 关系

- 不替代 [continuity_chain.md](continuity_chain.md) / meaningful-motion / vo-motion-link。  
- 强化 [production-discipline.md](production-discipline.md) 的「计划 ≠ 交付」。  
- Frame-1 声明与 [lessons-2026-07-20-frame-chain.md](lessons-2026-07-20-frame-chain.md) 一致：**不是** first-last-frame。

## Opt2 增量（2026-07-20 同日第二轮）

| 项 | 落点 |
|----|------|
| Edge 空流重试 | `tts_backend.tts_edge`：`<500B` 最多 3 次 + backoff |
| `next` 路由 tts-rehearse | clips 齐、无 rehearsal receipt → 建议 `aifilm tts-rehearse` |
| `next` fix-framing | `_framing_lint.ok=false` → fix-framing |
| queue 禁 ghost shot | `media-queue add`：`shot_id` 必须 ∈ film-spec |
| preflight framing | soft `framing_crop_prone`；`framing_strict` hard |
| `aifilm.media_duration` | 统一走 `media_duration.probe_duration_sec` fail-loud |

## Opt3 · VO atempo 三轴（同日第三轮）

| 项 | 落点 |
|----|------|
| 视频定长 + 语音 atempo | `vo_atempo.plan_vo_atempo` / `fit_voice_to_plate`；`render_final` slot 默认 |
| 方向 `vo/plate` · 上限 1.5 | 超限 fail_over，不 choppy |
| `vo_fit` / `--vo-fit` | `atempo`（默认）\| `legacy` |
| 文档 | [lessons-2026-07-20-vo-atempo-three-axis.md](lessons-2026-07-20-vo-atempo-three-axis.md) |

## Opt4 · FRW 官方 dispatch（同日 · 平台插件 + cn）

| 项 | 落点 |
|----|------|
| 平台契约 v1.0.6 | components.rcyq.net `img-video-frw-toJy`；勿整包覆盖本机 frwclaw |
| Grok 适配文档 | [frw-degrade-dispatch.md](frw-degrade-dispatch.md) |
| 分镜动态 | **Seedance `newvideo`**（默认 `seedance-2-fast-i2v`）；有尾帧 `seedance-2-pro-flf`；legacy `img2video` 仅显式 |
| 入组 | `reencode-clips`（不放大）+ `register-clip`（`frw_seedance_*`）；同源 provider |
| 非 port | Grok I2V ≠ FLF；错 poll batch FLF |

## Opt5 · FRW Seedance 2V 优先（无限配额 · 质量版 · 同日）

| 项 | 落点 |
|----|------|
| 语义翻转 | FRW **不再**只是「Imagine 挂了才降级」→ **bulk 2V 默认 FRW** |
| **质量翻转** | 无限配额 **≠** 旧 `img2video`；默认 **Seedance 720p 原生**（胃镜室事故） |
| film-spec | `i2v_provider` 默认 `frw`；**`frw_video_model` 默认 `seedance-2-fast-i2v`** |
| endpoints | `frw_seedance_i2v` / `frw_seedance_flf` / `frw_newvideo` + legacy `frw_img2video` 等 |
| 入口 | `"$AIFILM" frw newvideo --model seedance-2-fast-i2v …` · `scripts/frw_dispatch.py` |
| 文档 | [lessons-2026-07-20-frw-2v-first.md](lessons-2026-07-20-frw-2v-first.md) · [lessons-2026-07-20-seedance-quality.md](lessons-2026-07-20-seedance-quality.md) |

## Opt6 · 片头标题双烧（同日 · 用户验收）

| 项 | 落点 |
|----|------|
| 现象 | FFmpeg 烧字 + HF 设计片头叠影（戏服玩心夜） |
| 默认 | `post-engine hyperframes\|remotion` → **`plate-cards blank`** + **`subs off`** |
| CSS | 片头 `white-space: nowrap`（短中文不拆行） |
| 文档 | [lessons-2026-07-20-title-double-burn.md](lessons-2026-07-20-title-double-burn.md) · post-compose · production-discipline |

## Opt7 · 转场丝滑 + 中英双字幕 + HF/Remotion 盘点（同日）

| 项 | 落点 |
|----|------|
| 割裂感 | continue=hard match-cut + mid_motion；silk fluency 只作用于**非 continue** |
| 声轨 | 连续 mixed underlay = L/J-cut 话术 |
| 双字幕 | `caption_mode: zh_en` + `nar_en`；HF 双行 / Remotion pre-line |
| 能力矩阵 | [hf-remotion-capability-matrix.md](hf-remotion-capability-matrix.md) |
| 专文 | [lessons-2026-07-20-cut-silk-bilingual.md](lessons-2026-07-20-cut-silk-bilingual.md) |

## Opt8 · 转场 + 运镜 v2（同日晚 · 男娘咖啡厅）

| 项 | 落点 |
|----|------|
| continue soft 假丝滑 | **`enforce_continue_hard_joins`**：作者 soft/hold 也强改 hard；`_transition_continue_hard_fixes` |
| 运镜腻（全 push-in） | **`dsl.camera_axis`** 轮换注入；微动后缀不再绑死 push-in |
| 轴菜单 | `dolly_in\|pan_with\|locked\|ecu_hold\|low_lean\|pull_back` |
| lint | `CAMERA_AXIS_FLAT` · `STYLE_SOUP` · 加强 `SOFT_SOUP` |
| 满 60s | **加镜**，不拉长 dissolve 装时长 |
| 假 continue | 无 promote 字节时改 `chain_mode: cut`，别硬叫接戏 |
| 专文 | [lessons-2026-07-20-transition-motion-v2.md](lessons-2026-07-20-transition-motion-v2.md) |

## Opt9 · Seedance 403 / LTX 参数 / 质量 fallback（同日）

| 项 | 落点 |
|----|------|
| Seedance | `403 无权使用该模板`（seedance / byteplus） |
| LTX 契约 | width/height/duration/fps **string**；竖屏 **720×1280**；禁 int（400） |
| LTX 探针 | **ltx-t2v** 201→**completed**；**ltx-i2v/flf** 全 **502**（平台） |
| 经典 | text2image / img2image / text2video / img2video **201**（质量非默认） |
| 纪律 | **禁止**默认 legacy 576；路由 Seedance→LTX i2v→Grok 720p |
| film-spec | `ltx-*` + `frw_width/height/fps`；`_frw_fallback_chain` |
| register | `frw_ltx_i2v` / `frw_ltx_t2v` / `frw_seedance_*` |
| 文档 | [lessons-2026-07-20-frw-ltx-probe.md](lessons-2026-07-20-frw-ltx-probe.md) · [frw-degrade-dispatch.md](frw-degrade-dispatch.md) |

## Opt10 · 分层路由：人物 I2V × LTX T2V 合成层（同日）

| 项 | 落点 |
|----|------|
| 问题 | T2V 无人物导入 → 只能做合成层 |
| L0/L1 | Grok still + Seedance/Grok I2V 锁脸 |
| L2 | **`frw_env_model: ltx-t2v`** + `shot_role: env\|bridge\|insert` |
| 字段 | `shot_role` · `frw_env_model` · `_layer_routing` · `_recommended_engine` |
| 专文 | [lessons-2026-07-20-layer-routing.md](lessons-2026-07-20-layer-routing.md) |

## 2026-07-20 全日课索引（agent 速查）

| 课 | P 码 | 一句话 |
|----|------|--------|
| directors-lens | P0 P4 | 先故事重构再 film-spec，禁插图化 |
| seedance-quality | P0 P1 P5 | bulk 2V 默认 Seedance 720p；禁 legacy 默认 |
| frw-2v-first | P1 P5 | FRW 烧 bulk；Grok 锁 still |
| transition-motion-v2 | P2 P3 | continue 强 hard + camera_axis 轮换 |
| cut-silk-bilingual | P2 P3 P5 | silk 非 continue；zh_en 双字幕 |
| title-double-burn | P5 | plate-cards blank + subs off |
| frame-chain / action-fluency | P2 P3 | 字节 promote + mid_motion |
| meaningful-motion | P0 P4 | 动态有叙事意涵 |
| designed-post-fluency | P5 | HF/Remotion 只做观感胶水 |
| vo-atempo-three-axis | P0 | 视频定 plate；VO atempo |
| bgm-anti-fatigue / audio-compose | P5 | rnb + sidechain + loudnorm |

总入口：[principles.md](principles.md) · 本文件 Opt1–Opt9。

## 验证

```bash
cd ~/.grok/skills/ai-film-grok
python3 -m pytest tests/test_frw_degrade_docs.py tests/test_cut_silk_bilingual.py \
  tests/test_title_double_burn_docs.py tests/test_edit_policy.py -q
# 关注：Seedance 默认 · continue hard 覆盖 · camera_axis · plate-cards blank
```
