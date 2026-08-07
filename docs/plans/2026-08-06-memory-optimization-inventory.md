# Plugin 优化点全表（从 memory 反查 · 2026-08-06）

> **Slim board (structure/docs deadcode):** [2026-08-07-code-slim-consolidation-todoplan.md](2026-08-07-code-slim-consolidation-todoplan.md) — do not reopen package vanity / whole-file delete waves here.

**范围：** 主仓 `ai-film-grok` plugin（`~/.grok/plugins/ai-film-grok`）；记忆 active **~39**（2026-08-06 归档 ~47 → `memory/archive/`）+ session 索引 + 既有 plan。plugin **2.40.12**。  
**读法：** 记忆里的「优化」分三类，**不要混成同一待办清单**：

| 类 | 含义 | 该怎么用 |
|----|------|----------|
| **A 法条 IRON** | 片例翻车沉淀的「以后别再犯」 | 遵守 + 测/门禁已在则勿重写散文 |
| **B 已 ship 工程** | 代码/CLI 已落地的优化 | 当基础，禁绿野重开 |
| **C 仍 OPEN / PARTIAL** | 记忆或 canary 写明未闭合 | **真迭代队列** |

**单一执行板：** [CTO](2026-08-06-cto-optimization-todoplan.md)  
**铁律内化子板（I0–I5）：** [2026-08-07-iron-internalization-todoplan.md](2026-08-07-iron-internalization-todoplan.md) · **I0 账实 2026-08-07**  
**养分对账：** [2026-08-06-nutrient-matrix.md](2026-08-06-nutrient-matrix.md)（L3/L4/L5 · I0 刷新）  
**历史出片板（A1–A5 SHIPPED）：** [2026-08-06-optimization-todoplan.md](2026-08-06-optimization-todoplan.md)  
**结构残余：** [2026-08-05-residual-monolith-w4-todo.md](2026-08-05-residual-monolith-w4-todo.md) · [monolith-relief](2026-08-06-monolith-relief-todoplan.md)  
**反脆弱：** [archive/2026-08-05-antifragility-todoplan.md](archive/2026-08-05-antifragility-todoplan.md)（主项多已 ship）

---

## 0. 结论（先看这）

1. **记忆里 70%+ 是「产品铁律 + 已入库门禁」**（成人 MAX、毒镜、不回穿、h3_primary、字幕硬烧、gate-auto…），不是「还没写的功能」。  
2. **真还没闭合的优化** 集中在：**假绿路径（variety 像素 / plate-boring / anti-hijack 全入口）**、**人证 harden（毒镜 attestation / speaker hard）**、**运维 5090 诚实 OPEN_OPS**、**巨石挡路 peel**。  
3. **禁止**把 A 类当「可以优化掉的限制」；优化 = 更少假绿、更少废片、更高有用 GPU%、更易维护，不是软化 IRON。  
4. **出 todo 用五问卡**（A/B/C · L 阶 · 挂载层 · 证据 · 人判）→ [MEMORY_GOVERNANCE](../MEMORY_GOVERNANCE.md) · [iron plan](2026-08-07-iron-internalization-todoplan.md)。

---

## 1. 类 C · 仍 OPEN / PARTIAL（优先队列）

| ID | 优化点 | 记忆/证据 | 状态 | 下一步 |
|----|--------|-----------|------|--------|
| **C1** | until-empty 真烧到 `queue_empty` | `2026-08-06-c1-*` · AF7 | **SHIPPED 2026-08-06** suse-ep01 canary | 独占 + `--i-own-the-gpu` + variety 绿 · takes 91→103 |
| **C2** | free-first 不杀 foreign + 禁默认 hog | multi-agent-gpu-no-hog | **机读 ship 2.39.98**；真片仍纪律 | exclusive flag + 回执 |
| **C3** | 正牌 final plate vs master 在交付文案 | `2026-08-06-suse-ep01-official-final-iron` | **ship 2.40.12** | 新片强制看 `official-final-report.json` + `test_suse_final_iron.py` 回归 |
| **C4** | rnb 仅 license 无 wav → procedural 诚实 | 同上 · A4 | ship | 有 wav 再换库 |
| **C5** | 模型极限勿硬上 / soft-max 档 | `2026-08-06-wardrobe-no-redress-fullnude-fallback` · scale_fallback | 码+receipt ship | promote 路径再压一轮真片 |
| **C6** | 构图防抢走 multi-seed | `2026-08-05-composition-anti-hijack` | gate 在 | shortlist/pk **禁只比 mean** 纪律 |
| **C7** | Material fidelity 闭环纪律 | `2026-08-05-material-fidelity-loop` | M0–M6 ship | 每 restricted 镜 request.json |
| **C8** | Fill-Idle 真烧 + 人 promote | `2026-08-04-h3-fill-idle` · session-wrap | **OPEN_OPS + evidence** | 绿片 + idle 5090 |
| **C15** | 时长目标 vs H3 镜数 | savani · Q4.1 | **ship 2.39.81** | bulk `duration_target` |
| **C16** | h3 ship-native plate | savani · Q5.1 | **ship 2.39.81** | 叠 hardburn 仍待 final |
| **C17** | crop-master still 告警 | savani · Q1.4 | **ship 2.39.82** | 真片再压 |
| **C18** | 原声 volumedetect sample | savani · Q5.2 | **ship 2.39.82** soft | ASR 可选延后 |
| **C9** | render_final / heat / film_spec 巨石 | residual-monolith plan | 包边界 ship · **orchestrator 仍厚** | **bug 驱动** peel only |
| **C10** | 热路径 bare subprocess | antifragility AF1 | 主热路径有 timeout；Popen 长跑保留 | 触达再补，勿全仓冲刺 |
| **C11** | Job-graph checkpoint 超 final | antifragility deferred | 延后 | takes 文件 + stale reclaim 已部分抗重烧 |
| **C12** | Provider 质量拒 vs 429 签名再审计 | antifragility deferred | 延后 | 另开会话 |
| **C13** | Process slim P6 | process-slim-phase2 | 未开 | 低优先文档税 |
| **C14** | 吞吐量计数收据（D0 metrics） | strategy plan | 未做 | optional `throughput-counters.json` |

---

## 2. 类 B · 已 ship 的工程优化（勿当绿野）

| 主题 | 记忆指针 | 落地形态 |
|------|----------|----------|
| h3_primary + capacity-plan + until-empty | `2026-08-05-h3-primary-capacity` | CLI + 测 |
| gate-auto 机读过闸 | `2026-08-04-gate-auto` | 单入口 machine lane |
| post caption_path / pixel 硬烧 | `2026-08-05-post-caption-path-pixel` · huangdao | post_route + caption-pixel |
| Mix partial / post-doctor / closeout 串 | post-p1 · AF3 | closeout steps |
| Material fidelity M0–M6 | material-fidelity-loop | still_source + generation_request |
| Fill-Idle list/next/pk/cycle | h3-fill-idle-challenge | 2.37–2.38+ |
| FRW i2i still-challenge | frw-i2i-still-challenge | plan\|next\|run\|promote |
| H3 max 效果 / FLF / timeline L4 / 2V ref | h3-max · h3-flf · h3-timeline | h3_workflow / prompt |
| Module W0–W7 包边界 | project-module-refactor | core/post/narrative/audio/media… |
| Routing rewire R0–R7 | routing-rewire plan | route-catalog |
| 对白主链 / 零旁白 / speaker-frame | dialogue-primary · speaker-frame | gates |
| true-video-only hero | true-video-only-hero | still 不进 timeline |
| 构图 anti-hijack 机读 | composition-anti-hijack | shortlist/pk |
| 圣旨协议 | user-command-is-edict | Agents.md |
| Agent 出货纪律 / runtime-lock | agent-ship-discipline | pre-push · lock |
| Workflow A–H + ROI A–E | workflow-merge · roi plan | CLOSE/SHIPPED |
| Suse final A1–A5 | suse-ep01-official-final-iron | sex floor · VO 窗 · plate · BGM |
| scale-fallback 机读 | wardrobe-no-redress-fullnude | SCALE_* 码 |

---

## 3. 类 A · 法条 IRON（记忆最密 · 优化=守住，不是删）

### 3.1 成人 / 衣着 / 毒镜

| 优化/铁律点 | Memory | 一句话 |
|-------------|--------|--------|
| 成人尺度 MAX + 四拍弧 | adult-scale-max-sex-arc · core-adult-iron | 肉戏≥50% · 全弧 · bare climax |
| 冲击全闸 | adult-impact-max-gates · adult-max-pipeline-force | coitus/size/pose 等 strict |
| 性爱时长底 | sex-hard-floors · sex_duration | act+climax 占比；**禁空改 10s**（A1） |
| 卸装不回穿 | wardrobe continuity 多卡 | rank 只升不降 |
| 全裸诱惑兜底 + **模型极限勿硬上** | 2026-08-06-wardrobe | 插不进→裸诱→软 max |
| 毒镜 futa/喷奶/霓虹 | poison-shot-anatomy | 毒 still 禁 I2V |
| headroom 不裁头 | headroom-no-crop-heads | 构图 |
| 状态照 / keyframe-first | continuity · core-adult | 先验后生 |

### 3.2 画面 / 运动 / 构图

| 点 | Memory |
|----|--------|
| 高动 mean≥18 肉戏≥20 + 画风锁 | high-motion-style-final |
| 抗无聊 ≥4 体位 ≥2 脸 CU ≥2 L4 | shot-variety-anti-boring |
| 门绿≠好看 | 同上 |
| 构图防抢走（沙俯视脚印/男胸抢女主） | composition-anti-hijack |
| still=prompt 对齐 | i2v-still-prompt-match |
| true video only | true-video-only-hero |
| 转场丝滑 / cut-silk / 标题双烧 | cut-silk · title-double-burn · transition-motion |
| 分层 hero×env | layer-routing |
| 角色立场多 POV | character-stance |
| 剪辑反呆板 | editorial-craft |
| VO 不拖腔 | vo-drag-motion-snap |

### 3.3 声音 / 字幕 / 后期

| 点 | Memory |
|----|--------|
| 口白中文 · Edge · 禁 zh 挂 ja | dialogue · ep2-voice（旧日文轨已中文唯一） |
| 对白主链 Grok/H3 原音 | dialogue-primary · dialogue-native-audio |
| 后期对嘴冻结 | hard-defaults · lipsync |
| BGM rnb 非 dark（非恐怖） | bgm-anti-repeat |
| 字幕 ship 像素硬烧 | huangdao-caption-hardburn |
| speaker=画面主体 | speaker-frame · huangdao |
| plate subs=off · HF 单 owner | post · caption_path |
| 5-track · −16 LUFS | hard-defaults / stages |
| final 超时 / sidechain partial | evirus bulk-final · post |
| review≠approved · sha 匹配 | closeout-gates |

### 3.4 5090 / Comfy / 队列

| 点 | Memory |
|----|--------|
| 隧道 **18188→8188** 非 8189 | comfy-tunnel-queue-neon |
| 一机一 owner · 禁 pgrep 自杀 | comfy-multifilm · gpu-priority |
| pilot 独占 · 进度只认 takes 文件 | comfy-gpu-priority-pilot-i2v |
| interrupt 假进度 | i2v-still-prompt-match-comfy-interrupt |
| free-memory --confirm | comfy anatomy batch |
| capacity 不 ready 禁假 execute | h3 capacity · fill-idle |

### 3.5 流程 / Agent

| 点 | Memory |
|----|--------|
| pilot 用户批 · 不自批 | hard-defaults · workflow |
| 不静默降 heat / 换 provider | 多卡 |
| closeout 链 plate≠完 | closeout-gates-iron |
| bulk→final 出片 | evirus-ch04-bulk-final |
| script-value-debrief lock 前 | script-value-debrief |
| input fidelity | input-fidelity |
| 圣旨短令 | user-command-is-edict |
| SKILL 短 · runtime-lock · 干净树 push | agent-ship-discipline |
| dispatch 只跑 next | pipeline-methodology |

### 3.6 武器 / 通道（部分已演进）

| 点 | Memory | 注 |
|----|--------|-----|
| Seedance 质量/403 | seedance-quality | **主产线已 h3_primary**；勿回 FRW-first 文案 |
| FRW LTX / key 403≠502 | frw-ltx · frw-key | env/legacy/opt-in |
| Grok OAuth | grok-oauth-pack | |
| ltx23 adult audio lane | ltx23-adult-audio | opt-in 非默认全片 |
| H3 FLF / R2V / T2V 路由 | weapon-lane · h3-max | |

---

## 4. 按流水线阶段的「记忆优化菜单」

```text
故事 receive → script-value-debrief → plan → fidelity → write-spec
  → design-go → pilot GO → bulk-preflight → bulk/h3
  → gate-auto → final → review-final → closeout → export
```

| 阶段 | 记忆里反复出现的优化目标 |
|------|--------------------------|
| Agent/Plan | 戏剧意义 · 零旁白 · 成人弧写全 · 衣着单调 · variety 设计时就够 L4 |
| Visual | 身份锁 · material fidelity · 毒镜 · 高动 · anti-hijack · still-challenge |
| Media/H3 | h3_primary · fill-idle · free-first · 不抢卡 · takes 计数 |
| Voice | 中文 Edge · 原音 prefer · TTS partial 诚实 · 口白窗三角 |
| Post | 字幕硬烧 · 单引擎 · mix partial · plate≠master · rnb procedural |
| Deliver | gate-auto 绿 · closeout · 抽帧有中字 · PARTIAL 诚实 |

---

## 5. 与其它 plugin / skill 边界（Agents 日常 Combo）

记忆与制度里 **分引擎**，勿混：

| 工作 | Owner |
|------|--------|
| AI 短片 / 漫剧 / Grok Imagine 成片 | **ai-film-grok** |
| 连续剧 project 蓝图 / cast 复用 | **ai-film-project** |
| 已有影片剪辑字幕 | video-use / ChatCut |
| HTML/GSAP 动效 | hyperframes* |
| Remotion 程序化 | remotion* |

本表 **不** 展开 hyperframes/remotion 的 memory（不在本 plugin memory/）。

---

## 6. 建议执行序（只动类 C）

```text
P0  片场：绿 variety 片 → C1 queue_empty
P0  新 final：强制读 official-final + bgm-source + scale-fallback 回执
P1  anti-hijack / material fidelity 纪律（少写新码）
P1  C5 promote 真片压 soft-max 停手
P2  C9 巨石仅 bug 驱动 peel
P2  C10 触达文件补 timeout
P3  C11–C14 deferred / optional
```

**明确非目标（记忆反复写）：** 自动批 pilot · 静默降 heat · 假绿 master · 全自动毒镜 CV · 虚荣压 LOC · 用 FRW 换掉 h3_primary 默认。

---

## 7. 索引入口（按日期扫）

| 索引 | 覆盖 |
|------|------|
| `memory/2026-07-20-session-index` | 转场/字幕/分层/Seedance 时代 |
| `memory/2026-07-21-session-index` | 流水线主脊 · 声 · 成人硬底 |
| `memory/2026-07-24-session-index` | 声线 · final · 高动指针 |
| `memory/2026-07-27-session-index` | 成人 MAX · 高动 · 不回穿 |
| `memory/2026-07-29-session-index` | Comfy/毒镜/收尾/抗无聊 **大包** |
| `memory/2026-08-0x-*` | gate-auto · H3 · fill-idle · fidelity · anti-hijack · suse · wardrobe · C1 |
| `memory/README.md` | 短卡契约 |

---

_Generated 2026-08-06 from ~80 memory cards + session indexes + active plans. C1 **queue_empty SHIPPED** on suse-evolution-ep01 (canary artifacts/2026-08-06-c1-until-empty-suse-ep01-canary.json). C3 ship-aligned with `test_suse_final_iron.py`._
