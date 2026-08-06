# 资深开发代码质量把控 & 团队技术提升计划

> **作者角色**：Senior Developer（高级开发工程师）· 全栈工程 / 代码质量把控
> **日期**：2026-08-06 · **仓库**：ai-film-grok（v2.40.22）
> **范围**：`skills/ai-film-grok/scripts/`（673 .py / 167,609 LOC）+ `tools/`（BGM 资产流水线）
> **互补说明**：既有 `docs/optimization-plan-2026-08-06.md` 已覆盖 *功能正确性质量门*（抗无聊/接戏/转场/视觉圣经/介质路由…）。本文档聚焦 **工程卓越维度**：代码结构、可维护性、错误纪律、CI、可复现性、团队评审标准——即"代码质量把控 + 团队技术 uplift"。

---

## 0. 结论速览（Verdict）

项目**能力已全、功能正确性门已扎实**（13 轮硬化），但**工程结构负债高**，主要风险不在"缺功能"而在"不可持续维护"：

- 🔴 **巨型函数是头号风险**：74 个函数 ≥200 行；`render_final` 单函数 **2,454 行**（占文件 82%），`validate_film_spec` 2,322，`run_preflight` 1,937。这些函数无法被单测、无法被 review、改一处全局震颤。
- 🔴 **安全关键闸门存在"静默失败开放"**：`gates/production_gates.py:518-519` `except Exception: pass` 后 `return {"ok": True}`；`:709-710` 静默 `return {}`。闸门本应 fail-closed，却吞异常放行——正确性隐患。
- 🟠 **错误体系未统一**：`FilmError` 存在但约 30 个子系统异常类全部直接继承 `RuntimeError`/`ValueError`，无统一基类，调用方无法统一捕获。
- 🟠 **重复 JSON I/O**：`read_json` 在 8 个模块被各自定义义、抛出不同异常类型——同名不同语义的陷阱。
- 🟠 **可观测性缺失**：全仓 0 个模块 `import logging`，185 处 `print()`（含库代码直接 `print(json.dumps(...))`）。
- 🟡 **类型注解 73% 但不均**（新包好、legacy 滞后）；**109 个顶层 legacy 模块**未完成向 package 迁移；**2 个模块硬编码机器路径**（`/Users/dex`、`/opt/homebrew`）。
- 🟡 **CI 强但留口**：`test-full`(slow, 368 例) 很可能不阻塞合并；无 mypy 门；`requirements.lock` 仅钉 4 个包（克隆不可复现）；README/GRAPH 版本指针漂移（2.39.69 / 2.40.21 vs 实际 2.40.22）。

**好消息（纠正一个误判）**：架构初扫曾报"零测试"——这是**误判**。实测有 **441 个测试文件 / ~3,643 个测试函数 / ~80k 行测试**，覆盖 media/audio/spine/gates 良好。真正缺口是 `core`/`util`/`node`/`final`(单元层) 零覆盖，以及校验类模块（film_spec/story_contract/subtitle_typesetter/edit_policy）薄弱。

---

## 1. 审计方法 & 一个必须记录的原则

- **三层核查**：① 派 Explore 子代理分工深挖（架构质量 / 测试CI文档）；② 亲自跑定量指标（AST 函数长度、类型比、except/print/logging 计数）；③ **对子代理矛盾结论逐一复核**（见下）。
- **信任但要验证（Trust but Verify）**：两个子代理对"测试是否存在"给出相反结论。我未照单全收，而是直接 `find` + `pytest --co` 核实——发现测试真实存在、只是位于 `tests/` 而非 `scripts/`。**这条原则本身应写进团队评审标准**：任何"某处完全缺失/完全坏掉"的结论，合并前必须有人独立验证。

---

## 2. 量化指标（实测）

| 指标 | 值 | 评价 |
|---|---|---|
| 源 LOC（scripts/） | 167,609 | 大型系统 |
| 函数 ≥200 行 | **74** | 🔴 头号风险 |
| 最大单函数 | 2,454 行 | 🔴 render_final |
| 类型注解覆盖率 | 73%（2709/3689 def） | 🟡 不均 |
| `except Exception` | 536 | 🟠 部分静默吞掉 |
| `print(` | 185 | 🟠 库代码应改用 logger |
| `import logging` | **0** | 🔴 可观测性缺失 |
| 重复 `read_json` 定义 | 8 | 🟠 |
| 硬编码 `/Users`·`/home` | 2 模块 | 🟡 |
| 测试文件 / 函数 | 441 / ~3,643 | ✅ 存在（位置在 tests/） |
| 零覆盖基座 | core/util/node/final-unit | 🟠 补漏优先 |

---

## 3. 分阶段 TODO Plan

> 优先级逻辑：**先止血（正确性/可观测）→ 再减负（巨型函数）→ 再统一纪律（错误/IO）→ 再补测试缺口 → 最后收尾（迁移/类型/文档）**。每阶段都"先写表征测试再改代码"。

### Phase 0 — 止血 & 护栏（最高优先级，1–2 周）
- **[P0-1] 闸门 fail-closed 化**：审计 `gates/` 全部 `except Exception: pass/return ok`；改为显式 `raise FilmError(...)` 或返回 `{ok:False, reason}`，**绝不静默放行**。先补表征测试锁定当前行为，再改。涉及 `production_gates.py` `preflight.py` `narrative_rebind.py` `cinematic_gate.py` 等。
- **[P0-2] 接入项目级 logging**：引入 `util.logger`（或 stdlib logging）统一输出；库代码 `print(json)` 改为 `logger.debug(structure)`。CLI 输出层保留 stdout，但业务/库代码禁 `print`。
- **[P0-3] CI 加固**：① `test-full`(slow) 设为 required status check（否则 368 例不拦合并）；② 新增 mypy 作业（先对 `core`/`gates`/`final` 强类型、逐步扩）；③ ruff 扩到 `tools/` 与 `skills/ai-film-project/scripts/`；④ CI 加"README/GRAPH 版本 == plugin.json"校验；⑤ 启用 ruff 复杂度规则（`C901`）作为新代码门禁。

### Phase 1 — 拆解巨型函数（最高维护 ROI）
- **[P1-1] 为 4 个最大函数建"黄金主"表征测试**（golden-master）：`render_final` / `validate_film_spec` / `run_preflight` / `build_dispatch`。用真实 spec/输入跑一遍、快照输出，作为重构安全网。
- **[P1-2] 逐步抽取**：每个函数按"单一职责"拆成 5–15 个 50 行内的小函数/类。顺序：render_final(2454) → validate_film_spec(2322) → run_preflight(1937) → build_dispatch(1187) → 其余 70 个按风险排序。**约束：每个 PR 只拆一个函数，且配套测试不降**。
- 预期收益：review 可行、单测可行、回归可定位。

### Phase 2 — 错误 & I/O 纪律
- **[P2-1] 统一错误体系**：所有子系统 `*Error` 改为继承 `FilmError`；保留原有类名。调用方可用 `except FilmError` 兜底。
- **[P2-2] 集中 JSON I/O**：删除 8 处本地 `read_json`，统一走 `util.read_json` / `require_json`（已存在，语义明确）。消除"同名不同语义"陷阱。
- **[P2-3] 禁静默 except**：`except Exception` 必须 log + 重抛或显式降级；Code Review 标准里列为 **blocker**。

### Phase 3 — 完成迁移 & 去重
- **[P3-1] 收口 109 个顶层 legacy 模块**：按职责移入对应 package（workflow_pack→spine/post；input_fidelity→gates；prompt_injector→spine；state_index_gate→gates；shortform_director→plan；config_loader→util）。每移一个补 1:1 测试。
- **[P3-2] 外部化硬编码路径**：`/Users/dex`、`/opt/homebrew` 改为从 config/env 解析（已有 `config_loader`/`runtime-python` 机制）。消除"仅本机可跑"陷阱，让 CI/Linux 可复现。

#### P3-1 迁移配方（repeatable template · 首个落地见 v2.40.27 `ltx23_audio_canary`）
对 109 个模块的迁移是迭代工程，不是一次性重写。每模块一个 PR，按以下 6 步：
1. **选模块**：`ast` 扫 `scripts/*.py`（顶层），统计每个模块的 importer 数（`from X import` / `import X` 命中），**优先挑 0–1 importer** 的低风险模块（如 `*_canary`、`*_probe` 系列）。零 importer = 删除旧位置零回退风险。
2. **定归属**：按职责选 package——`*_canary`/`*_adapter`/`tts*`→`audio/`；`*_gate`/`*_fidelity`→`gates/`；`i2v`/`h3`/`media_*`→`media/`；`shortform`/`story*`→`plan/`；`config_loader`/`paths`/`retry`→`util/`。
3. **调深度**：任何 `__file__` 相对路径（`parent.parent`、模板/资源加载）在下沉一层后必须 +1 个 `.parent`。用真实资源路径做断言测试锁死（参考 `test_ltx23_audio_canary` 加载真实模板）。
4. **查 dangling**：全仓 grep 旧模块名（`scripts/X.py` / `from X import` / 动态按名加载），确认无引用；若有，先改引用再删旧文件。
5. **锁契约**：写 1:1 测试覆盖公共函数的正常 + 异常边界（ValueError 条件、返回值结构）。这是"迁移不引入回归"的硬保障。
6. **收敛推送**：单 PR 单模块；测试不降绿；双远端 `git fetch --all` 后 merge（禁强推）再 push。并发分叉时重复 fetch→merge→push 直到三端一致。

> 进度（v2.40.27 起）：已迁 1/109。剩余按 importer 升序批量推进，建议每周 5–10 个，配合 code-review 轮值。

### Phase 4 — 测试缺口补漏
- **[P4-1] 零覆盖基座优先**：`core`(film_io/paths/constants/media_ops/emit)、`util`(retry/validators/subprocess/errors/json_io)、`node`(各 GPU 适配)、`final`(单元层)。这些是全局地基，漏测=全局风险。
- **[P4-2] 校验类模块加测**：`film_spec*`、`story_contract`、`subtitle_typesetter`、`edit_policy_*`——最易回归处，补契约测试。

### Phase 5 — 收尾（类型 / 文档 / 可复现）
- **[P5-1] 类型均匀化**：把 legacy 文件类型注解补到 90%+；用 mypy 增量门禁守住。
- **[P5-2] 修文档漂移**：README(2.39.69→2.40.22)、GRAPH(2.40.21→2.40.22)；统一由 `make sync-docs` 生成（CI 已校验版本一致）。
- **[P5-3] 修可复现性**：`requirements.lock` 补全（或改用完整 lock + `--require-hashes`），让"克隆即跑"成立。

---

## 4. 团队技术提升方案（用户明确诉求：资深指导 + 代码质量把控）

### 4.1 代码评审标准 / Definition of Done（PR 合入闸门）
每条 PR 必须满足；以下任一条不达标 = **blocker**（资深 sign-off 才可 override）：

1. **无静默 except**：`except Exception` 必须 log + 重抛/显式降级；禁止 `except: pass`。
2. **无新巨型函数**：新增/修改后的函数 ≤ 80 行（复杂度预算）；超限须拆或附"为何不可拆"说明 + 表征测试。
3. **统一错误**：新异常继承 `FilmError`；不新造裸 `RuntimeError`。
4. **集中 I/O**：JSON 读走 `util`；不本地重定义 `read_json`。
5. **禁库代码 print**：业务/库代码用 logger；仅 CLI 输出层可用 stdout。
6. **类型注解**：新增公共函数 100% 注解；mypy 增量零新增错误。
7. **测试伴生**：任何逻辑改动附测试；拆函数时表征测试不降绿。
8. **路径外部化**：不硬编码 `/Users`/`/opt/homebrew`/绝对路径。
9. **ruff 干净**：`make check-all` 中本 PR 触及文件 ruff 零错误（既有债务不归本 PR，但禁止新增）。
10. **文档同步**：命令/架构变更须 `make sync-docs` + README/GRAPH 版本对齐。

### 4.2 复杂度预算（Complexity Budget）
- 把 ruff `C901`(mccabe) + `成功率` 作为**新代码硬门**；存量 74 个巨型函数进 Phase 1 计划逐步还债。
- 单函数 > 200 行 = 技术债标记，禁止在无测试情况下改动其内部逻辑。

### 4.3 ADR（架构决策记录）
- 新增 `docs/adr/`：模块边界、package 迁移规则、错误体系、路径外部化方案等**已定型决策**写成 ADR，避免"每次又吵一遍"。
- 例：ADR-001 "所有子系统异常继承 FilmError"；ADR-002 "JSON I/O 唯一入口 util"；ADR-003 "测试位于 tests/，与 scripts/ 平级"。

### 4.4 参考模式（Reference Pattern）
- **资深带头拆第一个巨型函数**（`render_final`）：边拆边录"如何安全重构巨型函数"的内部 tech-talk（30 min），作为团队模板。
- 模式：**表征测试 → 提取纯函数 → 注入依赖 → 单测新函数 → 删除旧分支 → 全量绿**。这套流程在 Round 8–14 的 `h3_fill_idle` 纯函数化已跑通，可直接推广。

### 4.5 评审节奏 & 资深 sign-off
- **双远端并发分叉教训**（见记忆 Round 13）：push 前 `git fetch --all` 必做；remote 占用版本号须 rebase 后重编版本。
- gates/media/audio 变更 = **资深必 review**（fail-closed 正确性相关）。
- 每周 1 次 code-review 轮值 + 1 次 30min 技术分享（围绕本计划 Phase 落地）。

---

## 5. 建议立即开做的 3 个 PR（本周可交付）

1. **PR-A（止血）**：`gates/production_gates.py` 静默 except 改为 fail-closed + 配套测试（P0-1 子集）。→ 最高正确性杠杆。
2. **PR-B（护栏）**：CI 加 `test-full` required status check + mypy 作业（先 core/gates/final）+ ruff 扩范围（P0-3）。→ 锁住后续所有改动。
3. **PR-C（示范）**：抽 `render_final` 第一个纯函数 + 黄金主表征测试（P1 起点）。→ 给团队一个可复制的重构模板。

---

## 6. 风险提示（不要做的事）
- ❌ **不要在没有表征测试的情况下直接重写 `render_final`/`validate_film_spec`**——会无声破坏既有行为。
- ❌ **不要新增 `except: pass`** 来"让 CI 绿"——这是在 gate 上开洞。
- ❌ **不要在双远端分叉时强推**——先 `git fetch --all`、优先 rebase/merge 收敛（记忆 Round 13 教训）。
- ❌ **不要并行大改 74 个巨型函数**——分批、每 PR 一个、伴生测试。

---

## 附录：核实命令（可复现审计）
```bash
# 巨型函数（AST）
python3 - <<'PY'
import ast, pathlib
data=[]
for p in pathlib.Path("skills/ai-film-grok/scripts").rglob("*.py"):
    if "__pycache__" in str(p): continue
    try: t=ast.parse(p.read_text())
    except: continue
    for n in ast.walk(t):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.end_lineno:
            L=n.end_lineno-n.lineno+1
            if L>=200: data.append((L,str(p),n.name))
data.sort(reverse=True)
print(">=200 lines:",len(data)); [print(f"{L:5d} {p} {n}") for L,p,n in data[:18]]
PY
# 测试存在性
find . -name 'test_*.py' | wc -l          # 441
# 静默 except（gates）
grep -rnE "except Exception" skills/ai-film-grok/scripts/gates/ | head
```
