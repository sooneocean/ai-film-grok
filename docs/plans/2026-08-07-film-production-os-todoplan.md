# AI Film Production OS · 优化 Todo Plan

**结论先行：** 你的仓库**已经是**「AI 电影生产操作系统」的骨架与车间（v**2.40.106**），不是「还缺一个生成器」。优化路径 = **把传统片厂职责补成机读生产图**（Scene/Beat/Shot Card/Coverage/Continuity In→Out/Take/Gate），**禁止**再开第二套导演系统或从零重写。

**一句话类比：** 片厂大楼和分车间门牌都在；缺的是「场记本统一格式 + 剪辑进棚前检查表 + 导演拍板单」被**默认强制走**，而不是再贴标语。

| 项 | 值 |
|----|-----|
| Status | **CLOSED · W0–W7 SHIPPED**（2026-08-07 收工；console Shot Card UI deferred） |
| 基线版本 | `plugin.json` **2.41.4**（W7 performance/sound/cine/asset-version；2.41.2 W5–W6；2.41.1 W3–W4） |
| 工作树 | `/Users/dex/.grok/plugins/ai-film-grok`（本会话真相） |
| 战略约束 | CTO 板：禁止第二套导演系统 · 巨石挡路才拆 · 机读门禁 > 散文 IRON |
| 北极星 | **剧本 → 可剪、可审、可接戏的 Shot Card**（用户 MVP §44）；生成质量是第二位 |
| 成功定义 | 导演能走完 §44 的 1–17，且每步有 schema + CLI + pytest + receipt |

**与既有板关系（单一真相，勿重做已 ship）：**

| 板 | 角色 |
|----|------|
| `docs/plans/2026-08-06-cto-optimization-todoplan.md` | 工程主执行板（稳态运营） |
| `docs/plans/2026-08-07-iron-internalization-todoplan.md` | 铁律内化 **CLOSED** |
| `docs/plans/2026-08-07-delivery-honesty-rail-todoplan.md` | 出片诚实 **CLOSED** |
| `references/generative-film-craft.md` · `pipeline-methodology.md` · `professional-director-system.md` | 工序哲学已存在 |
| **本 plan** | **制片 OS 对齐愿景**：补「生产图完备度」缺口，映射到现有 drama-graph / film-spec / bibles / gates |

---

## 0. 原则对齐（写代码前先认）

用户愿景与现系统**高度同构**；差异在「字段完备 + 强制门禁 + 审片物」而非「缺概念」。

| 愿景原则 | 现有落点 | 缺口 |
|----------|----------|------|
| Story → Scene → Beat → Shot → Gen | drama-graph `episode→scene→beat→shot`；film-spec 投影 | Sequence 层弱；Beat 可被 thrash 跳过 |
| Generation never controls Story | production-book + locks + impact_dry_run | 上游改后 silent stale 仍有路径 |
| Director-first 八问 | `director_board` · `dramatic_function` · `dramatic_meaning` | 未默认产出「Director Interpretation」receipt |
| Shot purpose 显式 | `dramatic_function` · shot-intent | 缺完整 purpose 枚举 + 「只为好看」拒收 |
| Coverage before produce | `coverage_strategy` 字段 · animatic gate | **无**「不可连贯剪辑 → 禁 production」硬门 |
| Prompt = 执行物非真相 | shot package · cinema_prompt · H3 adapter | provider 语法仍渗入部分 project 数据 |
| Take 不覆盖 | `take_registry` archive | 审片维度（performance/continuity/camera）偏薄 |
| 最小单位重生 | scale_fallback · face · state-index | 缺统一 defect class → action 路由表 |
| 五阶段 DEVEL→DELIVERY | 7 段 dispatch + 11 阶段 professional | 状态名与愿景 30+ 闸不完全同名（映射即可，勿重命名用户进度） |

**硬规则（执行本 plan 时）：**

1. **扩展现有实体**，不新建平行 `FilmOS v2` 包。  
2. **Schema → CLI → gate → pytest → stages 指针**（五问卡 / iron 路径）。  
3. **禁止**一上来接新模型；Prompt Compiler 先服务现有 H3/Grok lane。  
4. 每个功能先答 Codex 九问：片厂职责 · 实体 · 上游 · 下游 · 状态 · 人审 · 修订 · 溯源 · 失败重试。  
5. 便利与「导演控制 / 接戏 / 可剪 / 可追溯」冲突时，**保片厂**。

---

## 1. 现状雷达（相对愿景）

| 域 | 成熟度 | 代表资产 | 相对愿景 |
|----|--------|----------|----------|
| 故事图 | ★★★★☆ | `drama_graph` · `story_plan` · `story_quality` · debrief | 差 Sequence + 强 Scene 戏剧字段 |
| 意图 / 主题 | ★★★☆☆ | `director_intent` · script-value-debrief | 差完整 `CreativeIntent` 文档契约 |
| 镜头意图 | ★★★★☆ | film-spec shot + `dramatic_function` · shot-intent | 差 Shot Card 审片面 + purpose 枚举 |
| Coverage | ★★☆☆☆ | 字段/文案 · premium animatic | **缺机读 Coverage Checker** |
| 资产 Bible | ★★★★☆ | style/audio/post bible · cast · wardrobe | Prop/Location ID 引用在 prompt 侧未硬约束 |
| 生成 / Take | ★★★★☆ | media-queue · H3 · take_registry | 差 Variant 对比卡与 Director score 维度 |
| 接戏 | ★★★★☆ | continuity · state-index · wardrobe ladder | 差统一 Continuity In/Out 状态机（道具/知识态） |
| 声音先行 | ★★★☆☆ | audio-bible · 5track · sound_plan | Shot 级 SoundCue 图不完整 |
| 剪辑 | ★★★☆☆ | editor_cut · picture_lock · render_final | 多版本 cut 并行支持弱 |
| 审批闸 | ★★★★☆ | director lock-stage · production-book | 状态名多套并存；需**投影表**而非替换 |
| Prompt 编译 | ★★★☆☆ | motion_prompt_spine · h3_official_prompt | 缺统一 Compiler + Adapter 边界测试 |
| 缺陷重生 | ★★☆☆☆ | 分散 repair 路径 | 缺分类路由 CLI |

---

## 2. 目标架构（贴现仓，不绿地）

```text
CreativeIntent  (扩展 director_intent / debrief)
      ↓
drama-graph     Episode [→ Sequence?] → Scene → Beat → Shot
      ↓ 投影
film-spec + Shot Package + Shot Card (人读)
      ↓
Coverage Gate + Animatic Gate + Story Validate
      ↓
Bibles (style/audio/post) + Continuity State Graph
      ↓
Prompt Compiler → Model Adapter (H3 / Grok / …)
      ↓
Keyframe → Motion → Take[] → Review → Select
      ↓
Assembly → Rough → Fine → Picture Lock → Master
```

**真相分层（已有，守住）：**

| 层 | 文件/概念 | 可写方 |
|----|-----------|--------|
| 故事真相 | `drama-graph.json` | plan / narrative |
| 视听部门 | style / audio / post bible | 各部门 lock |
| 依赖与陈旧 | production-book | impact → stale |
| 执行投影 | film-spec · shot package | derive only |
| 媒体证据 | clips / takes / receipts | register 不覆盖 |

---

## 3. 分 Phase Todo（对齐用户 MVP，按现仓增量）

> 勾选顺序 = 用户 §43 Phase 1→6。每项：**产物 · 挂载点 · 验收 · 估点**。  
> 估点：S≤0.5d · M≈1–2d · L≈3–5d · XL>1w（单人 coding agent 量级）。

---

### Phase 0 — 对齐与防走偏（先做 · 0.5–1d）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|----|
| **P0.1** | 愿景↔实体映射表（本 plan §1–2 落档到 repo） | `docs/plans/2026-08-07-film-production-os-todoplan.md` | CTO 指针一行 | 旧 plan 顶部指向本板 | S |
| **P0.2** | 状态机投影：愿景 30+ 闸 ↔ professional 11 阶段 ↔ dispatch 7 段 | `references/production-state-map.md` | stages/approval | 表完整；**不改用户可见进度名** | S |
| **P0.3** | 冻结反模式清单 | 写入 plan + hard-defaults 一行指针 | agent | 「禁第二导演系统 / 禁剧本直灌模型 / 禁只为好看的 shot」可机指 | S |

**完成定义：** 任何 agent 读本板后不会去新建 `DirectorAgent` 绿地包。

---

### Phase 1 — Story Structure（用户 Phase 1 · 优先）

**目标：** 剧本可靠变成可编辑 Scene/Beat 图；弱场禁烧钱。

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|----|
| **P1.1** | **CreativeIntent 契约** | schema 字段并入 `director_intent` 或 `receipts/creative-intent.json`：theme · audience_emotion · protagonist_pov · genre · visual_language · pacing | `film_spec_lints.validate_director_intent` · debrief | 缺字段 → plan/write-spec 红；下游 agent context 必带 | M |
| **P1.2** | **Story Validation 门** | `aifilm story validate-structure`：主角目标 · 阻力 · 场是否改变 · 可删场 flag · 弧升级 | 扩 `story_quality` / `narrative_control` | 弱场 `flag`；`strict` 时禁 media-queue | M |
| **P1.3** | **Scene 戏剧模型硬化** | Scene 必填：`dramatic_goal` · `conflict` · `scene_turn` · `emotional_arc{start,mid,end}` · `continuity_in/out`（结构化，非散文） | drama-graph + film-spec schema | schema 测 + `scene_strict` 红 | L |
| **P1.4** | **Beat 强制中间层** | 禁止 screenplay 段落 → shots；`beat extract` 后才 `shot list` | `beat_extraction` · craft_spine · plan run | thrash 跳 beat → fail-closed receipt | M |
| **P1.5** | **Sequence 可选层**（长片） | longform 下 `sequence_id`；短片可 flatten 单 sequence | longform schema | longform 绿；短片兼容 | M |
| **P1.6** | **DialogueLine 图** | 台词挂 beat/shot，非游离 | dialogue_screenplay 对齐 | speaker+purpose 已有则复用；缺挂点红 | S |

**MVP 勾：** 用户 §44 的 1–5（建项目 · 进剧本 · 拆 Scene · 编意图 · 拆 Beat）。

---

### Phase 2 — Shot Planning（用户 Phase 2 · 核心里程碑）

**目标：** 第一生产里程碑——**可编辑、可审、接戏感知的 Shot Cards**。

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|----|
| **P2.1** | **Shot Card schema** | 人读+机读：purpose · audience info before/after · emotional · pov · framing · camera · subject · action · performance · duration · lighting · continuity_in/out · dialogue · sound · asset_refs · status | 扩 film-spec shot + 导出 `shot-cards/*.md|json` | 非仅 image prompt；pytest 最小字段 | L |
| **P2.2** | **Shot Purpose 枚举 + 拒收** | enum：establish_location · reveal_information · show_reaction · …；flag `looks_cool` / 空 purpose | `dramatic_meaning` 扩展 | 无 purpose → SHOT_MEANING / PURPOSE_EMPTY 红 | M |
| **P2.3** | **Director Interpretation receipt** | 场景级固定格式：Dramatic Function · POV · Emotional Arc · Info · Visual · Performance · Sound · Editorial · Risk | `aifilm director interpret-scene` → `receipts/director-interpretation/<scene>.md` | **先于** shot list；dispatch context 可读 | M |
| **P2.4** | **Shot List 生成器** | 从 Beat → Shot List（§42 格式），可编辑 | plan / craft | 输出非 prompt-only | M |
| **P2.5** | **Coverage Checker（硬门）** | 场景级：establish/master/CU/reaction/insert/transition…；对白场 eyeline / reverse / cutaway | 新 `gates/coverage_check.py` + preflight | 不可剪预测 → **禁** SHOT_READY / bulk | L |
| **P2.6** | **Storyboard 规划物** | 低保真构图/轴线/景别优先；`storyboard_review` 状态 | visual stage · still 草稿 lane | 可批可驳；未批禁 keyframe bulk | M |
| **P2.7** | **Animatic 闸强化** | frames + temp VO + duration → ANIMATIC_APPROVED 才 bulk | 现有 `build_animatic_gate` · shot_animatic_lock | longform/premium 默认 hard；短片可 soft 但写 receipt | M |

**MVP 勾：** §44 的 6–10（Shot List · 编辑 Shot · 分资产 · Storyboard · 批 Storyboard）。

**本 Phase 完成 = 用户定义的「第一个生产里程碑」。**

---

### Phase 3 — Asset Bible（用户 Phase 3）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|----|
| **P3.1** | Character 不可变 traits + prohibited_changes | 扩 cast / style-bible face nodes | identity_generation_lock · partner_cast | 违禁改 → 红 | M |
| **P3.2** | Location / Prop / Wardrobe **ID 引用** | shot.asset_refs 必填 canonical ID | shot package · prompt compiler | prompt 禁裸写长描述替代 ID（可测启发式） | M |
| **P3.3** | VoiceBible 对齐 cast_voices | zh Edge 规则已有 → 挂 shot performance | voice stage | 中文片 ja 声继续红 | S |
| **P3.4** | LookBible / visual_language ← CreativeIntent | style lock 继承 intent.visual_language | lock-style | 漂移写 stale | S |

---

### Phase 4 — Generation（用户 Phase 4 · 编译器优先）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|----|
| **P4.1** | **Prompt Compiler 边界** | 输入：ShotSpec+Bibles+Continuity+Director+Cine rules；输出：adapter prompt；**禁止**回写 provider 语法进 graph | 收敛 `cinema_prompt` / `h3_*` / `motion_prompt_spine` | 单测：同 ShotSpec → 两 adapter 不同串、graph 不变 | L |
| **P4.2** | Model Adapter 接口 | `Adapter.compile(shot_package) -> PromptArtifact` | H3 + Grok 先；禁新厂商 | 接口测 + 现有 canary 不回归 | M |
| **P4.3** | Keyframe → Approve → Motion 状态 | shot.status 机读链 | generation_ready · dispatch | 跳步红 | M |
| **P4.4** | Take 元数据加厚 | review: performance/continuity/camera/artifacts；states: Generated/Candidate/Selected/Approved/Rejected/Archived | take_registry | 永不覆盖；history 可 diff | M |
| **P4.5** | Variant 对比 CLI | `aifilm takes compare --shot` | review | 人批 selected 写 ledger | S |

**MVP 勾：** §44 的 11–14（Keyframe · multi take · compare · approve one）。

---

### Phase 5 — Review / Continuity / Revision（用户 Phase 5）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|----|
| **P5.1** | **Continuity State Graph** | physical · prop · emotional · spatial · knowledge；In → Action → Out → next In | 扩 continuity + state_index | 冲突检测 CLI；未解禁 picture lock | L |
| **P5.2** | ContinuityAgent = **规则引擎+报告**（非聊天 agent 绿地） | `aifilm continuity audit` | preflight / closeout | 衣着只前进等 IRON 并入同入口 | M |
| **P5.3** | **Defect class → 最小重生** | 表：face→repair · hand→regional · performance→new take · camera→reshoot · continuity→transition shots · dialogue→ADR · bg→inpaint · timing→edit | `aifilm revise plan --defect` | 默认不整场重渲；receipt 写范围 | L |
| **P5.4** | Change Impact 人读 | 已有 impact_dry_run → 输出「影响镜/takes/锁」清单 | director impact CLI | 上游改锁前必须 dry-run | S |
| **P5.5** | 评论 / 批注模型 | shot/take 级 comment + resolution | review_ui / receipts | 可选；不阻塞 P5.1–3 | M |

**MVP 勾：** §44 的 15（连续性冲突）。

---

### Phase 6 — Editing / Delivery（用户 Phase 6）

| ID | 项 | 产物 | 挂载 | 验收 | 点 |
|----|-----|------|------|------|----|
| **P6.1** | 多版本 Cut 状态 | Assembly → Rough → Fine → Director → Picture Lock 投影到 post-bible | picture_lock · editor_cut · **edit_director** desk | 状态可机读；见 [edit-director plan](2026-08-07-edit-director-todoplan.md) | M |
| **P6.2** | 时间线装 approved takes only | 禁 draft take 进 rough 默许 | render / compose | 测 | M |
| **P6.3** | 音画字幕 honest export | 沿用 gate-auto · 5track · hardburn；plate≠master | deliver | 已有诚实轨不回退 | S |
| **P6.4** | Rough cut 一键 | approved shots → timeline → export | final path | §44.16–17 | M |

---

### Phase 7 — 横切增强（可并行，非 MVP 阻断）

| ID | 项 | 说明 | 点 |
|----|-----|------|----|
| **P7.1** | Performance 丰富度 | objective · subtext · intensity · eye/breath/tempo（扩 `performance_cue`） | M |
| **P7.2** | SoundCue 对象 | 镜级 ambience/SFX/silence bridge；continues_into_next | M |
| **P7.3** | Cinematography rules 表 | 情绪→镜头语言映射（数据驱动，非散文） | M |
| **P7.4** | 版本父子链 | CHAR_v01→v03 APPROVED；下游记 used_version | M |
| **P7.5** | 巨石 peel | 仅当本 plan 改到 validate_film_spec / render_final / preflight 时顺手拆叶 | 按需 |
| **P7.6** | Web console Shot Card 视图 | 可选；CLI 真优先 | L |

---

## 4. 推荐执行波次（90 天内可落地）

| Wave | 内容 | 用户价值 | 依赖 | 状态 |
|------|------|----------|------|------|
| **W0** | P0.1–P0.3 落档 | 防误工 | — | ✅ |
| **W1** | P1.1 + P1.2 + P1.4 | 弱故事不烧 GPU | W0 | ✅ |
| **W2** | P2.1 + P2.2 + P2.3 + P2.4 | **Shot Card 里程碑** | W1 | ✅ |
| **W3** | P2.5 + P2.6 + P2.7 | 剪辑前 Coverage + Animatic | W2 | ✅ 2.41.1 + production-ready |
| **W4** | P1.3 + P5.1 + P3.1–3.2 | 接戏与资产 ID | W2 | ✅ 2.41.1（asset_refs 仍可加深） |
| **W5** | P4.1–P4.5 | 编译器 + Take 审片 | W2 | ✅ **2.41.2** |
| **W6** | P5.3–P5.4 + P6.* | 最小重生 + 粗剪导出 | W5 | ✅ **2.41.2** |
| **W7** | P7.1–P7.4（P7.6 console UI deferred） | 表演 / SoundCue / 摄影表 / 版本链 | 非阻断 | ✅ **2.41.4** |

**本板 CLOSED（2026-08-07）：** MVP §44 主链有 CLI+receipt+pytest。后续 ROI 另开短板，勿重开第二套导演系统。

---

## 5. 明确不做 / 延后（防范围爆炸）

| 不做 | 原因 |
|------|------|
| 新建独立 `DirectorAgent` 服务/包 | 职责已在 director_cli · dramatic_meaning · dispatch；做 **receipt + gate** 即可 |
| 同时接入 Kling/Veo/Runway 等 | 用户 §43：先 Shot Card；Adapter 接口预留即可 |
| 重命名用户 7 段进度 | 成本高、收益低；用投影表 |
| 全量 UI 产品化 | CLI + receipt + 可选 console |
| 为「最大自动化」削弱人审 pilot/bulk | 违反 Director-first 与现 IRON |
| 只写 memory 不写 schema/测 | 违反 iron-internalization |

---

## 6. 验收总表（对照用户 §44）

| # | 能力 | 现状 | 目标 Wave | 机读证明 |
|---|------|------|-----------|----------|
| 1 | Create Project | ✅ init | — | 已有 |
| 2 | Enter screenplay | ✅ receive | — | 已有 |
| 3 | Break into Scenes | ⚠️ | W1 | story validate + graph |
| 4 | Edit scene intent | ⚠️ director_board | W1/W4 | scene 字段硬 |
| 5 | Break into Beats | ⚠️ | W1 | beat 强制 |
| 6 | Generate Shot Lists | ⚠️ | W2 | shot list CLI |
| 7 | Edit Shots | ⚠️ | W2 | Shot Card |
| 8 | Assign assets | ⚠️ | W4 | asset_refs |
| 9 | Storyboards | ⚠️ 弱 | W3 | storyboard status |
| 10 | Approve storyboards | ⚠️ | W3 | lock |
| 11 | Keyframes | ✅ 路径 | W5 状态化 | status 链 |
| 12 | Multi video Takes | ✅ | W5 加厚 | take_registry |
| 13 | Compare Takes | ⚠️ | W5 | compare CLI |
| 14 | Approve Take | ✅ 偏薄 | W5 | ledger |
| 15 | Continuity conflicts | ⚠️ 分散 | W4 | continuity audit |
| 16 | Timeline assembly | ✅ | W6 收紧 | approved only |
| 17 | Export rough cut | ✅ | W6 | export 绿 |

---

## 7. 工程落地约定

```bash
# 每波结束
make -C "$(git rev-parse --show-toplevel)" check-all
# 功能变更：bump plugin.json + CHANGELOG
# 改 scripts 指纹：make lock-runtime
# commit message 英文；沟通中文
```

| 改动类型 | 测试优先 |
|----------|----------|
| schema / lint | `test_film_spec*` · schema validate |
| story/beat | `test_story_*` · `test_drama_graph` |
| coverage / meaning | `test_dramatic_meaning` · 新 `test_coverage_check` |
| take / revise | take_registry · 新 defect 路由测 |
| compiler | 纯函数测 + H3 canary 不回归 |
| gate | preflight / director_stage_gates |

**Provenance：** 每闸写 `receipts/`；lock 绑 hash；take 不删档。

**失败语义：** fail-closed；PARTIAL 诚实；禁静默 `ok: true`。

---

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 范围变「第二系统」 | P0 冻结 + CTO 指针；只扩现包 |
| Scene 字段过重导致真片卡死 | `scene_strict` 分档：pilot soft / bulk hard |
| Coverage 过严卡短片 | 短片 checklist 子集；longform 全量 |
| Prompt Compiler 大重构回归 | 先边界测，再迁 H3 入口；不一次搬完 |
| 双 checkout 分叉 | 只改当前 git 根；同步用 git |

---

## 9. 确认后执行顺序（用户 `go` 时）

1. 将本 plan **复制落档**到 `docs/plans/2026-08-07-film-production-os-todoplan.md`，CTO 板加指针。  
2. 实施 **W0**（映射表 + 状态投影 + 反模式）。  
3. 实施 **W1**（CreativeIntent + story validate + beat 强制）。  
4. 实施 **W2**（Shot Card + purpose + Director Interpretation + Shot List）。  
5. 每波 `check-all` → bump → commit；需要则 verifier。  
6. **停在 W2 演示点** 等人确认再进 W3（Coverage/Animatic），除非用户圣旨 `继续推进`。

---

## 10. 给主理人的决策摘要

你要的不是「更会生成视频的工具」，而是 **可控的电影生产 OS**。  
仓库 **70% 已是这套 OS**；优化杠杆是：

1. **把 Scene/Beat/Shot 补成真正生产单元**（不是散文 prompt）  
2. **Coverage + Animatic 挡住废片流水线**  
3. **Shot Card 成为导演与系统的共同语言**  
4. **Prompt/模型永远是下游执行器**  
5. **最小单位重生 + 接戏状态机** 保住已锁工作

**第一可交付里程碑：**  
`screenplay → structured scenes/beats → director interpretation → editable shot cards`  
—— 对应 W0–W2，不先碰新模型。
