# MiniMax H3 效果最大化（2026-08-04 5090 实机）

> **结论先行**：主角/肉戏默认 **I2V**；要能量或狠嘴 CU 用 **R2V**；无脸环境才 **T2V**。  
> 续镜 = **批准末帧 → I2V**（接缝 L1≈7.7 已证）。高动靠 **狠 prompt + 对的状态 still**，不是换 T2V。  
> 运营矩阵：[weapon-lane-matrix.md](weapon-lane-matrix.md) · 短卡：[memory/2026-08-04-h3-max-effect.md](../memory/2026-08-04-h3-max-effect.md)

## 证据根（本机 artifacts）

| 批次 | 路径 | 证明什么 |
|------|------|----------|
| 三模式 canary | `artifacts/5090-evaluation/minimax-h3-canary/retest-20260804T015711Z/` | T2V/I2V/R2V 全 PASS · 704×1280 · keep_native |
| 身份 A/B | `artifacts/5090-evaluation/h3-quality-ab-20260804/` | 真人像 still：I2V 锁脸胜；R2V 中；T2V 换人 |
| 高动+对白 | `artifacts/5090-evaluation/h3-stress-ab-20260804/` | 高动 prompt 抬 I2V 4.3→23；R2V 34；台词注入成功 |
| 全链路 register | `artifacts/5090-evaluation/h3-e2e-runthrough/` | list→plan→run --register→manifest candidate |
| 景别角度 | `artifacts/5090-evaluation/h3-angles-runthrough/` | MS/反应/对白CU/续镜/插入/环境 7/7 PASS |

## 模式选型（效果最大化）

| 模式 | 像什么 | 最强场景 | 弱项 |
|------|--------|----------|------|
| **I2V** | 把定妆 still 动起来 | 主角 hero、肉戏、状态照驱动、续镜硬接、反应镜 | 软肖像 prompt 会偏静；要靠动作 still/狠 prompt |
| **R2V** | 看着参考演一版 | 高能量体、邻镜换构图、对白大嘴 ECU | 身份不如 I2V 贴 still |
| **T2V** | 只听文字瞎编 | 无脸 env/bridge/insert 气氛 | **禁挂角色**（会换人） |

### 口诀

```
有角色 still     → I2V
要续戏           → 末帧 → I2V
要大嘴/换机位    → R2V
无脸环境         → T2V
安全对白         → LTX（不是 H3）
安全 bulk        → Grok
```

### 机读自动选型（v2.37.3 · `scripts/h3_mode.py`）

`aifilm h3 plan|list` 调 `resolve_h3_mode`：显式 `h3_mode` > 续镜 I2V > env T2V > 对白 CU/高难 flag R2V > 默认 I2V（高动带 `alt_mode=r2v`）。  
`plan.command` / `list[].command` 已带 `--mode`；能量不够跟 `command_alt`。测：`tests/test_h3_mode.py`。

## 景别 × 模式（angles 实跑）

| 景别 | 模式 | 提示要点 | 实测 motion mean（约） |
|------|------|----------|------------------------|
| WS 环境 | T2V | 无人物、雨夜/空气 | ~5.5 |
| MS 在场 | I2V | 腰上构图、慢推、锁脸衣着 | ~5 |
| MCU 反应 | I2V | **锁机位**、仅微表情 | ~3.7（最低） |
| CU 对白 | I2V 默认 / R2V 狠嘴 | 台词注入 + lip sync | R2V ~16 |
| ECU 插入 | I2V + **细节 still** | 手/织物/接触；勿用半身 still 硬怼 | ~14（构图可能仍偏半身） |
| 体位高动 | I2V→不够再 R2V | HIGH MOTION 字样 + 已在动的 bare still | I2V 23 / R2V 34 |
| 续镜 B | I2V | `CONTINUE from this exact end frame` | 接缝 L1≈7.7 |

## 对白（restricted → H3）

1. `audio_cues` 写 `spoken_text` + `screen_mode=on_camera`（镜级或 cue 级）。  
2. **代码会注入** `Audio: … Mandarin … lip sync priority; line:「…」`（v2.34.1：即使有 `receipts/prompts/<id>.i2v.txt` 也会合并台词，不再被覆盖吃掉）。  
3. 安全近景对白仍走 **FRW LTX**；只有 restricted/bare 才钉 H3。  
4. `audio_policy=prefer_native` → 可用则 `keep_native`（aac stereo 已证）。

## 续镜硬接 SOP

**自动（2.36.2+）**：`h3 run s_a` 写 `receipts/continue-handoff/s_a_end.png`；`s_b` 设 `dsl.chain_mode=continue` 或 `parent_shot_id=s_a` → `h3 plan/run s_b` 自动用 endframe（**不覆盖**已批 stills）。

```bash
# 1) 跑 A（自动 handoff）
aifilm h3 run --root "$ROOT" --shot-id s_a --mode i2v --register --no-queue
# 2) film-spec: s_b.dsl.chain_mode=continue （或 parent_shot_id）
aifilm h3 plan --root "$ROOT" --shot-id s_b   # still_source=continue_handoff
aifilm h3 run --root "$ROOT" --shot-id s_b --mode i2v --register --no-queue
# 可选：仅 still 空缺时复制
# AIFILM_CONTINUE_COPY_STILL=1 aifilm h3 plan --root "$ROOT" --shot-id s_b
```

## 5090 运维（效果=稳定性）

| 规则 | 做法 |
|------|------|
| 独占 | `gpu-lease` + 单 comfy client；禁并行第二 film |
| 换模式前 | `aifilm comfy free-memory --confirm`（残留可把 VRAM 压到 4GiB 以下） |
| 产能 floor | free VRAM ≥24GiB；queue idle |
| 时长 | pilot 5s / draft mp0.2；bulk 仍要人批 pilot |
| 隧道 | `18188→8188`（非 8189） |
| 权重 | `diffusion_models/fl2va`（T2V+I2V）· `ref2va`（R2V）· `text_encoders/qwen3vl_32b…` · video+audio VAE |

## 质量门（H3 车道）

- 几何交付 ≥704×1280（run 自动 upscale）  
- 原声：mean volume 明显非静音（样片约 −14 dB）  
- 身份：I2V 中段 L1 应明显优于 T2V；续镜 end→start L1 宜 <15  
- 肉戏：仍过 motion-gate mean≥20（H3 样片要高动 prompt，勿用软肖像 prompt 交差）  
- bulk：candidate ≠ approved；人审后才批

## Motion Prompt Spine（v2.35 · 电影核进动向）

Grok 与 H3 **同一拼装顺序**（`scripts/motion_prompt_spine.py`）：

1. `dramatic_function`  
2. `want_beat`（`director_intent.protagonist_want` / theme）  
3. dsl action / motion / visible_change  
4. `camera_prompt`  
5. 对白 lip-sync 或 foley  
6. 高 heat/DF → `HIGH MOTION priority…`

`build_shot_intent` 输出 `motion_tier` / `want_beat` / `has_action_core`。  
空核 → `MOTION_CORE_*` fail closed（h3 run + media-queue）。

## Fill-Idle 运营（2026-08-04 定策 · 与模式选型互补）

> 用户要：Grok 主轴 + 本地免费 PK；能烧就烧；R2V 能量位；人拍板替换。  
> 正文表与调度：[weapon-lane-matrix · Fill-Idle](weapon-lane-matrix.md) · 短卡 `memory/2026-08-04-h3-fill-idle-challenge.md`

| 级 | 烧什么 | 要点 |
|----|--------|------|
| P0 | restricted 主生成 + 续链 | **永不**被 soft 挑战挤掉 |
| P1 | gate 失败弱镜 | I2V 狠 prompt → R2V |
| P2 | 已有 Grok、idle 填空 | 先 I2V 挑战；仍闷再 R2V；短 pilot |
| 发布 | final | **不**阻塞于 P2 100% 完成 |

**纠正「尽可能多 R2V」**：R2V 应 **占满高能量/大嘴/高难槽**，不是把默认 mode 改成全 R2V（锁脸会漂、续缝会断）。

**PK**：`select-shortlist` 建议 → 人 dailies → `--promote`。禁 mean 静默 preferred。

## 不要做

- 安全 setup **在 P0 未完时**硬塞 H3 填空（饿死肉戏）——P0 清空后的 P2 填空除外  
- T2V 锁脸  
- 毒 still 进任何 H3  
- 用 `s_*.i2v.txt` 写「no speech」又期望台词（现已强制注入台词，但会与作者 ambient 叠句——对白镜请别写 no speech）  
- 静默 bulk / 静默改 `i2v_provider` / **mean 静默 promote**  
- 无 DF/动作/对白的「空核」prompt 进 queue  
- 全局默认 mode 改 R2V（违反能量位优先定策）

## 片级开关

- 成人 max → 自动 `h3.enabled` + hybrid 行为  
- 显式 `AIFILM_I2V_PROFILE=hybrid_h3`  
- CLI：`aifilm h3 list|plan|run --register`
