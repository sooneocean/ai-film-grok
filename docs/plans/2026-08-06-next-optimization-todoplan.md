# 若我来优化：ai-film-grok 代码库 Todo Plan（2026-08-06 · v2.40.12）

**Status:** **ACTIVE 单一执行板 · 2026-08-06 closeout 2.40.12（执行中）**  
W0–W1.5 · W4 诚实 except · W5 纪律卡 · W6 archive **SHIPPED** · W2 tunnel **up** + capacity canary（until-empty **DEFERRED_SAFE** 默认 max5）· W3 巨石仍 bug-driven only  
**副导演工序板：** [2026-08-06-ad-process-optimization-todoplan.md](2026-08-06-ad-process-optimization-todoplan.md)（Wave A–D 2.40.11）  
**Repo:** `/Users/dex/.grok/plugins/ai-film-grok`

**结论先行：** 这不是「缺功能」的仓库，而是 **片厂已建完、规章已上墙、车间仍塞着几个 3k–4k 行总控台** 的成熟产线。下一轮优化应以 **诚实出片 + 可维护热路径 + 运维吞吐** 为主，**禁止**再开「全员压到 1500 行」或「再写一套 IRON 散文」。

| 项 | 现状（本机探针） |
|----|------------------|
| 版本 | `plugin.json` **2.40.12** |
| 脚本 | ~**637** `.py` · scripts 树合计 ~**163k** LOC（含 shim） |
| 测试 | ~**406** `test_*.py` · 体量很大，绿线靠 `make check-all` |
| 文档税 | references ~**172** · memory active ~**42** · `docs/plans/*` 优化板 **20+** |
| 最大石 | `edit_policy_heat` **4024** · `film_spec` **3147** · `render_final` **2985** · `story_plan` **2948** · `export_composition` **2804** |
| 包边界 | W0–W7 **已 ship**（`core/post/narrative/audio/media/plan/cli…` + hard-compat shim） |
| 今日已 ship | 内容质量 P0 五门 · final 诚实/watchdog · shortform · GPU no-hog 机读 · 字幕 CJK · motion mean · BGM fatigue… |

## 0.1 A/B/C 执行映射（本轮快照）

- **A（已定性已收口）**：final 交付语义与 manifest 字段源已统一（`delivery_class`/`delivery_source`/`delivery_visibility`/`master_lock`），并且 queue `run-next` 缺条件有固定 `halt_reason_code + open_ops` 产出。
- **B（已增强可回放）**：`test_fill_idle_run_next_ledger.py` 与 `test_h3_until_empty.py` 已覆盖 run-next/ until-empty 的关键分支（busy、capacity、dry-run、执行成功路径）；`test_suse_final_iron.py` 新增 OFFICIAL_FINAL_PLATE 与 TECHNICAL_FINAL 语义回归。
- **C（本轮可执行块）**：把 C1 queue 真烧改为 `queue_empty` 收口（需独占 GPU 条件满足）、并保持文档状态与 tests 对齐后继续执行 W3 巨石 bug-driven peel。

**与旧板关系：** 本 plan 是 **「独立诊断 + 下一轮执行序」**，不取代历史档案；已 CLOSED 的板只当证据，不重开。

| 旧板 | 角色 |
|------|------|
| `docs/plans/2026-08-06-optimization-todoplan.md` | 产品/出片 A–G 波；**A1–A5 等已 ship**，C1 OPEN_OPS |
| `docs/plans/2026-08-06-codebase-quality-todoplan.md` | 工程质量 **CLOSED 2.39.95** |
| `docs/plans/2026-08-05-residual-monolith-w4-todo.md` | 巨石历史 wave · **bug-driven peel only** |
| `docs/plans/2026-08-06-monolith-relief-todoplan.md` | **巨石诊断 + M0–M6 执行队列**（M0 SHIPPED 2.40.10） |
| `docs/optimization-plan-2026-08-06.md` | 内容五域 P0 **已落地 2.40.7+** |
| `docs/plans/2026-08-06-memory-optimization-inventory.md` | 记忆反查 · 类 C 真 OPEN |

---

## 1. 诊断：我会改什么 / 不改什么

### 1.1 类比

仓库像 **消防规范齐全的片厂**：

- 再贴标语（memory/lesson）收益递减；
- 真正掉片的是 **总控台（orchestrator）太厚**、**假绿交付语义**、**多 agent 抢 5090**、**双 checkout 分叉**；
- 优化 = 少事故、少废片、少「门绿但难看」、少 agent 读错旧 plan。

### 1.2 健康处（不要动）

1. **法条 IRON** 已进 hard-defaults + 测（成人 MAX、毒镜、不回穿、字幕硬烧、anti-hijack、GPU no-hog…）  
2. **包目录 + shim 策略** 清晰（`docs/SHIM_POLICY.md`）  
3. **CI / check-all / secret_scan / hotpath** 已对齐  
4. **JSON / volume / retry** 主路径收敛（util + core.media_ops）  
5. **产品能力面**：dispatch / H3 / final / gates 完整

### 1.3 真痛点（我会排期的）

| 痛点 | 为什么痛 | 杠杆 |
|------|----------|------|
| **P0 交付诚实** | 宿色等真片仍可能在槽长/口白/plate 语义上翻；代码补了但 **回归与新片纪律** 未成为肌肉记忆 | 出片首过率 |
| **P0 运维 OPEN_OPS** | until-empty / fill-idle **代码在、真烧少**；Comfy 隧道 down 时只能记 canary | GPU 有用率 |
| **P1 巨石改不动** | heat/film_spec/render_final/export 仍 3k–4k；**触达成本高、覆盖偏低** | 改 bug 速度 |
| **P1 plan 文档发散** | 20+ optimization plan + 状态过期 → agent **重做已 ship 项** | token + 误工 |
| **P1 双 checkout** | `~/.grok/ai-film-grok` vs `plugins/ai-film-grok` 分叉风险（AGENTS 已警告） | 改错树 |
| **P2 热路径尾巴** | 大量 `except Exception` / bare `subprocess`；主路径已 timeout，边缘仍可能 hang/silent | 过夜可靠性 |
| **P2 上下文税** | 407 测 + 172 refs + 42 memory；冷启动 agent 易吃满 | 协作效率 |

### 1.4 明确非目标

- 虚荣 LOC 冲刺 / 全仓 FilmError 迁移  
- 静默改 heat / pilot / `i2v_provider`  
- 重写 references 全书 / 软化 IRON  
- 用 FRW 替换 h3_primary 默认  
- 把 plate 刷成假 master  
- 再开绿地「专家团 P0 五门」（**2.40.7 已做**）

---

## 2. 优化原则（若我主理）

1. **默认只做类 C 残余 + 真片翻车闭环**；类 A IRON 只守不拆。  
2. **行为变更与结构 peel 分 commit**。  
3. **巨石只在挡路时 peel**（先抽纯函数 + 单测，再动 orchestrator）。  
4. **DONE = 测绿 +（指纹变则）lock-runtime + CHANGELOG + 英文 commit**；ops 项无 GPU 则 **OPEN_OPS 诚实收工**。  
5. **单一执行板**：新会话只认本 plan + hard-defaults；旧 plan header 指向本档。  
6. **圣旨短令 `go`** = 按 §4 当前 P0 链最小推进，不重开辩论。

---

## 3. 成功定义（一迭代结束）

| 标准 | 信号 |
|------|------|
| 新片 final 不可 1s 假绿 / plate≠master 机读 | closeout + official-final-report 字段绿 |
| 至少一次诚实 GPU 结论 | `queue_empty` **或** `OPEN_OPS` canary + 原因 |
| 触达巨石时有叶函数 + 测，无「只搬家」PR | residual-monolith 勾选 + 测 |
| agent 不再按过期 plan 重做 A1–A5 / quality P0 | 旧 plan 顶部 **CLOSED → 指针** |
| `make check-all` 绿 | 工程纪律 |

---

## 4. Todo 波次（可勾选）

### Wave 0 · 账实与执行入口（半天 · 必先）

> 类比：开工前先钉哪块白板是「今日任务」，旧白板写「已结案」。

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **W0.1** | **单一执行板钉死** | 确认本 plan 落 `docs/plans/2026-08-06-next-optimization-todoplan.md`（或刷新既有 08-06-optimization header 状态到 2.40.12） | ✅ 旧板 RESIDUAL POINTER → 本档 |
| **W0.2** | **刷新巨石 LOC 表** | residual-monolith 表改为本机数字（heat 4024 / film_spec 3147 / render_final 2985…） | ✅ 2.40.12 `wc -l` |
| **W0.3** | **双 checkout 纪律一页** | AGENTS 已有；加「本 session `git rev-parse` 自检」到 CONTRIBUTING 或 doctor 提示 | ✅ CONTRIBUTING |
| **W0.4** | **OPEN 清单冻结** | 从 memory inventory 抽出 ≤15 条 C 类 → 本 plan §4；其余标 deferred | ✅ §4 即冻结集 |

**W0 SHIPPED（2.40.12 closeout）.**

---

### Wave 1 · 出片诚实回归（P0 eng · 1–2 天）

> 宿色 EP01 类事故：代码 A1–A5 多已 ship，**缺的是回归 harness + 新片默认路径不会回退**。

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **W1.1** | **final 入口契约测常驻** | 确保 `test_final_hotpath` / shim→main 断言在 CI hotpath；缺则补 | ✅ `test_suse_final_iron` A3 + `test_final_hotpath_contracts` |
| **W1.2** | **短 H3 源 + sex floor 回归** | fixture：~5s take + low ratio → **不**静默 10s 不可 stretch 槽 | ✅ `test_suse_final_iron` + `plan/film_spec_sex_floor` |
| **W1.3** | **口白窗三角回归** | `tts ≤ cue ≤ slot` 失败路径给 next_cmd | ✅ `check_vo_window_triangle` 单测 |
| **W1.4** | **plate vs master closeout** | gate 红 / skip → 强制 PARTIAL 字段；禁 final_complete | ✅ shortform S1.4 已 ship；`official_final` 语义回归见 `test_suse_final_iron.py` |
| **W1.5** | **真片抽检清单（文档）** | stages/post 或 deliver 短指针：official-final-report / final-timeout / BGM source | ✅ deliver.md + `test_suse_final_iron.py` 已覆盖 `OFFICIAL_FINAL_PLATE`/`TECHNICAL_FINAL` 字段 |

**不做：** 重写 render_final 整文件。

---

### Wave 2 · 运维吞吐（P0 ops · 等人+GPU）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **W2.1** | **Comfy 隧道 health 先** | `18188→8188` doctor/canary；down 则只写 OPEN_OPS，不假执行 | ✅ `artifacts/2026-08-06-w2-comfy-health-canary.json`（18188 up） |
| **W2.2** | **独占 until-empty** | variety 绿片 + `--i-own-the-gpu` + free-first；默认 `run-next --max 5` | **DEFERRED_SAFE**（pending=6 · 主机 ram_free≈14MB 不启长烧） |
| **W2.3** | **双片 drain 纪律回执** | 不 cancel 外片；busy 零 submit；禁 pgrep 脚本源码误杀 | 纪律在 hard-defaults/memory；本轮未误杀 |
| **W2.4** | **（可选）throughput-counters** | 片根 still scrap / I2V scrap / re-final 计数 JSON | deferred |

**W2 诚实收工：** tunnel 通 + capacity-plan 绿；**未**假报 queue_empty。

---

### Wave 3 · 巨石「挡路才拆」（P1 structure）

**完整诊断 + 可勾选 M 队列：** [2026-08-06-monolith-relief-todoplan.md](2026-08-06-monolith-relief-todoplan.md)（**M0 SHIPPED**）。  
排序 = **风险 × 近期触达**，不是行数虚荣。

| 序 | 模块 | ~LOC | 触发条件 | 拆法 | M-id |
|----|------|-----:|----------|------|------|
| **W3.1** | `plan/film_spec.py` | 3147 | 再动 sex floor / validate / write-spec | validate 叶 + projectors；sex_floor 已存在 | M1 |
| **W3.2** | `post/render_final.py` | 2985 | 再动 VO/mix/subtitle/timeout | 加深 `final/*` stages；orchestrator 只编排 | M2 |
| **W3.3** | `post/export_composition.py` | 2804 | 字幕双烧 / HF export bug | harness 测优先，再 peel | M3 |
| **W3.4** | `media/h3_fill_idle.py` | 2300 | capacity / until-empty 逻辑再变 | cycle vs plan 分离 | M5.1 |
| **W3.5** | `narrative/edit_policy_heat.py` | 4024 | **仅** heat 码 bug | pack 级 peel；禁预防性全拆 | M4 |
| **W3.6** | `cli/cli_post.py` / `cli_media.py` | 2.4k/2.1k | 子命令继续膨胀 | 按 verb 再抽，保持 public 字符串 | M5.4 |

Iron：public CLI 不变 · shim hard-compat · 每 peel 独测 · 与行为变更分 commit。

---

### Wave 4 · 反脆弱尾巴（P1 eng · 可穿插）

| ID | Todo | 验收 |
|----|------|------|
| **W4.1** | `media_queue` 等热路径 `except Exception` 审计 → warning/partial，禁 silent pass | ✅ validate fallback + pilot load → `note_queue_partial` |
| **W4.2** | 再触达的 bare subprocess 补 timeout（**不**全仓 150 处冲刺） | deferred（未触达新 subprocess 点） |
| **W4.3** | provider 质量拒 vs 429 签名再审计（inventory C12） | deferred |
| **W4.4** | doctor：假 plate 当 master 的 soft advisory | deferred（deliver 清单已覆盖人读） |

---

### Wave 5 · 导演工艺默认（P1 process · 少写代码）

| ID | Todo | 说明 |
|----|------|------|
| **W5.1** | multi-seed **强制** anti-hijack 纪律 | ✅ stages/agent.md 快卡 |
| **W5.2** | design-go / script-value-debrief 出片前存在 | ✅ agent 快卡 |
| **W5.3** | 对白主链：原音优先，禁后期对嘴复活 | ✅ agent 快卡 |
| **W5.4** | 内容质量 P1 深化（按 ROI 选 1–2） | deferred（2.40.7–9 已 ship 多门；本轮不新开产品） |

---

### Wave 6 · 上下文与仓库卫生（P2 · 便宜但复利）

| ID | Todo | 验收 |
|----|------|------|
| **W6.1** | memory：active 只留指针卡；长文 archive | deferred（已 ~42；未再砍） |
| **W6.2** | `docs/plans` 归档目录 `plans/archive/` 移 7 月 CLOSED 板 | ✅ 18 板入 archive + README |
| **W6.3** | process-slim 残余（inventory C13） | deferred |
| **W6.4** | artifacts 日志/canary 是否进 git 审计 | canary JSON 入仓；大 .log 勿 add |
| **W6.5** |（可选）pytest 标记再分层 | deferred |

---

## 5. 建议执行序

```text
缺 GPU / 纯工程日：
  W0 账实 → W1 final 回归 → W3 仅当 W1 碰文件顺手 peel → W4 尾巴 → W6 卫生

有独占 5090：
  W2.1 health → W2.2 until-empty → 回写 memory 短卡

内容/导演日：
  W5 纪律 + 最多 1 条 P1 产品深化（勿与 W3 大 peel 同 PR）

默认 `go` 最小链：
  W0.1–W0.2 → W1.1–W1.2 测绿 → commit →（有卡）W2
```

---

## 6. 风险与回滚

| 风险 | 缓解 |
|------|------|
| peel 引入 import cycle | 先纯函数无 I/O；参考 heat↔shared 教训 |
| 行为变更混进 move | 分 commit；review checklist |
| 改错 checkout | W0.3；只改 `git rev-parse` 树 |
| 假 DONE（只写 plan） | DONE 定义强制测/canary |
| token 再顶满 | W6 + `/compact`；长片 `/new` |

---

## 7. 我个人的 Top-5 ROI（若只能做 5 件）

1. **W1.2 短源 sex-floor 回归锁死** — 防止宿色类 stretch 再炸  
2. **W1.1 final 入口 hotpath 契约** — 防 1s 假绿  
3. **W0 plan 账实** — 阻止 agent 重做已 ship  
4. **W2 真烧或诚实 OPEN_OPS** — 吞吐问题不能只靠代码  
5. **W3.1 film_spec 在下次触达时 peel sex floor** — 唯一值得预防性拆的边界（与 W1.2 同文件）

---

## 8. 实现时注意（仓库惯例）

- 功能变更：bump `plugin.json` + CHANGELOG（英文 commit）  
- 脚本指纹：`make lock-runtime`  
- 装机：`grok plugin update ai-film-grok`  
- 制度/hard-defaults：先 `~/.grok/backups/`  
- 非琐碎收尾：`verifier` subagent  
- 沟通中文 · 结论先行  

---

## 9. 请你拍板（确认后可执行）

1. **主攻轴：**  
   - **A（推荐）** 工程日：W0 + W1 回归 + 触达式 W3  
   - **B** 运维日：W2 GPU drain（需独占）  
   - **C** 产品日：W5 + 一条内容 P1  
2. **本 plan 落档路径：** 默认 `docs/plans/2026-08-06-next-optimization-todoplan.md`，并把旧 08-06-optimization 标 residual pointer。  
3. **是否允许** 在无 GPU 时把 W2 整波标 OPEN_OPS 并从「迭代完成」定义里拿掉（推荐：**是**）。

---

*分析基线：plugins checkout `ai-film-grok` @ 2.40.12 · 2026-08-06 · 只读探针，未改业务代码。*
