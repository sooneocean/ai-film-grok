# ai-film-grok — 项目长期笔记

本地 AI 影视生产流水线：资产+元数据仓库（无应用源码）。路径 `/Users/dex/.grok/ai-film-grok`。

## 数据契约（写前必校验）
- catalog 顶层 schema `aifilm-bgm-library-v1`；资产 `aifilm-bgm-asset-v1`；TTS `tts-evaluations/manifest.json` schema `aifilm-tts-manifest-v1`。
- 校验器：`tools/validate_catalog.py`（自包含，无第三方依赖）。**任何修改 catalog.json 前先跑它**作为 gate。

## bgm-library
- `catalog.json`：46 资产（revision 152，round6 闭环 60 fill 缺口前为 92）。`technical.fingerprint` 为 101 维声纹。
- `similarity_cluster`：全部 46 资产已填（曾 3 个 pending 为 null，已修）。聚类规则 = 同 mood 内对 fingerprint 做余弦相似度、阈值 0.95 贪心归组。新增资产后需重跑聚类。
- `gap-queue.jsonl`：缺口生命周期 `status` ∈ {open, routed_generate, filled, rejected}；`action` ∈ {fill, generate}；`routed_backend` / `generation_job_id` 在 routed_generate 时填。当前 **100 缺口 = 80 filled + 20 routed_generate(acep-step·submitted)**（round7 前瞻排产 30 coverage_gap：20 被现有资产复用填充、10 路由待生成；6 个 `pulse` 死路已通过给后端补 `pulse` stem_profiles 解锁）。**关键发现（round6 审计）：原 60 个 open fill 缺口全部 `suggested_asset_id` 指向 approved 资产——此前无任何自动化闭环（只能人手 `fill_gap.py`），已于 round6 经 `fill_open_gaps.py --apply` 一次闭环（rev 92→152，仅 2 个资产被 60 次复用）；全部 generate 缺口原缺 `duration`，已 `reconcile --fix` 按 to-generate.jsonl 回填 30s。**
- `generators.json`（schema aifilm-generators-v1）：声音生成后端能力注册表（acestep local active / ltx23 api active / grok15 api active 角色待定 / h3 pending）。新增声音源 = 加一条目，router/generate_loop 不变。
- `generation-jobs.jsonl`：generate 回路台账（job_id/source_gap_id/backend/ext_id/status/spec）。
- 修改前备份：`catalog.json.bak`、`gap-queue.jsonl.bak`（已被 .gitignore 忽略）。

## tts-evaluations
- 统一 `manifest.json`（6 引擎 / 16 样本）。fish 引擎 8/8 HTTP 402 已归档至 `_archive/2026-07-29-fish`，移出活跃轮换。

## 治理
- 仓库已 `git init`；`.gitignore` 忽略 `*.lock`/`.DS_Store`/`melo-cache/`/`*.wav`/`*.flac`/`*.mp3`/`*.onnx`/`*.bak`。媒体不入 git（仅元数据版本化）。
- `.git/hooks/pre-commit` 门禁：提交前跑 `tools/validate_catalog.py --no-sha`。

## 工具（tools/）— 资产流转管线
- `validate_catalog.py`：catalog 契约校验（写前 gate）。
- `cluster_assets.py`：同 mood 声纹余弦聚类（阈值 0.95），回填 similarity_cluster；可复现。
- `fill_gap.py`：填充缺口闭环，维护 use_count / last_used_*；generate 类缺口无候选会拒绝。
- `fill_open_gaps.py`（round6 新增）：批量闭环 open `fill` 缺口。默认 `--dry-run`，`--apply` 才写盘；扫描 action==fill&status==open 且 suggested_asset_id 指向 approved 资产的缺口，逐条委托 `fill_gap.py` 闭环。`eligible(gaps,cat)` 纯函数可单测；`--limit N` 限量。可重入（filled 跳过）。
- `coverage.py`（round7 新增）：供需覆盖分析器。按 (mood,stem,energy桶) 交叉比对 approved 供应 + routed_generate 在制 vs 全缺口需求，标记 STARVED/THIN/OK，输出优先级生成队列（deficit 降序）；`--emit-generate [--apply]` 把 Top-N 落成 open generate 缺口 + to-generate.jsonl 台账（默认 dry-run）；`--json` 机读。含纯函数 `analyze()/priority_queue()`。
- `pipeline_lib.py`：共享库（路径/load-save+备份/bump/sha256/stdlib 声纹指纹/状态机转移校验）。
- `route.py`：资产+缺口状态机契约（单一事实源）+ `check` 校验。round6 新增软 WARN（不破坏 gate）：`generate` 缺口缺 `duration` 字段时告警（reconcile --fix 回填）。
- `approve_asset.py` / `reject_asset.py`：真实 approve/reject（替代旧 review 页只打印的 `aifilm` CLI）；原子改 status+移文件+校验门禁。
- `gen_review.py`：由 catalog 动态生成 review/index.html（消除漂移 + 孤儿告警）。
- `backends/` + `router.py`：Backend 抽象 + 能力矩阵路由。
  - `capable_backends(spec, gens, exclude=())`：active 且能力匹配的后端有序列表（local 优先，pending/死后端如 fish 自动排除）。
  - `choose_backend` 现委托 `capable_backends`（支持 exclude 做提交失败自动退避）。
  - `find_existing_candidate(gap, catalog)`：已有 approved 资产匹配 mood/stem/energy 或近重复 → 返回 id，循环**填充而非重新生成**。
  - `choose_route(gap, gens)`：P5 按 `asset_kind` 分流（tts→`tts:<engine>`，bgm→能力矩阵）。
- `qa_audio.py`（round3 新增，round5 深化）：音频质量门禁，纯 stdlib。
  - **硬门禁（阻塞 auto-approve，决定 ok）**：peak∈[0.55,0.99]、rms≥0.008、silence≤0.10、duration 在请求±15% 且 ≥1s。
  - **软信号（仅 advisory，不阻塞）**：zcr 亮度、dc_offset 直流偏置、lufs_est（ITU BS.1770 K 加权估计）、loop_score 无缝循环、near_dup 与已批准声纹余弦≥0.98。`ok` 只由硬门禁决定；`issues`=硬，`advisories`=软。
- `normalize_audio.py`（round5 新增）：stdlib 去直流 + 峰值归一化（默认 0.95）；`ingest_generated --normalize` 入库前就地修复太轻/有偏置的床。
- `ingest_generated.py`：生成音频回写为 pending 资产（重建 sha256/指纹/technical/**qa**/bump/校验）。**注意：analyze_wav 返回 dict，须按 key 取值（`duration_sec` 等），不能直接元组解包。** round5：① 加载 catalog 取 approved 指纹做 near_dup 告警；② 存 `advisories` + 全量 qa metrics；③ `--asset-kind`(bgm/tts) 选 QA；④ `--normalize` 可选。
- `generate_loop.py`（round3 增强，round5 接 breaker）：
  - submit：① P5 tts 缺口只路由不生成；② `find_existing_candidate` 命中则直接 `fill_gap` 闭环；③ 否则走能力矩阵 + **提交失败自动退避到下一个 capable 后端**；④ 失败记 breaker。
  - poll：done→ingest→可选 auto-approve+fill；**ingest 失败会回退 gap 到 open**；backend 失败同样回退。
  - auto-approve **受 QA 门禁**（`--no-qa-gate` 可强制覆盖）。
  - `_fill_from_existing` 复用已批准资产闭环。
  - `_build_spec` 现优先用 `gap.get("duration")`（reconcile 回填），再 to-generate.jsonl，再 30s 默认。
- `breaker.py`（round5 新增）：后端熔断（连续失败 3 次冷却 600s，half-open 试探，成功复位），状态持久化于 `bgm-library/.breaker.json`。`capable_backends(..., breaker=)` 自动跳过 tripped 后端；generate_loop submit 记录失败/成功。
- `reconcile.py`（round5 新增，round6 扩）：管线体检（跨 catalog/gaps/jobs/磁盘）。只读审计 + `--fix` 安全修复（重算空/非规范指纹、补 similarity_cluster、复位 failed/missing 工单的 stuck 缺口、回填 generate 缺口缺失的 duration（来自 to-generate.jsonl））；`--strict` 可当 CI gate。审计新增：open fill 缺口可闭合/死路计数、generate 缺口缺 duration 计数。
- `run_tests.py` + `tools/tests/`（round5 新增，round6 加 test_fill_open_gaps，round7 加 test_coverage）：纯 stdlib `unittest` 套件（pipeline_lib / router / qa_audio / breaker / api / validate / tts / fill_open_gaps / coverage），**58 测试全过**。回归防护。
- `report.py`：可观测汇总 + 孤儿审计（round5 加 tts 缺口计数行；round6 加 open fill 缺口可闭合/死路 + generate 缺口缺 duration 计数；round7 加 library coverage STARVED/THIN 摘要）。
- `pipeline.py`（round7 新增）：统一编排入口，把 ~20 脚本收口为 dispatcher（check/doctor/submit/poll/run-acestep/fill-open/reconcile/coverage/one-shot/status）。`one-shot` 串 fill-open→reconcile --fix→submit→run-acestep→poll --auto-approve→doctor（`--demo` 走 MockBackend 端到端）；`status --json` 汇 coverage/reconcile/jobs 为健康 blob。各子命令委托现有已测工具（subprocess），行为不变。
- `gen_review.py`：由 catalog 动态生成 review/index.html（round5 加 TTS 车道状态块）。
- `self_test.py`：临时副本用 Mock 跑通全闭环。**round5 加固：注入 1 个 tts 缺口，断言它“被路由但不生成/不回填”，证明 BGM↔TTS 双管线分离。round6 扩：先 `reconcile --fix` 验证 10 generate 缺口 duration 回填；注入 3 个 open fill 缺口（approved 候选）+1 死路，断言 `fill_open_gaps --apply` 闭环 3/留 1/rev+3/use_count+3，且 `--dry-run` 不写。**
- Mock 后端（round3 修两 bug）：振幅 2000→24000 让峰值过 QA 门槛；**修复 for-s 循环缩进错误**。
- `tts.py`（round5 新增）：TTS 车道契约——`gap_asset_kind(g)`(默认 bgm)、`choose_tts_engine()`(选活跃有样本引擎)、`tts_qa()`(复用硬门禁但抑制 loop 告警，标注 voice)。`ingest_generated --asset-kind tts` 走 `tts_qa`。
- `run_acestep.py`（round5 新增）：acestep 工单执行器（5090 触发步骤）。`--pending` 跑全部 submitted 工单；检测 `REPLACE_ME` 占位 cmd 并跳过告警；`--dry-run` 只打印。
- `RUNBOOK.md`（round5 新增）：闭合真实回路手册（配 generators.json → submit → run_acestep → poll/auto-approve → 验证）。
- `bgm-library/to-generate.jsonl`：10 条 ambient 生成任务（已被 generate_loop 路由消费，10 缺口现 routed_generate/acep-step）。

## 媒体格式
- 已批准母带已转 FLAC（无损，省 ~213MB 磁盘），catalog 路径/sha256/codec 已同步；可 flac→wav 还原。下游若只认 wav 需告知（当时未确认）。

## 未决
- `use_count` 已由 round6 闭环 60 fill 缺口 + round7 submit 复用 20 次起跳；`reconcile --fix` 已回填全部 generate 缺口 duration（10 ambient + 30 coverage_gap）。实时仓库现状：rev 172、gaps 100 = 80 filled + 20 routed_generate(acep-step·submitted，0 open)，6 个 `pulse` 死路已解锁（generators 补 pulse stem_profiles）。
- 外部依赖（closure 路径已就绪，差真实凭据/命令）：
  - acestep `invocation.cmd` 仍是 `REPLACE_ME` 占位（generators 已补 pulse 能力）；`run_acestep.py --pending` 检测 `REPLACE_ME` 会跳过，操作员配好真实 5090 ACE-Step CLI 后即可落 wav。配好后 `run_acestep.py --pending` → `generate_loop.py --poll --auto-approve` 闭合 20 工单（10 ambient + 10 coverage，见 RUNBOOK.md）。cmd 模板变量：`{seed}{mood}{stem}{duration}{out}{job_id}`，`out`=`bgm-library/pending/{job_id}.wav`。
  - ltx23 / grok15 的 `endpoint`/`auth_env` 仍是 `REPLACE_ME`；`ApiBackend` 已实现（重试/退避/鉴权），填好即用，填前建议把 `status` 置 `pending` 避免 failover+熔断。`grok15` 角色仍待定（垫乐 vs 配音）；若是配音应走 TTS 车道（`asset_kind:"tts"`）而非 BGM 生成。
  - H3 接口待补（capabilities 为空、status pending）。
- melo-cache 模型缓存应移出资产库；approve 当前 wav→approved 保留 wav，FLAC 转码未接（可选）。
- TTS 车道已接（routing/QA/report/review/self_test 全通）；但真实 TTS 生成/评估接入仍待补 tts 类缺口数据。
