# 武器库双车道矩阵（Grok Video 1.5 + 5090 H3）

> 2026-08-03 · 运营真相 · **2026-08-04 H3 效果最大化补丁**。  
> 类比：**Grok = 量产流水线**；**H3 = 重工车间**；**LTX = 对白棚**；**Qwen = 本地修片台**。  
> 实机课：[lessons-2026-08-04-h3-max-effect.md](lessons-2026-08-04-h3-max-effect.md) · 短卡 `memory/2026-08-04-h3-max-effect.md`

## 对白优先（v2.34）

- **对白镜画面必须可见「人在讲」**（on_camera>嘴动+近景；肉戏对白→H3 i2v/r2v 注入 Mandarin 台词）。
- **禁全场纯 silence/action_cover 或纯 nar**：每场 ≥1 条 on/off_camera 对白；逃生 `narration_reason`（见 [hard-defaults](hard-defaults.md) 对白场景级规）。
- 工具组 = `grok i2v`（安全 setup/只做 bulk） · `5090 H3 i2v/r2v`（restricted/肉戏/对白restricted） · `FRW LTX`（安全对白棚） · `Qwen`（状态照）。

## 默认

| 片型 | Profile / H3 |
|------|----------------|
| `genre=adult` 或 `heat_scale=max/hot/extreme` | 自动 `h3.enabled=true`，片级 `_i2v_profile→hybrid_h3`（Grok bulk + H3 meat） |
| 非成人 / `heat soft` / `adult_max_iron:false` / `h3.enabled=false` | 保持 `grok_primary`，不锁 H3 |
| 显式 `AIFILM_I2V_PROFILE=hybrid_h3` | 始终 dual-lane |

## 镜头路由

| 类型 | Still | Motion | Audio |
|------|-------|--------|-------|
| Setup / 非敏感 hero | Grok `image_edit(cast)` | Grok Video 1.5 `media-queue` | Edge TTS + BGM |
| Foreplay soft clothed | Grok | Grok 优先；moderation → 签名切 H3 | 同上 |
| Act / climax / bare / undressed | Qwen Edit / undress-anchor | **H3 I2V**（queue 硬拦云 bulk） | H3 `prefer_native` |
| 高难（deep_thrust / creampie / L4+contact / force_local_h3） | 本地状态照 | **H3 I2V**；能量不够 → **R2V** | 同上 |
| 对白近景（非敏感） | Grok face | FRW LTX 2.3 | 原生有声（中文） |
| **对白近景（restricted / bare）** | Qwen 状态照 | **H3 I2V**（台词注入）；狠嘴 CU / 状态链 → **H3 R2V** | H3 原声 spoken Mandarin |
| Env / bridge | 可选 | FRW env 或 **H3 T2V**（无脸） | 环境 |
| 续镜 / continue | **批准末帧** | **H3 I2V** | 原声或沿用策略 |
| 毒镜 | Qwen 解剖修 | **禁 I2V** | — |

## H3 三模式 · 效果最大化（2026-08-04 实机）

| 模式 | 一句话 | 用 | 不用 |
|------|--------|----|------|
| **I2V** | 定妆 still 动起来 | 主角、肉戏、反应镜、**续镜硬接** | 无 still；无脸垫片 |
| **R2V** | 参考演一版 | 高能量、换构图、对白大嘴 ECU | 必须像素贴 still 时（优先 I2V） |
| **T2V** | 纯文生 | 无脸 env/bridge | **任何锁脸 hero** |

**景别速查**：WS 环境→T2V · MS 在场→I2V · MCU 反应→I2V 低动 · CU 对白→I2V/R2V · ECU 插入→I2V+细节 still · 体位高动→I2V 狠 prompt（不够再 R2V）。

**高动**：软肖像 prompt 会静（motion~4）；写清 HIGH MOTION / 体位 / 每秒可见变化，I2V 可到 ~20+（同 still 实测 4.3→23）。**不是**改 T2V。

**对白注入**：`audio_cues.spoken_text` 必写入 prompt（v2.34.1 起与 `receipts/prompts/*.i2v.txt` **合并**，不再被覆盖吃掉）。对白镜勿在自定义 prompt 写「no speech」。

**续镜 SOP**：`h3 run A` → `ffmpeg -sseof -0.15` 抽末帧 → `stills/B.png` → `h3 run B --mode i2v`（接缝 L1≈7.7 已证）。

## CLI

```bash
aifilm comfy free-memory --confirm   # 换模式 / 开跑前
aifilm comfy capacity                # ready · VRAM≥24GiB · queue idle
aifilm h3 list --root "<film>"       # 应走 H3 的镜（restricted 为主）
aifilm h3 plan --root "<film>" --shot-id shot03
aifilm h3 run  --root "<film>" --shot-id shot03 --mode i2v|r2v|t2v --register --no-queue
# restricted 误入 Grok queue → QueueError；逃生 AIFILM_ALLOW_CLOUD_RESTRICTED=1
```

## 产能日历

1. 云：Grok setup + 非敏感 pilot  
2. 本地：Qwen 卸装 / bare state masters  
3. **5090 独占**：H3 meat 串行（`gpu-lease` + 单 comfy client + **每 job free-memory**）  
4. 云：桥接 / 对白 LTX  
5. select → final（HyperFrames）

## 质量门分车道

- Grok：mean ≥18/20 + MEDIUM LOCK cel  
- H3：解剖安全 + 接触可读 + 几何 ≥704×1280（run 时自动 upscale）+ 原声可用性 +（肉戏）motion-gate  
- 毒 still：禁任何 I2V  
- candidate ≠ bulk：人审后才 approved

## Motion Prompt Spine（电影核 → 动向 · P0 + 整合 A · 2.36.0）

生成顺序（Grok 与 H3 **同一套**）：

```text
dramatic_function → want_beat → action/motion/visible_change
→ camera_prompt → 对白 lip-sync 或 foley →（provider 前缀）
```

| 机制 | 行为 |
|------|------|
| `motion_tier_resolve` | **单一真相**：`prompt_tier` + `optical_tier` + floor 映射 |
| `motion_prompt_spine.py` | 共用拼装 + `assert_motion_prompt_core` |
| `build_shot_intent` | 带出 `want_beat` / `motion_tier` / `optical_tier` / `spoken_text` |
| `h3 run` | 空核拒跑；写 `receipts/prompts/<id>.h3.spine.txt`；register 时 variety 硬门 |
| `media-queue` | 入队前 enrich + fail closed（**不 silent pass**） |
| `prompt_injector` I2V | 注入 spine + **assert 空核**；写 `*.grok.spine.txt` |
| `i2v-motion-gate --root` | 自动 DF + mean → audit/final-gate（Phase B） |
| closeout film_core | 审 `.motion/.h3/.grok` spine（advisory） |

**prompt_tier**（进 prompt）：`soft` · `medium` · `high`（act/bare/action 加 HIGH MOTION）  
**optical_tier**（mean 门）：soft≥10 · medium≥16 · normal≥18 · meat/high≥20  

逃生：`AIFILM_SKIP_MOTION_CORE=1` · `AIFILM_SKIP_VARIETY_PREFLIGHT=1`

## 代码入口

- `production_router.build_shot_intent` / `classify_shot_content`  
- `film_spec.resolve_h3_config`（成人自动 dual-lane）  
- `media_queue.add_job`（restricted → 硬拦云 · motion core）  
- `motion_prompt_spine` · `h3_workflow._prompt_for_shot` · `prompt_injector.assemble`  
