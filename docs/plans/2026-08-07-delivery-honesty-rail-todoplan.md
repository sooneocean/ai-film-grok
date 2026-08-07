# 出片诚实审计轨 Todo Plan（真洞审计 · 2026-08-07）

**结论先行：** 记忆与教训体系已成熟，I0–I4 铁律内化已 SHIPPED（实码 v2.40.61）。剩余真洞**不在任何板的 OPEN 集**：SKIP 逃生**无运行期记账**（全树 112 处读 `AIFILM_SKIP`，无中央 helper 可 hook）· 人证**无溯源** · 双 checkout 漂移**无探针** · I5 运维残余半吞吐。本板 = **出片诚实审计轨**（新子板，挂 CTO 下，不另起第三综合板）。

**类比：** 喷淋系统装齐了，但「把警铃关掉的动作」没人记录。本板要给**每一个关警铃的动作**装牌子 + 收尾清点。

| 项 | 值 |
|----|-----|
| Status | **Active** · 2026-08-07 R0+R1 partial ship· 主执行板 [CTO](2026-08-06-cto-optimization-todoplan.md) |
| Repo | `ai-film-grok`（target）· 版本探针 `plugin.json` = **2.40.67**（本轮） |
| 内化子板 | [iron](2026-08-07-iron-internalization-todoplan.md)（I0–I4 产品链 CLOSED · I5 ops 待收编） |
| 养分对账 | [nutrient-matrix](2026-08-06-nutrient-matrix.md) |
| 治理 | [MEMORY_GOVERNANCE](../MEMORY_GOVERNANCE.md) |
| 执行姿势 | **ulw**：场景契约 + RED→GREEN→SURFACE + 真机验收 + reviewer gate |

---

## 0. 五问卡（每洞：A/B/C · L 阶 · 挂载层 · 人判）

| 洞 | 类 | L | 挂载层 |
|----|----|----|--------|
| SKIP 记账 | **C 真 OPEN** | 目标 **L3 机读** | validate / dispatch / **render** / **closeout** |
| 人证溯源 | **C 真 OPEN** | 目标 **L3 机读** | queue / promote · render |
| checkout 漂移 | **C 真 OPEN** | 目标 **L4 必查** | doctor（ops） |
| I5 运维残余 | **C 半吞吐** | 目标 **L3–L4** | dispatch / queue |
| 板间账实 | **C 纪律** | L5 行为 | 每周 reconcile |

**人判边界**永远保留：pilot / PK / review-final 不机器代签；「缺记录的人证」= 待判定，不自动绿。

---

## 1. 真洞清单（证据 · 防重复提案）

| # | 洞 | 证据 | 为何无人认领 |
|---|-----|------|--------------|
| 1 | **SKIP 逃生无记账** | `hard-defaults` 列 21 个 `AIFILM_SKIP_*`；`grep` 全树 **112 处**读 `AIFILM_SKIP`；治理禁默认 SKIP，但无法 enforce 到运行期 | 每门独立 `read`，无中央 helper |
| 2 | **人证无溯源** | `anatomy_safe`/`speaker` 靠字段 attestation；真 CV 已后置 → 轻量溯源现可做 | 缺 provenance 契约 |
| 3 | **双 checkout 漂移无探针** | G0.2 纪律仅手动；AGENTS 明写两 checkout 已分叉 | 无 `doctor checkout-drift` |
| 4 | **I5 运维残余** | soft hog / 禁 pgrep 源码匹配 / canary 停在 iron 板 OPEN | 归 ops，无 GPU 则 OPEN_OPS |
| 5 | **板间账实漂移** | iron「I1.4 pending」vs nutrient「✅」；CTO header 2.40.42 vs 实码 2.40.61 | G0.4 未激活 |

---

## 2. 非目标

- 第二套 hard-defaults / 假 CV 当 Done（忌讳——假 Done）
- 全树 112 处一次性全清（触达式 vs 一次 wave 爆改）
- 软化 IRON 换绿门 / 默认设 SKIP
- 巨石 peel 与 logging 大跃迁（C4/C5 已认领）
- 新开「第二套导演系统」（stage 判定 C4）

---

## 3. Todo 波次（执行链）

### Wave R0 · 账实钉板（先 · 支柱 D）

| ID | Todo | 验收 |
|----|------|------|
| R0.1 | 本 plan 顶部 `Status` 标记为 `Active`；与 CTO「OPEN 冻结集」互映 | 两板 header 账实一致 | ✅ 2.40.67 |
| R0.2 | 补 diff：版本号对齐实码；iron 板 I1.4/I1.1 pending↔✅ 对齐 | reconcile 一次 | ✅ 2.40.67 pointer |

### Wave R1 · SKIP 逃生记账闭环（P0 · 支柱 A）

**U1（洞 1）** `scripts/core/skip_audit.py`（新）：
- `skip_flag(name, *, origin)` → bool；首次读取写 `receipts/skip-usage.json`（name/source/call_site/file/ts/film_root）
- 统一 CLI 逃生（继续 `--skip-*`）→ 收进同一 ledger
- 统一经原生 JSON emit，closeout 汇总清单

**接入点 A** `scripts/post/closeout.py`（主接入点）
- 收尾时 `verify_skip_usage`：汇总本片所有 SKIP + 是否带 `skip_reason`
- **IRON 级 SKIP 无理由 → 交付拒 cert + 降 PARTIAL**（hybrid 硬规则核心）
- `official-final-report.json` 增 `skips_used:[...]` 字段

**接入点 B** `scripts/gates/cinematic_gate.py`
- 重跑 gate-auto 时列本片忽略清单；gates 改用 `skip_flag` 中央读

**场景契约（test / receipt 字段）**

| 事件 | 断言 |
|------|------|
| `skip_flag` 读首次写入 usage | `receipts/skip-usage.json[name]` 出现 |
| 同 env 再次读不重复记账 | usage 计数 = 1（幂等） |
| 非 IRON 级 `--skip-option` 无理由 | 允许但报收到录 |
| IRON 级 SKIP 无理由 at closeout | 拒绝 cert，`classification=PARTIAL` |
| IRON 级 SKIP + 有 `skip_reason` | 收据 + 列出，不拦（合法逃生） |
| 未设任何 SKIP 片 | `skips_used=[]` 完全干净 |

**Test file：** `skills/ai-film-grok/tests/test_skip_audit.py` · **PARTIAL SHIP 2.40.67:** `core/skip_audit.py` + heat-final/cinematic pilot + closeout `verify_skip_usage` step（`test_opt_round_a1_heat_final_receipt.py`）
**Execution note：** 首个 test 先 RED（断言 usage.json 有写入）→ GREEN；`skip_flag` 试点应用在 `closeout` + `cinematic_gate` 两条 hot 路径，其余 112 处触达式进 follow-up（非本板全清）。
**Non-target：** 不与 `I4.2 iron-status`（静态列门 + 逃生 env 表）撞车；本板管**运行期记账**，I4.2 管静态清点，只引用不重复。

### Wave R2 · 人证溯源（P1 · 支柱 A 尾）

- **做法：** 现有人证字段写成来源；落地 `anatomy_safety.py` / `dialogue_speaker_frame_gate.py`（触达处）的人证写入 `receipts/attestation-*.json`，带 provenance：`agent_session / reviewer / timestamp / still_path`。
- **受影响文件：** `skills/ai-film-grok/scripts/anatomy_safety.py` · `skills/ai-film-grok/scripts/dialogue_speaker_frame_gate.py` · `skills/ai-film-grok/scripts/post/closeout.py`（读聚合）
- **Test：** `test_attestation_provenance.py`
- **Scenarios：**
  - happy：`anatomy_safe=true` → 回执带 4 个 provenance 字段全部非空
  - edge：缺 provenance（如 batch 自动填而 reviewer 缺）→ 标记 `pending_human_review`，不假来源
  - regression：不破坏现有 `closeout` 三轨 hash / S 分逻辑
- **Non-goal：** 不做真 CV 毒镜分类器（板已 DEFERRED）；只把现有 attestation 做成可回查，不把「人判」自动化成「机器判」。

### Wave R3 · 双 checkout 漂移探针（P1 · 支柱 B/D）

- **做法：** `scripts/post/post_doctor.py` 加 subcommand `checkout-drift`（或 `scripts/cli_doctor.py`，以实现着定）；比较两树 `git rev-parse --show-toplevel` + 相对 HEAD 未提交/未推送文件清单（仅 `git status` / `git rev-list`，不做文件比对）；有未提交工作 + 两树 rev 不等 → 警告 + 列出差异文件（**禁手拷同步**提示）；非 git 环境（plugin validate 或 CI）→ 降级 SKIP 不失败。
- **Files：** `scripts/post/post_doctor.py`（或 `cli_doctor.py`）· test
- **Test file：** `test_checkout_drift.py`
- **Scenarios：**
  - happy：两树同步 → 输出 `clean`
  - edge：plugins 领先未提交 → 警示 + 文件清单，非零 exit 但 info
  - non-git 根 → warn，不破 doctor ok（`doctor` 保持绿）
- **Execution note：** characterization-first，先跑现 `doctor` 的既有测试锁行为，再新增 subcommand。

### Wave R4 · I5 运维收编（IRON 子板 I5 残余收编）

| ID | Todo | Files | 验收 |
|----|------|-------|------|
| R4.1 | 收紧：`--until-empty --execute` 须 `--i-own-the-gpu` 的现状 + 软 hog（`run-next`）契约测加固 | `scripts/media/next_*` 相关 | `test_run_next_soft_hog.py` green |
| R4.2 | 禁 `pgrep -f` 源码匹配（宽匹配）审计：未清 → 全部改片路径 + 加测 | `scripts/media/` 相关批次 | `test_pgrep_no_source_match.py` green |
| R4.3 | 真片 canary：drain 结束 → `queue_empty` 或 `OPEN_OPS+reason` 机读回执 | `scripts/media/h3_fill_idle.py` 邻近 | `test_openops_receipt.py` green |

**Non-goal：** I5 其余 deferred（真机无 GPU 时直接 bail 并记 OPEN_OPS，不算工程失败）。

### Wave R5 · 记录卡（P2 · doc）

- **板间 reconcile：** 每周（`go next` 日）对一眼 CTO / iron / nutrient header vs `plugin.json` 的 pending/pass 标志，账实对齐建议。
- **memory** 一条 P0 指针卡（three-line → `skills/ai-film-grok/memory/2026-08-07-delivery-honesty-rail.md`），链接本 plan；hard-defaults 加一行：SKIP 必须被记账。

---

## 4. `go` 默认链

```text
R0 账实 → R1（先 skip_audit.py 测试）→ R1 closeout 混合拒 → R2 溯源 → R3 checkout → R4 I5 → R5 记录卡
```

- **工程日（无 GPU）：** R0→R1→R2→R3
- **有 GPU 出片日：** 先出片才 R1–3；R4 在 drain 时顺做（写回 canary），不抢占
- 每次 commit：**行为与结构分** · 英文 message · `make check-all` · 可能 `lock-runtime`
- **完成定义（与 CTO §8 一致）：** 无新静默 except · 新增 helper 有测 · 逻辑拆隔离 `FilmError` · JSON 走 util · 0 生产路径硬编码 · gate 逃生必写 receipt

---

## 5. ulw 契约（执行时严格遵守）

- **每 unit 先写 test（名称含 `test_`）：RED → 见红 → GREEN → 见绿**，不得跳步。
- **SURFACE（真机面）：** R1 实际设 `AIFILM_SKIP_*` → 跑一次 `closeout`/`gate-auto` → 看 `receipts/skip-usage.json` + final report；R3 `doctor checkout-drift` 真跑。
- **Cleanup：** 每次跑完清 `/tmp` 临时、回执文件残留要列、无驻留进程/端口。
- **Reviewer gate：** 所有 unit 完成后跑 `ce-code-review` 对 diff 高严格一轮；每个 blocker 只认 criterion 命中，notes 不 blocker。

---

## 6. 验收证据

把每个 unit 的 test log 期望、SURFACE 路径、`receipts/` 产物记在 `docs/reports/2026-08-07-honesty-rail-evidence.md`，最终回报路径 + 三行摘要。
