# 闭合真实回路 Runbook（视频镜头流水线）

本仓库的视频镜头流水线已是**闭环**：`缺口 → 路由 → 后端 → 生成 → 入库 → 审核 → 回填缺口`。
本地 `self_test.py` 用 Mock 视频后端已验证整套链路（含三条车道隔离：bgm / tts / video 互不污染）。
下面是如何用**真实后端**把 `video-library` 里的 `routed_generate`（生成）缺口真正闭合。

你的真实生成栈已映射到两个 `active` 后端（见 `bgm-library/generators.json`，视频车道专用）：

- **`grok-video15`**（云端，kind `video_api`）：Grok Video 1.5，OAuth 鉴权走 `XAI_API_KEY`。
  支持 `t2v` / `i2v` / `r2v` 三种模式。`ApiBackend` 已实现（带重试 / 指数退避 / 鉴权头），
  `endpoint` 填好即用，无需改代码。
- **`h3`**（本地 5090，kind `video_local`）：本地 H3 引擎，跑 `t2v` / `i2v` / `r2v`。
  提交时把工单写到 `video-library/.gen-tickets/*.json`，操作员在 5090 上跑完把 `.mp4`
  落到 `video-library/pending/`，`poll` 就能发现并入库。

## 当前状态

- `video-library/catalog.json`：镜头资产仓库（schema `aifilm-video-library-v1`）。
- `video-library/gap-queue.jsonl`：开缺口（含 `routed_generate` 的生成缺口）。
- `video-library/generation-jobs.jsonl`：生成工单台账。
- `video-library/.gen-tickets/*.json`：本地 H3 工单（`cmd` 目前多为占位符）。

## Step 0 — 配置 generators.json（视频后端）

编辑 `bgm-library/generators.json`（视频车道与声音车道共用同一份 generators 注册表，
靠 `asset_kind: ["video"]` 区分）：

1. **`grok-video15`**（云端，必填其一）：
   把 `endpoint` 从 `REPLACE_ME` 换成真实 Grok Video 1.5 上传/轮询 URL，
   并确保环境变量 `XAI_API_KEY` 已注入（OAuth token）。`auth_env` 已设为 `XAI_API_KEY`，
   不用改。`ApiBackend` 提交后轮询 `ext_id` 直到 `done` → 下载 `.mp4` 到 `pending/`。
   在 endpoint 就绪前建议把 `status` 设为 `pending`，避免提交触发 failover + 熔断冷却。

2. **`h3`**（本地 5090，必填其一）：
   把 `invocation.cmd` 从占位符换成**真实的 H3 调用**，模板变量会被自动替换：
   `{seed} {mood} {mode} {prompt} {resolution} {duration} {out} {job_id}`，
   其中 `{out}` 即 `video-library/pending/<job_id>.mp4`（`poll` 会在这里等文件）。
   例：`h3-cli --seed {seed} --mode {mode} --prompt "{prompt}" --res {resolution} --dur {duration} --out {out}`
   若是 `i2v` / `r2v`，参考图路径也会随工单下发（见 `ingest_video.py --source-image/--reference`）。

3. **模式覆盖**：两个后端都声明了 `modes: ["t2v","i2v","r2v"]`，路由按缺口的 `mode`
   过滤可用后端；若某后端不支持某模式，会自动被 capability matrix 排除（不会硬塞）。

## Step 1 — 路由 / 重提工单

```bash
python3 tools/video_pipeline.py submit              # 把 open 生成缺口路由到可用视频后端，写工单
python3 tools/generate_loop_video.py --submit --dry-run   # 只看决策不动手
```

若工单已在，可跳过。bgm / tts 缺口**绝不会被**交给视频后端（车道隔离，见「不变量」）。

## Step 2 — 在真后端上生成

### 2a. 本地 H3（5090）

```bash
python3 tools/video_pipeline.py run-h3 --dry-run     # 先只打印 5090 命令确认
python3 tools/video_pipeline.py run-h3               # 列出每张工单的真实 H3 命令
```

按打印出的命令在 5090 上执行；每张工单的 `cmd` 来自 Step 0 配置的模板。执行后 `.mp4`
必须落在工单 `out` 路径，`poll` 才能在下一步发现它。`run-h3` 会自动跳过已产出（文件已存在）的工单。

### 2b. 云端 Grok Video 1.5（OAuth）

`video_api` 后端在 `submit` 时直接调用 `ApiBackend.submit()`：上传 prompt / 参考图 → 拿 `ext_id`
→ 轮询状态。`endpoint` + `XAI_API_KEY` 配好后无需人工介入；失败会触发熔断退避到下一个可用后端
（例如 H3）。

> 想强制指定后端：`generate_loop_video.py --submit --backend h3`（或 `grok-video15`）。

## Step 3 — 入库 / QA / 审核 / 回填

```bash
python3 tools/video_pipeline.py poll                 # == generate_loop_video.py --poll --auto-approve
```

`poll` 发现 `pending/*.mp4` → `ingest_video` 重算 sha256 / 指纹 / QA 并写入 catalog
（status `pending_human_review`）→ QA **硬门禁**不达标则 **HOLD 等人工**；达标则自动 approve + fill 缺口。

**视频 QA 硬门禁**（任一项挂则 `ok=False`，不自动通过）：
- 可解码：存在真实视频流（codec / width / height / fps 齐全）。
- 时长：`duration >= 0.5s`，且在请求时长 ±15% 内（如请求 12s → 允许 10.2s~13.8s）。
- 黑场：`black_frame_ratio <= 5%`（signalstats YAVG，limited luma 黑=16，不是 0）。
- 冻结：`frozen_score > 0.02`（帧间 YAVG 增量，静态图伪装的视频会被拦下）。

**软信号（仅告警，不阻塞，需人眼判断）**：分辨率档位不符（480p/720p/1080p/1440p）、
镜头自带音轨（assemble() 会压到 BGM / TTS 底下）、与已批准镜头的近重复（cosine ≥ 0.98）。

> 想强制忽略 QA 告警自动通过：`generate_loop_video.py --poll --auto-approve --no-qa-gate`
> （操作员覆盖，默认不开）。
> 想单独复检某个文件：`python3 tools/qa_video.py pending/foo.mp4 --duration 12 --strict`
> （`--strict` 失败时非 0 退出）。
> ffmpeg / ffprobe 缺失时 QA 退化为「仅可解码 + 时长」，并上报告警。

### 人工审核入口

```bash
python3 tools/approve_asset_video.py --asset-id <id> --reviewer dex --auto-fill-gaps
python3 tools/reject_asset_video.py  --asset-id <id> --reviewer dex --reason "黑场过多"
```

审核页面：`python3 tools/gen_review.py` 同时生成 `bgm-library/review/index.html`
与 `video-library/review/index.html`（含 `<video>` 卡片 + 批准 / 拒绝命令 + 孤儿告警）。

## Step 4 — 验证

```bash
python3 tools/run_tests.py              # 76+ 单元测试（纯 stdlib + ffmpeg，零第三方依赖）
python3 tools/self_test.py              # 离线闭环回归（Mock 视频后端，三车道隔离断言）
python3 tools/reconcile_video.py        # 跨实体一致性体检（孤儿 / 缺口 / 指纹）
python3 tools/reconcile_video.py --fix  # 安全修复：stuck 工单复位、回填指纹
python3 tools/report.py                 # 可观测汇总（含视频车道：按状态 / 模式 / 缺口 / 覆盖 / 工单）
python3 tools/video_pipeline.py status --json   # 机器可读健康 blob
python3 tools/video_pipeline.py check   # 路由契约校验 + reconcile 体检
```

## Step 5 — 场景装配（可选）

把已批准镜头 + 匹配 BGM（压低到 0.35）+ 可选 TTS 配音合成为成片：

```bash
python3 tools/video_pipeline.py assemble --segments 3 --film-id my-film --out films/my-film.mp4
# 等价于：python3 tools/assemble.py --auto --segments 3 --film-id my-film --out films/my-film.mp4
```

`assemble.py` 用 ffmpeg `filter_complex` 合成：BGM 与 TTS 按 energy / mood 匹配，`--auto`
会读 catalog 自动挑镜头与配乐并写出 `films/film_manifest.json`（含 sha256）。
`--dry-run` 只看命令不落盘。

## 运维要点

- **熔断（breaker）**：某后端连续失败 3 次冷却 600s，路由自动跳过；成功一次即复位。
  `generate_loop_video.py --submit` 失败会记录 breaker，自动退避到下一个 capable 后端。
- **缺口回退**：生成失败或入库失败时，缺口回退为 `open` 以便重试，不会卡在 `routed_generate`。
- **stuck 清理**：`reconcile_video.py --fix` 会把「工单 failed / 缺失」的 stuck
  `routed_generate` 缺口复位为 `open`。
- **资格短路（eligibility）**：若已有 approved 镜头匹配同 mood/mode/energy 或近重复，
  路由会**直接 fill 缺口**而非重新生成（省算力，`use_count` 累加）。
- **车道隔离**：`video` 缺口只走视频后端；`bgm` / `tts` 缺口互不交叉（self_test 已断言）。
- **外部依赖单一**：视频车道只认 ffmpeg / ffprobe；缺失时 QA 自动降级而非崩溃。
- **安全**：所有工具按绝对路径操作仓库；self_test / run_tests 用临时副本，绝不污染真实仓库。
  提交前有 `validate_video_catalog.py` 门禁（pre-commit hook，与 BGM catalog 并列校验）。

## 不变量

- catalog schema `aifilm-video-library-v1`；资产 `aifilm-video-asset-v1`；
  任何改 `video-library/catalog.json` 前先跑 `tools/validate_video_catalog.py`。
- 媒体文件（mp4 / wav / flac / mp3 / onnx / png 参考图）不进 git，仅元数据版本化（见 `.gitignore`）。
- 新增生成后端 = 在 `generators.json` 加一条目（`asset_kind: ["video"]` + `modes`）；
  router / generate_loop 代码不变。
- 三车道（bgm / tts / video）共享 `generators.json` 注册表，但各自按 `asset_kind` 过滤后端，
  互不污染。
