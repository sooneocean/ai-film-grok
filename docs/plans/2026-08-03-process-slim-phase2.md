# ai-film-grok 流程瘦身 Phase 2 — 2026-08-03

**Status:** P0–P5 DONE 2026-08-03 · v2.31.16 · not pushed  
**前置:** ROI A–E + release 2.31.15 已合入；见 `2026-08-03-roi-optimization-plan.md`  
**目标:** 更有效率、更稳定——**少重复真相、少 token 税、少流程名词、少仓内垃圾**

### Session result

| Batch | Result |
|-------|--------|
| P0 | ruff + fast suite + doctor core green；story/shot extract 已在 2.31.14–15 |
| P1 | voice lesson `required:false`；stages/voice 自洽（2.31.15 已含部分） |
| P2 | `~/.grok/Agents.md` 102→85 行指针（备份 process-slim）；plugin AGENTS 硬规则改指针 |
| P3 | `memory/README.md` 契约；18 对 memory 已是短卡 |
| P4 | `docs/reports/2026-08-03-artifacts-inventory.md` 清单 only |
| P5 | craft-spine / generative-film-craft / INDEX / SKILL 七步映射 |

---

## 0. 诊断（结论）

| 痛点 | 证据 | 后果 |
|------|------|------|
| **规则四层复写** | `~/.grok/Agents.md` 日常影音 Combo 长贴 IRON ≈ 全抄 `hard-defaults` + lessons + memory | 每轮固定税；改一处漏三处；漂移静默 |
| **课案双份** | ≥18 对 `memory/X` ↔ `references/lessons-X` | 检索混乱；agent 读长课当默认 |
| **流程多套名** | 用户主流程 7 步 · dispatch 8 stage · pipeline_stages · 八环 craft · Professional 11-stage | 人与 agent 对不上号；SKILL 已声明「只对外 7 步」但仍散落 |
| **context 灌长课** | `context-routing` voice 段 **required** 整份 126 行 lesson | 每步 voice 多烧 ~4k token |
| **仓体积** | 仓 5.2G（`.local-runtimes` ignore）；**git 仍 track artifacts ~26MB**；双份 `g2pW` 152M×2 磁盘 | clone/fsck 慢；心智噪音 |
| **CLI 单体** | `aifilm_grok.py` 仍 11k 行 | 改 cmd 易冲突；**不单独开 sprint**（ROI F） |
| **WIP** | working tree：`story_plan` −650 行、`shot_planning` 抽出、lock/docs 更新 | 须收口 commit 才算完成 |

**已做得对的：** `stages/*` 极短；`dispatch` compact `context_refs` max 3；`hard-defaults` 作门禁表；今日 `story_plan`/`shot_planning` 拆模块。

---

## 1. 文档分层（目标架构 · 单一真相）

```text
层 0  制度短卡（每会话必载）
      ~/.grok/Agents.md · plugin AGENTS.md
      → 只写：入口命令 · 不可逆协议 · 影音路由一行 · 链到层 1
      → 禁止再贴整段 IRON 正文

层 1  机读门禁（工程真相）
      references/hard-defaults.md + 代码 gates
      → 改规则只改这里（+ 对应 pytest）

层 2  阶段卡（按 dispatch 回合）
      references/stages/{agent,visual,voice,post,deliver,approval}.md
      → 每卡 ≤30 行；链 hard-defaults 锚点，不复制

层 3  短记忆卡（可选 · 人读速查）
      memory/*.md
      → 仅：用户原话 · 三句话 · 检查清单 · 链 lesson
      → 禁止与 lesson 双写完整铁律表

层 4  长课案（按需 · 不进默认 context）
      references/lessons-* · references/*-workflow.md
      → 失败复盘、片例矩阵；context-routing 默认 required=false
```

**完成定义：** 同一 P0 规则在层 0 最多 **一行指针**；正文只在层 1（或代码）。

---

## 2. 流程名词收敛（用户可见）

对外只保留 SKILL 已写的 **7 步主流程**：

1. 定义故事 → 2. 设计演出 → 3. Pilot → 4. 批量 → 5. 选片粗剪 → 6. 后期母版 → 7. 审片交付  

映射（内部，不要求用户记）：

| 用户步 | dispatch stage | 阶段卡 |
|--------|----------------|--------|
| 定义故事 | idea / story / beats | stages/agent |
| 设计演出 | shots | stages/visual |
| Pilot / 批量 | media | stages/visual |
| 选片粗剪 | selects / rough | stages/visual → post |
| 后期母版 | rough + voice + design | stages/voice + post |
| 审片交付 | verified / deliver | stages/deliver |

- `craft-spine` / `generative-film-craft` / Professional 11-stage → 标 **内部证据/诊断**，INDEX 降权，不进默认 context。
- 新 agent 文案禁止 invent 第四套阶段名。

---

## 3. 可执行批次（独立可验）

### Batch P0 — 收口今日 WIP  ⏱ 20–40min · **先做**

1. 全量 fast pytest + ruff + doctor core  
2. 纳入 `test_shot_planning.py`（若未 track）  
3. commit（message 英文）：story_plan / shot_planning / lock / changelog 2.31.13  
4. **不 push**（等授权）

**Done when:** working tree clean；fast suite 绿；plugin version 与 CHANGELOG 顶一致。

### Batch P1 — Context 与 token 税  ⏱ 1–2h · **ROI 最高**

1. `context-routing.json`：  
   - voice `lessons-…ep2-voice…` 改为 **required=false** 或换成 `stages/voice.md` + `hard-defaults` 锚  
   - rough 段 lesson 保持 optional  
2. `stages/voice.md` 补 5 行声线 P0 摘要（指 hard-defaults）  
3. 校验 `dispatch --compact` 仍 ≤3 refs、bytes 限  
4. 测：`test_dispatch` / context routing 相关  

**Done when:** voice 回合默认不加载 100+ 行 lesson；行为测绿。

### Batch P2 — 制度档瘦身（须备份 + 你确认）  ⏱ 1h

1. `cp ~/.grok/Agents.md ~/.grok/backups/Agents.md.YYYYMMDD-HHMM`  
2. 「日常影音 Combo」IRON 长段 → **bullet 一行 + 路径**（正文以 hard-defaults / memory 为准）  
3. plugin `AGENTS.md` 硬规则段同样压到指针  
4. SKILL P0 保持短列表（已短，仅去重复措辞）  

**Done when:** Agents 影音段行数明显下降；无丢失「成人 MAX / 毒镜 / 声线 / 5090」任一指针；人工 spot-check。

### Batch P3 — memory 契约 + 双份收敛  ⏱ 1–2h

1. 写 `memory/README.md`：短卡模板（原话 / 三句 / checklist / 链 lesson）  
2. 对 **已成对** 的 18 个 memory：删「全文复写铁律」只留 checklist（若已是短卡则不动）  
3. 无 lesson 的 memory 独苗：保留或晋升 hard-defaults 后归档  
4. INDEX 刷新 lessons/refs 计数  

**Done when:** 无 memory 与 lesson 双份完整铁律；INDEX 数字准。

### Batch P4 — 仓卫生（可选 · 部分需确认）  ⏱ 30min

1. 评估 `git rm --cached` artifacts 大媒体（保留 README/json 契约样例）— **先列清单再删 track**  
2. 磁盘：确认 `g2pW` 双份是否可只留 skill 侧（repo 根 g2pW 已 ignore）  
3. `.local-runtimes` 列清单；**不擅自 rm -rf**  

**Done when:** tracked 体积下降或有明确 keep 理由；磁盘动作有清单。

### Batch P5 — 流程文案统一  ⏱ 1h

1. README / SKILL / INDEX 顶部统一 7 步 + 映射表  
2. `craft-spine.md` 文首加「内部投影，非用户进度」  
3. 删或合并 superseded plans 指向 Phase2 + ROI  

**Done when:** 新人只读 SKILL+INDEX 不会看到两套「主进度」。

### Batch P6 — CLI 再抽（按需 · 不主动开）

同 ROI F：仅碰某 cmd 组时再抽 `aifilm_grok.py`。

---

## 4. 建议顺序

```text
P0（收口绿线） → P1（context 税） → P2（制度指针 · 需你确认） → P3（memory） → P5（文案）
P4 并行可选
P6 永不单独 sprint
```

**默认推荐本轮：`P0 + P1`。** P2 改全局宪法，你说 `ok Agents` 再动。

---

## 5. 明确不做

| 项 | 原因 |
|----|------|
| 删 lessons 文件 | 历史证据；只降默认加载 |
| 无行为 diff 的 11k CLI 大搬家 | 冲突面与假进度 |
| 未授权 push / 清 `.local-runtimes` | 对外/不可逆 |
| 再发明第四套阶段名 | 违背收敛目标 |

---

## 6. 你怎么回

| 回复 | 含义 |
|------|------|
| `P0` / `P0+P1` / `GO` | 按序做推荐批（GO=P0+P1） |
| `P0+P1+P2` | 含制度档瘦身（会先备份 Agents） |
| `全开` | P0–P5（P4 只列清单不删大目录） |
| `先看清单` | 只输出 P4 artifacts 与 memory 对账表，不改档 |

---

_Generated 2026-08-03 from live inventory + ROI closeout._
