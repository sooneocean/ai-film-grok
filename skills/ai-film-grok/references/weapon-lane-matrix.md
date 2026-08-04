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

## H3 三模式 · 效果最大化（2026-08-04 实机 · 2.37.3 自动选型）

| 模式 | 一句话 | 用 | 不用 |
|------|--------|----|------|
| **I2V** | 定妆 still 动起来 | 主角、肉戏、反应镜、**续镜硬接** | 无 still；无脸垫片 |
| **R2V** | 参考演一版 | 高能量、换构图、对白大嘴 ECU | 必须像素贴 still 时（优先 I2V） |
| **T2V** | 纯文生 | 无脸 env/bridge | **任何锁脸 hero** |

**自动选型（v2.37.3 · `scripts/h3_mode.py` · `resolve_h3_mode`）**：写进 `h3 plan` / `h3 list`。

| 优先级 | 条件 | mode |
|--------|------|------|
| 1 | `shot.h3_mode` / `operation` 显式 | 该值 |
| 2 | `chain_mode=continue` / parent 续镜 | **i2v** |
| 3 | `shot_role=env|bridge` | **t2v** |
| 4 | insert + still | **i2v**（alt r2v） |
| 5 | restricted + 对白 CU/ECU；或 high + 高难度 flag；`force_r2v` | **r2v**（alt i2v） |
| 6 | 默认有 still | **i2v**（高动 soft → `alt_mode=r2v`） |

`list` 每行带 `mode`/`command`/`alt_mode`；`plan` 带 `mode_resolve` + `effect_tips` + `command_alt`。CLI `--mode` 可覆盖。

**景别速查**：WS 环境→T2V · MS 在场→I2V · MCU 反应→I2V 低动 · CU 对白→I2V/R2V · ECU 插入→I2V+细节 still · 体位高动→I2V 狠 prompt（不够再 R2V）。

**高动**：软肖像 prompt 会静（motion~4）；写清 HIGH MOTION / 体位 / 每秒可见变化，I2V 可到 ~20+（同 still 实测 4.3→23）。**不是**改 T2V。

**对白注入**：`audio_cues.spoken_text` 必写入 prompt（v2.34.1 起与 `receipts/prompts/*.i2v.txt` **合并**，不再被覆盖吃掉）。对白镜勿在自定义 prompt 写「no speech」。

**续镜 SOP（2.36.2）**：`h3 run A` 自动写 `receipts/continue-handoff/A_end.png` → 镜 B 设 `dsl.chain_mode=continue`（或 `parent_shot_id`）→ `h3 plan/run B --mode i2v` **自动读** endframe（**不覆盖**已批 `stills/B.png`）。可选 `AIFILM_CONTINUE_COPY_STILL=1` 仅在 still 空缺时复制。接缝 L1≈7.7 已证。

## CLI

```bash
aifilm comfy free-memory --confirm   # 换模式 / 开跑前
aifilm comfy capacity                # ready · VRAM≥24GiB · queue idle
aifilm h3 list --root "<film>"                    # P0 primary（restricted）
aifilm h3 list --root "<film>" --challenge        # + P1/P2 Fill-Idle 挑战队列
aifilm h3 next --root "<film>"                    # 下一条命令（P0→P1→P2 mean 最低）
aifilm h3 pk-compare --root "<film>" [--shot-id]  # 多 take 机读建议（禁自动 promote）
aifilm h3 plan --root "<film>" --shot-id shot03
aifilm h3 run  --root "<film>" --shot-id shot03 --mode i2v|r2v|t2v --register --no-queue
# restricted 误入 Grok queue → QueueError；逃生 AIFILM_ALLOW_CLOUD_RESTRICTED=1
```

## 产能日历

1. 云：Grok setup + 非敏感 pilot / bulk baseline  
2. 本地：Qwen 卸装 / bare state masters  
3. **5090 独占**：H3 按 **Fill-Idle 优先级** 串行（下节）  
4. 云：桥接 / 对白 LTX（安全近景）  
5. `select-shortlist` 建议 → **人审** promote → ship-prep → final（HyperFrames）

## Fill-Idle · Grok 主轴 + H3 挑战（2026-08-04 定策）

> 类比：Grok = 流水线铺底；H3 = 重工 + **空闲就去 PK**。  
> 短卡：[memory/2026-08-04-h3-fill-idle-challenge.md](../memory/2026-08-04-h3-fill-idle-challenge.md) · 模式细则见上「H3 三模式」与 [h3-max-effect](lessons-2026-08-04-h3-max-effect.md)

### 已定策三句

1. **Soft / 已有 Grok take：能烧就烧**——5090 空闲就填挑战；**不得**抢 P0。  
2. **R2V = 能量位优先**（大嘴 CU / 高难体位 / I2V 偏静）——**不是**全片默认 R2V。  
3. **机读建议 + 人最终拍板**——shortlist/mean 可推荐；`preferred` / approved **必须人一眼**（防换人、毒、回穿）。

### 谁是主轨

| 镜类 | 主生成 | H3 角色 |
|------|--------|---------|
| restricted / bare / 高难 | **H3** | 主轨（云硬拦） |
| 非 restricted setup/soft | **Grok** | **填空挑战者** |
| env 无脸 | FRW / H3 T2V | 气氛；不进锁脸 PK |

### 优先级（硬顺序）

| 级 | 内容 | 默认 mode | 可被 P2 挤掉？ |
|----|------|-----------|----------------|
| **P0a** | restricted 肉戏主生成 | I2V；高难 flag → R2V | **否** |
| **P0b** | restricted 对白近景 | R2V 或 I2V+台词注入 | **否** |
| **P0c** | 续镜链 / 毒后重生 | **仅 I2V** 末帧 | **否** |
| **P1** | 已有 take 但 gate 失败（mean 低 / 嘴死） | I2V 狠 prompt → 仍低则 R2V | 仅次 P0 |
| **P2 填空** | 已有 Grok、尚无 H3 take、capacity idle | **先 I2V 挑战**；仍闷 → R2V | 新 P0/P1 可抢占 |
| **P3 跳过** | 毒 still、空核、无 still 锁脸、T2V 挂人 | — | 永不入队 |

**调度**：先耗尽 P0→P1 → idle 且 ready 才拉 P2 → 新 P0 **立即暂停 P2**。进度只认 `takes/` + register 收据。

**P2 排序（agree all · 2026-08-04）**：**mean 最低优先**（最弱 Grok 先挑战）→ 并列按时间轴。跨集 **不** 自动记 R2V/I2V 胜率。

### 填空挑战口诀

```text
挑战 Grok soft：先 I2V（锁脸公平）→ 仍闷再 R2V
P0 能量位：高难/大嘴/I2V 不够 → R2V 占满这些槽
P2 优先 mean 最低；短 pilot；人说值得再 bulk 加长
final 不阻塞于「P2 100% 完成」（能烧就烧=质量上限，≠发布门；高光不强制挑战）
```

### PK（替换）

```bash
aifilm select-shortlist --root "<film>"              # 机读建议，不写 preferred
# 人 dailies 一眼后：
aifilm select-shortlist --root "<film>" --promote
aifilm ship-prep --root "<film>"
```

人审 30s：同人？体位可读？有事件？对白嘴动？——否决权高于 mean。

## 质量门分车道

- Grok：mean ≥18/20 + MEDIUM LOCK cel  
- H3：解剖安全 + 接触可读 + 几何 ≥704×1280（run 时自动 upscale）+ 原声可用性 +（肉戏）motion-gate  
- 毒 still：禁任何 I2V  
- candidate ≠ bulk：人审后才 approved  
- **Fill-Idle PK**：机读可建议 preferred；**禁** mean 静默 promote；身份/毒否决 > 能量

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
| continue-handoff | H3 写 endframe；下一镜 `chain_mode=continue` 自动读（Phase C；不覆盖 stills） |

**prompt_tier**（进 prompt）：`soft` · `medium` · `high`（act/bare/action 加 HIGH MOTION）  
**optical_tier**（mean 门）：soft≥10 · medium≥16 · normal≥18 · meat/high≥20  

逃生：`AIFILM_SKIP_MOTION_CORE=1` · `AIFILM_SKIP_VARIETY_PREFLIGHT=1`

## 代码入口

- `production_router.build_shot_intent` / `classify_shot_content`  
- `film_spec.resolve_h3_config`（成人自动 dual-lane）  
- `media_queue.add_job`（restricted → 硬拦云 · motion core）  
- `motion_prompt_spine` · `h3_workflow._prompt_for_shot` · `prompt_injector.assemble`  
