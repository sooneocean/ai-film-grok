# 闭合真实回路 Runbook（关闭 10 个 ambient 缺口）

本仓库的 BGM 生成流水线已是**闭环**：`缺口 → 路由 → 后端 → 生成 → 入库 → 审核 → 回填缺口`。
本地 `self_test.py` 用 Mock 后端已验证整套链路。下面是如何用**真实后端**把仓库里现存的
10 个 `routed_generate`（acestep 工单）缺口真正闭合。

## 当前状态

- `bgm-library/gap-queue.jsonl`：60 个 open(fill) + 10 个 routed_generate（ambient 生成缺口）。
- `bgm-library/generation-jobs.jsonl`：10 个 `submitted` 的 acestep 工单。
- `bgm-library/.gen-tickets/*.json`：10 张 acestep 工单（`cmd` 目前是占位符）。

## Step 0 — 配置 generators.json

编辑 `bgm-library/generators.json`：

1. **acestep**（本地 5090，必填）：
   把 `invocation.cmd` 从占位符换成**真实的 ACE-Step CLI 调用**，模板变量会被自动替换：
   `{seed} {mood} {stem} {duration} {out} {job_id}`，
   其中 `{out}` 即 `bgm-library/pending/<job_id>.wav`（poll 会在这里等文件）。
   例：`ace-step --seed {seed} --mood {mood} --stem {stem} --duration {duration} --out {out}`

2. **ltx23 / grok15**（云端，可选）：填 `endpoint` + `auth_env`（去掉 `REPLACE_ME:` 前缀）。
   在真实 endpoint 就绪前，建议把 `status` 设为 `pending`，避免提交时触发 failover + 熔断冷却。
   `ApiBackend` 已实现（带重试/退避/鉴权），填好即用，无需改代码。

3. **grok15 角色待定**：先确认它产出的是**垫乐(BGM)**还是**配音(voice)**。
   若是配音，应走独立 TTS 车道（`asset_kind:"tts"`，由 `tts-evaluations` 评估样本池提供），
   而非 BGM 生成后端 —— 不要让它生成人声当垫乐用。

## Step 1 — 路由 / 重提工单（通常已做）

```bash
python3 tools/generate_loop.py --submit        # 把 open 生成缺口路由到 acestep，写工单
python3 tools/generate_loop.py --submit --dry-run   # 只看决策不动手
```
若 10 个工单已在，可跳过。TTS 缺口不会被交给声音后端（仅记录路由）。

## Step 2 — 在 5090 上真正跑 ACE-Step

```bash
python3 tools/run_acestep.py --pending --dry-run   # 先只打印命令确认
python3 tools/run_acestep.py --pending             # 逐张执行，把 .wav 落到 pending/
```
每张工单的 `cmd` 来自 Step 0 配置的模板；执行后 `.wav` 必须落在工单里的 `out` 路径，
`--poll` 才能在下一步发现它。

## Step 3 — 入库 / QA / 审核 / 回填

```bash
python3 tools/generate_loop.py --poll --auto-approve
```
`poll` 发现 wav → `ingest_generated` 重算 sha256/指纹/QA 并存入 catalog（status `pending_human_review`）
→ QA **硬门禁**（peak/rms/silence/duration）不达标则 **HOLD 等人工**；达标则自动 approve + fill 缺口。
软信号（zcr/dc/lufs/loop/近重复）只上报告警，不阻塞。

> 想强制忽略 QA 告警自动通过：`--no-qa-gate`（操作员覆盖，默认不开）。
> 想修复“太轻/有直流偏置”的床：`ingest_generated --normalize` 会就地去直流 + 峰值归一化。

## Step 4 — 验证

```bash
python3 tools/run_tests.py     # 43+ 单元测试（纯 stdlib，零依赖）
python3 tools/self_test.py     # 离线闭环回归（Mock 后端，不改真实仓库）
python3 tools/reconcile.py     # 跨实体一致性体检（孤儿/缺口/指纹）
python3 tools/report.py        # 可观测汇总 + 审计
python3 tools/route.py check   # 状态机契约校验
```

## 运维要点

- **熔断（breaker）**：某后端连续失败 3 次会冷却 600s，路由自动跳过；成功一次即复位（`tools/breaker.py --reset`）。
- **缺口回退**：生成失败或入库失败时，缺口回退为 `open` 以便重试，不会卡在 `routed_generate`。
- **stuck 清理**：`reconcile.py --fix` 会把“工单 failed/缺失”的 stuck `routed_generate` 缺口复位为 `open`。
- **TTS 车道独立**：`tts` 缺口由已评估引擎样本池服务，不经过声音生成后端。
- **安全**：所有工具按绝对路径操作仓库；self_test/run_tests 用临时副本，绝不污染真实仓库。
  提交前有 `validate_catalog.py` 门禁（pre-commit hook）。

## 不变量

- catalog schema `aifilm-bgm-library-v1`；资产 `aifilm-bgm-asset-v1`；任何改 catalog 前先跑校验器。
- 媒体文件（wav/flac/mp3/onnx）不进 git，仅元数据版本化（见 `.gitignore`）。
- 生成后端 = 在 `generators.json` 加一条目；router / generate_loop 代码不变。
