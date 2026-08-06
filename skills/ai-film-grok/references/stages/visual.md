# Visual 阶段卡

先验后生：静帧、身份、状态、几何未过闸，不得进入 I2V。

## 谁喂谁（素材 → 模型 · 一眼图）

```text
L0 style-v1          → 画风锁（MEDIUM LOCK）
L1 cast master       → image_edit 定妆 / R2V identity ref（禁 peak 直接当 I2V 首帧）
L2 state photo       → 卸装阶梯 undressed/bare / undress-anchor
L3 still|keyframe    → 一镜一静帧（I2V/H3 first 主粮）
L4 clip take         → Grok I2V / H3 I2V·FLF·R2V / LTX 对白
L5 endframe handoff  → 下镜 L3（continue；smash 勿盲 promote）

武器吃什么：
  Grok I2V     ← L3 still + motion spine prompt
  H3 I2V       ← L3（或 L5 continue）+ 狠 motion
  H3 FLF       ← L3 first + L3_end last
  H3 R2V       ← L3 + L1 identity refs（+ 可选 last 作 pose）
  H3 T2V       ← 无脸 env only
  FRW LTX      ← 对白脸 still + 有声中文
  Qwen / FRW i2i ← 修 L2/L3（still-challenge；人 promote）

机读单出口：`still_source.resolve` · `generation_request.build` →
  receipts/prompts/<id>.request.json
命名：[material-fidelity-loop](../material-fidelity-loop.md) · primary：[weapon-inventory](../weapon-inventory.md)
```

- 有角色的 still 使用已批准 cast/face/state 来源；禁止从零抽脸绕过 moderated 结果。
- 9:16 keyframe 默认至少 704×1280，接受 provider 原生 704×1280 且不强制放大；禁止横图、缩略图和压糊来源。
- `state-index check|plan` 先于 bulk；衣着状态只前进，已脱不得回穿。
- Continue 镜使用已批准末帧作为下一镜输入，按实际姿势、服装与视线接戏。
- pilot 必须由用户批准；付费或外部生成必须实时 capability 检查。
- **Pilot GO 包**：`aifilm pilot pack` → `receipts/pilot-go.json`（三镜+卸装三拍+score+heat+state + **three_look 构图/衣着/毒镜** + debrief_gate）；bulk 前一屏。
- **选片（AD C2）**：`select-shortlist` multi-take **禁只比 mean**；须 composition anti-hijack 列；`receipts/select-shortlist.json` `mean_only_forbidden=true`。
- **尺度 promote（AD C3）**：`scale-fallback` `promote_ban` 时禁 blind approve；须 re-gen soft-max 或 review-note 含 `soft-max`/`scale_fallback`。
- **Bulk 单门**：`aifilm bulk-preflight`；**pilot 已批后 media-queue 默认硬拦**（逃生 `AIFILM_SKIP_BULK_PREFLIGHT=1` / `--allow-without-pilot`）。
- **设计期 variety**：`aifilm variety-precheck`（体位/脸 CU/邻镜 motion）— bulk 前改 spec 比重渲便宜。
- **5090**：`aifilm gpu-lease acquire|heartbeat|release`；`tunnel-probe`（18188→8188）；进度只认 `queue-progress` 非空 takes。
- **武器路由（P0 · 2026-08-06 free-first）**：**默认 `AIFILM_I2V_PROFILE=h3_primary`** → 全镜 5090 MiniMax H3 主生成（setup/meat/对白/env 均 comfy-h3；**Grok Video 1.5 = 技术/escape 兜底 only**；云 bulk 默认硬拦）。兼容 **`hybrid_h3`**：setup→Grok；肉戏→H3。无 GPU 才 `grok_primary`。逃生 `AIFILM_ALLOW_CLOUD_RESTRICTED=1`。dispatch 优先 `h3-run-next`。
- **MiniMax H3（hybrid_h3 / 片级 h3.enabled）**：敏感/肉戏本地 lane → `aifilm h3 list|plan|run --register`（pilot 闸；禁静默 bulk；**原声 prefer_native**：可用则保留，不可用再 strip→TTS）。云 bulk 仅 general 镜走 Grok media-queue。
- **H3 效果最大化（2026-08-04 · 2.37.3 自动 mode）**：**I2V** 锁脸默认；**R2V** 高能量·对白大嘴 CU；**T2V** 仅无脸 env。`h3 list|plan` 调 `resolve_h3_mode` 写 `mode`/`command`/`alt_mode`。续镜=末帧→I2V。换模式前 `comfy free-memory --confirm`。见 [h3-max-effect](../lessons-2026-08-04-h3-max-effect.md)·[weapon-lane-matrix](../weapon-lane-matrix.md)。
- **Fill-Idle（2.38.2）**：`h3 cycle --execute --max 5` 一循环；多 take 时 ship-prep **defer promote**；`pk-dailies.md`；dual 粘连/够动停/free-memory。见 [fill-idle memory](../../memory/2026-08-04-h3-fill-idle-challenge.md)。
- **Motion Prompt Spine（P0）**：每镜动向必须带 `dramatic_function` + want 一句 + 可见动作 +（对白则台词）。`h3 run`/`media-queue` 空核拒跑；Grok I2V 与 H3 共用 `motion_prompt_spine.py`。
- **运镜服务事件（β）**：先写 `visible_change`/action，再写 camera；禁空 push-in。邻镜肉戏换 camera **或** shot_size **或** motion 主句。H3：`aifilm h3 list` 的 mode/command 为真相。
- **高动态常态（P0 · 2026-07-27）**：I2V 后逐镜 mean 平常≥18、肉戏≥20；多 take 取最高动且时长够；肉戏 10s 优先 6s×2。禁止 Ken Burns/微抖装片。见 [high-motion-style-lock](../lessons-2026-07-27-high-motion-style-lock-final.md)。
- **MEDIUM LOCK（P0 · 同案）**：每条 I2V 源= style-locked still；prompt 首段 cel 动漫锁；高动/连戏不得漂半写实；装片竞标 motion×medium 双过。
- **禁设定拼图 keyframe（P0 · 2026-08-03 荒岛）**：turnaround/多格表情板 **不得** 入 `keyframes/` 再 I2V；`register-still approved` 硬拦 `STILL_LOOKS_LIKE_CHARACTER_SHEET`。一镜一连续叙事静帧。
- **要影片不要图（true-video）**：**运镜 = 模型生成视频内**；still 只作 I2V/R2V first 输入，**永不**进成片轨。禁 Ken Burns/zoompan/panel still-motion 当 hero。`register-clip`/`ship-prep`/`final` 走 `true_video_policy`。剧情片禁 `motion_plan` Ken Burns；仅 `production_mode=panel` 旁路。moderated → 末帧 continue + 真 I2V/H3。
- **末帧链**：`extract-frame --promote-keyframe NEXT` 默认；下镜从 seed 开，禁 cast 重起。**smash/跨空间勿盲 promote**（防沙滩污染洞穴肉戏）。
- **对白镜 speaker=画面（P0 · v3）**：`on_camera` 台词角色须占画面主读（脸/口型）；禁 A 台词 + B 肉身。
- **构图防抢走（P0 · 2026-08-05）**：multi-seed 禁只比 white0/音量/mean；`aifilm anti-hijack` + shortlist 自动拒沙俯视/脚印、拒男胸抢女主镜。逃生 `AIFILM_SKIP_ANTI_HIJACK=1`。
- **DP 焦段自动注入（v2.35 P0）**：根据 `shot_size` 拼入焦段词 — wide: `35mm deep focus` · medium: `50mm f/2.8` · close-up: `85mm f/1.4 creamy bokeh` · insert: `105mm macro`。三点式光影预设按 `director_intent.tone` 自动匹配（warm/tense/dramatic/afterglow）；Teal&Orange 调色词默认拼入末行。禁正面均光/平光无层次。见 [hollywood-optics](../hollywood-optics-prompts.md)。
- **对白三相表演注入（v2.35 P0）**：Keyframe Prompt 必含三段 — Pre-Speech（0.15-0.25s `subtle intake of breath`）· Spoken Delivery（`mouth articulates、eye contact`）· Afterglow Breath（0.35-0.70s `gentle exhale, expression lingers`）。台词 >4.5s 自动拆镜，DX 轨不断。见 [hollywood-optics](../hollywood-optics-prompts.md)。
- **肉戏邻镜差异 + afterglow**：邻镜禁同构图复读；余韵禁无对象单人站桩。见 [huangdao §H](../lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md)。

深入资料：[weapon-lane-matrix.md](../weapon-lane-matrix.md) · [consistency.md](../consistency.md) · [keyframe-first-state-index.md](../keyframe-first-state-index.md) · [i2v-grok-primary.md](../i2v-grok-primary.md) · [frw-degrade-dispatch.md](../frw-degrade-dispatch.md) · [high-motion-style-lock](../lessons-2026-07-27-high-motion-style-lock-final.md) · **[huangdao-rhythm-still-voice-silk](../lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md)** · **[caption-hardburn-meat](../memory/2026-08-03-huangdao-caption-hardburn-meat-variety.md)** · **[hollywood-optics](../hollywood-optics-prompts.md)** · **[5track-audio](../5track-audio-master.md)**
