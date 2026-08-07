# 副导演流程盘点 + 优化 Todo Plan（2026-08-06）

> **Slim board (structure/docs deadcode):** [2026-08-07-code-slim-consolidation-todoplan.md](2026-08-07-code-slim-consolidation-todoplan.md) — do not reopen package vanity / whole-file delete waves here.

**Status:** **SHIPPED 2.40.11**（A–C 代码+阶段卡 · D OPEN_OPS canary）· 2026-08-06  
**结论先行：** 你的片厂已经不是「缺规章、缺门禁」——**法条 IRON + 质量五门 + final 诚实契约大多已上墙且有测**。真正拖片的是三类事：**(1) 计划时长与 H3 实源仍系统性偏短**；(2) **5090 有用烧满率靠运维日，不靠再写代码**；(3) **交付语义在真片肌肉记忆还不够（plate≠master、门绿≠好看）**。本轮已把 A–C 工序机读化；D 无独占 GPU 诚实 OPEN_OPS。

| 项 | 现状 |
|----|------|
| 版本基线 | plugin **2.40.10** · 单一工程执行板已 closeout W0–W6 |
| 主产线 | `dispatch` 脊：agent → visual → voice → post → deliver |
| 旁路 | `aifilm shortform`（真人 A-roll 编排，**不进** dispatch） |
| 已 ship | A1–A5 final IRON · quality P0 五门 · GPU no-hog 机读 · CJK 字幕 · motion mean · BGM multi-chapter · 短版 S0–S4 代码板 |
| 真 OPEN | **C1 until-empty 真烧** · **时长 plan vs media 根因纪律** · **真片 promote/审片纪律** · 巨石 **bug-driven only** |

**与既有 plan 关系（勿重做）：**

| 板 | 角色 |
|----|------|
| `docs/plans/2026-08-06-next-optimization-todoplan.md` | 工程 ACTIVE 板（W0–W6 多已 ship；W2.2 DEFERRED_SAFE） |
| `docs/plans/2026-08-06-optimization-todoplan.md` | A1–A5 SHIPPED · residual pointer |
| `docs/plans/2026-08-06-shortform-optimization-todoplan.md` | CODE CLOSED · S5 OPEN_OPS |
| `docs/plans/2026-08-06-memory-optimization-inventory.md` | 类 A/B/C 反查 |
| **本 plan** | **副导演工序视角**：拍什么、卡在哪、人该干什么、下一迭代勾什么 |

---

## 1. 片厂类比（一眼看懂）

| 片厂角色 | 你产线对应 | 健康度 |
|----------|------------|--------|
| 剧本部 | story.receive → debrief → plan run → write-spec | 🟢 流程齐；⚠️ 时长菜单仍常大于灶上实菜 |
| 美术/造型 | locks · style_lock · face · wardrobe 不回穿 | 🟢 门禁硬；⚠️ 模型极限勿硬上靠 promote 纪律 |
| 摄影/动作 | still → I2v · H3 lane · mean 门 · anti-hijack | 🟢 武器矩阵清晰；⚠️ multi-seed 仍易只比 mean |
| 场务/GPU | h3 run-next max5 · capacity-plan · no-hog | 🟢 机读；🔴 until-empty 少真烧穿 |
| 录音/对白 | 原音主链 · Edge TTS · 零旁白 · 口白窗三角 | 🟢 契约在；⚠️ 真片仍要抽听可懂中文 |
| 剪辑/后期 | render_final · HF 字幕 · gate-auto · closeout | 🟢 假绿路径已堵代码；⚠️ 人读清单要成肌肉 |
| 审片/交付 | plate vs master · review-final 人签 | 🟡 字段诚实，**首过 master 率**仍靠真片习惯 |

---

## 2. 分阶段盘点（副导演 checklist）

### 2.1 Agent（故事与计划）— 最该动「时长诚实」

**已好：**

- 顺序钉死：receive → script-value-debrief → 用户确认 promise → plan → locks → write-spec  
- design-go / debrief 进 stage 快卡（W5）  
- duration_target / sex_floor fail-closed（A1）有测  
- 短版默认 `DEFAULT_DURATION_SEC≈5.2` 与 H3 对齐（S0 ship）

**仍痛：**

| 痛点 | 现象 | 为何伤片 |
|------|------|----------|
| **计划≥媒体系统性缺口** | savani 目标 300s / 媒体 ~212s；suse 目标与 media 双 hard | 纸面「够长」→ final 槽 stretch 炸或交付 DURATION hard |
| **热度抬 target 不加镜** | adult 抬 55–100s 不自动 ceil(target/5.2) 加 shot | 菜单加长、灶上份数不变 |
| **rebalance 加长 meat 不增 shot** | sex floor 纸面够、源仍 ~5s | 假办事时长风险（代码已禁静默 10s，流程仍会压计划） |
| **debrief 易被赶工跳过** | 纪律在卡上，人/agent 可 thrash 直进 media | 下游整集重做成本 |

**优化杠杆（工序，不全是代码）：**

1. **plan 锁死前强制看 `duration_density` / shot 下限**（ceil(target/5.2)）  
2. adult 抬 target → **同批加镜或砍 promise**，二选一写 receipt  
3. lock 前 30 秒：回显 must_have beats + 预计镜数 vs 目标秒数

---

### 2.2 Visual（定妆 still → I2V/H3）— 废片与抢构图

**已好：**

- 先验后生；毒镜禁 I2V；face-identity / continuity 九项 gate  
- anti-hijack 机读 + agent 快卡  
- motion mean register hard（2.40.8）  
- weapon-lane：I2V/FLF/R2V/T2V 有矩阵  
- Fill-Idle 挑战位 + PK 不自动 promote

**仍痛：**

| 痛点 | 说明 |
|------|------|
| **门绿≠好看** | anti-boring gate 在，体位/CU/L4 仍依赖计划设计，不靠事后刷门 |
| **multi-seed 习惯** | 人/agent 仍可能 shortlist 只比 mean/音量 |
| **restricted 镜 request.json** | material fidelity 闭环 ship，执行密度不一 |
| **衣着尺度** | 不回穿 + 全裸诱惑 + 模型极限阶梯 **码在**；promote 仍可能硬推崩帧 |

**优化杠杆：**

1. pilot 批片清单强制 3 项：构图主体 / 衣着 rank / 毒镜扫一眼  
2. shortlist 模板：anti-hijack 分 ≥ mean，并列才比 motion  
3. 尺度失败路径：**自动写 scale_fallback receipt** 再重出，禁 blind promote

---

### 2.3 Voice（对白与声线）— 主链清晰，验收靠耳朵

**已好：**

- 对白主链 = Grok/H3 原音；后期对嘴 v2.40 移除  
- 中文 Edge；禁 zh 挂 ja；语言 ping-pong 检测  
- 口白窗 tts≤cue≤slot；BGM rnb + 无 wav → procedural；长板 anti-fatigue 分章

**仍痛：**

| 痛点 | 说明 |
|------|------|
| **aac≠可懂中文** | ship-native 有 soft checklist；真片仍要抽听（savani 课） |
| **VO 与槽争** | 契约在；长 spoken 仍会撞窗 → 应砍词而非只拉 cue |
| **5-track 门红** | gate-auto 诚实红 → plate PARTIAL，人常想刷绿 |

**优化杠杆：**

1. ship 前 **每场抽 1 句** 人耳（中文可懂）  
2. cue 超槽 → 编剧剪台词模板（字数/秒）挂 voice 阶段  
3. 门红五轨：允许 plate ship，**禁**改 master 文案

---

### 2.4 Post / Final — 工程债多已还，纪律债未还清

**已好：**

- shim→main 假绿堵死；watchdog；heartbeat timeout receipt  
- plate vs master 字段；official-final-report  
- 字幕 CJK auto-fix + pixel check；deliver 1 屏抽检清单  

**仍痛：**

| 痛点 | 说明 |
|------|------|
| **总控台厚** | render_final ~3k orchestrator；**只挡路再 peel** |
| **人跳过 1 屏清单** | 文档在 stages/deliver，真片会话易口头「final 好了」 |
| **re-final 成本** | 改 final 须清 quality 缓存 + 叙事重绑（纪律在，易忘） |

**优化杠杆：**

1. 每集 final 后 **强制读 official-final-report 三字段** 再汇报用户  
2. closeout 红 → 固定 next_cmd 链，禁止手点循环  
3. 工程：仅当再动 VO/mix/字幕时加深 `final/*` 叶拆（W3.2）

---

### 2.5 Deliver / Ops — 最大 ROI 在「真烧 + 真看」

**已好：**

- gate-auto 机写；cinematic-gate 绑 export  
- GPU no-hog：until-empty 须 `--i-own-the-gpu`；默认 max 5  
- tunnel canary 诚实（OPEN_OPS / DEFERRED_SAFE）

**仍痛（OPEN）：**

| ID | 项 | 状态 |
|----|-----|------|
| **C1** | until-empty → `queue_empty` 真烧 | OPEN_OPS（人+独占 5090+RAM） |
| **C8** | Fill-Idle 真 execute + 人 promote | dry 多、capacity/variety 常卡 |
| **审片** | 完整观看 + 盲审不可模型代签 | 流程在，执行看人 |
| **双 checkout** | plugins vs 开发树 | 纪律在 CONTRIBUTING，仍易改错树 |

---

## 3. 健康 / 勿动 / 真该优化

### 3.1 健康处（副导演：守住，不「优化掉」）

- 成人 MAX / 毒镜 / 不回穿 / 零旁白 / 字幕硬烧 / h3_primary / anti-hijack  
- pilot 须人批；gate-auto 后人只 pilot / PK / review-final  
- final ≠ final_complete；plate 可 PARTIAL  
- 多 agent 禁 hog；busy 零 submit  

### 3.2 明确非目标

- 再写一套 IRON 散文 / 软化成人与毒镜  
- 全仓 LOC 压到 1500 / 全量 FilmError 迁移  
- 复活后期 lipsync 当主轨  
- 无 GPU 时假报 queue_empty  
- 把 plate 刷成假 master  

### 3.3 真优化轴（按 ROI）

```text
P0 工序   时长诚实（镜数 vs 目标秒）+ 交付读回执肌肉
P0 运维   独占日 until-empty 真烧 或 诚实 OPEN_OPS
P1 工艺   pilot 三看 · shortlist anti-hijack · 尺度 fallback promote
P1 工程   触达巨石才 peel；热路径 except 触达再补
P2 卫生   plan 不重开已 ship；memory 只留指针；token 控 /compact
```

---

## 4. Todo Plan（可勾选 · 副导演序）

> 工程细节仍以 `2026-08-06-next-optimization-todoplan.md` 为代码板；**本表是出片工序执行序**。  
> 圣旨 `go` = 按当前波 **最小验证推进**（有 GPU 走 D；无 GPU 走 A→B→E）。

### Wave A · 计划台「菜单=灶上菜」（P0 craft · 最高杠杆）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **A1** | **目标秒 → 镜数下限** | `finalize_duration_density` + duration_target shot hard | ✅ 2.40.11 · `test_ad_process_optimization` |
| **A2** | **成人抬 target 必须加镜或砍 promise** | `receipts/adult-target-shot-lift.json` + density codes | ✅ plan write path |
| **A3** | **debrief 30 秒门** | pilot-go debrief_gate；strict env / design-go 红则拦 | ✅ pilot_pack schema v3 |
| **A4** | **一集一「时长诚实」canary** | closeout `duration_honesty` + receipt | ✅ closeout soft step |

**不做：** 静默把单镜 duration 拉到 10s。

---

### Wave B · 交付肌肉（P0 process · 零/低代码）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **B1** | **final 后强制 1 屏读报告** | deliver.md Agent 回报 4 步 + closeout readback | ✅ stages |
| **B2** | **门红 = plate ship 话术** | deliver #13 + post plate 话术 | ✅ stages |
| **B3** | **抽听中文 1 句/场** | deliver #12 + voice 抽听 | ✅ stages |
| **B4** | **改 final 清缓存 checklist** | post.md 清缓存 | ✅ stages |

---

### Wave C · 样片与选片（P1 craft）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **C1** | **pilot 批片三看** | `pilot-go.json` → `three_look` | ✅ |
| **C2** | **shortlist 禁纯 mean** | select-shortlist v2 `mean_only_forbidden` + codes | ✅ |
| **C3** | **尺度 fail → fallback 再 promote** | register-clip promote_ban gate | ✅ |
| **C4** | **肉戏抗无聊前置** | agent 卡 + 既有 variety-precheck | ✅ 纪律指针 |

---

### Wave D · 机房日（P0 ops · 等人+GPU）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **D1** | 隧道 health | canary probe 18188/8188 | ✅ `artifacts/2026-08-06-ad-wave-d-ops-canary.json`（本机 18188 down） |
| **D2** | **独占 until-empty** | 未执行 | **OPEN_OPS**（无用户独占） |
| **D3** | 双片纪律 | hard-defaults 既有 | 纪律在 |
| **D4** | Fill-Idle 一轮真 promote | 未执行 | **OPEN_OPS** |

**无独占日：** 整波标 OPEN_OPS，**不阻塞** Wave A/B/C 完成定义。 ✅

---

### Wave E · 工程挡路才拆（P1 eng · 与 next-optimization W3 对齐）

| 序 | 模块 | 触发 | 动作 |
|----|------|------|------|
| **E1** | `film_spec` / duration | 再动 A1 时长 | 纯函数 + 测；禁行为混搬迁 |
| **E2** | `render_final` | 再动 VO/mix/字幕 | 加深 `final/*` |
| **E3** | `export_composition` | 双烧/HF bug | harness 测优先 |
| **E4** | `edit_policy_heat` | **仅 heat bug** | pack peel，禁预防全拆 |
| **E5** | 热路径 except | 触达 silent pass | note_partial 模式（W4 已开先例） |

---

### Wave F · 协作卫生（P2 · 便宜复利）

| ID | Todo | 验收 |
|----|------|------|
| **F1** | 新会话只认本 plan + next-optimization + hard-defaults | 不重做 A1–A5 / quality P0 |
| **F2** | `git rev-parse` 开场自检 checkout | 不改错树 |
| **F3** | 长片 `/new`；中途 `/compact` | token 不顶满 |
| **F4** | memory 只增指针卡；长文 archive | active 不膨胀 |

---

## 5. 建议执行日历（副导演排期）

```text
无 GPU 的工程/流程日（推荐默认 go）：
  A1–A3（时长诚实最小码+纪律）→ B1–B2（交付话术）→ C1–C2 模板 → E 仅挡路

有独占 5090 的运维日：
  D1 → D2 → D4 → 回写 memory 短卡

内容/导演日：
  C3–C4 + 最多 1 条产品深化（勿与 E 大 peel 同 PR）

迭代完成定义（诚实）：
  ✓ A 或 B 至少一项可测绿 / 真片 canary
  ✓ D 有 queue_empty 或 OPEN_OPS 记录
  ✗ 禁止「只更新了 plan 文档」当 DONE
```

---

## 6. Top-5 ROI（若只能做五件）

1. **A1 目标秒→镜数下限** — 直接砍 savani/suse 类时长 hard 惊喜  
2. **B1 final 后读 official-final-report** — 零代码，防假绿叙事  
3. **D2 独占 until-empty 真烧** — 吞吐问题代码解不了  
4. **C2 shortlist anti-hijack 强制列** — 降废片与「门绿难看」  
5. **A2 成人抬 target 必须加镜** — 纸面肉戏够、媒体不够的根  

---

## 7. 风险

| 风险 | 缓解 |
|------|------|
| 把工序优化做成再贴规章 | 每项必须有 receipt / 命令 / canary 字段 |
| 无 GPU 假装运维完成 | OPEN_OPS 合法收工 |
| 时长硬门过严卡创作 | 先 soft advisory + next_cmd；hard 仅 bulk-preflight 已对齐路径 |
| 与 next-optimization 双板打架 | 代码勾选认 next 板；工序勾选认本 plan；交叉引用 ID |

---

## 8. 请你拍板

1. **主攻轴（推荐 A）：**  
   - **A** 计划时长诚实（Wave A）+ 交付肌肉（Wave B）— 无 GPU 也能推进  
   - **B** 运维独占日（Wave D）— 需你点名 5090  
   - **C** 样片工艺模板（Wave C）— 少代码  
2. **本 plan 是否落档到 repo：**  
   - 建议：`docs/plans/2026-08-06-ad-process-optimization-todoplan.md`  
   - 并在 next-optimization 顶部加一行指针  
3. **A1 时长镜数：要 fail-closed 硬门，还是先 soft + next_cmd？**（推荐：bulk-preflight **hard**，plan run 先 **soft 强建议**）

确认主攻轴后即可按圣旨 `go` 最小推进；默认假设 **轴 A + A1 soft→preflight hard**。
