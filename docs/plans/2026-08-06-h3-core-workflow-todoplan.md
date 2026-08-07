# 5090 H3 核心产线 · 重头打通优化 Todo Plan

**Status:** **DOC+OPS 闭环 · 2026-08-07**（真烧 OPEN_OPS：5090 他会话占用）  
**进度：** H0–H1 · H6 **SHIPPED** · H2–H5 纪律卡在 · **H3 真烧** 见 canary  
**Canary：** [artifacts/2026-08-07-h3-core-workflow-canary.json](../../artifacts/2026-08-07-h3-core-workflow-canary.json) · 片 `0806/abroad-slut-manhua-h3`  
**日期：** 2026-08-06 → 推进 2026-08-07  
**范围：** 工作流 / 工序 / 运维（不是再写一套 IRON 法条）  
**Repo：** `/Users/dex/.grok/plugins/ai-film-grok` · plugin **2.40.39+**  
**阶段卡：** [stages/h3-core-day.md](../../skills/ai-film-grok/references/stages/h3-core-day.md)  
**短记忆：** [memory/2026-08-06-h3-core-workflow.md](../../skills/ai-film-grok/memory/2026-08-06-h3-core-workflow.md)  

### 自检 + canary 快照（2026-08-07）

| 项 | 结果 |
|----|------|
| doctor core | ✅ |
| comfy tunnel 18188 | ✅ system_stats · RTX 5090 |
| weapon primary | ✅ still=Qwen · motion=H3×4 · audio=Edge+rnb · `h3_primary` |
| capacity-plan（abroad-slut） | ✅ 33 pending · ETA ~4.4h · next `ep01_sh06` i2v |
| comfy queue | 🔴 **running=1** MiniMaxH3 I2V（他会话）→ **busy 零 submit** |
| free-memory | ⚠️ 忙时勿调用；空闲后才 free |
| pilot 路径 | 🟡 pack 仍有 three_look/PILOT_MEDIA 等 blocker；bulk 前须人 GO |
| run-next --execute | **跳过**（no-hog） |

**结论先行：** 代码层「H3 全镜主生成」已经默认（`AIFILM_I2V_PROFILE=h3_primary`）。下一轮不是再发明武器，而是把 **日课打成一条肌肉记忆金路径**：Still 喂料（Qwen/Grok 辅）→ 5090 H3 烧片 → 人审 PK → gate-auto → plate/master 诚实交付。其它工具只当辅线，禁止回漂成「Grok bulk 主轨」。

---

## 0. 一句话定位

| 角色 | 武器 | 类比 |
|------|------|------|
| **核心发电厂** | 本机 5090 MiniMax **H3**（I2V / FLF / R2V / T2V） | 重工车间：所有「动起来」的镜头默认在这烧 |
| **静帧辅线** | **Qwen** 本机 T2I/Edit · Grok Imagine 定妆 · FRW i2i still-challenge | 修零件台：只修 first frame，不占 H3 长时间 |
| **云逃生** | Grok Video 1.5 ·（opt-in）FRW LTX 安全对白 | 备用机：仅技术失败签名切换 / 用户点名 |
| **声音辅线** | H3 原声 prefer_native · Edge 中文字幕钟/ADR · BGM rnb | 录音棚：禁原声+TTS 双重念白 |
| **后期辅线** | HyperFrames 字幕/母版 · gate-auto · Real-ESRGAN（选后升画质） | 剪辑室：运镜不在后期做 |

**已 ship 勿重做：** `h3_primary` profile、media-queue 云硬拦、`h3 run-next --max 5`、until-empty 须 `--i-own-the-gpu`、mode 自动选型、Fill-Idle 机读、成人/毒镜/不回穿 IRON。  
**与旧板关系：** 工程板 → `docs/plans/2026-08-06-next-optimization-todoplan.md`；副导演工序 → `docs/plans/2026-08-06-ad-process-optimization-todoplan.md`。**本 plan 是「H3 日课重打通」专用执行序**，不取代上述两板的工程债项。

---

## 1. 现状诊断（为何要「重头打通」）

### 1.1 已经好的（守住）

- 默认 profile = **`h3_primary`** → provider `comfy-h3`；dispatch 优先 `h3-run-next`
- 模式矩阵：有 last→**FLF** · 无 last→**I2V** · 高动/大嘴→**R2V** · 无脸 env→**T2V**
- 多 agent 禁 hog；busy 零 submit；进度认 **takes 文件数**
- 先验后生 / 毒镜禁 I2V / anti-hijack / mean 门 / native XOR TTS / plate≠master  
- **镜头分型（2026-08-07 Wave 0–6）**：`aifilm shot-lane` · 对白/毒/满幅/variety/续镜安全 · [shot-generation-lane plan](2026-08-07-shot-generation-lane-todoplan.md) · canary `artifacts/2026-08-07-shot-lane-canary.json`

### 1.2 真痛点（拖片根因）

| # | 痛点 | 用户可见 | 杠杆 |
|---|------|----------|------|
| **T1** | 文档/习惯仍混「Grok 铺底 + H3 挑战」与「全片 H3」 | agent 误走 media-queue / hybrid | **金路径 SOP 钉死 h3_primary** |
| **T2** | 计划秒数/镜数与 H3 实源 ~5.2s 系统性错位 | stretch 炸 / 片长假够 | 菜单=灶上菜（AD A 已有码，**真片纪律**） |
| **T3** | Still 弱仍烧 H3（crop-master / 毒 / 构图抢） | 废算力 + 难看 take | **CODE CLOSED 2.40.60** composition_fill+poison+shot-lane · still-challenge 先修 · 真烧纪律仍靠日课 |
| **T4** | 5090 有用率靠「有没有人独占」 | 队列堆、多会话互抢 | 独占日 until-empty / 平日 max5 两档 |
| **T5** | 门绿≠好看 · plate 当 master | 交付翻车 | gate-auto + 人审三看 + 报告三字段 |
| **T6** | 原声可懂中文抽听缺肌肉 | aac 有声听不懂 | ship 前每场 1 句耳朵 |
| **T7** | Fill-Idle / P2 挑战语义在 h3_primary 下易混淆 | 烧错优先级 | 重写「h3_primary 下 Fill-Idle = 弱 take 补烧」 |

### 1.3 明确非目标

- 再开绿地 IRON / 软化成人 MAX / 复活后期 lipsync  
- 默认改回 `hybrid_h3` 或 `grok_primary`  
- 无独占 GPU 时假报 `queue_empty`  
- 把 plate 刷成假 master  
- 虚荣拆巨石（仅挡路才 peel）  
- Seedance / Wan 回主轨  

---

## 2. 目标态：H3 核心日课金路径（SOP）

```text
[Agent] story.receive → script-value-debrief → 用户确认 promise
      → plan run（镜数 ≥ ceil(target/5.2)）→ write-spec（_i2v_profile=h3_primary）
      → design-go / locks / state-index

[Visual 静帧辅] Qwen/Grok 产 still → 身份/毒镜/几何/anti-hijack 先验
      → 弱 still：still-challenge（FRW i2i）或 Qwen edit → 人 promote
      → pilot pack 三看（构图/衣着/毒镜）→ 用户 GO

[Motion 核心] capacity-plan → h3 run-next --execute --max 5（平日）
      或 用户点名独占：cycle --until-empty --execute --i-own-the-gpu
      mode 自动：I2V | FLF | R2V | T2V；换模 free-memory
      续镜：endframe handoff → 下镜 I2V/FLF
      弱 mean / 毒 / 回穿：禁 promote → 修 still 或 re-run

[选片] ship-prep（多 take defer promote）→ 人 shortlist/PK（禁只比 mean）
      → register preferred

[声+后] native XOR TTS · Edge 字幕钟 · rnb BGM
      → gate-auto → final（门红=plate PARTIAL）→ closeout 读报告
      → 人 review-final → export-desktop（须 cinematic 绿）
```

### 2.1 辅助武器何时上场（铁表）

| 场景 | 用 | 不用 |
|------|----|------|
| 定妆 / soft hero still | Grok `image_edit(cast)` 或 Qwen T2I | 直接 H3 T2V 锁脸 |
| 卸装 / bare 状态照 | **Qwen Edit** + undress-anchor | full cast master 当 peak I2V |
| 弱 still / 构图 hijack | **still-challenge** 或 Qwen 修 → 再 H3 | 带毒 still 硬烧 |
| 全片动作 | **H3 only** | media-queue Grok bulk |
| 云 I2V | 仅技术失败 + 签名 escape | 质量拒片静默切云 |
| 安全对白有声云 | 仅 `ltx23_adult` opt-in | bare/肉戏 |
| 字幕/母版 | HF master 或 ship 硬烧 | 后期对嘴 |
| 升画质 | selects 后 Real-ESRGAN（opt-in） | bulk 前抢 5090 超分 |

### 2.2 每日两档 GPU 纪律

| 档 | 条件 | 命令 | 禁 |
|----|------|------|-----|
| **平日多会话** | 未点名独占 | `h3 run-next --execute --max 5` | until-empty / 自动 restart supervisor |
| **独占夜班** | 用户圣旨「独占/排水」 | `h3 cycle --until-empty --execute --i-own-the-gpu` | 同时开第二 film drain |
| **别人要用** | 用户喊占满 | 立刻杀 drain + neuter 外源 supervisor | `pgrep -f` 宽杀 |

---

## 3. 成功定义（一迭代结束可验收）

| 标准 | 信号 |
|------|------|
| 新片 `write-spec` 后 `_i2v_profile=h3_primary` 且 dispatch next 含 `h3-run-next` | dispatch.json / 人眼 |
| bulk 路径不出现默认 Grok media-queue（无 escape） | queue 无 restricted 云 job |
| 计划镜数 ≥ ceil(target/5.2)；media 总长与 target 偏差诚实记 receipt | duration-target / duration_honesty |
| 平日 max5 批处理可连续；独占日至少 1 次 queue_empty 或 OPEN_OPS 诚实 | canary JSON |
| pilot 三看 + shortlist 非纯 mean | pilot-go / select-shortlist.json |
| final 回报含 `delivery_class` / plate≠master / 抽听记录 | official-final-report |
| 文档矩阵文案：h3_primary 下 Grok 仅 escape，Fill-Idle=弱 take 补烧 | weapon-lane 修订勾选 |

---

## 4. Todo 波次（可勾选）

### Wave H0 · 账实钉死（半天 · 开工先做）

> 类比：先确认「主发电厂是哪台」，别在两套说明书之间来回切。

| ID | Todo | 做法 | 验收 | 估时 |
|----|------|------|------|------|
| **H0.1** | **本 plan 落档为 H3 工作流执行板** | 写入 `docs/plans/2026-08-06-h3-core-workflow-todoplan.md`；旧 h3-primary / fill-idle 文首指针本档 | 文件在 + 旧板 header 指针 | 30m |
| **H0.2** | **环境自检一页** | `aifilm doctor` + tunnel 18188→8188 + `AIFILM_I2V_PROFILE=h3_primary` + capacity | doctor 绿 / 隧道 up / profile 打印 | 15m |
| **H0.3** | **武器主表对账** | `aifilm weapon inventory --tier primary`：motion=H3 · still=Qwen · VO=Edge | 与 hard-defaults 一致 | 15m |
| **H0.4** | **禁重做清单** | 本文 §1.3 + 已 ship 列表贴 memory 短卡 10 行 | agent 不重开 h3_primary 实现 | 15m |

---

### Wave H1 · 金路径 SOP（P0 工序 · 最高 ROI）

| ID | Todo | 做法 | 验收 | 估时 |
|----|------|------|------|------|
| **H1.1** | **日课 12 步清单（人/agent）** | 浓缩 §2 为 `references/stages/visual.md` 或新 `stages/h3-core-day.md` 一屏；dispatch context 可挂 | 新片 agent 只跑清单不跑旁支 | 1–2h |
| **H1.2** | **澄清 Fill-Idle 在 h3_primary 语义** | 矩阵文案改写：P0=缺 clip 主生成；P1=gate 失败补烧；P2=仅 hybrid 下挑战 Grok。**h3_primary 无「Grok 铺底」** | weapon-lane-matrix §Fill-Idle 修订 + 1 测或 receipt 文案 | 2h |
| **H1.3** | **时长菜单=灶上菜（纪律）** | plan 锁前强制 `duration_density` / shot 下限；adult 抬 target 必须加镜或砍 promise | 新片 plan 无 DURATION_SHOT_COUNT_SHORT_HARD | 沿用 AD A；真片 1 集 canary |
| **H1.4** | **pilot GO 硬三看** | 构图主体 / 衣着 rank / 毒镜扫；`pilot pack` 已有 three_look → **批 bulk 前必须读屏** | pilot-go.json + 用户短语 | 0 码 / 肌肉 |
| **H1.5** | **弱 still 先修再烧** | mean 低 / hijack / 毒：优先 still-challenge 或 Qwen，**禁止**立刻 re-I2V 同一脏 still | 弱镜有 still_challenge 或 scale_fallback 收据 | 0–1h 文档 |

---

### Wave H2 · 静帧辅线「喂满 H3」（P0 质量）

| ID | Todo | 做法 | 验收 | 估时 |
|----|------|------|------|------|
| **H2.1** | **一镜一 still 唯一 + 禁 crop-master 静默铺满** | 已有 uniqueness + crop_master_still 门；真片抽检 ≥1 集 | 无全片 crop-master ≥55% hard 撞 | 纪律 |
| **H2.2** | **状态照索引先于 meat bulk** | state-index undress/bare hard；peak 禁 full cast master | bulk-preflight 绿才 run-next | 纪律 |
| **H2.3** | **end still / FLF 产能** | continue 链与卸装终点：优先产 `_end.png` 升 FLF，少单 I2V 盲烧 | h3 list 有 last 的镜 mode=flf 占比↑ | 1 集 canary |
| **H2.4** | **material fidelity request.json** | 每镜 generation_request 写 text+ref sha；queue/h3 回读 | receipts/prompts/*.request.json 齐 | 抽样 10 镜 |
| **H2.5** | **Qwen vs Grok still 分工卡** | soft 定妆可 Grok；restricted/卸装默认 Qwen 本机（不抢 H3 视频队列时可并行注意 VRAM） | 分工进 stage 卡 5 行 | 1h |

---

### Wave H3 · 5090 吞吐与调度（P0 运维）

| ID | Todo | 做法 | 验收 | 估时 |
|----|------|------|------|------|
| **H3.1** | **平日默认 max5 批循环** | agent 只建议 `run-next --max 5`；禁止默认 until-empty | dispatch next_cmd 符合 | 已码；回归 1 次 |
| **H3.2** | **独占排水日** | 用户点名后：`capacity-plan` → `cycle --until-empty --execute --i-own-the-gpu --free-first` | `stop_reason=queue_empty` 或 OPEN_OPS 诚实 canary | 半日–1 夜 |
| **H3.3** | **双片/多 agent 零抢** | busy 零 submit；禁 neuter 外片除非用户；进度认 takes | 无误杀 / 无双 drain | 纪律 + memory 已有 |
| **H3.4** | **隧道自愈** | LaunchAgent / `tunnel-ensure`；18188→8188 非 8189 | doctor + 真 POST system_stats | 15m |
| **H3.5** | **换模 free-memory** | I2V↔R2V↔T2V 前 `comfy free-memory --confirm`（run-next 已可） | OOM 率↓ | 纪律 |
| **H3.6** | **capacity-plan 当菜单** | 每集 bulk 前贴 ETA（按 mode 队列）给人决策「今晚烧几集」 | 会话有 ETA 一行 | 0 码 |

---

### Wave H4 · 动作质量闭环（P1 · 好看）

| ID | Todo | 做法 | 验收 | 估时 |
|----|------|------|------|------|
| **H4.1** | **motion spine 非空** | dramatic_function + visible_change + 对白台词注入；空核拒跑 | 无 MOTION_CORE 漏网 | 已码；抽检 |
| **H4.2** | **mean 门 + 肉戏 ≥20** | gate-auto / i2v-final-gate；弱镜 re-I2V 或 R2V alt，禁装静帧联播 | meat 镜 mean 分布诚实 | 纪律 |
| **H4.3** | **variety 设计期** | bulk 前 variety-precheck：体位≥4 / 脸 CU≥2 / L4≥2 / 邻镜 camera 差 | 纸面改完再烧 | 1 集 |
| **H4.4** | **PK 禁纯 mean** | shortlist anti-hijack 优先；人 30s：同人？体位？事件？嘴？ | select-shortlist mean_only_forbidden | 已码 |
| **H4.5** | **高动够了停盲 R2V** | dual 粘连 / 够动跳 R2V（fill-idle 已有） | 不浪费 R2V 槽 | 观察 |
| **H4.6** | **scale fallback promote** | 插不进→全裸诱惑→模型极限；promote_ban 禁 blind | scale-fallback.json | 纪律 |

---

### Wave H5 · 声音 + 后期诚实（P1 交付）

| ID | Todo | 做法 | 验收 | 估时 |
|----|------|------|------|------|
| **H5.1** | **原声 XOR TTS** | dialogue_audio_lane 互斥；禁双重念白 | 无 DUPLICATE_DIALOGUE | 已码 |
| **H5.2** | **每场抽听 1 句中文** | ship 前耳朵；aac≠可懂 | deliver 清单勾 | 0 码 |
| **H5.3** | **H3 短源槽诚实** | 单镜 ~5.2；禁 validate 空拉 10s；sex floor 加镜不 stretch | 无 stretch 炸 | 已码+纪律 |
| **H5.4** | **gate-auto → plate/master** | 门红 = OFFICIAL_FINAL_PLATE；绿才冲 master | official-final-report | 纪律 |
| **H5.5** | **混音防假死** | 优先 FORCE_BROADBAND_DUCK；禁默认死等 acrossover | mixed.wav 有时限 | 已教训 |
| **H5.6** | **字幕像素抽帧** | ship 硬烧中文；抽帧可见 | caption-pixel-check | 纪律 |
| **H5.7** | **选后升画质（可选）** | Real-ESRGAN 仅 preferred；不抢 bulk H3 | 默认 off 文档一致 | P2 |

---

### Wave H6 · 工程小补（仅挡路 · P2）

| ID | Todo | 做法 | 验收 | 估时 |
|----|------|------|------|------|
| **H6.1** | **矩阵/SKILL 文案去 hybrid 惯性** | 扫「Grok 铺 soft baseline」在 h3_primary 段的误导句 | PR + 指针 | 1–2h |
| **H6.2** | **dispatch compact 一行武器** | 已有 weapon_inventory_line；确认 h3_primary 时不推 media-queue 为主 next | 1 次 mock film | 30m |
| **H6.3** | **巨石 peel** | heat/final/export **仅**再出事故时 bug-driven | 有测的叶函数 | 按需 |
| **H6.4** | **双 checkout 自检** | 改前 `git rev-parse --show-toplevel` | 不改错树 | 纪律 |

---

## 5. 推荐执行序（你说 `go` 时的默认链）

```text
H0（自检+落档）
 → H1.1–H1.2（SOP + 矩阵语义，半日可见）
 → H3.1 + H3.4（平日批处理 + 隧道）
 → 下一集真片按 H1.3–H1.5 + H2 跑满
 → 用户点名独占日：H3.2 排水 canary
 → H4–H5 在真片上勾肌肉（不全写新码）
 → H6 仅文档/误导句
```

**圣旨短令：**

- `go` / `从 p0 推进` = 按上序 **最小验证推进** 当前未勾第一项  
- `独占排水` = H3.2（须确认无其它 agent 抢卡）  
- `只改文档` = H0.1 + H1.1–H1.2 + H6.1  

---

## 6. 单集「重头打通」检查清单（复制即用）

```bash
export AIFILM_I2V_PROFILE=h3_primary
AIFILM="$HOME/.grok/plugins/ai-film-grok/skills/ai-film-grok/scripts/aifilm"
ROOT="<film>"

"$AIFILM" doctor
"$AIFILM" tunnel-ensure   # 或依赖 auto
"$AIFILM" weapon inventory --tier primary
"$AIFILM" dispatch --root "$ROOT" --full   # 确认 next=h3-run-next 类

# 计划诚实
# plan run / write-spec 后：镜数 ≥ ceil(target/5.2)

# still 先验 → pilot pack → 用户 GO
"$AIFILM" pilot pack --root "$ROOT"
"$AIFILM" bulk-preflight --root "$ROOT"

# 核心烧片（平日）
"$AIFILM" h3 capacity-plan --root "$ROOT"
"$AIFILM" h3 run-next --root "$ROOT" --execute --max 5
# 独占夜班（用户点名）：
# "$AIFILM" h3 cycle --root "$ROOT" --until-empty --execute --i-own-the-gpu --free-first

"$AIFILM" ship-prep --root "$ROOT"    # 多 take 人 promote
"$AIFILM" gate-auto --root "$ROOT"
"$AIFILM" final --root "$ROOT" --post-engine hyperframes --music-mood rnb --tts-backend edge
"$AIFILM" closeout run --root "$ROOT" # 读 official-final-report
# 人：review-final · 抽听 · export-desktop
```

---

## 7. 风险与假设

| 假设 | 说明 |
|------|------|
| 本机可达 5090 Comfy（隧道） | 否则只能 OPEN_OPS / 降级 grok_primary |
| 用户接受「时间换无限」 | H3 慢但本地无限；不为赶工默认切云 bulk |
| 成人 max 片 | 继续 H3 hard；不静默 LTX 全片 |
| 工程债不阻塞工序 | final 巨石不挡日课；挡路再 peel |

**信心：** 对「代码已默认 h3_primary」**高（~95%）**；对「真片纪律是主杠杆」**高**；对具体下一集 ETA **依赖 capacity-plan 实跑**（未代跑）。

---

## 8. 交付物（本 plan 批准后）

1. `docs/plans/2026-08-06-h3-core-workflow-todoplan.md`（本内容入库）  
2. 可选：`references/stages/h3-core-day.md` 一屏日课  
3. 可选：weapon-lane-matrix Fill-Idle 语义补丁  
4. 真片 1 集 canary 收据路径 + 三行摘要  
5. memory 短卡指针（用户要求「写进记忆」时再落）

---

## 9. 请你拍板的一点（默认已选）

若无额外指示，执行默认：

- **Profile 固定 `h3_primary`**（不默认 hybrid）  
- **平日 max5**；独占排水只听你圣旨  
- **先 H0+H1 文档/SOP**，再真片 canary，再独占夜班  

若你要「立刻真片跑通一集」优先于改文档，说 `go 真片` 即可跳过 H0 文档入库、直扑 H0.2 自检 + 指定 film root。
