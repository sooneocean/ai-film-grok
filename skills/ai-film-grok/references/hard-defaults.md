# 默认与跨层决策（收敛层 · 少硬编码）

> 从 SKILL.md 抽出。  
> **工程门禁**（pilot / VO 预算 / continue / 双烧）= 硬。  
> **成人尺度（2026-07-24 IRON）** = **硬**：肉戏拉满、能脱就脱、能露就露。  
> 女主人数 / 非成人 genre = 仍跟用户；显式 `heat_scale:soft` / `adult_max_iron:false` 才降火。

## 叙事与规划

| 规则 | 弹性默认 |
|---|---|
| 文本入口 | Director’s Lens → 再 film-spec；禁止原文一句一图 |
| 规划 vs 剪辑 | clips 齐后建议 Editor’s Cut；用户赶交付可缩短 |
| **成人尺度 IRON** | 成人信号 → **自动 `heat_scale:max` + `spice_level:extreme`**；禁静默降档 |
| **亲密核** | max 硬底 **≥60%** 镜比（foreplay+act+climax）；建议 ≥70%；`heat_arc_strict` 默认 true |
| **setup 天花板** | max 硬底 **≤20%** 镜比 |
| **性爱片段时长** | **IRON 硬底**（2026-07-24 · **50%**）：`heat_scale=max` 时 **act+climax ≥ 总片板 50%**；write-spec 默认 `sex_floor_strict`；重口男向 ≥55%；`sex_min_duration_ratio` 可覆盖 |
| **办事卸甲/脱衣 IRON** | **产品硬底**：act ≥`undressed`；**climax = bare**；须有卸甲拍；默认 `sex_wardrobe_strict`；write-spec **自动 phase 抬升**（能脱就脱/能露就露）；码 `HEAT_SEX_WARDROBE_*` / `HEAT_BARE_PEAK_MISSING` |
| **卸装延续·不回穿** | **产品硬底**（2026-07-21+）：rank 单调不降；后镜继承；**回穿自动 clamp**（max/hot）；`start_pose` 从已脱开场；prompt 注入 `Costume continuity HARD` + Adult max IRON 行；码 `HEAT_WARDROBE_RE_DRESS` / `HEAT_WARDROBE_TEXT_CONFLICT` |
| **卸装后 still 源** | **P0 像素硬底**（2026-07-21 席德案）：peak 后 **禁止** `image_edit(全装 cast master)`；必须 `canonical/wardrobe/undress-anchor` 或上一已脱 still；I2V 锁 first-frame 衣着；见 [wardrobe-no-redress-still](lessons-2026-07-21-wardrobe-no-redress-still.md) |
| **I2V 末帧不回穿 + promote 门** | **P0**（2026-07-22 astra 红外套案）：register 前验 last frame 肩/胸未整穿已脱衣物；毒末帧禁止 promote；identity 只锁脸发；见 [i2v-endframe-no-redress](lessons-2026-07-22-i2v-endframe-no-redress.md) |
| **Keyframe-first · 状态照** | **产品硬底**（2026-07-21）：先状态照索引 `cast_state_masters` → 再 keyframe → 再 I2V；视频坏先改 keyframe/状态照；prompt 注入 `State photo ref`；见 [keyframe-first-state-index](keyframe-first-state-index.md) |
| **生成 first/last** | **产品硬底**（2026-07-21）：`register-clip` 后自动 last→next first（continue/卸装/max）；下镜 I2V 禁 cast 重起；按真实末帧衣着/姿势写 prompt；**末帧须先过 W8 不回穿门**；见 first-last-gen · i2v-endframe-no-redress |
| **旁白荤梗** | **产品硬底**（2026-07-21）：max 办事剧 **每镜 nar 须含荤梗**；act/climax 须办事动词（沉腰/办穿/吃进…）；禁纯文艺灯暗句；默认 `sex_vo_strict` |
| **用户原文保真** | **P0**（2026-07-22 金瓶梅案）：用户剧本/诗白是脊柱；`_SPICY_NAR` 仅无用户句时兜底；**禁止**整句盖成「展厅落锁」；多段剧本禁止 dual-climax 自动×N 克隆；`user_source_fidelity_strict`（max 默认）→ `USER_SOURCE_NAR_POLLUTED`；见 [user-source-fidelity](lessons-2026-07-22-user-source-fidelity.md) |
| heat_phase | 可选；`heat_phase_auto` 时从 dramatic_function 填，**不猜 climax** |
| 女主 | **默认 single**；multi 仅证据（Prompt/多图/显式字段）；勿臆造 |
| 定妆 | style-v1 + cast masters + lookbook → pilot 3 镜用户批准 → bulk |
| 发色 | **硬锁**（P1）：`cast_locks` 写色名+NEVER 禁色；`hair_swatches` 建议；双人多 cast 锚；pilot 发色 fail=identity fail（2026-07-21） |
| **画面工程字** | **致命禁**（P0）：禁烧 `shot##`/keyframe/cast master v#；prompt 不写镜号字串；register 前四角检；脏 still 先 scrub（2026-07-21） |
| **资深剪辑** | Editor’s Cut 必写蒙太奇设计；craft **≥4 种**；60s insert≥2 / smash≥1 / montage 段≥1；禁顺序幻灯片（2026-07-21） |
| **重口男向** | 用户点名重口/男向 → heat max + sex≥55% + act≥4 + climax≥2 + 荤 VO + coitus/size/montage strict（2026-07-21 / IRON 抬档） |
| **Adult max IRON** | 肉戏≥50% · 亲密≥60% · setup≤20% · act undressed · climax bare · spice extreme · 自动卸装抬升 · **持续挑战尺度最大**（phase 只升不降、禁泄火/长平台、必 climax bare；`challenge_max_scale`）（2026-07-24） |
| **成人尺度最高优先（P0 · 最重要 · 2026-07-27）** | 用户明示：**尺度拉满是最重要目标**。与画风/剪辑偏好冲突时 **先保 max 尺度与完整办事弧**。退出仅显式 soft / `adult_max_iron:false`。见 [adult-scale-max-sex-arc](lessons-2026-07-27-adult-scale-max-sex-arc.md) |
| **肉戏起承转合全弧（P0 · 同日）** | 成人 max 肉戏块必须可读：**前戏（起）→ 蓄力/纳入前（承）→ 插入抽送（转）→ 高潮/射出（合）**。禁只抱吻；禁无插入；禁无射出/高潮拍。建议 `sex_arc_beat` 标注；时间四拍皆非零。见同上 lesson |
| **插入衣裤脱尽 + 定器特写（P0 · 同日追加）** | **插入拍双方衣裤脱尽**（女 bare；男至少下装脱尽）；禁内裤/军裤冒充办事。肉戏块默认至少 **1 镜结合部/腰腹定器特写**。Imagine 若拦 true bare → 记 PARTIAL，**禁止**静默改回内衣全穿当「已插入」。见 [adult-scale-max-sex-arc](lessons-2026-07-27-adult-scale-max-sex-arc.md) |
| **max 默认全闸 hard（P0 · 2026-07-28）** | `heat_scale=max` 且 `adult_max_iron≠false` 时默认 **true**：`coitus_strict` · `size_ladder_strict` · `pose_strict` · `sex_arc_strict` · `sex_detail_cu_strict` · `both_undress_strict` · 既有 sex_floor/wardrobe/vo/heat_arc。裸抱不算 penetration；合拍须高潮/射出标记；`aifilm heat check` 输出四拍占比 + 定器 CU + **erotic impact** 分。 |
| **首帧结构** | **致命**（P0）：keyframe 解剖/融合 fail → 禁 I2V；I2V 后必抽 t=0；坏首帧=整段废（2026-07-21 33s 案） |
| **景别堆叠** | 成人 60s：宽≥1·中≥2·近≥2·局部≥2；act→climax 收紧不回退全景；连续 3 镜同 size fail（2026-07-21） |
| **性交冲击力标竿** | 用户要性交/办事冲击/尺度太小→`coitus_grammar`；act 静帧过 **Mute Frame Test**；六拍 ENTRY→HOOK；禁拥抱冒充办事；审核软化走双轨不降 heat（2026-07-21） |
| **成人脊柱 + 机器闸（v1.9–1.10）** | plan 成人脊柱；六拍/景别；**sex≥30%**；`spice_level` extreme；声画同动词；act 自动 SFX；hardcore 娇喘轨建议开；蒙太奇 craft 注入；`sex_pose` 多体位；`heat check|vo-suggest|soften-log`；[adult-max-playbook.md](adult-max-playbook.md) · [pose-packs/coitus-beats.md](pose-packs/coitus-beats.md) |
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
| **人物对白 / 口白语言** | **P0**（2026-07-23 / **07-24 强化**）：**口白·说书=中文**；**角色开口=日文**（`dialogue_spoken_lang=ja`，女 `ja-JP-NanamiNeural` / 男 `ja-JP-KeitaNeural`）；**字幕仍中文**（`caption_lang=zh`，烧 `nar` 非 `nar_ja`）。角色镜须 `speaker` + `nar` + `nar_ja`；说书镜 **禁** `nar_ja`。**禁止无 speaker 理由的中日乒乓**；成块切换。禁赶片清空 `nar_ja`。见 [character-dialogue-ja](lessons-2026-07-23-character-dialogue-ja.md) · [ep2-voice-heat-final](lessons-2026-07-24-ep2-voice-heat-final.md) · [voices.md](voices.md) |
| **final / SRT** | **P0**（2026-07-24）：`sub_lead=0` 或写盘前非重叠钳制；长片直调 `render_final.py`（勿被 plate-timeout 假失败）；plate 后中文硬烧。见 [ep2-voice-heat-final](lessons-2026-07-24-ep2-voice-heat-final.md) |
| Voicebox | **质量升级 + opt-in 本地兜底**（非默认替换 edge）；固定 `VOICEBOX_PROFILE`；`AIFILM_TTS_VOICEBOX_FALLBACK=1` 才 edge 失败再试 |
| 机位 | 开场 **`aifilm dispatch`**（craft+capability+next）；或 `capability`；`--suggest-i2v` / `--apply` 改 I2V 须显式 |
| 自动调配 | 每回合 `dispatch` → 只执行 `next_cmd`；不自批 pilot；不静默换 provider |
| 语速 | `vo_rate +0%`（色气 +5%~+8%；禁 -3% 拖腔） |
| VO 增益 | ~1.32；BGM 侧链；优先 `audio/mixed.wav` |
| BGM | 色气 **rnb**（禁 dark 除非 horror）；**硬兜底=程序 v3 multi-style**；**听感兜底=纯乐器曲库池**；`--music-seed` / `audio_policy.music_seed`；`audio_recipe` 调床厚薄；auto_sfx；见 [bgm-generation.md](bgm-generation.md) |
| VO 预算 | `nar` ≤55 字（快节奏 ≤28）；`est_vo_sec ≤ duration_sec+0.5`；日文对白按 `nar_ja` 估长 |
| loop | hook/action 永不 stream_loop |
| 一角一声 | 固定 `vo_voice` / `cast_voices`；显式 TTS 失败不静默跨商降级 |
| **声线主导** | **旁白 `nar` + BGM**；`vocal_color` 娇喘独立轨 **默认关**（`voice_tracks.enabled=false` · gain=0）；`tone_tags` 只进画面；`sound_cues` 可进 SFX；见 [voice-tracks.md](voice-tracks.md) |

## 视觉与一致性

| 规则 | 默认 |
|---|---|
| bulk 2V | **`grok_primary`**：Grok `image_to_video`；FRW Seedance/LTX 仅在技术失败后 fallback |
| **高动态常态（P0 · 2026-07-27）** | **产品硬底**：平常 mean≥**18**；肉戏 act/climax mean≥**20**（目标≥24）；成片 1:00→片尾包络≥**18**。禁止 Ken Burns/仅微呼吸/弱 raw 装片；多 take 取 mean 最高且时长≥镜长；肉戏 10s 优先 **6s×2 hybrid**。交付前写 `i2v-high-motion-audit` + `i2v-final-gate`；**仅 gate ok 才拷桌面 film_final**。**代码入口**：`scripts/i2v_motion_gate.py`（`MEAN_NORMAL_FLOOR=18` / `MEAN_MEAT_FLOOR=20`）· CLI `aifilm i2v-motion-gate --rows …`。见 [high-motion-style-lock](lessons-2026-07-27-high-motion-style-lock-final.md) |
| **I2V 画风锁 MEDIUM（P0 · 同案）** | 源图= style-locked still/keyframe；prompt 首段 **MEDIUM LOCK cel anime**（match style-v1；禁 photoreal/3D/半写实油光）；高动重跑与 last-frame 连戏 **不得** 用 mean 换 medium fail；交付前 style audit 抽帧。见同上 lesson |
| **vocal_color 默认** | **never**（2026-07-27 用户永久禁娇喘轨除非显式恢复）；`forbid_vocal_color` / gain=0 |
| I2V profile | `AIFILM_I2V_PROFILE` 仅兼容读取；`write-spec` 的 `auto` 永远是 Grok primary |
| FRW key canary | 仅在 provider-switch 后执行 `upload-probe`；不会作为 Grok primary 的前置步骤 |
| 403 / 502 | **403**=未开通；**502**=平台挂；勿混淆 |
| FRW fallback | Grok timeout/429/5xx/连接失败后才进入 typed FRW upload/I2I/FLF；质量/人工拒绝不切换 |
| env 无脸 | 默认仍走 Grok no-face motion；FRW `env-plate` 只有 provider-switch receipt 后可用 |
| 口型 | 默认 off（说书）；对白近景 opt-in `frw-lipsync probe`→run；403/502 跳过勿硬上 |
| 静帧 | 主角 Grok **`image_edit(cast)`**；禁反复纯 `image_gen`；加载 `/imagine` |
| **静帧几何·禁压缩** | **P0**：I2V 前 keyframe **≥704×1280 且 9:16 竖比**；FRW 原生 704×1280 不强制升到 720；禁横图/缩略图/缩水 jpg。 |
| **先验后生·算力刀口** | **P0**（2026-07-22）：**验证通过才烧下一级**（still 先验→I2V；ref 先验→image_edit bulk）。禁止未验批量 I2V/出图；坏了只修上游。见 [verify-before-generate](lessons-2026-07-22-verify-before-generate.md) |
| Grok Build | 推理+Imagine 优先；静帧与 bulk 动默认 Grok；会话外 OAuth 仅批处理入口 |
| 构图 | 禁裁头（P0·2026-07-27 强化）：主戏镜 full head+headroom；**裁脚优先于裁头**；定器特写=「脸+结合同镜」或短 insert，禁无头主镜；打包慎用 increase+crop 切顶。见 [headroom-no-crop-heads](lessons-2026-07-27-headroom-no-crop-heads.md) |
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
3. hero bulk 默认使用已通过当前 canary/pilot 的 provider；当前可复现默认为 `grok_primary`，Seedance 只有 canary+pilot 全过才升级
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

---

## 2026-07-22 · 少婦案补记（脸锁 / 字幕 / BGM / final）

见 [lessons-2026-07-22-shaofu-cast-subs-bgm-final.md](lessons-2026-07-22-shaofu-cast-subs-bgm-final.md)。

- 角色 still：只 `image_edit(cast)`；禁审核失败后 t2i 绕脸
- HF `subs=off` 仅当 HF 真完成；否则 plate **burn**
- 色气 BGM：`assets/bgm/rnb/*` 优先
- `aifilm final` → render_final **timeout≥600s**
