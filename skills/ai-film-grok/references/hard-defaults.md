# 默认与跨层决策（收敛层 · 少硬编码）

> 从 SKILL.md 抽出。  
> **工程门禁**（pilot / VO 预算 / continue / 双烧）= 硬。  
> **叙事·尺度·女主人数** = **软**：跟用户 Prompt 与参考图，禁止用固定比例或关键词钉死。

## 叙事与规划

| 规则 | 弹性默认 |
|---|---|
| 文本入口 | Director’s Lens → 再 film-spec；禁止原文一句一图 |
| 规划 vs 剪辑 | clips 齐后建议 Editor’s Cut；用户赶交付可缩短 |
| 成人尺度 | **用户要热才 `heat_scale:max`**；不自动钉 max |
| 亲密核 | **建议**（max 时可参考 ≥60% 镜比）；`_heat_arc` 报指标；极端偏低 soft warn |
| **性爱片段时长** | **产品硬底**（2026-07-21）：`heat_scale=max` 时 **act+climax 的 `duration_sec` 合计 ≥ 总片板 20%**；write-spec 默认 `sex_floor_strict`；重口男向目标 ≥40%；`sex_min_duration_ratio` 可覆盖 |
| **办事卸甲/脱衣** | **产品硬底**（2026-07-21）：act/climax 禁止全装铠甲；`wardrobe_state`=partial\|undressed\|bare；须有卸甲/脱衣动作拍；默认 `sex_wardrobe_strict`；静帧/I2V 须画到裸露可读 |
| heat_phase | 可选；`heat_phase_auto` 时从 dramatic_function 填，**不猜 climax** |
| 女主 | **默认 single**；multi 仅证据（Prompt/多图/显式字段）；勿臆造 |
| 定妆 | style-v1 + cast masters + lookbook → pilot 3 镜用户批准 → bulk |
| 发色 | **硬锁**（P1）：`cast_locks` 写色名+NEVER 禁色；`hair_swatches` 建议；双人多 cast 锚；pilot 发色 fail=identity fail（2026-07-21） |
| **画面工程字** | **致命禁**（P0）：禁烧 `shot##`/keyframe/cast master v#；prompt 不写镜号字串；register 前四角检；脏 still 先 scrub（2026-07-21） |
| **资深剪辑** | Editor’s Cut 必写蒙太奇设计；craft **≥4 种**；60s insert≥2 / smash≥1 / montage 段≥1；禁顺序幻灯片（2026-07-21） |
| **重口男向** | 用户点名重口/男向 → heat max + 亲密核目标≥70% + act≥4 + climax≥2 + 荤 VO；禁 setup 过长（2026-07-21） |
| **首帧结构** | **致命**（P0）：keyframe 解剖/融合 fail → 禁 I2V；I2V 后必抽 t=0；坏首帧=整段废（2026-07-21 33s 案） |
| **景别堆叠** | 成人 60s：宽≥1·中≥2·近≥2·局部≥2；act→climax 收紧不回退全景；连续 3 镜同 size fail（2026-07-21） |
| **性交冲击力标竿** | 用户要性交/办事冲击/尺度太小→`coitus_grammar`；act 静帧过 **Mute Frame Test**；六拍 ENTRY→HOOK；禁拥抱冒充办事；审核软化走双轨不降 heat（2026-07-21） |
| 导演门禁 | `director_intent` + 每镜 `dramatic_function` 过 `write-spec` 才 queue |
| 口白·动作 | `nar` 动词 = `dsl.action` = `dsl.motion` 首要运动 |
| 防腻 | 连续 3 镜 ≥2 维变化（景别·主动词·`camera_axis`） |
| 长片接戏 | Continuity Chain；continue **hard**；`cut_on: mid_motion`；字节 promote |
| 转场 | silk；continue 强制 hard；满 60s 靠加镜 |
| 立场 | `focal_character` + `viewpoint` + `look_axis` |
| 双字幕 | `caption_mode: zh\|zh_en\|en`；`nar_en` 可只上字幕 |

## 语音与混音

| 规则 | 默认 |
|---|---|
| TTS | 中文成片 **edge**；storyteller `auto`→edge |
| Voicebox | **质量升级 + opt-in 本地兜底**（非默认替换 edge）；固定 `VOICEBOX_PROFILE`；`AIFILM_TTS_VOICEBOX_FALLBACK=1` 才 edge 失败再试 |
| 机位 | 开场 **`aifilm dispatch`**（craft+capability+next）；或 `capability`；`--suggest-i2v` / `--apply` 改 I2V 须显式 |
| 自动调配 | 每回合 `dispatch` → 只执行 `next_cmd`；不自批 pilot；不静默换 provider |
| 语速 | `vo_rate +0%`（色气 +5%~+8%；禁 -3% 拖腔） |
| VO 增益 | ~1.32；BGM 侧链；优先 `audio/mixed.wav` |
| BGM | 色气 **rnb**（禁 dark 除非 horror）；**硬兜底=程序 v3 multi-style**；**听感兜底=纯乐器曲库池**；`--music-seed` / `audio_policy.music_seed`；`audio_recipe` 调床厚薄；auto_sfx；见 [bgm-generation.md](bgm-generation.md) |
| VO 预算 | `nar` ≤55 字（快节奏 ≤28）；`est_vo_sec ≤ duration_sec+0.5` |
| loop | hook/action 永不 stream_loop |
| 一角一声 | 固定 `vo_voice`；显式 TTS 失败不静默跨商降级 |

## 视觉与一致性

| 规则 | 默认 |
|---|---|
| bulk 2V | **当前 `grok_primary`**：Grok `image_to_video` 720p 串行；Seedance 恢复后 `seedance_first` |
| I2V profile | `AIFILM_I2V_PROFILE=grok_primary\|seedance_first`；`write-spec` auto 跟 profile |
| FRW key canary | Seedance 季：bulk 前必 canary；**grok_primary 季可选**（仅 env LTX） |
| 403 / 502 | **403**=未开通；**502**=平台挂；勿混淆 |
| Seedance 不可用 | L1→**Grok I2V**；L2/无角色→**FRW `ltx-t2v`**（`env-plate`，无限额度）；禁默认 legacy |
| env 无脸 | `shot_role=env\|bridge\|insert` → `aifilm env-plate` · register `frw_ltx_t2v`；禁 T2V 锁脸 |
| 口型 | 默认 off（说书）；对白近景 opt-in `frw-lipsync probe`→run；403/502 跳过勿硬上 |
| 静帧 | 主角 Grok **`image_edit(cast)`**；禁反复纯 `image_gen`；加载 `/imagine` |
| Grok Build | 推理+Imagine 优先；无原生 T2V；bulk 动默认 FRW；会话外 xai-sdk 可选非默认 |
| 构图 | 禁 ECU/fill frame/push-in on face 裁头；full head + headroom |
| 库存 | film-spec 镜数 = approved clips |
| 同源 | 禁止半 Grok 半 FRW still/2V |
| 漫剧 | 禁默认 photoreal bible；改 medium+signature 再 lock-style |
| 分层 | L0 Grok still · L1 I2V 脸 · L2 LTX 无脸床 · L3 HF · 矩阵见 frw-key-capability |

## 后期

| 规则 | 默认 |
|---|---|
| 交付 | `final --post-engine hyperframes` |
| 双烧 | `plate-cards blank` + `subs off` |
| final | 串行；FRW clip 先 re-encode 再 register |
| loudnorm | auto ≈ -16 LUFS |
| 路径 | HF 忌空格路径 → 可拷 `/tmp/...` |
| 证据 | intent ≠ executed ≠ human_review |

## 量产十条（与代码门禁一致）

1. `write-spec` 过 → 才 `media-queue add`  
2. pilot 用户批准 → 才 bulk（无批准最多 3 shot_id）  
3. bulk 默认 Seedance；一次 claim 一件  
4. continue 串行 + 字节 promote；禁 cast 重起  
5. 失败只用 fail/requeue；禁手改 queue JSON  
6. moderation：换 soft still，荤点留给 VO  
7. 静戏 motion 可测  
8. 同源 provider  
9. final 硬拦 loop-risk  
10. FRW：reencode（不放大）→ register 真实 endpoint（`frw_seedance_*` / `frw_ltx_*` / `frw_img2video` / Grok）  
11. FRW key 先 canary；403 不假装 Seedance；register-note 写真实 model/fallback

## 不可宣称（证据不足时禁说）

| 未做 | 不得声称 |
|---|---|
| lock-style + cast | 角色已锁定 |
| pilot 用户批准 | 可 bulk |
| continue 字节复用 | 动作已串接 / match-cut |
| write-spec | 已进入生产 |
| mix_report / final_film | 已混音 / 已拼板 |
| review-final | 正式交付 |
| 批准 I2V clip | 动态成片（禁 Ken Burns/纯字卡冒充） |
| editor-cut | 剪辑已优化 |

额外：Grok I2V ≠ first-last-frame；FRW ≠ 一定 Seedance；只改 motion 不 re-I2V ≠ 运镜已更新；`export-compose` 成功 ≠ 成片交付；classic img2video completed ≠ 质量过关。

## 权威链接

- [pipeline-methodology.md](pipeline-methodology.md) · [principles.md](principles.md)  
- [directors-lens.md](directors-lens.md) · [film-spec.md](film-spec.md) · [consistency.md](consistency.md)  
- [continuity_chain.md](continuity_chain.md) · [post-compose.md](post-compose.md) · [production-discipline.md](production-discipline.md)  
- [editor-cut-pass.md](editor-cut-pass.md) · [ecchi-story.md](ecchi-story.md) · [voices.md](voices.md)  
- [frw-degrade-dispatch.md](frw-degrade-dispatch.md) · [lessons-2026-07-21-frw-key-capability.md](lessons-2026-07-21-frw-key-capability.md)
