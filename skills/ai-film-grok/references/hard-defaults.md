# 默认与跨层决策（收敛层 · 少硬编码）

> 从 SKILL.md 抽出。
> **工程门禁**（pilot / VO 预算 / continue / 双烧）= 硬。
> **零旁白（2026-08-04 IRON）** = **硬**：`dialogue_drama` 默认 `zero_narration_strict`；无用户句时禁说书 `nar` 抢时钟；仅 `narration_reason` 逃生通道。
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
| **性爱片段时长** | **IRON 硬底**（2026-07-24 · **50%**）：`heat_scale=max` 时 **act+climax ≥ 总片板 50%**；write-spec 默认 `sex_floor_strict`；重口男向 ≥55%；`sex_min_duration_ratio` 可覆盖。**P0 · 2026-08-06**：`HEAT_SEX_DURATION_LOW` **fail-closed**（加镜/re-I2V/降 ratio），**禁**静默把 act/climax 空拉 `duration_sec=10`（短 H3 源 stretch 炸）。见 [suse final](lessons-2026-08-06-suse-ep01-official-final-iron.md) |
| **办事卸甲/脱衣 IRON** | **产品硬底**：act ≥`undressed`；**climax = bare**；须有卸甲拍；默认 `sex_wardrobe_strict`；write-spec **自动 phase 抬升**（能脱就脱/能露就露）；码 `HEAT_SEX_WARDROBE_*` / `HEAT_BARE_PEAK_MISSING` |
| **卸装延续·不回穿** | **产品硬底**（2026-07-21+ · **强化 2026-08-06 用户圣旨**）：rank 单调不降；后镜继承；**回穿自动 clamp**（max/hot）；`start_pose` 从已脱开场；prompt 注入 `Costume continuity HARD` + Adult max IRON 行；码 `HEAT_WARDROBE_RE_DRESS` / `HEAT_WARDROBE_TEXT_CONFLICT`。**一句话：衣服脱了就不能再穿回来。** 见 [memory 2026-08-06](../memory/2026-08-06-wardrobe-no-redress-fullnude-fallback.md) · [lesson](lessons-2026-08-06-wardrobe-no-redress-fullnude-fallback.md) |
| **卸装后 still 源** | **P0 像素硬底**（2026-07-21 席德案）：peak 后 **禁止** `image_edit(全装 cast master)`；必须 `canonical/wardrobe/undress-anchor` 或上一已脱 still；I2V 锁 first-frame 衣着；见 [wardrobe-no-redress-still](lessons-2026-07-21-wardrobe-no-redress-still.md) |
| **I2V 末帧不回穿 + promote 门** | **P0**（2026-07-22 astra 红外套案）：register 前验 last frame 肩/胸未整穿已脱衣物；毒末帧禁止 promote；identity 只锁脸发；见 [i2v-endframe-no-redress](lessons-2026-07-22-i2v-endframe-no-redress.md) |
| **大尺度做不到 → 全裸诱惑兜底（P0 · 2026-08-06）** | 真插入/结合/办事像素做不到（供应商拦、毒镜、合拍失败）→ **禁止** 内衣/半脱/假办事装绿；**改走 bare 全裸诱惑 MAX**（pose·距离·感官·权力），弧记 **PARTIAL**。见 [memory](../memory/2026-08-06-wardrobe-no-redress-fullnude-fallback.md) · [lesson](lessons-2026-08-06-wardrobe-no-redress-fullnude-fallback.md) |
| **全裸诱惑也做不到 → 模型极限勿硬上（P0 · 2026-08-06）** | bare 诱惑 MAX 仍拦 / 连出崩坏畸形 → **以当前模型能稳出的最高色气为准**（侧影·遮挡·implied bare·undressed 极致）；**禁止**反复硬 prompt 冲 bare/结合把画面冲烂。稳帧优先于名义 MAX 标签；delivery **PARTIAL** + 实际 wardrobe 档。机读：`narrative/scale_fallback` 码 `SCALE_HARD_ON_BAN` / `SCALE_SOFT_MAX` / `SCALE_BARE_TEASE_FALLBACK` → `receipts/scale-fallback.json`；毒镜/moderation 连败禁 promote。与毒镜 IRON 同向。见 [memory](../memory/2026-08-06-wardrobe-no-redress-fullnude-fallback.md) |
| **Keyframe-first · 状态照** | **产品硬底**（2026-07-21）：先状态照索引 `cast_state_masters` → 再 keyframe → 再 I2V；视频坏先改 keyframe/状态照；prompt 注入 `State photo ref`；见 [keyframe-first-state-index](keyframe-first-state-index.md) |
| **武器库全模态盘点（P0 · 2026-08-05）** | 文图影声音 primary 表：`registry/weapon-inventory.json` · [weapon-inventory](weapon-inventory.md)。5090：still=Qwen · motion=H3 · VO=Edge · BGM=rnb。 |
| **Material Fidelity 闭环（P0 · 2026-08-05）** | **单一领料单**：`still_source` 决议 I2V 首帧；`generation_request` 写 `receipts/prompts/<id>.request.json`（text+ref sha）；peak 禁 full cast master；queue 有回执则校验 sha。逃生 `AIFILM_SKIP_GENERATION_REQUEST=1`。见 [material-fidelity-loop](material-fidelity-loop.md) · stages/visual「谁喂谁」 |
| **一镜一静帧 · still 去重（P0 · 2026-07-29）** | **产品硬底**：approved still **禁止跨 shot 字节复用**（同 sha 多镜 = 成片「画面重复」）。`register-still --status approved` 撞 sha **硬失败**；`stills_complete` / `final_complete` 依赖 `still_uniqueness.ok`。连续亲密弧须换景别/相位/机位，禁 `cp A.png B.png`。见 [still-unique-no-reuse](lessons-2026-07-29-still-unique-no-reuse.md) |
| **静帧内容 · 禁设定拼图（P0 · 2026-08-03 荒岛案）** | keyframe **必须** 单场景连续叙事静帧（可读 `playable_action`）。**禁止** turnaround / 多格表情板 / ORTHO 设定拼图入 `keyframes/` 再 I2V。`register-still approved`：`lint_still_not_character_sheet`（路径含 sheet/turnaround/ortho **硬拦** `STILL_LOOKS_LIKE_CHARACTER_SHEET`；多格布局 **soft** 警示，agent 须肉眼拒）。见 [huangdao-rhythm-still-voice-silk](lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md) |
| **对白节奏 VO-fit（P0 · 2026-08-03 荒岛 · 强化 2026-08-04 γ）** | `dialogue_drama` 默认 **`visual_fit=vo`**（plate 跟口白长，禁等长 6s PPT）。对白镜 / `cut_on=mid_motion` / 有 `spoken_text` → 片级或镜级 vo。驱动镜（hook/approach/action/act/climax）缺 `cut_on` 时写 **`mid_motion`**。**freeze pad ≤0.15s**（禁 loop 镜 ≤0.20s）— 长 tpad 当静帧垫。continue 缝 **hard**；非 continue 可 soft xfade。preflight soft：`EQUAL_SLOT_PPT_RISK`。代码：`edit_policy.default_visual_fit` · `resolve_shot_visual_fit` · `plan_stretch`。见 [vo-drag](lessons-2026-07-20-vo-drag-motion-snap.md) |
| **5-Track 影院混音（P0 · 2026-08-04 δ MVP）** | DX/FX/BG/MX/SUB 契约：`dialogue_drama`·heat max·premium 自动 `five_track` + **lufs_strict** + 目标 **-16 LUFS ±1.5**（`lufs_min=-17.5`/`lufs_max=-14.5`）。final stems 映射见 [5track](5track-audio-master.md)。meat 须 `sex_sfx` 事件（write-spec 已 inject）。`aifilm five-track plan|audit` · ship-prep 阶梯 · post-audit 合入。逃生 `AIFILM_SKIP_FIVE_TRACK=1` 或 `five_track:false`。代码：`scripts/five_track.py`。 |
| **Cinematic-gate 复合闸（P0 · 2026-08-04 ε）** | 一键红绿：`true_video` + inventory + `i2v-final-gate` + variety + five_track + edit_rhythm → `receipts/cinematic-gate.json`。CLI：`aifilm cinematic-gate --root`（可 `--ship-prep`；默认 **auto_i2v** 测 mean 并写 gate）。**export-desktop** 要求 gate ok（缺收据自动重跑）。dispatch 在 clips 齐后推 **gate-auto** 再 final。逃生 `AIFILM_SKIP_CINEMATIC_GATE=1`。代码：`scripts/cinematic_gate.py`。 |
| **Gate-auto 机读过闸（P0 · 2.39.13 整并）** | **单入口** `ensure_machine_lane`（ship-prep/closeout/export）；dispatch/next 共用 `next_machine_lane_action`（默认 gate-auto；多 take 才 ship-prep）。i2v 绿不重跑；`--force` 才重测。永不自动绿 pilot/PK/review-final。逃生 `AIFILM_SKIP_GATE_AUTO=1`。 |
| **字幕 ship 硬烧（P0 · 2026-08-03 v3）** | 用户可见 = **像素里有中文**，不是 ledger 有 `caption_text`。ship 默认 **PIL/底片硬烧**（≥36–40@704、深底、安全区）；**禁止** 仅 HF `opacity:0`+GSAP 当唯一字幕。交付前每条对白 cue **抽帧证明**。正式 master 仍可 HF owner；ship/门红路径硬烧优先。见 [huangdao §G](lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md) · [memory](../memory/2026-08-03-huangdao-caption-hardburn-meat-variety.md) |
| **对白镜 speaker=画面主体（P0 · 同 v3）** | `on_camera` + 具名 `speaker` → 画面主读该角色脸/口型；**禁止** 角色 A 的台词配角色 B 全身肉戏特写（荒岛 climax「到了」配男主）。 |
| **构图防抢走 IRON（P0 · 2026-08-05 · 后面不要再犯）** | multi-seed **禁止** 只按 white0 / mean_volume / motion mean promote。须过 **composition anti-hijack**：对白开场拒 **沙俯视/脚印铺满**；女主存在镜拒 **男胸躯干 CU 填满**。机读：`composition_anti_hijack.py` · `aifilm anti-hijack --root` · `select-shortlist`/`pk-compare` 自动 demote hijack。仍须 speaker=画面。逃生 `AIFILM_SKIP_ANTI_HIJACK=1`。见 [memory](../memory/2026-08-05-composition-anti-hijack.md) |
| **对白优先·场景级拒旁白（P0 · 2026-08-03 v2.34）** | `dialogue_drama`：每个 scene（嵌套 shots）**必须**有 ≥1 个 `on_camera`/`off_camera` 对白镜（`spoken_text` 非空）。**禁止**整场纯 `silence`/`action_cover`/`reaction` 或纯 `nar` 撑；无 `narration_reason` 即 raise。逃生=scene `{"silent_scene": true, "narration_reason": "…"}`（须交代原因）或 spec `allow_silent_scenes:true`；**默认当对白片做**。对白镜画面必须可见「人正在讲」：on_camera 镜 speaker 的脸/口型是主体；H3/Grok prompt 注入「角色开口说话，口型清晰」。 |
| **对白肉戏 → H3（5090）本地对白路径（P0 · 同 v2.34）** | `restricted`（heat/bare/高难）+ 对白镜不再硬钉 `cloud_dialogue_ltx`；路由 `local_dialogue_h3`（`minimax-h3-i2v-pilot`；有状态照→`r2v`）。H3 prompt 首部注入 `Audio: the visible character speaks this line in natural Mandarin on camera` 与台词；`audio_policy=prefer_native`。无台词镜仍走 ambience/foley。 |
| **对白原音 IRON（P0 · 2026-08-05 · v2.40 代码移除后期对嘴）** | **有声镜生成源** = Grok Imagine Video · **5090 H3** · **opt-in FRW LTX 2.3 `img2video-audio`**。成片混音 **`prefer_native`**。**v2.40：后期对嘴代码墓碑**（`final --lipsync` 仅 off；lipsync CLI/节点 raise）。Edge 仅字幕时钟/ADR。禁 genre=adult 静默切 ltx23 全片 primary。见 [lipsync.md](lipsync.md)。 |
| **要影片不要图（P0 · 2026-08-03 · 强化 2026-08-04 true-video）** | 用户拒静图：**运镜只许模型内生成**（Grok I2V / H3 I2V·FLF·R2V / LTX 对白·env）。**Still 永不进 timeline**（只作 I2V 输入）。hero clip **禁止** Ken Burns / zoompan / panel-animation / shortform still-motion。`register-clip` + `preflight` + `final` + `ship-prep` 机读 `true_video_policy`（码 `TRUE_VIDEO_*` / `PANEL_MOTION_NOT_HERO`）。`production_mode=panel` 才允许 panel 包；剧情片默认禁。moderated → 末帧 continue + 真 I2V/H3；记 PARTIAL，禁静默 still 过交付。逃生 `AIFILM_SKIP_TRUE_VIDEO_POLICY=1`。代码：`scripts/true_video_policy.py`。 |
| **运镜服务事件（P0 · 2026-08-04 β）** | **角色/事件先动，摄影机服务变化**。禁 drive 镜（hook/approach/action）仅 push-in/blink 无 `visible_change`。码：`CAMERA_WITHOUT_EVENT` · `MOTION_NO_MEANING` · `MOTION_CORE_CAMERA_ONLY`。`build_motion_prompt` **不再**静默塞 subtle push-in。邻镜肉戏：`ADJACENT_CAMERA` / `ADJACENT_FRAMING` / `ADJACENT_TRIPLE_COLLISION`（variety-precheck）。H3 默认跟 `h3 list` 的 `mode`/`command`；能量不够才 `alt_mode=r2v`。 |
| **末帧 promote 默认（P0 · 强化 2026-08-03）** | register 后 `extract-frame --which last --promote-keyframe NEXT`；下镜 I2V 从 seed 开，禁 cast 重起。**smash / 跨空间 / 跨大 wardrobe** 勿盲 promote（防沙滩链污染洞穴肉戏）。丝滑先帧链后 xfade。 |
| **画面抗重复·抗无聊（P0 · 2026-07-29 · 机读 hard）** | **门禁绿 ≠ 好看**。`variety_precheck` / `assert_variety_preflight` + gate-auto/cinematic：**肉戏 pose/CU/L4/相邻 motion** hard。主戏 **片上 ≥4.5–6s**。逃生 `AIFILM_SKIP_VARIETY_PREFLIGHT=1`。见 [shot-variety-anti-boring](lessons-2026-07-29-shot-variety-anti-boring.md) |
| **肉戏体位·特写·运镜（P0 · 2026-07-29 强化 · 后面不要再犯）** | 用户原话：**不同体位 + 不同特写 + 运镜**。肉戏窗 **≥4 可读体位**（骑/传教/后入/侧/站…像素一致，禁只改字段）；**≥2 脸反应 CU + ≥2 定器 L4 insert + ≥2 体位关系镜**；相邻 I2V **禁止**同 camera（池：locked / push-in / pull-back / orbit / tilt-up / low-angle / handheld）。禁止 7 镜全是半身拥抱。contact 须能说「这是后入」「这是腰特写」。优先级：尺度弧 ＞ 体位/特写/运镜差 ＞ mean。见 [shot-variety-anti-boring](lessons-2026-07-29-shot-variety-anti-boring.md) §F–H · [memory](../memory/2026-07-29-shot-variety-anti-boring.md) |
| **生成 first/last** | **产品硬底**（2026-07-21）：`register-clip` 后自动 last→next first（continue/卸装/max）；下镜 I2V 禁 cast 重起；按真实末帧衣着/姿势写 prompt；**末帧须先过 W8 不回穿门**；见 first-last-gen · i2v-endframe-no-redress |
| **旁白荤梗** | **产品硬底**（2026-07-21）：max 办事剧 **每镜 nar 须含荤梗**；act/climax 须办事动词（沉腰/办穿/吃进…）；禁纯文艺灯暗句；默认 `sex_vo_strict` |
| **用户原文保真** | **P0**（2026-07-22 金瓶梅案）：用户剧本/诗白是脊柱；`_SPICY_NAR` 仅无用户句时兜底；**禁止**整句盖成「展厅落锁」；多段剧本禁止 dual-climax 自动×N 克隆；`user_source_fidelity_strict`（max 默认）→ `USER_SOURCE_NAR_POLLUTED`；见 [user-source-fidelity](lessons-2026-07-22-user-source-fidelity.md) |
| **Input Fidelity 全链（P0 · 2026-08-04 F0–F3）** | **尺子+落锚**：`fidelity status\|check\|apply` → `receipts/input-fidelity.json`。**apply** 写 `source_quote`/must_keep/保护台词。**design-go** 一页设计期 GO（不代签 pilot）。I2V prompt 首部 `Story beat:`。still 注册 `still_source_overlap`（`still_source_overlap_strict` / env 才 hard）。closeout/ship-prep 含 `input_fidelity` 阶梯。plan≥0.75；strict 时 final floor 0.80。逃生 `AIFILM_SKIP_FIDELITY_FINAL_GATE=1`。≠ dramatic_meaning。 [memory](../memory/2026-08-04-input-fidelity.md) · [plan](../../../docs/plans/2026-08-04-input-fidelity-flow.md) |
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
| **毒镜·解剖像素 IRON（P0 · 2026-07-29 · 后面不要再犯）** | 成人 bare/肉戏 **禁止** futa/女体阴茎、泌乳喷奶/母乳流、霓虹生殖器符号、**结合处霓虹光爆/光球**、错性别器。尺度拉满 ≠ 畸形。i2i/I2V 须中英双写硬 NEG + POS（`penis only on man` / `DELETE on woman` / **dry nipples**）。静帧见毒 **禁 I2V**；clip 见毒 **禁 register/promote/final** → archive → 解剖安全 i2i → 重渲。毒 preview 不交付。片例 ch4 避难所。见 [anatomy-milk-futa](lessons-2026-07-29-anatomy-milk-futa-comfy-batch.md) · [memory](../memory/2026-07-29-poison-shot-anatomy-iron.md) |
| **Comfy 隧道端口与排队 IRON（P0 · 2026-07-29 · 后面不要再犯）** | 本机 **`18188` 只转到远程 Comfy `8188`**；断线用 **`aifilm tunnel-ensure`**（doctor 默认 `AIFILM_COMFY_TUNNEL_AUTO=1` 自愈；LaunchAgent 每 5 分）。`18188→8189` = 鉴权服务 → `{"detail":"unauthorized"}` 401（**不是** Comfy 要登录）。健康探针：`/system_stats` 200 + Comfy JSON。lipsync 用 **18790→8790**。bulk 占卡：idle **立刻** `run-workflow`，禁先 free-memory 丢空档；禁盲 cancel 未知 running。见 [tunnel-8188-not-8189](lessons-2026-07-29-comfy-tunnel-8188-not-8189.md) · [memory](../memory/2026-07-29-comfy-tunnel-queue-neon-canary.md) |
| **Comfy 多片独占 + 本机单 client（P0 · 2026-07-29 · 后面不要再犯）** | **5090 共享**：提交前 capacity idle + VRAM≥24GiB；**本机同时只 1 个** `comfy_video.py generate`（16GB Mac 双 client → exit 137 / Killed:9）。停外片只按 **片根路径** 匹配，**禁** `pgrep -f comfy_video` 宽匹配（会杀自己）。批脚本 `set +e`；shot id **禁** `$s=09` 算术八进制。邻镜 meat 顶替须 receipt 标 FALLBACK + delivery **PARTIAL**，禁静默当 DONE。卡死 SSH restart 见 [comfy-ssh-self-restart](lessons-2026-07-28-comfy-ssh-self-restart.md)。全文 [comfy-multifilm-contention-oom](lessons-2026-07-29-comfy-multifilm-contention-oom.md) · [memory](../memory/2026-07-29-comfy-multifilm-contention-oom.md) |
| **多 agent 共用 5090 禁抢闲占满（P0 · 2026-08-06 · 不准再犯）** | **`free-first` 不 cancel ≠ 可 until-empty 抢空档**。多 agent/多会话：**默认禁止** overnight drain；`h3 cycle --until-empty --execute` **机读拒绝**除非 `--i-own-the-gpu` 或 `AIFILM_I_OWN_THE_GPU=1`（dry-run 仍可）。默认 next=`run-next --max 5`。禁自动 restart supervisor。submit 前 Comfy idle；忙则 **零 submit**。用户点名「独占」才排水；喊「占满/别人要用」→ **立刻杀 drain + neuter supervisor**。进度认 **takes 文件数** 非 pending。记忆 [multi-agent-gpu-no-hog](../memory/2026-08-06-multi-agent-gpu-no-hog.md)。 |
| **bulk→final 出片 IRON（P0 · 2026-07-29 · 强化 2026-08-06）** | **Imagine 拦 bare I2V** → undress 末帧 continue + HIGH MOTION 软词 + MEDIUM LOCK cel；禁 photoreal assembly；soft-pass 须测 mean 再装片；禁内衣冒充插入。**重拍后**全轨 review+register **两轮**。**final**：**`render_final.py` shim 必须调 main**（2026-08-06 已修；禁 1 秒假成功）；H3 短源槽≤~5.9，**禁** validate 空拉 act 到 10s（调 `sex_min_duration_ratio` 或 re-I2V）；口白 TTS≤cue≤slot；**rnb 仅 license 无 wav→procedural** 写 `receipts/bgm-source.json`；**skip gate / gate-auto 红 → `OFFICIAL_FINAL_PLATE`（`receipts/official-final-report.json`），禁当 master-lock**。超时≥1800s；字幕 `/tmp` 或 PIL 硬烧。见 [evirus-ch04](lessons-2026-07-29-evirus-ch04-bulk-final-iron.md) · [suse-ep01-final](lessons-2026-08-06-suse-ep01-official-final-iron.md) |
| **时长目标诚实（P0 · 2026-08-06 Q4.1 · S0.1–S0.2）** | 计划默认单镜 **`DEFAULT_DURATION_SEC=5.2`**（禁 6/8s 纸面槽）；`target` vs planned/media：>12% soft / >20% hard；**`shot_count < ceil(target/5.2)` → `DURATION_SHOT_COUNT_SHORT_HARD`**（即便 `duration_sec` 垫满）。**write-spec fail-closed**；plan 写 receipt。5 分片 ≥**58** 镜或降 target。机读 `receipts/duration-target.json`。逃生 `AIFILM_SKIP_DURATION_TARGET=1`。见 [shortform plan](../../docs/plans/2026-08-06-shortform-optimization-todoplan.md) · [h3-native-ship-review](../memory/2026-08-06-h3-native-ship-review-lessons.md) |
| **副导演工序（P0 · 2026-08-06 AD）** | **菜单=灶上菜**：`finalize_duration_density` + `adult-target-shot-lift`（adult 抬 target 须加镜或砍 promise）。**pilot 三看** + debrief 门。**shortlist 禁纯 mean**。**scale promote_ban** 禁 blind approve。**final 回报**必读 official-final-report。until-empty 仍须独占 GPU。见 [ad-process plan](../../docs/plans/2026-08-06-ad-process-optimization-todoplan.md) · stages agent/deliver。 |
| **H3 原声季 ship-native（P1 · 2026-08-06 Q5.1）** | `aifilm h3 ship-native`：timeline 序 concat **保 clip aac**；交付 **`OFFICIAL_FINAL_PLATE`**（非 master）；有 aac≠可懂中文须抽听。正式 master 仍 gate-auto 绿 + review-final。回执 `receipts/h3-ship-native.json`。 |
| **Still 禁整集 crop-master 静默（P0 · 2026-08-06 Q1.4）** | Imagine 挡后 **禁止** 不告警地用 cast master ffmpeg 裁切铺满全片 still。机读 `crop_master_still_report`（path/note/`parent_sha`）；≥35% soft · ≥55% hard 拦 bulk。回执 `receipts/crop-master-still.json`。逃生 `AIFILM_SKIP_CROP_MASTER_STILL=1`。见 [h3-native-ship-review](../memory/2026-08-06-h3-native-ship-review-lessons.md) |
| **收尾门禁 IRON（P0 · 2026-07-29 · 后面不要再犯）** | **有 plate ≠ 收尾完。** heat：S 分仍看 `codes`（`SEX_BOTH_UNDRESS_UNSTATED` → 写 `partner_wardrobe_state`）。adult sensory：act/climax `sex_sfx` 事件 + `mix_report.artifacts` 三轨 hash + AV≥90。改 film-spec 立刻刷 `truth_contract.contract_sha256`。pilot 用 `approved_by=user` + 白名单原话。still `frame_chain_seed`≠approved。字幕钟=真 concat（`film_timeline.shot_starts`=**片上槽**，手拼 6s 须重写 0,6,12…）；cue 不跨 hard 切。改 final：**删** quality-report + **重绑** narrative `media_sha256`（勿乱改 planned shot_id）。链：review-final→**post-audit**→export-desktop。SIZE 禁 act 回宽≥2/三连同 L。简化 final 须 PARTIAL。ch04 GO 见 closeout §9。见 [closeout-gates-chaebol](lessons-2026-07-29-closeout-gates-chaebol.md) |
| **max 默认全闸 hard（P0 · 2026-07-28）** | `heat_scale=max` 且 `adult_max_iron≠false` 时默认 **true**：`coitus_strict` · `size_ladder_strict` · `pose_strict` · `sex_arc_strict` · `sex_detail_cu_strict` · `both_undress_strict` · 既有 sex_floor/wardrobe/vo/heat_arc。裸抱不算 penetration；合拍须高潮/射出标记；`aifilm heat check` 输出四拍占比 + 定器 CU + **erotic impact** 分。 |
| **adult 默认钉 max + 交付 impact 底（P0 · 2026-07-29）** | `genre=adult`（默认）→ **强制** `heat_scale=max` + `spice=extreme` + `ADULT_MAX` 脊柱（仅显式 soft/medium / 非成人 genre 退出）。plan 写全 `sex_arc_beat`/`coitus`/`wardrobe`。`SEX_ARC_RATIO_SKEW`（转≥25% 肉戏窗）与 `SEX_ARC_RELEASE_RATIO_LOW`（合≥12%）**hard**。弱 nar **auto-apply**（`sex_vo_auto_apply`，用户句只追加）。**erotic impact ≥75 (A)** 才过 write-spec / review-final。state-index：undress-anchor + undressed/bare 状态照 **hard**。 |
| **Wave 3 冲分/色气 checklist（P1 · 同日）** | `aifilm heat boost --apply` 把 impact 冲向 **S≥90**（加长 meat/bare/定器/动词/VO）；`lint_ecchi_checklist` 6 项（距离/失序/感官/权力/双关/完成）；mute-frame advisory 只列 act/climax 须人工 coitus 分（**无假 CV**）。`ecchi_checklist_strict:true` 才 hard。 |
| **Wave 4 agent 回路（P0 · 同日）** | `dispatch`/`next` 优先 `heat boost --apply`；`preflight` max 对时长/回穿/四拍/impact&lt;A **hard**；write-spec 自动写 `receipts/heat-boost.json`；`auto_heat_boost:true` 才自动字段 patch。 |
| **Wave 5 fail-closed bulk（P0 · 同日）** | `media-queue add` 遇 `heat_agent_status.hard_fail` **硬拦**（`assert_heat_allows_media`；pilot skip 不绕过）；craft/dispatch compact 露出 heat；逃生 `AIFILM_SKIP_HEAT_QUEUE_GATE=1`。 |
| **Wave 6 final 闭环（P0 · 同日）** | `final_ok`=impact≥S(默认90)+弧/时长；`aifilm final` / `review-final` / `export-desktop` 绑 `assert_heat_allows_final`；逃生 `--skip-heat-gate` / `AIFILM_SKIP_HEAT_FINAL_GATE=1`。queue 仍只硬拦 A 以下。 |
| **Agent 出货纪律（P0 · 同日 · 后面不要再犯）** | `SKILL.md` **≤6000B** 且保留文档锚点；改 scripts **必刷 runtime-lock**；push 前工作区干净；完成=origin 绿。见 [agent-ship-skill-budget-push](lessons-2026-07-29-agent-ship-skill-budget-push.md)。 |
| **wardrobe ladder（P0 · 同日）** | 逐件卸装：garments → 串行 state I2I → `state-index approve-state`（本地登记、不调 provider）；exact `wardrobe_state_id` 未批 = state-index hard。 |
| **dialogue_drama（P0 · 默认主链 · 2026-08-03）** | 默认 `vo_mode`。**角色口中文** + 字幕 zh（**仅 HyperFrames 烧字**）；散文拆句正反打；禁说书 `nar` 抢时钟。 |
| **Wave 2 强制拉满（P0 · 同日）** | plan **秒数预分配** meat≥50%；multi-scene compact 含 **climax bare**；`aifilm heat soften-compensate --apply`（VO+SFX+energy，禁降 heat）；promote **回穿 rank 硬拦**；`music_spotting` 跟 phase energy；pilot 批准须 **undress+union/rhythm** 三拍证据才 bulk。 |
| **首帧结构** | **致命**（P0）：keyframe 解剖/融合 fail → 禁 I2V；I2V 后必抽 t=0；坏首帧=整段废（2026-07-21 33s 案） |
| **景别堆叠** | 成人 60s：宽≥1·中≥2·近≥2·局部≥2；act→climax 收紧不回退全景；连续 3 镜同 size fail（2026-07-21） |
| **性交冲击力标竿** | 用户要性交/办事冲击/尺度太小→`coitus_grammar`；act 静帧过 **Mute Frame Test**；六拍 ENTRY→HOOK；禁拥抱冒充办事；审核软化走双轨不降 heat（2026-07-21） |
| **成人脊柱 + 机器闸（v1.9–1.10）** | plan 成人脊柱；六拍/景别；**sex≥30%**；`spice_level` extreme；声画同动词；act 自动 SFX；hardcore 娇喘轨建议开；蒙太奇 craft 注入；`sex_pose` 多体位；`heat check|vo-suggest|soften-log`；[adult-max-playbook.md](adult-max-playbook.md) · [pose-packs/coitus-beats.md](pose-packs/coitus-beats.md) |
| **Extreme 尺度扩展（P0 · 2026-07-29）** | `spice_level=extreme` + `adult_max_iron=true` 时强制启用以下机制：
| | **深插抽送**：`coitus_beat=deep_thrust` 优先；prompt 注入 `deep penetrating thrust, pelvis bottoming out, skin-to-skin friction impact`；I2V 动词必须含 `thrust/pelvis/bottoming-out`
| | **内射/中出**：`coitus_beat=internal_peak` 或 `creampie_release`；climax 镜必须描述 `internal ejaculation / 体内` 或 `creampie release / 渗出`；`sex_arc_beat=climax_release` hard；静帧可 I2V，clip 须 `register-clip --status approved` 后交付
| | **六拍扩展**：ENTRY → UNION → RHYTHM/DEEP_THRUST → LOCK → INTERNAL_PEAK/CREAMPIE → FINISH；`coitus_strict` 默认 true；六拍缺一不可
| | **VO 荤话**：act 阶段 `sex_vo_strict` 强制 `dirty talk`（`deep inside / 塞进去 / 顶进去`）；climax 阶段强制 peak vocalization（娇喘+抽搐描述）
| | **SFX**：act/climax 自动叠加 wet SFX + rhythmic impact；`aifilm audio add-sfx --category explicit` |
| 导演门禁 | `director_intent` + 每镜 `dramatic_function` 过 `write-spec` 才 queue |
| **殿堂级意涵堆叠（P0 · 2026-08-04 · 2.37.6 全包默认）** | 每镜须有 `dramatic_function` + `visible_change`/`story_beat`；运镜禁 drive-beat 空转（blink/push-in）；对白须 speaker+text+subtext/emotion/purpose；ordered shots 须穿过 `director_intent.emotional_arc`（覆盖+非平）。**validate/preflight 默认 fail-closed（全 genre）**；逃生 `dramatic_meaning_strict:false` 或 `AIFILM_SKIP_MEANING_GATE=1`（`strict:true` 仍硬）。`write-spec` 经 `cinematic_audit` 始终 fail-closed。码：`SHOT_MEANING_EMPTY` · `MOTION_NO_MEANING` · `DIALOGUE_PURPOSE_EMPTY` · `ARC_STACK_FLAT`/`ARC_NODE_ORPHAN`。代码：`scripts/dramatic_meaning.py`。见 [meaningful-motion](lessons-2026-07-20-meaningful-motion.md) |
| 口白·动作 | `nar` 动词 = `dsl.action` = `dsl.motion` 首要运动 |
| 防腻 | 连续 3 镜 ≥2 维变化（景别·主动词·`camera_axis`） |
| 长片接戏 | Continuity Chain；continue **hard**；`cut_on: mid_motion`；字节 promote |
| 转场 | silk；continue 强制 hard；满 60s 靠加镜 |
| 立场 | `focal_character` + `viewpoint` + `look_axis` |
| 双字幕 | `caption_mode: zh\|zh_en\|en`；`nar_en` 可只上字幕 |
| **零旁白 IRON（P0 · 2026-08-04 · 真门 2.36.4）** | `dialogue_drama` 默认 `zero_narration_strict:true`：全片第三人称 `nar` 占比硬底 **0%**。代码：`film_spec.zero_narration_gate` → `validate_film_spec` 报 **`NAR_BUDGET_VIOLATION`**。**替代**：① 角色对白/潜台词；② 道具特写 `dramatic_function: sensory/insert`；③ Foley。逃生：`zero_narration_strict:false` 或镜级 `silent_scene+narration_reason`。解封后回落 `narration_budget_ratio`（默认 5%）。测：`tests/test_zero_narration_gate.py`（真函数，非 stand-in）。 |
| **Delivery Truth（P0 · 2.36.4）** | **桌面拷贝硬拦**：`export-desktop` 要求 `receipts/i2v-final-gate.json` **ok=true**（缺收据=红）。`closeout` 阶梯加 `i2v_motion` 步。**film_core**：异常≠通过；`heat_scale=max` / `premium_vertical` / `dramatic_meaning_strict` 时 film_core **挡** `delivery_ready`。逃生：`AIFILM_SKIP_I2V_MOTION_GATE=1`。测：`tests/test_delivery_truth.py`。 |
| **Throughput 一键（P0 · 2.37.0）** | **`aifilm ship-prep --root`**：自动 mean（ffmpeg）→ variety → shortlist（`--promote` 写 preferred 进 manifest）→ motion-gate → film_core。clips 齐后 dispatch 优先推 ship-prep。mean 规格：fps=5 · 140×248 gray。逃生：`--skip-variety` / `AIFILM_SKIP_VARIETY_PREFLIGHT` / `AIFILM_SKIP_I2V_MOTION_GATE`。测：`test_ship_prep_throughput.py`。 |
| **Grok continue + DP 焦段（2.37.2）** | **Continue 双车道**：`continue_handoff.py` 写/读 endframe（H3 run · media-queue complete · register-clip）；Grok I2V injector 注入 CONTINUE 句；禁覆盖 stills。**DP 焦段**：spine `focal_clause` — wide/full→35mm · ms/mcu→50mm · cu→85mm · insert/ecu→105mm；作者 `lens_mm` 优先。测：`test_continue_and_dp_optics.py`。 |

## 语音与混音

| 规则 | 默认 |
|---|---|
| TTS | 中文成片 **edge**；storyteller `auto`→edge |
| **人物对白 / 口白语言** | **P0**（**08-04 中文唯一**）：**角色开口=中文 only**（`dialogue_spoken_lang=zh` 硬锁；女 `zh-CN-XiaoyiNeural` / 男 `zh-CN-YunxiNeural`）；**字幕中文** `caption_text`。**日文路径已退役**（禁 `ja` / `dialogue_ja` / `ja-JP-*` 生产）。正式 master=HF owner（plate `subs=off`）；**ship/门红=硬烧优先**。无对白=纯画面。见 [dialogue-first-workflow](dialogue-first-workflow.md) · [voices.md](voices.md) |
| **cast_voices 与 spoken_lang 同锁（P0 · 2026-08-04）** | 仅 `zh`；**禁止** `cast_voices` 挂 `ja-JP-*` / 英声（运行时自动改回中文池）；ledger 须有中文 `spoken_text`。TTS 前打印 `speaker\|voice\|spoken_lang=zh`。见 [huangdao-rhythm-still-voice-silk](lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md) |
| **final / SRT** | **P0**（2026-07-24；07-29 长片 v1）：`sub_lead=0` 或写盘前非重叠钳制；`aifilm final` 默认按时长/镜数/lipsync 动态 timeout，长片不再固定 1200s；plate 后中文硬烧。见 [ep2-voice-heat-final](lessons-2026-07-24-ep2-voice-heat-final.md) · [longform](longform-workflow.md) |
| Voicebox | **质量升级 + opt-in 本地兜底**（非默认替换 edge）；固定 `VOICEBOX_PROFILE`；`AIFILM_TTS_VOICEBOX_FALLBACK=1` 才 edge 失败再试 |
| 机位 | 开场 **`aifilm dispatch`**（craft+capability+next）；或 `capability`；`--suggest-i2v` / `--apply` 改 I2V 须显式 |
| 自动调配 | 每回合 `dispatch` → 只执行 `next_cmd`；不自批 pilot；不静默换 provider |
| 语速 | `vo_rate +0%`（色气 +5%~+8%；禁 -3% 拖腔） |
| VO 增益 | ~1.32；BGM 侧链；优先 `audio/mixed.wav` |
| BGM | 色气 **rnb**（禁 dark 除非 horror）；**硬兜底=程序 v3 multi-style**；**听感兜底=纯乐器曲库池**；`--music-seed` / `audio_policy.music_seed`；`audio_recipe` 调床厚薄；auto_sfx；见 [bgm-generation.md](bgm-generation.md) |
| VO 预算 | `nar` / 中文对白 ≤55 字（快节奏 ≤28）；`est_vo_sec ≤ duration_sec+0.5` |
| loop | hook/action 永不 stream_loop |
| 一角一声 | 固定 `vo_voice` / `cast_voices`；显式 TTS 失败不静默跨商降级 |
| **声线主导** | **对白主链·中文**：角色中文 `spoken_text` + 中文 `caption_text`（正式 HF / ship 硬烧）+ BGM duck；无对白=静镜。第三人称 `nar` **仅 gap**。`vocal_color` 默认关；见 [voice-tracks.md](voice-tracks.md) |
| **5-Track 影院级混音（P0 · 2026-08-04）** | 全片默认 5 轨合成：**DX**（对白/居中/-16LUFS）· **FX**（Foley 点缀/服装摩擦/脚步）· **BG**（环境底噪/Room Tone 全程贯穿·绝不静音）· **MX**（BGM Score·DX 出现自动 sidechain -4~-6dB）· **SUB**（LFE 低频脉冲·剧情转折触发）。BG 轨禁止出现零值静音段（>200ms 纯 0）；DX 与 BG 合并 → `-16 LUFS (±1.5dB)` 最终响度；见 [bgm-generation.md](bgm-generation.md) · [5track-audio-master.md](5track-audio-master.md) |

## 视觉与一致性

| 规则 | 默认 |
|---|---|
| bulk 动作 I2V | **有 5090 推荐 `h3_primary`**（全镜本地 H3，时间换无限产能）。**`hybrid_h3`** 双轨：setup=Grok 云；肉戏/bare=H3。对白安全镜可 FRW LTX。矩阵见 [weapon-lane-matrix.md](weapon-lane-matrix.md)。无 GPU 才纯 `grok_primary`。 |
| 本地 MiniMax H3 | **film-lane 已打通（verified + production_promoted）**：`comfy-h3` T2V/I2V/R2V；`aifilm h3 plan|run` 无需 `--allow-experimental`；成人 max **自动** `h3.enabled` + soft-lock；`media-queue` **硬拦** restricted 进云 bulk（逃生 `AIFILM_ALLOW_CLOUD_RESTRICTED=1`）；出片 **≥704×1280** upscale；**bulk 仍要用户 pilot 批准**；原声 `prefer_native`；证据 `registry/evidence/h3-canaries/`；Wan 2.2 本地 I2V 仍退役 |
| **H3 效果最大化（P0 · 2026-08-04 · 2.37.3 自动 mode）** | **模式**：**I2V**=有 still 的主角/肉戏/反应/续镜默认；**R2V**=高能量、换构图、对白大嘴 CU；**T2V**=仅无脸 env/bridge（**禁锁脸**）。**机读**：`scripts/h3_mode.py` `resolve_h3_mode` → `h3 list|plan` 输出 `mode`/`command`/`alt_mode`。**高动**=狠 prompt+状态 still。**续镜**=批准末帧→I2V。**对白注入**=`audio_cues` 必进 prompt。**运维**=换模式前 `comfy free-memory --confirm`；VRAM≥24GiB；5090 独占。见 [weapon-lane-matrix](weapon-lane-matrix.md)·[h3-max-effect](lessons-2026-08-04-h3-max-effect.md) |
| **Fill-Idle 挑战（P0 · 2026-08-04 · 2.37.5 机读）** | **Grok 铺 soft baseline**；**restricted 主轨 H3**。CLI：`aifilm h3 next` / `h3 list --challenge` / `h3 pk-compare`（P0→P1→P2 mean 最低；禁静默 promote）。PK：人 `select-shortlist --promote`。final **不**阻塞于 P2。见 [weapon-lane-matrix](weapon-lane-matrix.md) · [memory](../memory/2026-08-04-h3-fill-idle-challenge.md) |
| **FRW i2i 素材挑战（P0 · 2026-08-04）** | 平台硬限 **生图 ≥30s/次**（共享 `~/.hermes/cache/ai-film-frw-frw-rate.json`）；默认 **unit=1**。`aifilm still-challenge plan\|next\|run\|promote`：用 FRW **img2image** 产 candidate still → 人审 promote 后替换 I2V/R2V 源；**禁**静默 promote；续镜/毒镜 skip；**不抢** 5090 H3。弱 take 可先 still 再重 I2V。见 [weapon-lane-matrix](weapon-lane-matrix.md) · [memory](../memory/2026-08-04-frw-i2i-still-challenge.md) |
| **Speaker-frame（P0 · 2026-08-04 v2.37.8）** | `on_camera` 对白镜 speaker=画面主体（dsl.subject/cast）且=cue speaker；热窗同 beat 禁 speaker 翻转。preflight soft；max dialogue_drama / `speaker_frame_strict` hard。见 `dialogue_speaker_frame_gate.py` |
| **Fill-Idle run-next / PK ledger（2.37.8→2.37.12）** | `aifilm h3 run-next [--execute] [--max N]`（P2=pilot；默认 max=1 上限 20；非 daemon）；`h3 pk-ledger` 只记人审 PK，**禁**跨片自动胜率。 |
| **ship-prep × PK（2.37.10）** | `aifilm ship-prep` 在 shortlist 后挂 **advisory** `pk_compare` + `fill_idle_pending`（`human_pk_required`）；**永不**自动 promote。逃生 `--skip-pk` / `AIFILM_SKIP_SHIP_PK=1`。 |
| **Fill-Idle αβγ（2.38.0）** | **evidence** 收据；**pk_score** 复合分+身份软罚；dual **粘连**；I2V 够强跳盲 R2V；P2 基线过强可跳；`run-next` 换模 **free-memory**；Grok complete 打 `takes/.../grok_*`。禁静默 promote。 |
| **ship-prep 人审 PK（2.38.2）** | 多 take 时 **defer promote**（禁 mean 先静默写 manifest）；`h3 cycle` 一循环；`pk-dailies.md`。逃生 `AIFILM_SHIP_PROMOTE_FORCE=1`。 |
| **Motion Prompt Spine（P0 · 2026-08-04）** | 动向生成（**Grok I2V + H3**）必须携带电影核：`dramatic_function` → `want_beat`（自 `director_intent.protagonist_want/theme`）→ action/motion/visible_change → camera_prompt → 对白/foley。`build_shot_intent` 输出 `motion_tier`/`optical_tier`/`want_beat`/`has_action_core` 等核字段。**Grok injector + H3 + media-queue** 对空核 **fail closed**（`MOTION_CORE_*`）。逃生：`AIFILM_SKIP_MOTION_CORE=1`。代码：`scripts/motion_prompt_spine.py`。见 [weapon-lane-matrix](weapon-lane-matrix.md) |
| **Motion Core 整合 A（P1/P2 · 2.36.0）** | **单一 tier**：`motion_tier_resolve` → `prompt_tier` soft\|medium\|high + `optical_tier` soft\|medium\|normal\|meat\|high（spine 与 gate 同表）。**Variety 硬门**：`bulk-preflight` + `h3 run --register` fail-closed（`AIFILM_SKIP_VARIETY_PREFLIGHT=1`）；**禁 silent pass**。**DF 动门 floors**：soft≥**10** / medium≥**16** / normal≥**18** / meat·high≥**20**；act/climax 永不 soft-DF 降档。**Continue handoff 写**（读侧 Phase C）。**Closeout film_core** advisory。测：`test_motion_core_p1` · `test_motion_core_integrate_a` |
| **Motion Core 整合 B（2.36.1）** | **`aifilm i2v-motion-gate --root`** 自动从 film-spec 填 DF/wardrobe + takes/audit mean（可无 `--rows`）。**Grok spine**：`receipts/prompts/<id>.grok.spine.txt`。**film_core** 双轨审 `.motion/.h3/.grok` spine；缺 hero spine → `CORE_SPINE_MISSING`。**dispatch/next** 在 clips 后推 `i2v-motion-gate`，final 后推 `film-core-closeout` advisory。 |
| **Motion Core 整合 C（2.36.2）** | **Continue 闭环**：`h3 run` 写 `receipts/continue-handoff/<id>.json`+`_end.png`；下一镜 `chain_mode=continue` / `parent_shot_id` 时 `plan_h3_shot` **自动读** endframe 作 still（`still_source=continue_handoff`）。**禁止覆盖**已批 `stills/<id>.png`；仅缺 still 且 `AIFILM_CONTINUE_COPY_STILL=1` 才复制。 |
| **高动态常态（P0 · 2026-07-27）** | **产品硬底**：平常 mean≥**18**；肉戏 act/climax mean≥**20**（目标≥24）；成片 1:00→片尾包络≥**18**。**DF 分档（P1）**见上「Motion Core P1/P2」。禁止 Ken Burns/仅微呼吸/弱 raw 装片；多 take 取 mean 最高且时长≥镜长；肉戏 10s 优先 **6s×2 hybrid**。交付前写 `i2v-high-motion-audit` + `i2v-final-gate`；**仅 gate ok 才拷桌面 film_final**。**代码入口**：`scripts/i2v_motion_gate.py`（`MEAN_NORMAL_FLOOR=18` / `MEAN_MEAT_FLOOR=20` / soft=10 / medium=16）· CLI `aifilm i2v-motion-gate --rows …`。见 [high-motion-style-lock](lessons-2026-07-27-high-motion-style-lock-final.md) |
| **I2V 画风锁 MEDIUM（P0 · 同案）** | 源图= style-locked still/keyframe；prompt 首段 **MEDIUM LOCK cel anime**（match style-v1；禁 photoreal/3D/半写实油光）；高动重跑与 last-frame 连戏 **不得** 用 mean 换 medium fail；交付前 style audit 抽帧。见同上 lesson |
| **vocal_color 默认** | **never**（2026-07-27 用户永久禁娇喘轨除非显式恢复）；`forbid_vocal_color` / gain=0 |
| I2V profile | **推荐 `h3_primary`**（5090）；`hybrid_h3` 双轨；成人 max 无 profile 时仍可 auto-enable H3→hybrid；纯云 `grok_primary`；旧项目 `ltx23_primary`。退出 H3：`h3.enabled=false` / soft heat |
| FRW LTX canary | 影片级完整解码＋人工批准后才可执行；缺证据时跳到 Grok，但不永久改写 film-spec |
| 403 / 502 | **403**=未开通；**502**=平台挂；勿混淆 |
| 动作降级 | 未就绪路线可跳过；已尝试路线仅 timeout/429/5xx/连接失败才签名降级；质量/人工拒绝不切换 |
| FRW Wan | 公共 CLI 不可指定模型；只有回执明确证明 Wan 身份、全解码与人审通过才启用，否则跳到本地 |
| env 无脸 | FRW LTX T2V 优先；再走 Grok no-face 与已验证本地路线 |
| 口型 | **v2.40 移除**：仅 off；对白 Grok/H3 **原音**；旧工具墓碑 raise |
| 静帧 | 主角 Grok **`image_edit(cast)`**；禁反复纯 `image_gen`；加载 `/imagine` |
| **静帧几何·禁压缩** | **P0**：I2V 前 keyframe **≥704×1280 且 9:16 竖比**；FRW 原生 704×1280 不强制升到 720；禁横图/缩略图/缩水 jpg。 |
| **先验后生·算力刀口** | **P0**（2026-07-22）：**验证通过才烧下一级**（still 先验→I2V；ref 先验→image_edit bulk）。禁止未验批量 I2V/出图；坏了只修上游。见 [verify-before-generate](lessons-2026-07-22-verify-before-generate.md) |
| Grok Build | 推理+Imagine；静帧 Grok/Qwen；动作 I2V Grok/H3；**对白讲话镜 = Grok Video 或 H3 原音**（非 LTX/非后期对嘴） |
| 构图 | 禁裁头（P0·2026-07-27 强化）：主戏镜 full head+headroom；**裁脚优先于裁头**；定器特写=「脸+结合同镜」或短 insert，禁无头主镜；打包慎用 increase+crop 切顶。见 [headroom-no-crop-heads](lessons-2026-07-27-headroom-no-crop-heads.md) |
| 库存 | film-spec 镜数 = approved clips |
| 同源 | 禁止半 Grok 半 FRW still/2V |
| 漫剧 | 禁默认 photoreal bible；改 medium+signature 再 lock-style |
| 分层 | L0 Grok still · L1 I2V 脸 · L2 LTX 无脸床 · L3 HF · 矩阵见 frw-key-capability |

## 后期

| 规则 | 默认 |
|---|---|
| 交付 | `final --post-engine hyperframes` |
| 字幕唯一所有权 | `plate-cards blank` + `subs off`；最终烧字只能由 HyperFrames 完成，HF 失败即修复并重渲，禁 PIL/FFmpeg 兜底 |
| 字幕路径（P0） | `master_hf`（plate `subs=off` + HF 烧） vs `ship_hardburn`（PIL 硬烧，可烧底）；`aifilm caption-pixel-check` 底带 ink；禁双烧 |
| 后期单钟（P1） | 只认 `film_timeline.shot_starts`；`timeline-clock` / `post-doctor`；mix PARTIAL 写 receipt 不装五轨齐 |
| 审片 assist（P3） | `agent-review-final` 机读预填；**禁**代签 `review-final` / `final_complete`；须人短语 `--apply` |
| final | 串行；FRW clip 先 re-encode 再 register |
| loudnorm | auto ≈ -16 LUFS |
| 路径 | HF 忌空格路径 → 可拷 `/tmp/...` |
| 证据 | intent ≠ executed ≠ human_review |

## 量产十条（与代码门禁一致）

1. `write-spec` 过 → 才 `media-queue add`
2. pilot 用户批准 → 才 bulk（无批准最多 3 shot_id）
3. hero bulk 默认 **`h3_primary`**（5090 本地 MiniMax H3 I2V/FLF/R2V/T2V）；**Grok** = pilot 快看 / soft 对照，非主 bulk。无 5090 才 `grok_primary`；旧项目可 `ltx23_primary` / FRW LTX 对白安全镜。每一路仍须当前 canary/pilot
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
- [directors-lens.md](directors-lens.md) · [script-value-debrief.md](script-value-debrief.md) · [film-spec.md](film-spec.md) · [consistency.md](consistency.md)
- [continuity_chain.md](continuity_chain.md) · [post-compose.md](post-compose.md) · [production-discipline.md](production-discipline.md)
- [editor-cut-pass.md](editor-cut-pass.md) · [ecchi-story.md](ecchi-story.md) · [voices.md](voices.md)
- [frw-degrade-dispatch.md](frw-degrade-dispatch.md) · [lessons-2026-07-21-frw-key-capability.md](lessons-2026-07-21-frw-key-capability.md)

---

## 2026-07-22 · 少婦案补记（脸锁 / 字幕 / BGM / final）

见 [lessons-2026-07-22-shaofu-cast-subs-bgm-final.md](lessons-2026-07-22-shaofu-cast-subs-bgm-final.md)。

- 角色 still：只 `image_edit(cast)`；禁审核失败后 t2i 绕脸
- HF `subs=off` 仅当 HF 真完成；HF 失字即阻塞交付、修 HF 后重渲，禁止 plate/PIL 改烧
- 色气 BGM：`assets/bgm/rnb/*` 优先
- `aifilm final` → render_final **timeout≥600s**
