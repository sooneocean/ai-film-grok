# 短版（shortform）问题分析 + 优化 Todo Plan

**结论先行：** 短版默认主产线（`production_mode=shortform`）的 **消防规则与 final IRON 大多已 ship**；真正还在拖出片的，是 **「计划时长 / 镜数」与 H3 实源 ~5.2s 脱节**，以及 **`aifilm shortform` 导演包与主脊 dispatch 脱节**。下一轮应修 **plan 根因**，不是再开一轮 final 假绿/静默 10s 那类已修事故。

| 项 | 值 |
|----|-----|
| Repo | `/Users/dex/.grok/plugins/ai-film-grok` |
| 范围 | 默认 shortform 主产线 + `cli:shortform` 旁路 |
| 状态 | **ACTIVE** · **S0.1+S0.2 SHIPPED** (2.39.97) · S0.3–S5 待办 |
| 拍板记录 | `go` 用推荐默认 **fail-closed + 明确 next**（非 auto 增镜/降 target） |
| 与旧板关系 | 产品面 `docs/plans/2026-08-06-optimization-todoplan.md` Wave A/B 代码已多收；本档 = **短版残余专用板** |

---

## 0. 「短版」指什么（先对齐）

本仓有两层「短」：

| 层 | 是什么 | 代码入口 |
|----|--------|----------|
| **A. 默认 shortform 主产线** | `plan run` 默认 `production_mode=shortform`（相对 longform 480–900s）；绝大多数 15s–数分钟 AI 漫剧走这条 | `cli_plan` · `story_plan` · `film_spec` · `edit_policy` · `render_final` · `h3 ship-native` |
| **B. shortform 导演包** | 15–60s topic / A-roll / C-roll 的 **编排控制层**（provider 中立） | `shortform_director.py` · `shortform_motion.py` · `aifilm shortform *` |

下文 **P0 主攻 A**（真片 canary 已红）；**P1 理清 B**（功能在、主流程不用、且与「冻结后期 lipsync」政策打架）。

---

## 1. 已修勿重开（禁止当绿野）

| ID | 事故 | 证据 | 状态 |
|----|------|------|------|
| A1 | validate 静默 act/climax 拉 10s | `plan/film_spec_sex_floor.py` fail-closed | **SHIPPED 2.39.77–80** |
| A2 | 口白窗 tts≤cue≤slot | `final/voice.check_vo_window_triangle` | **SHIPPED** |
| A3 | `render_final.py` shim 假绿 | shim → `main` + `test_suse_final_iron` | **SHIPPED** |
| A4–A5 | rnb 无 wav / plate≠master | `bgm-source` · `delivery_class` | **SHIPPED** |
| Q4.1 / Q4.1b | 计划 vs 媒体时长硬门 | `plan/duration_target.py` + bulk-preflight | **SHIPPED 探测**（未修计划根因） |
| Q5.1–Q5.2 | H3 原声 ship-native + 抽听 soft | `h3_ship_native` | **SHIPPED plate 路径** |
| 工程质量板 | secret/hotpath/coverage/retry | `2026-08-06-codebase-quality-todoplan` | **CLOSED 2.39.95** |

---

## 2. 仍有问题的地方（代码 + 真片证据）

### 2.1 P0 · 计划时长 vs H3 实源（根因未修）

**现象（canary 已写死）：**  
`artifacts/2026-08-06-effect-board-film-canary.json`

| 片 | planned | media | target | 码 |
|----|--------:|------:|-------:|-----|
| savani-ep01 | 300s | **211.8s** | 300s | `DURATION_MEDIA_SHORT_HARD` |
| savani-ep02 | 300s | **211.8s** | 300s | 同上 |
| savani-ep03 | 300s | **108.5s** | 300s | 同上 |
| suse-ep01 | 153s | 134s | **600s** | planned+media 双 hard |

**根因链（类比：菜单写 5 分钟，灶上每道菜只烤 5 秒，再多份也凑不够）：**

1. **H3 单镜实长 ~5.0–5.3s**，`H3_NOMINAL_CLIP_SEC=5.2` 只用于 **事后 advice**，不约束 plan 写 `duration_sec`。  
2. **`edit_policy` shortform clamp**：`SHORTFORM_SRC_MAX_SEC=7.5` + `forbid_loop` → 槽位可 stretch 上限约 **~5.9s**（宿色 IRON）。计划写 6–10s 仍会 stretch 炸或被 clamp，成片「计划满、画面短」。  
3. **`film_spec.DEFAULT_DURATION_SEC = 6.0`** 略高于 H3 实源，系统性抬高 planned 相对 media 的 gap。  
4. **`story_plan` 成人热度抬 target**（max→55s、hardcore→60s、dual_climax→100s）**不自动加镜数**。  
5. **`beat_extraction.rebalance_adult_beat_durations`** 为凑 `sex_floor` **加长 meat `targetDuration`**，仍不增 shot → 纸面肉戏够、媒体不够。  
6. **`shot_planning`** 按 beat 预算切 `duration_sec`，未见 **ceil(target/5.2)** 硬约束。

**已有护栏：** bulk-preflight 会 hard 拦 → 好，但 **拦在 bulk 前**，人已花完 plan/still/pilot；缺的是 **plan run / write-spec 时** 就按 H3 名义时长 **加镜或降 target**。

| 文件 | 问题角色 |
|------|----------|
| `scripts/plan/duration_target.py` | 诚实探测 ✓；不改 spec |
| `scripts/plan/story_plan.py` | 抬 target、不抬 shot 密度 |
| `scripts/plan/beat_extraction.py` | rebalance 加时长不增镜 |
| `scripts/plan/shot_planning.py` | 预算切分未绑 H3 名义 |
| `scripts/plan/film_spec.py` | `DEFAULT_DURATION_SEC=6.0` |
| `scripts/narrative/edit_policy.py` | shortform 禁 loop + stretch 硬顶 |

---

### 2.2 P0 · 交付诚实半成品（路径通、成片不完整）

| 坑 | 说明 | 证据 |
|----|------|------|
| ship-native 只有 concat plate | 无中文硬烧、无 rnb 侧链；正式字幕仍须再走 final | memory `h3-native-ship-review` 待做 |
| final 与 graph v2 张力 | `require_current_canonical_truth` 缺字段硬挡 → 靠 `--skip-canonical-truth` / ship-native 逃生 | 同上 |
| aac ≠ 可懂中文 | 有原声软抽听，**无 ASR/中文可懂门** | Q5.2 soft only |
| plate 当 ship | gate-auto 红时 `OFFICIAL_FINAL_PLATE` 诚实，但纪律上仍易「当交片」 | A5 已码；ops 纪律 |

---

### 2.3 P1 · `aifilm shortform` 旁路孤岛

| 问题 | 细节 |
|------|------|
| **不进主脊** | `dispatch` / `next_actions` / stage 卡 **不引用** shortform package；与 `film-spec → pilot → bulk → final` 平行 |
| **政策打架** | SKILL/hard-defaults：**生产冻结** 后期 lipsync；`shortform enable-lipsync` / `render-lipsync` 仍暴露 LatentSync 路径（topic/C 近景对白） |
| **终局弱** | `assemble-aroll` 仅 `candidate_only`，文档写须再走 decode/字幕/混音/review-final——**无一键 handoff 到 film-spec** |
| **与 H3 原音时代脱节** | 设计年代偏 A-roll 源音 + 后制 lipsync；当前主叙事是 **Grok/H3 prefer_native** |
| **测试覆盖窄** | `test_shortform_director.py` 偏 package/review/aroll 分段；无 end-to-end 接到 final plate |

**不是废代码**：topic/A-roll 编排与 motion-plan 仍有独立价值；问题是 **未声明「何时用 B 而非 A」**，agent 易误用或重复造轮。

---

### 2.4 P1 · 成人 shortform 计划侧「纸面 MAX」

| 问题 | 位置 |
|------|------|
| sex rebalance 加长 meat beat | `beat_extraction.rebalance_adult_beat_durations` |
| heat 抬 target 不增镜 | `story_plan` ~1060–1065 |
| 崩坏/模型极限 stop | scale-fallback **B 已 ship**；plan 阶段仍可能写满 bare 词硬目标 |

与 **不回穿 + 模型极限勿硬上** 一致时：plan 应能输出 **soft-max / bare-tease 诚实档** 预算，而不是一律 50% 纸面肉戏时长。

---

### 2.5 P2 · 工程税（短版路径上的巨石）

| 模块 | ~LOC | 短版触达 |
|------|-----:|----------|
| `post/render_final.py` | ~2.9k | 每片 final |
| `plan/film_spec.py` | ~3.2k | 每片 validate |
| `narrative/edit_policy_heat.py` | ~4k | heat 门 |

**原则：** 只在改 2.1/2.2 时顺手 peel，**不**为 LOC 开拆。

---

### 2.6 OPEN_OPS（非代码伪完成）

- 5090 **until-empty → queue_empty**（多 agent 禁 hog IRON 仍有效）  
- 真片 Q1–Q3 效果链（仍须片根）  
- GitHub push 账号 403（canary 已记）

---

## 3. 优化原则

1. **先 plan 诚实，再 bulk 吞吐**——门禁 red 是症状，加镜/降 target 才是药。  
2. **不重开** A1–A5、Q4 探测、包边界搬家、全仓 monolith。  
3. **不**静默降 heat / 假 master / 复活 bulk lipsync。  
4. shortform 旁路：**要么桥接主脊，要么文档标 experimental**，禁止半死不活。  
5. DONE = 测绿 +（改 CLI/指纹）`make check-all` + 相关 receipt 契约。  
6. 短令 `go` = 从本板 **S0→S1** 最小链推进。

---

## 4. Todo 波次（可勾选）

### Wave S0 · 计划侧 H3 时长诚实（P0 · 最高杠杆）

> 目标：`plan run` / `write-spec` 后，planned 与「H3 名义可达」一致；bulk 前 `DURATION_MEDIA_SHORT_HARD` 不再是「计划写满、源只有 5s」的常态。

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **S0.1** | **plan 默认单镜 cap = H3 名义** | `DEFAULT_DURATION_SEC` / shot planner 默认 **≤5.2**（或 profile：`h3_primary`→5.2，云 I2V 可更高）；禁止默认 6.0 系统性虚高 | 单测：h3_primary 新 plan 镜 `duration_sec≤5.2` |
| **S0.2** | **target → 最少镜数硬建议写进 plan** | `suggest_min_shots(target)` 在 `plan run` / `write-spec` 产出 `receipts/duration-target.json` **且** 镜数不足时 soft/hard（可配置）；auto 模式：拆 beat 增镜或降 `target_duration` 二选一写 next | savani 类 300s 输入 → 建议 ≥58 镜或明确降 target |
| **S0.3** | **rebalance 禁「只加秒不加镜」** | `rebalance_adult_beat_durations`：不足 sex_floor 时优先 **复制/拆 meat beat 槽** 或 fail + next；若只加 `targetDuration` 须 cap 到 `n_meat_shots * H3_NOMINAL` | 单测：rebalance 后 meat 纸面 ≤ 可达媒体上限 |
| **S0.4** | **heat 抬 target 同步 shot 密度** | story_plan 把 55/60/100 时，按 5.2 算最少镜，写入 graph/spec metadata | 单测 + 一份 plan receipt |
| **S0.5** | **edit_policy 与 plan 对齐文档** | hard-defaults / stages 一行：短 H3 槽 ≤~5.9；plan 禁止 > stretch 上限的「空 duration」 | 指针即可，不写长 lesson |

**不做：** 静默把 sex_floor 降到绿；用 loop 填满 5 分。

---

### Wave S1 · 交付闭环（P0 · shortform 出片最后一公里）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **S1.1** | **ship-native 可选叠硬烧/BGM** | `h3 ship-native --caption hardburn --music-mood rnb` 或明确「仍须 `aifilm final`」双路径 CLI help + receipt | 一命令 plate 有中字+aac 或 help 禁止误导 |
| **S1.2** | **canonical_truth 逃生契约测** | 文档 + 测：何时必须 skip；默认 drama 系列不 skip | 回归不误伤锁定系列 |
| **S1.3** | **中文可懂 soft→可选 hard** | 样本 ASR 或人工 checklist 入 ship-native / review-final；默认 soft | soft 码存在；hard 靠 flag |
| **S1.4** | **closeout 拒绝「假 master」** | doctor/closeout 对 `OFFICIAL_FINAL_PLATE` + gate 红 → 不可标 final_complete | 已有 A5 则补测/文案 |

---

### Wave S2 · shortform 导演包定位（P1）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **S2.1** | **决策树文档** | `shortform-director.md` + SKILL 三行：何时用 B（真人口播 A-roll / 固定脚本 15–60s）vs 主产线 A | 人读 30s 能选对 |
| **S2.2** | **lipsync 与冻结政策对齐** | enable/render-lipsync：默认拒绝 + 文案指 prefer_native；仅 `--experimental-lipsync` 或 aroll 源音路径保留 | 单测：默认 raise；实验 flag 才过 |
| **S2.3** | **handoff 到 film-spec（可选）** | `shortform export-spec`：package → 最小 film-spec + timeline 草稿 + receipt | 可 `dispatch` 接着走 visual |
| **S2.4** | **或不做：标 deprecated** | 若半年无真片：route-catalog + help 标 experimental，免维护税 | catalog 字段 |

**推荐默认：** S2.1+S2.2 必做；S2.3 仅当你要主用 B。

---

### Wave S3 · 成人 shortform 诚实档（P1）

| ID | Todo | 验收 |
|----|------|------|
| **S3.1** | plan 输出 `wardrobe_ambition` vs `wardrobe_honest_cap`（模型极限） | receipt schema |
| **S3.2** | 与 `scale_fallback` / promote 停手表对齐 | B 板审计清单闭合 |

---

### Wave S4 · 清扫 / peel（P2 · 顺手）

| ID | Todo |
|----|------|
| **S4.1** | 改 S0 时 peel `film_spec` 中 duration 默认与 sex 相关纯函数（已有 sex_floor 模式） |
| **S4.2** | bare subprocess 仅 final/ship 热路径 timeout（不冲刺 150 处） |
| **S4.3** | 旧 optimization plan header 指到本短版板，避免 agent 重做 A1 |

---

### Wave S5 · OPEN_OPS（不阻塞代码）

| ID | Todo | 验收 |
|----|------|------|
| **S5.1** | 5090 idle 时单 owner until-empty → `queue_empty` | takes↑ + receipt；遵守 multi-agent no-hog |
| **S5.2** | 一片真 shortform 走 S0 后 plan→bulk 无 `DURATION_MEDIA_SHORT_HARD`（或明确降 target） | 片根 canary JSON |

---

## 5. 建议执行序

```text
S0.1 默认 duration 5.2
 → S0.2 plan 最少镜数
 → S0.3 rebalance 可达媒体
 → S0.4 heat 抬 target 同步密度
 → S1.1 ship-native 字幕/BGM 诚实
 → S2.1+S2.2 shortform 旁路政策
 → S3 诚实档（可并行读）
 → S5 有 GPU 再烧
```

**默认 `go` 最小链：** S0.1 → S0.2 单测绿 → commit →（可选）S1.1。

---

## 6. 成功定义

| 标准 | 信号 |
|------|------|
| 新 shortform plan 的 planned 不系统性 > H3 可达 | S0 测 + 可选真片 canary |
| savani 类 5 分目标要么 ≥58 镜要么 target 下调有 receipt | S0.2 |
| ship plate 路径不误导「已有字幕 master」 | S1 |
| shortform CLI 与「冻结 lipsync」不矛盾 | S2.2 |
| 无重开 A1–A5 / 虚荣 peel | 纪律 |

---

## 7. 非目标

- 用 loop/freeze 把 5s 源硬撑到 10s 当「满目标」  
- 自动批 pilot / 静默改 `i2v_provider`  
- 删 shortform 旁路而不写决策树  
- 长片 longform 480–900 全面重做  
- 全自动 ASR 中文完美评分  

---

## 8. 落档与实现注意

- 确认后写入仓库：`docs/plans/2026-08-06-shortform-optimization-todoplan.md`  
- 行为变更：bump `plugin.json` + CHANGELOG（英文 commit）  
- hard-defaults 只加表行指针  
- 非琐碎收尾：`verifier`  

---

## 9. 请你拍板（1 个关键偏好即可）

**S0 镜数不足时默认策略（推荐 #1）：**

1. **fail-closed + 明确 next**（加镜 / 降 target）— 不静默改故事  
2. **auto 增镜**（拆 beat，可能改变节奏）  
3. **auto 降 target_duration** 对齐 `n×5.2`（改承诺时长）

S2.3 handoff 默认 **先不做**，只做 S2.1+S2.2，除非你明确要 shortform 包进主产线。
