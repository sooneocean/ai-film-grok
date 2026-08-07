# CTO 全面优化 Todo Plan · ai-film-grok

**结论先行：** 这不是「缺功能」的仓库，而是 **片厂已建完、规章已上墙、车间仍塞着几个 2k–2.5k 行总控台** 的成熟产线（v**2.40.38**）。下一轮优化应以 **诚实出片 + 闸门 fail-closed + 可维护热路径 + 运维吞吐** 为主；**禁止**再开虚荣 LOC 冲刺、绿地 IRON 散文、或重做已 ship 的包边界/A1–A5。

| 项 | 本机探针（2026-08-06 · plugins checkout） |
|----|------------------------------------------|
| 版本 | `plugin.json` **2.40.81**（C5.6 path externalization · 本轮） |
| 源码 | scripts **~688** `.py` / **~170k** LOC |
| 巨石函数 ≥200 行 | **74**；最大 `render_final` **2456** / `validate_film_spec` **2322** / `run_preflight` **1937** / `build_dispatch` **1249** |
| 顶层模块 | ~349（约 **256** 薄 shim + ~**93** 仍厚） |
| 错误/可观测 | `except Exception` **~550** · `print(` **~188** · logging **≈0** |
| 测试 | **~440** test 文件（强存在）；基座/巨石覆盖仍不均 |
| 文档税 | memory active **~41** · refs **~175** · plans 活跃 **~12** + archive 19 |
| 双 checkout | plugins 领先 `~/.grok/ai-film-grok` **4 commits**（勿手拷同步） |

**与旧板关系（单一真相）：** 本 plan = **CTO 主执行板**。旧板只当证据，header 应指向本档；**禁止** agent 按过期 plan 重开 A1–A5 / quality P0 / 包边界 W0–W7。

| 旧板 / 子板 | 角色 |
|------|------|
| **`docs/plans/2026-08-07-iron-internalization-todoplan.md`** | **铁律→代码内化子板** · **I0–I4 产品链 CLOSED 2.40.51**；I5 ops deferred |
| **`docs/plans/2026-08-07-delivery-honesty-rail-todoplan.md`** | **出片诚实审计轨** · **CLOSED R0–R5** 2.40.75（+ skip 热路径触达 wave） |
| `docs/plans/2026-08-06-nutrient-matrix.md` | L3/L4/L5 养分对账（I0 刷新） |
| `docs/plans/2026-08-06-next-optimization-todoplan.md` | 近期 W0–N 执行板（多数 SHIPPED） |
| `docs/plans/2026-08-06-optimization-todoplan.md` | 出片 A–G · A1–A5 SHIPPED |
| `docs/optimization-plan-2026-08-06.md` | 内容五域 P0 门 · **已落地** |
| `docs/senior-dev-code-quality-plan-2026-08-06.md` | 工程卓越维度（P0–P5）· 部分进行中 |
| `docs/reports/2026-08-06-code-metabolism-inventory.md` | 代谢 batch 2.40.38 账本 |
| `docs/plans/2026-08-06-monolith-relief-todoplan.md` | 巨石 M* · **挡路才拆** |
| `REFACTORING_PLAN.md` | **Superseded**（包布局 tracker 已替代） |

---

## 0. 类比（一句话给文科主理人）

仓库像 **消防规范齐全、分车间贴好门牌的片厂**：  
再贴标语（memory/lesson）收益递减；真正掉片的是 **总控台太厚**、**闸门偶发静默放行**、**假绿交付语义**、**多 agent 抢 5090**、**双 checkout 分叉**、**agent 读错旧 plan 重做**。

**优化 = 少事故、少废片、少假绿、少误工、更高有用 GPU%** —— 不是软化 IRON，也不是「全员压到 1500 行」。

---

## 1. 现状雷达（CTO 评分）

| 维度 | 成熟度 | 一句话 |
|------|--------|--------|
| 产品法条 / IRON | ★★★★★ | hard-defaults + 测 + memory 闭环；守住即可 |
| 内容质量门（抗无聊/接戏/脸/VO…） | ★★★★☆ | 08-06 专家团 P0 已机读；P1 残余按 ROI |
| 包边界 / shim 策略 | ★★★★☆ | W0–W7 + SHIM_POLICY 清晰；顶层仍有 ~93 厚模块待迁 |
| 出片诚实（plate≠master / final 假绿） | ★★★★☆ | A1–A5 + suse 回归已 ship；真片纪律仍要肌肉记忆 |
| 运维吞吐（5090 / until-empty） | ★★★☆☆ | 代码在、纪律在；真烧受 GPU/RAM 约束，须诚实 OPEN_OPS |
| 巨石可维护性 | ★★☆☆☆ | 74 个 ≥200 行函数；改 bug 成本高 |
| 错误 / 可观测纪律 | ★★☆☆☆ | FilmError 未统一；几乎无 logging；闸门 except 多 |
| CI / 可复现 | ★★★★☆ | check-all + secret-scan + lock；mypy 仅种子；slow 未必拦合 |
| 协作上下文税 | ★★☆☆☆ | plan/memory 发散 → token 与误工 |

**阶段判定：** 从「建能力」进入 **「稳态运营 + 工程代谢」**。默认预算 70% 正确性/诚实/运维，30% 结构债；禁止新开「第二套导演系统」。

---

## 2. 战略目标（90 天 North Star）

1. **首过可交片率 ↑**：新片 final 不可 1s 假绿；gate 红 → 强制 PARTIAL / plate，禁文案 master。  
2. **废片率 ↓**：毒镜 / 不回穿 / anti-hijack / face post_audit 在 promote 路径 fail-closed。  
3. **有用 GPU% ↑**：busy 零 submit；until-empty 仅独占；默认 `run-next --max 5`。  
4. **改 bug 速度 ↑**：触达巨石时有叶函数 + 表征测；每迭代迁 5–10 低 importer legacy。  
5. **协作误工 ↓**：单一执行板 + 双 checkout 纪律 + memory L5 废文。

### 成功指标（可机读优先）

| KPI | 基线（约） | 90 天目标 |
|-----|-----------|-----------|
| 假绿 final 回归 | 有测 | CI hotpath **必绿**；0 次生产 1s 假绿 |
| 闸门静默 `ok:True` | 多处 except | gates 热路径 **0** 静默放行 |
| ≥200 行函数 | 74 | **≤60**（只算 peel 净减，不虚荣） |
| 顶层 thick 模块 | ~93 | **≤70**（迁入 package + 薄 shim） |
| 基座测试 | core/util 起步 | core + util 公共 API **有测** |
| 出片 closeout | 部分 PARTIAL | 新片 ship-prep 红时 **字段诚实** 100% |
| GPU 结论 | 混合 | 每次 drain：**queue_empty 或 OPEN_OPS+原因** |
| Agent 重做已 ship | 仍发生 | 旧 plan 顶部 **CLOSED 指针** |

---

## 3. 铁律（非目标 / 禁止）

1. **不重开** ROI / Workflow / 包边界搬家 / 专家团 P0 五门 / A1–A5 绿地实现。  
2. **不**静默改 heat / pilot GO / `i2v_provider`。  
3. **不**虚荣「全员 <1500 行」或无表征测重写 `render_final` / `validate_film_spec`。  
4. **不**把 plate 刷成假 master；**不** soft 掉 IRON 换绿门。  
5. 行为变更与结构 peel **分 commit**。  
6. DONE = 测绿 +（指纹变）`lock-runtime` + CHANGELOG + 英文 commit；ops 无 GPU → **OPEN_OPS 诚实**。  
7. 只改 `git rev-parse --show-toplevel` 树；双 checkout **用 git 同步，禁手拷**。  
8. 圣旨短令 `go` = 按本 plan 当前 P0 链最小推进，不重开辩论。

---

## 4. 四大支柱 + Todo 波次

```text
支柱 A  正确性诚实 Correctness      ← 最高 ROI，先止血
支柱 B  运维吞吐   Operability      ← 有 GPU 日做；无则 OPEN_OPS
支柱 C  可维护代谢 Maintainability  ← 挡路 peel + 迁移节奏
支柱 D  协作减税   Collaboration    ← 便宜复利，穿插做
```

---

### Wave 0 · 治理钉板（0.5 天 · 必先 · 支柱 D）

| ID | Todo | 做法 | 验收 | 状态 |
|----|------|------|------|------|
| **G0.1** | **钉死本 CTO plan 为单一执行板** | 本 session plan 落档后，把 `docs/plans/2026-08-06-next-optimization-todoplan.md` header 改为 `SUPERSEDED → CTO plan`（或互指）；禁止第三块「综合板」 | 新会话只认一处 OPEN 表 | ✅ 2.40.42 |
| **G0.2** | **双 checkout 收敛** | plugins 为主可写；禁手拷 | 两树用 git 同步 | ✅ 2026-08-07 ff `~/.grok/ai-film-grok` → `c10cf4e`/`2.40.66` 链 |
| **G0.3** | **OPEN 冻结集 ≤12** | 从 memory inventory + 本 plan §4 抽出；其余 DEFERRED | 表在本档 §5 | ✅ 见下 |
| **G0.4** | **版本指针账实** | README/GRAPH 非 marker 硬编码 vs `plugin.json`；CI 可选 assert | `make sync-docs` + 抽检 | ✅ 2.40.73 CI assert |

---

### Wave 1 · 闸门止血 fail-closed（P0 · 1–2 周 · 支柱 A）

> 资深计划 P0-1：**闸门吞异常放行 = 正确性头号洞**。

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **A1.1** | **审计 `gates/` 静默 except** | 扫 `production_gates` / `preflight` / `cinematic_*` / `narrative_rebind` / `quality_gates`：`except` 后 `ok:True` / `return {}` / bare `pass` | 清单：文件:行 → 意图（降级 vs 必须红） |
| **A1.2** | **热路径改 fail-closed** | 先补表征测锁行为 → 改为 `{ok:False, reason}` 或 `FilmError`；**禁**为绿 CI 吞 | 相关 pytest 绿；无新 silent pass |
| **A1.3** | **promote / register 路径再压** | SCALE_* / anti-hijack / face post_audit 嵌套 decision 不漏 | 已有测巩固 + 缺口补 1–2 |
| **A1.4** | **final 假绿永不回退** | `test_suse_final_iron` + `test_final_hotpath` 留在 CI hotpath | CI 必跑；shim→main 断言在 |

**本周建议 3 个 PR：**  
1) gates 静默 except 子集 + 测  
2) final/hotpath 契约确认（防回退）  
3) 双 checkout 收敛 + plan header 指针  

---

### Wave 2 · 出片诚实与真片闭环（P0 eng · 持续 · 支柱 A）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **A2.1** | **新片默认路径 checklist** | stages/deliver 短指针：official-final-report / VO 三角 / BGM source / plate vs master | agent 出片不靠口头 |
| **A2.2** | **suse / 下一集 ship-prep 人链** | i2v_motion / five_track / gate-auto 红 → 修真因，不降 heat | ship-prep 绿 **或** PARTIAL 字段诚实 |
| **A2.3** | **衣着阶梯机读抽检** | 模型极限勿硬上；soft-max receipt；禁崩坏 blind promote | 1 条真片 promote 路径压过 |
| **A2.4** | **（触达时）sex-floor 不再静默 10s** | 与 `film_spec_sex_floor` 一致；短 H3 源不产不可 stretch 槽 | 回归测锁死 |

---

### Wave 3 · 运维吞吐（P0 ops · 有 GPU 才做 · 支柱 B）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **B3.1** | **Comfy 隧道 health** | `18188→8188`；down → 只写 OPEN_OPS | canary JSON |
| **B3.2** | **默认 max5；until-empty 须独占** | `--i-own-the-gpu` / env；busy 零 submit | 机读已有则只纪律+回执 |
| **B3.3** | **真烧 → queue_empty 或诚实停** | free-first 不杀外片；RAM 过低 DEFERRED_SAFE | `fill-idle-until-empty.json` |
| **B3.4** | **（可选）throughput-counters** | still scrap / I2V scrap / re-final 计数 | 单 JSON，勿新 IRON 段 |

**无空闲 5090 / 主机 RAM 见底：** 整波标 **OPEN_OPS**，**不算**工程失败。

---

### Wave 4 · 巨石「挡路才拆」（P1 · 支柱 C）

> 排序 = **风险 × 近期触达**，不是行数虚荣。每 PR **只拆一个入口函数/一个 stage**，先黄金主/契约测。

| 序 | 模块 | ~函数 LOC | 触发 | 拆法 |
|----|------|----------:|------|------|
| **C4.1** | `post/render_final::render_final` | 2456 | VO/mix/字幕/timeout/plate | stages → `final/*`（watchdog/plate-slot 已 peel） |
| **C4.2** | `plan/film_spec_validate::validate_film_spec` | 2322 | write-spec / sex floor / lint | 纯叶 projector；facade 已薄 |
| **C4.3** | `gates/preflight::run_preflight` | 1937 | 新门 / fail-closed 改造时 | 按 gate 族拆 report 函数 |
| **C4.4** | `spine/dispatch::build_dispatch` | 1249 | free-first / agent_do 触达 | 纯函数决策表 + 单测 |
| **C4.5** | export / closeout / cli_post | 700–800 | 双烧 / ship-prep bug | harness → builder |
| **C4.6** | heat residual | 文件已 facade | **仅** heat 码 bug | wardrobe/coitus pack；禁预防性全拆 |

**Iron：** public CLI 不变 · hard-compat shim · 行为与结构分 commit · `test_w3_package_shims` 不红。

---

### Wave 5 · 工程纪律统一（P1 · 2–4 周 · 支柱 C）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **C5.1** | **项目 logging** | `util.logger`；库代码禁 `print`；CLI 保留 stdout | 热路径 1–2 包试点 | ✅ 2.40.74 pilot skip_audit/gates/checkout_drift |
| **C5.2** | **FilmError 统一（增量）** | 新异常必继承；触达旧 `*Error` 时改基类 | 无大爆炸 PR | ✅ 2.40.76 hotpath RuntimeError×9 |
| **C5.3** | **JSON I/O 唯一入口** | 删本地 `read_json` 副本；`util.read_json` / `require_json` | grep 无新副本 | ✅ 2.40.77 facades + contract test |
| **C5.4** | **except Exception 纪律** | 必须 log+重抛或显式 partial；CR blocker | REVIEW_CHECKLIST 一条 | ✅ 2.40.76 checklist |
| **C5.5** | **subprocess timeout 触达补** | 不扫全仓 150 处；改到哪补到哪 | 触达点有 timeout | ✅ 2.40.79 util None→60 + contract |
| **C5.6** | **路径外部化** | 禁硬编码 `/Users/dex` `/opt/homebrew` | 0 生产路径硬编码 | ✅ 2.40.81 resolve_tool + contract |

---

### Wave 6 · Legacy 迁移代谢（P1–P2 · 持续 · 支柱 C）

> 代谢 inventory：Lane C MIGRATE + D PEEL。配方见 senior plan P3-1（选模块→定包→改 depth→dangling→1:1 测→commit）。

| ID | Todo | 节奏 | 验收 |
|----|------|------|------|
| **C6.1** | **低 importer 优先迁** | 每周 **5–10** 模块 → package + 薄 shim | metabolism inventory 更新 | ✅ safe queue empty · guard 2.40.78 |
| **C6.2** | **优先厚顶层** | `workflow_pack` / `input_fidelity` / `state_index_gate` / `prompt_injector` / `shortform_director`… | 归属 spine/gates/plan | IRON 禁 vanity；bug-driven peel only |
| **C6.3** | **Lane A 删除** | 0 import ∧ 0 CLI ∧ 0 test → 删 | 每 batch 报告 |
| **C6.4** | **基座测试补漏** | `core/*` `util/*` 公共 API | P4 延续；每模块 ≥ 契约测 | ✅ 2.40.78 media_ops/film_spec · 2.40.80 config_loader/gates |
| **C6.5** | **mypy 增量扩名单** | `make type` 每清一文件加名单；禁一次开全树 | 零新增错误 |

**当前厚顶层观察（启发式）：** `workflow_pack` ~2.2k · `input_fidelity` ~1.1k · `aifilm_grok` ~1k · 若干 prompt/director ~700–850。

---

### Wave 7 · CI / 可复现护栏（P1 · 支柱 C+D）

| ID | Todo | 验收 |
|----|------|------|
| **D7.1** | hotpath + secret-scan 保持 required | 合入不可跳 |
| **D7.2** | mypy job 与 `make type` 对齐（种子→扩） | CI 不红即可，不求全树 |
| **D7.3** | ruff 扩 `tools/`（若改 tools） | 触达才扩 |
| **D7.4** | 版本指针 CI assert（plugin.json vs README/GRAPH） | 防漂移 |
| **D7.5** | requirements.lock 与真实 import 收敛（可选 hash） | 克隆可装 |
| **D7.6** | （可选）slow 套件 nightly；非阻塞合入除非稳定 | 文档写清 |

---

### Wave 8 · 内容 / 工艺 ROI 残余（P2 · 产品日 · 支柱 A 尾）

> 只在工程 P0 不堵时做；**一次只挑 1–2 项**。

| ID | Todo | 说明 |
|----|------|------|
| **P8.1** | 首帧毒化 / 静帧压缩 → style_lock 默认硬锁 | 专家团 P1 残余 |
| **P8.2** | visual_bible 像素 palette（第二增量） | 第一增量已 ship |
| **P8.3** | sung 渲染期 LocalFallback 真接入 | provider 抽象已有 |
| **P8.4** | multi-seed anti-hijack 默认肌肉记忆 | 机读已有；人审纪律 |
| **P8.5** | 长片 SOP / material fidelity 新片抽检（C7） | 纪律卡，少代码 |

---

### Wave 9 · 上下文与仓库卫生（P2 · 支柱 D）

| ID | Todo | 验收 |
|----|------|------|
| **D9.1** | memory active 只留指针卡；长文 archive | active 稳定 ≤~35 |
| **D9.2** | 过期 optimization plan → archive + CLOSED 指针 | 无第二「综合板」 |
| **D9.3** | artifacts：canary JSON 可入仓；大 `.log` 勿 add | .gitignore 复核 |
| **D9.4** | process-slim / nutrient L5 废文 | 已 L4 的 lesson 可缩指针 |
| **D9.5** | pytest 标记再分层（fast/hotpath/slow） | 本地反馈 <2min |

---

## 5. OPEN 冻结集（≤12 · 真队列）

| ID | 主题 | 波次 | 优先级 |
|----|------|------|--------|
| 1 | gates 静默 except → fail-closed | A1 | **P0 · 2.40.67** heat-final 收据写盘 fail-closed + skip_audit pilot；2.40.66 state_index ladder |
| 2 | final/hotpath + plate≠master 永不回退 | A1/A2 | **P0** |
| 3 | 双 checkout + 单一执行板 | G0 | **P0 · G0.2 ✅** 2026-08-07 git ff 对齐（禁手拷） |
| 4 | 真片 ship-prep 人链 / 诚实 PARTIAL | A2 | **P0** · honesty-rail R0–R5 CLOSED 2.40.75（skip 触达 + closeout PARTIAL） |
| 5 | 5090 drain 或 OPEN_OPS | B3 | **P0 ops** · eng-day canary OPEN_OPS ✅ 2.40.76 round2 |
| 6 | 触达式 peel：final / validate / preflight | C4 | **P1** |
| 7 | logging + FilmError + JSON I/O 增量 | C5 | **P1** · C5.1–C5.6 ✅ 2.40.81 |
| 8 | legacy 迁 5–10/周 + 基座测 | C6 | **P1** · C6.1 empty ✅ · C6.4 ✅ 2.40.78–80 · 余 C6.5 mypy |
| 9 | CI 版本指针 + mypy 扩 | D7 | **P1** |
| 10 | subprocess timeout 触达补 | C5.5 | **P1** · ✅ 2.40.79 util/compose default |
| 11 | 内容 P1：毒化硬锁 / sung 接入（选一） | P8 | **P2** |
| 12 | throughput-counters / provider 429 签名 | B3.4 / 延后 | **P2 deferred** |

**铁律内化子集（并入支柱 A，详表见 iron plan）：** I1 假绿（anti-hijack 全入口 · variety 像素 · plate-boring · mix）· I2 人证 harden（anatomy attestation · speaker hard · material hard）· I3 上下文。I0 账实 **2026-08-07 ship**。

**明确 DEFERRED：** Job-graph 超 final、lipsync 复活、FRW 替换 h3_primary、全仓 except 扫荡、虚荣 LOC、hard-defaults 全量 markdown parser、假 CV 毒镜 Done。

---

## 6. 建议节奏（若你只说 `go`）

```text
工程日（无 GPU）默认链：
  G0.1–G0.2 → A1.1 审计 → A1.2 一个 gates 子集 PR → C6.1 迁 1–3 低 importer
  触达 bug 则夹 C4 peel 一片叶子 + 测

有独占 5090：
  B3.1 health → B3.2/3 drain → 回写 canary

出片日：
  A2 checklist + ship-prep 真因；禁大 peel 混进出片 commit

每周复盘 15 分钟：
  OPEN 表勾选 · inventory 刷新 · 旧 plan 有无误导 agent
```

**Top-5 ROI（只能做 5 件时）：**

1. **A1 闸门 fail-closed** — 正确性杠杆最大  
2. **I1 假绿内化（anti-hijack / variety 像素 / plate-boring）** — 门绿≠好看止血；见 iron plan  
3. **A1.4 / A2 final 诚实永不回退** — 防宿色类事故  
4. **B3 真烧或诚实 OPEN_OPS** — 吞吐不能只靠代码  
5. **C4.1 或 C4.2 在下次触达时 peel + 表征测** — 维护速度  

---

## 7. 资源与风险

| 风险 | 缓解 |
|------|------|
| peel 无测导致静默行为变 | 黄金主/契约测先于抽取 |
| 双远端/双 checkout 分叉 | fetch --all；禁 force；禁手拷 |
| 并行大改 74 巨石 | 每 PR 一个入口；资深 sign-off gates/media |
| 假 DONE（只写 plan） | DONE 强制测/canary/路径 |
| token 顶满 | `/compact`；长片 `/new`；memory 只指针 |
| 把 IRON 当可优化掉的限制 | 优化=守住+机读，不软化 |

**回滚：** 行为 PR 可 `git revert`；结构 PR 靠 shim 保持 import；runtime-lock 变更须成对提交。

---

## 8. Definition of Done（PR 合入 · 摘要）

1. 无新静默 `except: pass` / 闸门 `ok:True` 吞错  
2. 新函数复杂度可控（新增 ≤~80 行优先；>200 须说明+测）  
3. 新异常继承 `FilmError`（增量）  
4. JSON 走 util；无新本地 `read_json`  
5. 库代码不 `print` 业务（试点后强制）  
6. 逻辑改动伴测；`make check-all` 绿  
7. 功能变更 bump version + CHANGELOG；指纹变 `lock-runtime`  
8. 文档/plan 状态与代码 **账实一致**  

完整版可并入 `docs/REVIEW_CHECKLIST.md`（执行阶段做，本 plan 模式仅提案）。

---

## 9. 落档建议（你确认后执行）

| 动作 | 说明 |
|------|------|
| 写入仓库 | `docs/plans/2026-08-06-cto-optimization-todoplan.md`（本内容精简固化） |
| 旧板 header | next-optimization / optimization-todoplan → **RESIDUAL POINTER → CTO plan** |
| 可选 memory 短卡 | 三句 + 链本 plan；勿再写长 lesson |
| **不**自动开重构 | 等你 `go` 指定波次（推荐：G0+A1） |

---

## 10. 请你拍板（确认后退出 plan 即可执行）

1. **主攻轴（推荐 A）：**  
   - **A** 工程止血：G0 + A1 fail-closed + 低 importer 迁移  
   - **B** 运维日：B3 GPU（需独占）  
   - **C** 出片日：A2 真片 ship-prep  
   - **D** 全轴按 §6 默认链自动推进  
2. **是否允许** 无 GPU 时 B3 整波 OPEN_OPS 且仍算迭代完成？（推荐：**是**）  
3. **落档：** 是否把本 plan 写入 `docs/plans/` 并改旧板指针？（推荐：**是**）

---

*基线：`/Users/dex/.grok/plugins/ai-film-grok` @ 2.40.38 · 只读诊断 · 未改业务代码。*  
*角色：CTO 综合视角 = 产品诚实 × 工程代谢 × 运维吞吐 × 协作减税；非单一资深重构清单。*
