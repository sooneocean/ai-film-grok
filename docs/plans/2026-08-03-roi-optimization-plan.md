# ai-film-grok ROI 优化计划 — 2026-08-03

**Status:** proposed（未执行）  
**Repo:** `/Users/dex/.grok/plugins/ai-film-grok`  
**HEAD:** `166ed817` · **version:** `2.31.6` · **branch:** `main`（ahead origin 14，working tree clean）  
**Method:** 实跑基线（pytest / ruff / doctor / project_audit），按 impact×likelihood÷cost 排序

---

## 1. 当前状态（实测）

| 维度 | 实测 |
|------|------|
| 规模 | scripts **305** 文件 · **~128.5k** 行；tests **324** 文件 · **~61k** 行 |
| Ruff | **PASS**（scripts 全量） |
| Fast tests (`-m "not slow"`) | **2442 passed · 1 failed · 2 skipped · 316 deselected** · ~112s |
| Doctor `core_readiness` | **FAIL** — `requirements_lock` + `runtime_lock` 版本漂移 |
| Doctor `strict_ok` | **blocked**（同上锁漂移；lipsync 默认 off 不挡 core） |
| project_audit | `docs_current` FAIL · `baseline_current` FAIL · doctor FAIL |
| Coverage（audit 缓存） | 总 **~62%**；`dispatch` 81% · `continuity` 91% · **`render_final` 30%** · **`compose_render` 19%** · `production_gates` 50% |
| CLI 单体 | `aifilm_grok.py` 仍 **10994 行**（历史目标 <1500；已有 24 个 `cli_*.py` + `cli/` 但主文件仍巨） |
| 文档 | CHANGELOG 停在 **2.25.0**，plugin 已 **2.31.6**（至少 6 个 minor 未入账） |
| 远端 | **未 push** 14 commits（含 beat-spine / dialogue / canary / delivery 硬化） |
| 环境 | edge-tts **7.2.7** vs lock **7.2.8**；jsonschema **4.26.0** vs lock **4.23.0** |
| 磁盘（gitignore） | `.local-runtimes` **4.5G** · `g2pW` 152M · `artifacts` 43M |
| Worktrees | **15+** 登记，大量 `prunable` 残留 |

历史计划：`2026-07-21-codebase-optimization` / `2026-07-23-001-feat-full-optimization-plan` 已 **superseded**；基础设施半落地（`config_loader`/`logger`/`cache`/`checkpoint` 在，调用迁移未完）。

---

## 2. Findings（按 ROI）

### F1 · Runtime lock 漂移 → doctor + 1 测红  **ROI: 极高**
- **证据:**  
  - `pytest … test_runtime_policy.py::…test_current_environment_matches_declared_requirements` FAIL  
  - doctor: `edge-tts expected 7.2.8 found 7.2.7` · `jsonschema expected 4.23.0 found 4.26.0`
- **影响:** 本机 `make doctor` / `check-all` / release-check 伪阻塞；新机按 lock 装会与当前实测环境不一致。
- **成本:** 低（决定 pin 策略 → 一处改 lock 或 pip pin + 同步 `runtime-lock.json`）
- **建议:** **以当前可复现环境为准重写 pin**（edge-tts==7.2.7, jsonschema==4.26.0），并同步 runtime-lock；不要「装回旧版」除非有兼容回归。

### F2 · 新模块缺单测（beat-spine 批）  **ROI: 高**
- **证据:** HEAD 已合入 `beat_spine` / `story_contract` / `story_quality` / `plan_feedback` / `story_normalize` + 8 个 spine JSON；仅 `test_genre_beat_spines.py` 覆盖 spine 侧面。  
  `plan_feedback` / `story_contract` / `story_normalize` / `story_quality` → **无专用测试文件**。
- **影响:** plan run 反馈环、质量门、合同建议可静默回归。
- **成本:** 中（纯单测，无 API）。

### F3 · `story_plan` 双路径未抽干净  **ROI: 高**
- **证据:** `story_plan.py` 仍含 `def select_beat_spine` + `def _draft_story_contract`，同时又 `from beat_spine import` / `from story_contract import`。
- **影响:** 两套真相；改 spine JSON 未必打到所有调用点。
- **成本:** 中（删内联、统一 re-export 或只保留 facade）。

### F4 · CHANGELOG / baseline / docs 不同步  **ROI: 高（发版与协作）**
- **证据:** CHANGELOG 顶 `2.25.0`；version `2.31.6`；`project_audit` → `docs_current`/`baseline_current` FAIL。
- **影响:** 发布说明失真；audit 永远红；他人无法从 CHANGELOG 理解 14 个未推 commit。
- **成本:** 中（整理 2.26–2.31 条目 + `make audit` 写 baseline）。

### F5 · 热路径覆盖过低  **ROI: 中高**
- **证据:** `render_final` ~30% · `compose_render` ~19% · `production_gates` ~50%（audit）；却是 final/交付主链。
- **影响:** 字幕双烧、stage 顺序、gate 契约回归靠肉眼。
- **成本:** 高（需 fixture + 假 ffmpeg 路径）；应**按失败模式**补测，不追求行覆盖虚荣。

### F6 · logger / util 半迁移  **ROI: 中**
- **证据:** `def log` 仍在 `aifilm_grok` / `render_final` / `compose_render` / `compose_preview`；`_read_json/_write_json` 仍在 `final_stages` 等；`from util import` 仅 ~2 处。
- **影响:** 日志格式不统一、JSON I/O 行为分叉。
- **成本:** 中（机械替换 + 行为对齐测）。

### F7 · `aifilm_grok.py` 11k 行单体  **ROI: 中低（长期）**
- **证据:** 10994 行；已有 24×`cli_*.py` 仍未吃完主文件。
- **影响:** 冲突面、import 成本、review 成本。
- **成本:** 很高；**禁止**无行为 diff 的大搬家。只在有新 cmd 或碰某 cmd 组时顺手抽。

### F8 · 远端未推 + 僵尸 worktree  **ROI: 中（运维）**
- **证据:** ahead 14；`git worktree list` 十余条 prunable。
- **影响:** 备份风险、磁盘、分支心智负担。
- **成本:** 低（push 需你确认；prune 可本地做）。

### F9 · 刻意不做的「伪优化」
- 历史 U 系列「微表情图 / 光学 DOF / 空间声场物理」——无当前用户痛点，**不做**。
- 全库 ruff format 重排历史文件——**不做**。
- 无 bug 的 edit_policy/story_plan 大拆——**不做**，除非 F3 边界内。
- g2pW / artifacts 大目录：已 ignore；清理属磁盘卫生，单列可选。

---

## 3. 可执行批次（A → … 独立可验）

每批验收门：`ruff check scripts/` + 相关 pytest 绿 +（A 后）doctor core_readiness 绿。

### Batch A — 解锁绿线（锁漂移）  ⏱ ~20–40min · **先做**
1. 确认 edge-tts 7.2.7 / jsonschema 4.26.0 为当前 runtime 真值（已测）。
2. 更新 `skills/ai-film-grok/requirements.lock` + `runtime-lock.json`（及任何镜像 pin）。
3. 跑：`pytest tests/test_runtime_policy.py -q` → full fast suite → `aifilm doctor` → `core_readiness.ok==true`。
4. 可选：`make audit` 刷新 baseline 报告。

**Done when:** fast suite 0 fail；doctor core 绿（advisory 可留：always-approve、unified.log mode）。

### Batch B — Beat-spine 契约收口 + 单测  ⏱ ~1–2h
1. `story_plan.select_beat_spine` / `_draft_story_contract`：**删除内联实现**，只调 `beat_spine` / `story_contract`（保留薄 wrapper 仅当公开 API 需要）。
2. 为 `plan_feedback` / `story_contract` / `story_quality` / `story_normalize` 补最小单测（happy + fail-loud + 边界）。
3. 扩展 `test_genre_beat_spines`：每个 spine JSON load + 结构 schema 校验。
4. 跑 plan 相关 + genre spine 测试。

**Done when:** 新测文件齐；无双实现；plan 路径单测绿。

### Batch C — 文档与发版卫生  ⏱ ~1h
1. CHANGELOG：补 `2.26.0`…`2.31.6`（按 git log 归类 Added/Fixed/Changed；不编造）。
2. `make sync-docs` / `project_audit --write-baseline` → `docs_current` + `baseline_current` PASS。
3. 核对 README 版本指针与 plugin.json 一致。
4. **Push `origin/main`：等你明确授权**（对外动作）。

**Done when:** audit docs/baseline 绿；CHANGELOG 顶版 = plugin.json。

### Batch D — Final/交付热路径定向测  ⏱ ~2–4h
1. 盘点 `render_final` / `final_stages` / `compose_render` 已有测与缺口（双烧、subs off、stage receipt、HF caption owner）。
2. 只补 **曾踩坑 + 契约断言**（lesson 引用：title-double-burn、subs-always-burn、HyperFrames ownership）。
3. `production_gates` 补 fail-closed 用例（未知 key / 缺 proof）。
4. 覆盖率目标：**有意义路径**，不设虚假 % KPI；audit 里这三文件有可见提升即可。

**Done when:** 新测锁定 lesson 契约；fast suite 仍绿。

### Batch E — logger + JSON I/O 收口（可选）  ⏱ ~1–2h
1. `render_final` / `compose_*` / `aifilm_grok` 的 `log()` → `logger.log`（行为兼容 stderr）。
2. `final_stages` 等 `_read_json/_write_json` → `util`。
3. `tts_backend._load_config_env` → `config_loader`（若尚未）。
4. 禁止顺手大 refactor。

**Done when:** `rg '^def log\(' scripts` 仅剩 `logger.py`；相关测绿。

### Batch F — CLI 单体再抽（按需，不主动开）  ⏱ 多会话
- 仅当本周要改某 cmd 组时：把该组从 `aifilm_grok.py` 挪到已有 `cli_*.py` 模式。
- 每抽一组：help smoke + 该组测 + 无 flag 行为 diff。
- **不设「压到 1500 行」冲刺**。

### Batch G — 本机运维（可并行、低风险）  ⏱ ~15min
1. `git worktree prune` + 删除确认无用的 prunable worktree 目录。
2. 评估 `.local-runtimes` 4.5G 是否可清（**先列清单再删**）。
3. 安全 advisory（可选）：`chmod 600 ~/.grok/logs/unified.jsonl`；`always-approve` **不改**（需你明确）。

---

## 4. 建议执行顺序

```text
A（绿线） → B（新功能契约） → C（文档/可推） → D（交付热路径）
E 穿插在碰这些文件时
F 永不单独开 sprint
G 随时可做
```

**默认推荐本周只做 A+B+C。** D 在有成片回归痛时再开。

---

## 5. 明确不做

| 项 | 原因 |
|----|------|
| 微表情 / DOF / 光流插帧等「电影感模块」 | 无当前证据支撑 ROI；历史 plan 已 superseded |
| 全量 format / import 大扫 | 噪音 diff，挡 review |
| 静默改 i2v_provider / 自批 pilot | 产品铁律 |
| 未授权 push / 改 global permission_mode | 对外/制度 |
| Docker 化本机链路 | 德老师偏好本机直跑 |

---

## 6. 开放决策（执行前需你点头）

1. **Lock 策略：** 接受「以本机实测版本重写 lock」（推荐）还是「强制 pip 装回 7.2.8 / 4.23.0」？
2. **Push：** A+B+C 后是否推 `origin/main` 14+ commits？
3. **Batch 批准：** 回复 `A` / `A+B` / `A+B+C` / `GO`（高授权按序做完 A–C）即可开工。

---

## 7. 基线命令备忘

```bash
ROOT=/Users/dex/.grok/plugins/ai-film-grok
SKILL=$ROOT/skills/ai-film-grok
AIFILM=$SKILL/scripts/aifilm
RUNTIME=$($SKILL/scripts/runtime-python)

ruff check $SKILL/scripts/
cd $SKILL && $RUNTIME -m pytest tests/ -q --tb=line -m "not slow"
$AIFILM doctor   # 看 core_readiness.ok
$RUNTIME $ROOT/scripts/project_audit.py --write-baseline
```

---

_Generated 2026-08-03 from live audit; not executed._
