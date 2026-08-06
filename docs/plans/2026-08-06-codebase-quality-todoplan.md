# ai-film-grok 代码库工程质量 & 团队技术能力优化迭代 Todo Plan（2026-08-06）

> **作者角色**：Senior Developer（高级开发工程师）— 资深全栈 / 代码质量把控
> **结论先行**：本仓库**功能与产线规则已成熟**（见既有 `2026-08-06-optimization-todoplan.md`，那是「产品/出片」迭代板）。本档是**互补的另一面**——聚焦**代码库工程质量、技术债、测试纪律与团队能力 uplift**。一句话：规则不缺，缺的是「把规则变成机器门禁 + 把质量把控变成团队习惯」。

**Status（2026-08-06 round-2）:** Q0–Q2 底座 **SHIPPED** · residual volume **SHIPPED** (2.39.92) · edge `util.retry` sample **SHIPPED** · gate hotpath tags **SHIPPED** (2.39.91)  
**仓库真相：** `/Users/dex/.grok/plugins/ai-film-grok`  
**plugin：** 见 `plugin.json`（本轮 bump **2.39.92**）

### 账实快照（勿按旧段落重做）

| 项 | 状态 |
|----|------|
| `docs/CONTRIBUTING.md` / `REVIEW_CHECKLIST.md` | **DONE** |
| CI secret scan (`scripts/secret_scan.py`) | **DONE** |
| CI hotpath job | **DONE** |
| IRON coverage table | **DONE** `docs/reports/2026-08-06-iron-gate-coverage.md` |
| hotpath markers | **DONE**（≥6 test files；旧文「0 处」过时） |
| `core.hooksPath=.githooks` | **DONE**（`make install-hooks`） |
| 本地 `check-all` 镜像 CI（secret-scan + hotpath） | **DONE**（`scripts/check-all.sh` 2.39.92：本地绿线 ≡ CI = validate+ruff+doctor+pytest not-slow+secret-scan+hotpath） |
| `util.read_json_source` + semantic_index | **DONE** |
| volume probe → `core.media_ops` | **DONE** 含 canary/quality_check/reference_audit（2.39.92） |
| `util.retry` | **DONE** 工具 + **edge TTS 样板**；media_queue 等 OPEN |
| heat↔policy sys.modules | **OPEN** bug-driven |
| 虚荣 peel | **NON-GOAL** |

---

## 1. 本次分析证据地图（量化）

| 维度 | 观察 | 证据 |
|------|------|------|
| 巨型模块 | `edit_policy_heat.py` 4034、`film_spec.py` 3156、`render_final.py` 2869、`story_plan.py` 2858、`export_composition.py` 2804、`edit_policy.py` 2667、`cli_post.py` 2387、`workflow_pack.py` 2177、`h3_fill_idle.py` 2131 行 | `find … -name '*.py' -exec wc -l` |
| 重复探针 | `volumedetect` / `probe_native_audio_mean_volume` 在 **8 个文件**复制 | `core/media_ops.py:51-61`、`aifilm_grok.py:67,74-80`、`media/h3_ship_native.py:113-116`、`media/h3_workflow.py`、`post/compose_render.py`、`elevenlabs_canary.py`、`quality_check_video.py`、`reference_audit.py` |
| 单一真相违规 | `semantic_index.py:127` 自写 `_read_json_source`，未用 `util.read_json`/`require_json` | 违反 AGENTS 第 82 条 |
| 反劫持闸被绕过 | `composition_anti_hijack.py` 是唯一定义闸（含 `AIFILM_SKIP_ANTI_HIJACK`），但 mean/volume 仍被多处用作 promote 信号 | `composition_anti_hijack.py:1-10` 注释明示 |
| 循环导入 hack | `edit_policy_heat ↔ edit_policy` 靠 `sys.modules.get(...)` 运行时探测打破 | `edit_policy_heat.py:13-30` |
| 重试逻辑散落 | retry/backoff 散落 ≥14 处（media_queue×14、h3_combo_eval、frw_lipsync、grok_oauth、tts_backend…），无共享工具 | 多文件 grep |
| hotpath marker 失效 | `@pytest.mark.hotpath` **0 处实际使用**（仅 CHANGELOG 提及）；`make test-hotpath`(`-m "hotpath and not slow"`) 选 0 测试 | `pyproject.toml:30` 声明；`grep -rn '@pytest.mark.hotpath'` 仅 CHANGELOG 命中 |
| 门禁信任缺口 | `.githooks/pre-push`（secret scan + release gate）存在，但 `git config core.hooksPath` **未设** → 本地 push 不触发；AGENTS 第 11 步「pre-push 默认 light」不实 | `git config --get core.hooksPath` 空；`.githooks/pre-push:15-27` |
| 测试密度 | 3342 测试 / ~627 源码模块 ≈ 5.3 测试/模块；mock 1447 处、网络调用全 patch 隔离 | Explore agent 统计 |
| lint 配置 | ruff `select=[E,F,W,I,UP,B,SIM]`，但 **忽略 13 条**（含 E501 长行）；line-length 100；py311 | `skills/ai-film-grok/pyproject.toml` |
| 文档负债 | `memory/` 83 篇 dated `.md` + `references/` 170 篇（含 81 篇 `lessons-*`）≈ **334 篇**文档 | 目录统计 |

---

## 2. 五大工程主题 + Todo

### T0 · 安全 / 流程信任缺口（P0）

| ID | Todo | 做法 | 验收 | 证据 |
|----|------|------|------|------|
| **T0.1** | **修复或正式声明「唯一门禁」** | 二选一：① `git config core.hooksPath .githooks` 并让 pre-push 的 secret scan **不依赖** `gitea-publish` 才跑（缺依赖时静默跳过 = 漏扫，危险）；② 正式声明「**CI 是唯一真实门禁**」，删除 AGENTS 第 11 步错误承诺，并在 CI 里补 secret scan | 文档与实际一致；**secret scan 必须在 CI 真实运行**（本地不跑时 CI 兜底） | `git config --get core.hooksPath` 空；`.githooks/pre-push` 静默跳过分支 |

> 这是最危险的「信任缺口」：工程师以为本地 pre-push 在扫密钥，其实没跑。

### T1 · 规则机读化（把 IRON 从散文变成机器门）（P0→P1）

| ID | Todo | 做法 | 验收 | 证据 |
|----|------|------|------|------|
| **T1.1** | **anti-hijack 成为唯一 promote 通道** | 把 8 处 `volumedetect`/`probe_native_audio_mean_volume` 收敛到 `core/media_ops` 单一实现；所有 promote 决策强制经 `composition_anti_hijack.py`（禁只比 mean/音量） | `rg 'probe_native_audio_mean_volume\|volumedetect'` 仅 1 处定义，调用点经 anti_hijack；加单测 | 8 文件复制清单见 §1 |
| **T1.2** | **hard-defaults 子集机器化** | 仿 `duration_target.py:179`(`DURATION_MEDIA_SHORT_HARD`)、`core/constants.py:11`(`NATIVE_AUDIO_AUDIBLE_MIN_DB`) 模式，把最高风险 IRON 行（成人 MAX / 毒镜 / 不回穿 / 防抢走）加 error code + 单测 | 维护「IRON 规则 → 代码位置/测试」对照表；**新增 IRON 规则默认要求配单测** | `references/hard-defaults.md` 200+ 行，多数为文档无强制 |

### T2 · 去重 / 单一真相（P1）

| ID | Todo | 做法 | 验收 | 证据 |
|----|------|------|------|------|
| **T2.1** | 消除 `semantic_index.py:127` 自写 JSON 读取 | 改用 `util.read_json`/`require_json` | `rg '_read_json_source'` 0 处；回归测绿 | AGENTS 第 82 条 |
| **T2.2** | 抽共享 `retry/backoff` 工具 | 新增 `util/retry.py`，替换散落 ≥14 处重试循环 | 单一实现 + 行为测（含退避/超时） | media_queue/tts_backend/... |
| **T2.3** | shim 政策 | 227 个 `as _impl` 硬兼容 + 51 个 `cli_*.py` 是**纯透传**（无逻辑，好），但造成双真相/索引混乱。建立「shim 添加/移除政策」+ 标注权威 CLI 入口 | 一篇 shim 政策文档；CI 校验 shim 不引入逻辑 | Explore agent 统计 |

### T3 · 巨石风险驱动拆解（P1–P2，拒绝虚荣冲刺）

| ID | Todo | 做法 | 验收 | 证据 |
|----|------|------|------|------|
| **T3.1** | 消除 `edit_policy_heat ↔ edit_policy` 循环导入 hack | 以显式包边界 / 延迟导入 / 接口抽象替掉 `sys.modules` 运行时探测 | 删除 `sys.modules.get(...)` 探测；import 图无环 | `edit_policy_heat.py:13-30` |
| **T3.2** | 风险驱动 peel（**只在修 bug 时**） | `film_spec`(3156, A1 必碰→抽 auto-extend 纯函数)、`workflow_pack`(2177)、`render_final`(2869)、`edit_policy_heat`(4034,仅 heat bug)、`h3_fill_idle`(2131)、`export_composition`(2804)。每 peel 抽纯函数 + 独测；public CLI 字符串不变 | **无**「全员 <1500 行」虚荣冲刺；每个 peel 有独测 | §1 规模表 |
| **T3.3** | 收敛多 seed 探针到 anti_hijack（与 T1.1 合并执行） | — | — | — |

### T4 · 测试纪律（P1）

| ID | Todo | 做法 | 验收 | 证据 |
|----|------|------|------|------|
| **T4.1** | **落地 hotpath marker** | 给 `gates/*`、`post_doctor.py` 的 fail-closed 路径打 `@pytest.mark.hotpath`（当前 0 处实际用） | `make test-hotpath` 能选出真实 fail-mode 契约；CI 加对应 job | `grep '@pytest.mark.hotpath'` 仅 CHANGELOG |
| **T4.2** | slow 标记精度审查 | 复核 371 处 `@pytest.mark.slow` 是否真慢；巨型集成测（`test_comfy_video.py` 1133、`test_frw_ab.py` 1067）网络/凭据隔离复核 | 误标清零；CI 不抖动 | Explore agent |
| **T4.3** | gate 覆盖表 | 每个机器强制的 IRON/hard gate 有单测；跟踪 doc-only vs enforced | 对照表入 `references/` 或 docs | — |

### T5 · 团队技术能力 uplift（用户核心诉求）（P1）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **T5.1** | **统一 CONTRIBUTING / 入职单页** | 一篇涵盖：①`config.env.example` 全部键 ②`AIFILM_*`/`GITEA_*` 变量 ③唯一权威入口 `aifilm`（vs `backend-lock`/`media-queue`/`runtime-python`/`test` 辅助）④「CI 是唯一真实门禁」声明 | `docs/CONTRIBUTING.md` 存在并被 README/AGENTS 链接 |
| **T5.2** | **文档治理 / 防负债** | `memory/`(83) + `references/`(170) ≈ 334 篇。加留存/归档策略（如 60 天归档、数量上限）+ 稳定「规则索引」指向 `hard-defaults` + `stages/` | 索引页 + 归档脚本/CI 检查，新人可检索 |
| **T5.3** | **资深开发者代码质量把控机制（核心交付）** | 把 AGENTS 的「完成定义」operationalize 为 **PR review checklist**：①doctor 绿 ②相关 pytest 绿 ③若改 CLI/指纹 `make check-all` + `lock-runtime` ④英文 commit ⑤无 secret ⑥改 gates 须带 hotpath 契约测。提供 `make review` 概念（hotpath + 复杂度报告） | `docs/REVIEW_CHECKLIST.md` + 新 PR 默认过 checklist |
| **T5.4** | **lint / 复杂度预算** | 当前 ruff 忽略 13 条（含 E501 长行）。建议逐步启用（先 UP/SIM 全开）；加 per-function 复杂度上限（mccabe）作为**新代码硬门槛**，旧代码渐进 | `pyproject.toml` 调整 + CI 复杂度检查 |
| **T5.5** | **修正 AGENTS.md 不准确项** | 源码 checkout 路径误写 `~/.grok/plugins/...`（git 根实为 `/Users/dex/.grok/ai-film-grok`，symlink 现实）；第 11 步 pre-push 承诺不实 | AGENTS.md 与实际一致 |

---

## 3. 资深开发者代码质量把控机制（T5.3 展开）

这是用户「需要资深开发者的指导和代码质量把控」的**直接落地物**。目标：把质量从「靠个人自觉」变成「靠清单 + 机器门禁 + 习惯」。

1. **PR Review Checklist（强制）** — `docs/REVIEW_CHECKLIST.md`：
   - [ ] `aifilm doctor` 绿（或对应 `make doctor`）
   - [ ] 相关 pytest 绿（改哪测哪；改 gates 须带 hotpath 契约测）
   - [ ] 若改 CLI / 脚本指纹：`make check-all` + `make lock-runtime`
   - [ ] commit message 英文、语义清晰
   - [ ] 无密钥/凭据（`git diff` 无 secret；因本地 pre-push 不跑，CI secret scan 必须兜住 → 见 T0.1）
   - [ ] 无新增「绕过 anti_hijack 的 promote 信号」「自写 JSON 读取」「散落重试」（对应 T1/T2）
2. **复杂度预算** — 新函数 ≤ 80 行、模块 > 2000 行触发「peel 评审」门槛（对应 T3）。
3. **Pair / 入职**：新成员先读 `CONTRIBUTING` + `REVIEW_CHECKLIST` + `hard-defaults`，再碰代码。
4. **迭代节奏**：每轮「分析 → plan → 小步 commit（英文）→ CI 绿 → push」；禁止大爆炸式重写。

---

## 4. 建议执行序（依赖关系）

```text
T0.1 门禁真相（最高优先，1 小时内可决）
  → T1.1 anti_hijack 唯一通道（消除 8 处复制，最高杠杆）
  → T1.2 IRON 机器化（先最高风险 2-3 条）
  → T2.1/T2.2 去重（纯机械，低风险）
  → T3.1 循环导入 hack（为后续 peel 铺路）
  → T4.1 hotpath marker 落地（让 CI 有 fast-fail 契约）
  → T5.1/T5.2/T5.3 团队能力文档（可与上面并行写）
  → T3.2 风险驱动 peel（仅随 bug 修复顺手做）
  → T5.4/T5.5 lint 预算 + AGENTS 修正（收尾）
```

**默认 `go` 最小链**：T0.1 决策 → T1.1 → T4.1 → commit →（并行）T5.1/T5.3 文档。

---

## 5. 明确非目标

- 重开 ROI / Workflow / h3_primary 主实现 / 包边界搬家（产品 plan 已 SHIPPED）。
- 虚荣「全员 <1500 行」大重构冲刺。
- 全自动毒镜 CV 完美识别。
- 把 plate 红 gate 刷成假 master。
- 重写 `references` 全书 / 删 lesson。
- 静默改 heat / pilot GO / `i2v_provider`。

---

## 6. 成功定义（本迭代结束）

| 标准 | 达成信号 |
|------|----------|
| 门禁真相明确且 secret scan 在 CI 兜底 | T0.1 done |
| promote 信号全部经 anti_hijack，无 8 处复制 | T1.1 绿 |
| 最高风险 IRON 有代码门 + 测试 | T1.2 对照表 |
| 无自写 JSON 读取 / 共享 retry 工具 | T2.1/T2.2 绿 |
| `sys.modules` 循环 hack 移除 | T3.1 绿 |
| `make test-hotpath` 选得出真实契约 | T4.1 绿 |
| 团队有 CONTRIBUTING + REVIEW_CHECKLIST + 文档索引 | T5.1/T5.2/T5.3 done |
| AGENTS.md 与实际一致 | T5.5 done |

---

## 7. 与既有 plan 的关系

| 文档 | 角色 |
|------|------|
| **本档（codebase-quality-todoplan）** | **工程质量 / 团队能力**单一执行板（互补于产品 plan） |
| `2026-08-06-optimization-todoplan.md` | **产品 / 出片**迭代板（final IRON、衣着阶梯、5090 烧卡） |
| `2026-08-05-project-module-refactor.md` | 包布局 tracker（T3 peel 的 owner 参考） |
| `2026-08-05-residual-monolith-w4-todo.md` | 巨石残留 owner（T3 结构面） |

两档并行不冲突：产品 plan 管「出什么片」，本档管「代码与团队能不能持续、安全地出片」。

---

## 8. 实现时注意

- 改 `hard-defaults` / AGENTS：先备份 `~/.grok/backups/`。
- 功能变更：bump `plugin.json` + CHANGELOG（英文）。
- 脚本指纹变：`make lock-runtime`。
- 装机副本：`grok plugin update ai-film-grok`。
- 非琐碎收尾：派 `verifier` 复核。
- **所有 commit 英文**（AGENTS 硬规则）。

---

## 10. 双 checkout 分叉（2026-08-06 实测关键风险）

本机实测存在**两个分享历史但已分叉**的 git 仓库，禁止手动互拷：

- 开发/提交 checkout（本会话工作树）：`/Users/dex/.grok/ai-film-grok`（git 根；远端 origin=Gitea + github=GitHub）。
- 插件加载 checkout（运行中插件实际读取处）：`/Users/dex/.grok/plugins/ai-film-grok`（HEAD `ce06076`；远端 gitea + gitea-aidev + origin=GitHub；含未提交 h3 工作）。

两者共享 `5379ca9`（本 plan 首提）后分叉；`plugins/ai-film-grok` 还被并行 agent 推到了 github/main（`ce06076`）。本会话的 quality uplift 先落在 `ai-film-grok`，后被并行 commit `922caf5`（2.39.90，含 `scripts/secret_scan.py`、`parse_mean_volume_db`、`util/retry.py`、CONTRIBUTING/REVIEW_CHECKLIST、CI hotpath job）覆盖为 **superset**。

**结论 / 行动项**：选定唯一 canonical 仓库（建议 `plugins/ai-film-grok`，契合 AGENTS 原意），统一远端与同步流程；将 `ai-film-grok` 的独有修正（AGENTS 路径纠错、3 个 gate 套件 hotpath 打标）以 follow-up commit（2.39.91）落到 canonical，解决 plugins 侧未提交 h3 工作后再 `grok plugin update`。

### 10.1 门禁信任缺口收尾（2026-08-06 · 2.39.92）

T0.1 的「唯一门禁」已闭环为两端：

- **CI 端（2.39.90）**：`ci.yml` 每个 push/PR 真实跑 `secret_scan.py` + `hotpath` job（fail-closed）。
- **本地端（2.39.92）**：`scripts/check-all.sh` 由 4 步扩到 6 步，新增 **secret-scan（step 1）** 与 **hotpath 契约（step 6）**，本地 `make check-all` ≡ CI 绿线。工程师本地即可复现远端门禁，不再有「以为在扫其实没扫」的盲区。

残留项（非阻塞，已文档化）：本地 `check-all` 未跑 coverage 58% 阈值（CI 独有）；`core.hooksPath` 仍需 `make install-hooks` 手动启用一次。对称缺口仅剩 canonical 仓库统一（§10 主项）。
