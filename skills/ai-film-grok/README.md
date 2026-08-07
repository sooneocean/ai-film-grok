# ai-film-grok（skill 本体）

> **安装 / 使用逻辑 / 架构图 / 可插拔模型** → 仓库根 [README.md](../../README.md)（对外主文档）。  
> **版本**：**`2.39.56`** · 变更 [CHANGELOG](../../CHANGELOG.md) · 本季要点见根 README「v2.39 本季要点」。

**一句话**：把「从灵感到可发布的 AI 动态短片」收成**可恢复、可验收**的七段流程——定义故事 → 设计演出 → Pilot → 批量制作 → 选片与粗剪 → 后期母版 → 审片与交付。

正式交付必须是**真实动态成片**（I2V 验收），不是静图轮播、Ken Burns 或只有关键帧。

### v2.39 本 skill 增量（相对 2.37 以前）

| 模块 | 做什么 | CLI |
|------|--------|-----|
| Script-value debrief | 锁 story 前 L0–L4 呈现价值 + 人确认 | `plan debrief` |
| Input Fidelity | 源句 / must_keep / 保护对白打分与 stamp | `fidelity status\|check\|apply` |
| design-go | debrief+fidelity+variety 一页；不签 pilot | `design-go` |
| **h3_primary（默认）** | 全片 5090 H3 主烧；Grok Video 仅 escape | `h3 run-next --max 5` · [h3-core-day](references/stages/h3-core-day.md) |
| hybrid_h3 + FLF | 双轨：Grok soft 可铺量；H3 攻坚肉戏；有首尾帧 FLF | `h3 plan\|run` · profile `hybrid_h3` |
| Fill-Idle | 空闲 P0→P2 挑战；PK shortlist；人 promote | `h3 next\|run-next\|cycle\|pk-*` |
| still-challenge | FRW i2i 刷更好静帧再 I2V | `still-challenge` |

### 四层方法论（主脊）

```text
用户 Prompt / 剧本
        ↓
Grok Agent（规划 + Prompt 优化 + 角色一致性 + dispatch）
  · plan debrief → fidelity apply → design-go（锁前）
        ↓
1. 视觉生成     静帧 Grok；I2V 有 5090 默认 **h3_primary**（否则 grok_primary）
                · 对白讲话镜 → FRW LTX 2.3 有声
                · hybrid_h3：肉戏/高难/受限对白 → 5090 MiniMax H3（FLF/R2V）
                · 空闲 → Fill-Idle 挑战（不自动 promote）
2. 语音生成     Edge TTS（可插拔 voicebox / grok / minimax / fish / external）
3. 动态合成     HyperFrames（优先） / Remotion（备选）
4. 最终后处理   FFmpeg（拼板 · 混音 · 导出 · 字幕硬烧）
        ↓
最终 MP4 + 预览 + 可下载资产
```

**Skill 入口**：[`SKILL.md`](SKILL.md) 主脊 + 阶段路由 + 命令  
- **电影工序**：[`references/generative-film-craft.md`](references/generative-film-craft.md)  
- **工具四层**：[`references/pipeline-methodology.md`](references/pipeline-methodology.md)  
- **硬默认**：[`references/hard-defaults.md`](references/hard-defaults.md)  
- **火力矩阵**：[`references/weapon-lane-matrix.md`](references/weapon-lane-matrix.md)  
- **剧本价值**：[`references/script-value-debrief.md`](references/script-value-debrief.md)

运行时：优先 `aifilm dispatch` 的 **`phase`**；`status|next|preflight|stage` 的 `pipeline_stage` 仅供 HUD／旧项目诊断。

### 架构总览

![ai-film-grok 四层流水线](docs/architecture.png)

> 有私有 5090 时推荐 **`h3_primary`**（全镜本地 H3）；双轨用 **`hybrid_h3`**；纯云 **`grok_primary`**。成人云有声铺量用 **`ltx23_adult`**（safe 对白/soft→LTX 原音；meat→H3；i2i=still-challenge）。`ltx23_primary` 仅旧项目。完整插拔矩阵见仓库根 README。

---

## 这个 skill 能帮你省多少功？

手工用聊天窗口「一张张出图 → 一张张转视频 → 自己剪 → 自己配音 → 自己对字幕」，做一条 **60 秒竖屏（约 10 镜）** 时，常见成本大致是：

| 工作块 | 手工常见耗时 / 痛点 | 用本 skill 后 |
|--------|---------------------|---------------|
| 角色/画风定妆 | 反复改 prompt，脸服每镜飘 | **双 master**（style-v1 + cast-v1）+ lookbook，全片同一锚 |
| 分镜与旁白节奏 | 旁白过长 → 画面 loop 重播、成片无聊 | **Director’s Lens**（文本→故事→storyboard）+ **film-spec + VO 预算门禁** |
| 批量出图出片 | 记不住哪镜过了、重跑撞墙 | **media-queue** 串行 claim、失败 typed requeue、断点可续 |
| 一致性验收 | 成片才发现换脸/换服/换模 | **全项目硬性 cinematic-audit**（节拍、表演、对白覆盖、构图、连续性）+ pilot 三镜门禁 + still/clip 注册 + 十六维 scorecard；旧项目同样必须重审与补拍 |
| 配音混音字幕 | 手搓 TTS、BGM 抢戏、无字幕 | **一键 `final`**：Edge/外部 TTS、R&B 床轨、旁白 duck、PIL 烧字幕 |
| 60 秒时长对齐 | 短旁白把成片压成 40 秒 | **`duration_sec` 槽位下限**（静音 pad + 画面 hold 满槽） |
| 色气片踩坑 | BGM 变恐怖、中文声线乱、审核连撞 | 默认 **rnb**、中文 **edge**、moderation 换 soft still 纪律 |
| 系列续作 | 每集重定妆 | **复用 cast master**，新 root + 新剧情即可 |

### 粗算（一条 10 镜 · 60s 竖屏）

| 角色 | 手工（无纪律） | 本 skill + Grok Build agent |
|------|----------------|-----------------------------|
| 制片/导演决策 | 2–4 h（结构、节奏、重拍标准模糊） | **~15–40 min**（Director’s Lens 重构 + intent + film-spec，门禁自动拦错） |
| 出图 / 出动态 | 3–8 h（重做、漂移、记不住版本） | **~1–2.5 h**（定妆 + pilot + 串行 I2V；墙钟主要等 Imagine） |
| 后期成片 | 1–3 h（剪、配、字幕、对齐） | **`final` 数分钟级**（含 TTS + BGM + 烧字幕） |
| 质检返工 | 难估（常到交付前才爆） | **preflight / motion QA / pilot / review-final** 前置拦截 |

> **合计体感**：从「折腾一整天还漂」压到 **半日～一工作日内可交付技术成片**（含等待 Grok Imagine 队列）。  
> 省下的不只是时间，更是 **重拍次数、loop 废片、画风漂移导致的整片作废**。

**你仍要做的**（skill 故意不替你跳过）：

1. 给参考角色 / 定妆审美；  
2. 批准 pilot 三镜（说「可以」等）；  
3. 完整看完成片，十六维 scorecard 签字。

---

## 技术栈（你实际在用什么）

### 核心生成：四武器 + 证据化路由（v2.39）

| 能力 | 在本 skill 中的角色 | 入口 |
|------|---------------------|------|
| **Grok Imagine（图像）** | 文生图 / 图生图：风格样张、定妆、每镜关键帧 | `image_gen`、`image_edit` |
| **Grok Imagine Video** | 纯云 / hybrid 安全 bulk；`h3_primary` 下仅 opt-in | `image_to_video` · OAuth video |
| **FRW LTX 2.3** | **安全向**对白讲话镜原生有声；分类技术失败 fallback | `"$AIFILM" frw img2video-audio --model ltx2.3` |
| **FRW API I2V / i2i** | Grok 不可用后的 I2V 备选；**still-challenge** 刷更好静帧 | `frw img2video` · `still-challenge` |
| **本机 MiniMax H3（5090）** | `hybrid_h3`：肉戏/高难/受限对白；**FLF** 首尾帧；R2V 能量位 | `aifilm h3 plan\|run\|next\|cycle` |
| **Qwen I2I（状态照）** | 衣着/状态前进的状态照链 | 见 stages/visual · state-index |

要点：

- **分层（当前季）**：静帧默认 **Grok**；动作 **Grok bulk** → 对白安全向 **FRW LTX** → 受限/肉戏 **H3**；切换写 receipt，禁静默换 provider。  
- **FLF**：首+尾静帧齐 → H3 优先 first+last frame；无 last → I2V；`force_r2v` 时 last 作 pose land。  
- **Fill-Idle**：GPU 空闲才 P0→P1→P2；多 take 只 **pk shortlist**，**人 promote**；final 不等 P2。  
- FRW 须区分 `FRW_API_KEY`（任务）与 `FRW_TOKEN`（上传 JWT）；上传前 `upload-probe`；i2i 全局限速 ≥30s。  
- Python **不内嵌 key**：Grok 由 agent / OAuth；FRW 经 `frw_dispatch`；H3 经 Comfy 隧道；本仓负责 **规格、队列、QA、成片门禁**。  
- **单镜头 provider 原则**：同 shot 一旦 fallback 到 FRW/H3，后续重试固定该轨。
### 本地控制台与成片

高质量竖屏项目可显式启用 authored creative gates：

```bash
aifilm director init --root <film-root> --quality-target premium_vertical
aifilm director status --root <film-root>
aifilm preflight --root <film-root>
```

Premium 项目在真实 Pilot 前可先建立无花费的质量闭环；它不会调用 provider 或花费额度：

```bash
aifilm quality-closure package --root <film-root>
aifilm quality-closure report --root <film-root>
```

只有真实 provider 媒体、当前成片交付证据和两位独立盲审齐全，报告才会标示艺术品质已验证；provider canary 还必须匹配已注册、approved、active 的 manifest clip。细则见 [`references/quality-closure.md`](references/quality-closure.md)。

旧项目默认 `standard`，不会被静默升级。

| 组件 | 用途 |
|------|------|
| **`aifilm` CLI** | dispatch / plan / fidelity / design-go / h3 / still-challenge / final / review / doctor … |
| **`media-queue`** | 本地 I2V 任务队列：add → claim → complete/fail → requeue；串行防 429 |
| **film-spec JSON + schema** | 导演意图、分镜 beat、旁白、运镜 DSL、转场与 sound_plan |
| **script-value-debrief** | 锁 story 前 L0–L4 价值卡（`receipts/script-value-debrief.json`） |
| **input-fidelity** | 源句/must_keep/保护对白评分（`receipts/input-fidelity.json`） |
| **style-bible** | medium / palette / signature_block / identity_lock / cast_masters / 上传画风图 SHA-256 锚 |
| **FFmpeg + PIL** | 拼接、xfade、stretch/hold、VO 混音、BGM duck、字幕硬烧 |
| **Edge TTS（默认中文）** | 说书 `write-spec` 钉 edge；支持 shot-level `performance_cue`；禁止 Neural 名塞 ElevenLabs |
| **表达式 TTS（显式）** | `qwen3` 本机 voice design/clone；`higgs` 可信 adapter；未就绪不静默替换 |
| **程序化 R&B + 听感** | rnb / auto_sfx / sidechain / loudnorm auto；本地 `audio/bgm.wav` 模板曲 |
| **HyperFrames / Remotion**（层 3 · 交付推荐） | 标题/双字幕/grade；`final --post-engine hyperframes`；Remotion 备选；**不能替代** I2V |
| **FFmpeg**（层 4） | 多镜拼板、VO/BGM 混音、loudnorm、编码导出；设计路径下 plate 默认 blank+subs off |
| **jsonschema / pytest** | 规格校验与门禁单测 |

### 竖屏电影悬疑包装

复制 [`templates/show-package.suspense-red.example.json`](templates/show-package.suspense-red.example.json) 为影片 root 的 `show-package.json`，再以 `final --post-engine hyperframes` 输出。`suspense-red` 固定使用 1.8 秒片头、2.2 秒片尾、单一字幕所有权与连载 `ending_question` 优先的钩子；本地生成的低音提示音只会落在 SRT 未覆盖的时段，避免压住最后一句对白。每集只能登记 `post_owner=hyperframes`；Remotion 仅可做对比或衍生版型。

### 数据与可恢复性

每个项目 root 是自包含工程目录：

```
film-root/
  style-bible.json      # 画风与身份锁
  film-spec.json        # 分镜 + 旁白 + 导演意图
  source/               # 上传的参考图（style-lock 保存并记录 SHA-256）
  canonical/            # style-v1 + cast/*-v1 + lookbook
  keyframes/            # 每镜静帧
  clips/                # 每镜 I2V（Imagine Video）
  audio/                # VO / BGM / mix_report；可选 bgm.wav 模板曲
  compose/              # 设计后期 HF/Remotion 包
  receipts/             # pilot、queue、compose-preview、审批痕迹
  out/film_final.mp4    # 技术成片
  manifest.json         # hash 与注册记录
```

听感 + 设计后期总表：[references/lessons-2026-07-20-audio-compose.md](references/lessons-2026-07-20-audio-compose.md)。

中断后续跑：`aifilm next --root …` / `media-queue claim`，不必重开人脑。

### 生成次数 / token / 费用

```bash
aifilm usage status --root "<film-root>"
aifilm usage list --root "<film-root>" --format table
aifilm usage summary --scan-root "/Users/dex/AI FILM SPACE"
```

OAuth/API 路径传 `--root` 后会自动保存每次请求的真实
`usage.cost_in_usd_ticks`；没有 provider 回执时明确显示 `unknown`。会话内原生
`image_gen` / `image_edit` / `image_to_video` 完成后用 `aifilm usage record`
补录次数，禁止按总 quota 差分摊。详见
[generation-usage-accounting.md](references/generation-usage-accounting.md)。

---

## 端到端流水线（技术细节 · v2.39）

```text
用户意图 / 剧本 / 角色参考图
        │
        ▼
   aifilm init + style-bible（anime/色气须改 medium，禁默认 photoreal）
        │
        ▼
   plan debrief（L0–L4 呈现价值 · 人确认）→ plan run
   fidelity apply/check → design-go（一页纸，不签 pilot）
        │
        ▼
   Grok Imagine：style-v1 + cast master + lookbook
        │
        ▼
   lock-style  →  write-spec（intent / beat / vo_budget / vo_pacing）
        │
        ▼
   Pilot 三镜：静帧 → I2V（Grok 或 H3）→ pilot score → 用户批准
        │
        ▼  (run_to_completion: 可一路做完)
   批量：Grok bulk ｜ hybrid_h3 肉戏 → h3 run（FLF）｜ 空闲 Fill-Idle
   弱 still → still-challenge（人 promote）→ 再 I2V
        │
        ▼
   register-still / register-clip（身份 + motion QA）
        │
        ▼
   aifilm final（edge TTS + rnb BGM + 字幕硬烧 + duration_sec 槽位）
        │
        ▼
   review-final 十一维 → export-desktop
```

### 1）一致性：双 master，而不是「每镜重新发明角色」

- **style-v1**：介质/色板/渲染语言样张。  
- **cast/\<id\>-v1**：着衣定妆（高色气参考可锁气质，但**不要**当全片唯一 naked 锚，否则构图坍缩）。  
- 主角镜头优先 **`image_edit`（cast 第一参考）**，避免纯 `image_gen` 换脸。  
- 每镜 prompt 前缀：`signature_block` + `Identity lock: …`。

### 2）导演规格：film-spec 硬门禁

- `director_intent`：logline / tone / emotional_arc。  
- 每镜 `dramatic_function`：`hook | approach | sensory | reaction | action | afterglow | bridge`。  
- 旁白 **≤55 字硬限，快节奏推荐 ≤28 字**；`est_vo_sec ≤ duration_sec + 0.5`。  
- **hook / action 禁止 stream_loop** 撑时长——不够就加镜或升 10s。  
- 色气 tone + `sound_plan.mood: dark` → write-spec **自动改 rnb**。

### 3）Grok Imagine Video 1.5：I2V 纪律

- 一次只 **claim 一件** `image_to_video`（并发易 429）。  
- 静戏必须可测微动：blink / breath / hair / push-in。  
- `register-clip`：解码、时长、抽帧 **motion_score** 门禁。  
- 失败 reason：`moderation | motion | rate_limit | decode | other`；**禁止手改** `media-queue.json`。

### 4）Pilot（S3）

- 无用户批准时最多 **3** 个不同 shot 进队列。  
- 批准词：`可以` / `pilot 过` / `ok` …；含「生成完成 / 做完」→ **`run_to_completion: true`**，agent 一路到 final。  
- **禁止 agent 自批**。

### 5）成片 `final`

- TTS：中文默认 **edge**（勿把 `zh-CN-*Neural` 塞进 ElevenLabs）。  
- BGM：色气 **rnb**；horror 才 dark。  
- `duration_sec`：stretch **下限**（短 VO → 静音 pad + 画面 hold），10×6s ≈ 60s。  
- 转场：soft xfade / hard / hold（可按 beat 自动）。  
- 可选 `--post-engine hyperframes` 做设计字幕（仍不替代 I2V）。

### 6）十一维 scorecard（`review-final`）

`identity | style | motion | escalation | audio | subs | dead-air`  
全 pass 才 `final_complete`，才允许正式 `export-desktop`。

---

## 安装

**推荐**：按仓库根 README 用 **Grok plugin** 安装（`grok plugin install` / 本机 symlink）。  
本机源码真相：`~/.grok/plugins/ai-film-grok`（skill 在其下 `skills/ai-film-grok`）。

```bash
# 从 Gitea 拉源码（开发机）
git clone http://172.238.15.154:3000/Redredchen01/ai-film-grok.git \
  ~/.grok/plugins/ai-film-grok
# 或组织仓：http://172.238.15.154:3000/aidev/ai-film-grok.git

cd ~/.grok/plugins/ai-film-grok
ln -sfn "$(pwd)/skills/ai-film-grok" ~/.grok/skills/ai-film-grok

cp skills/ai-film-grok/config.env.example skills/ai-film-grok/config.env
chmod 600 skills/ai-film-grok/config.env
# 按需填 TTS / FRW / Comfy 隧道；中文成片可保持 AIFILM_TTS_BACKEND=edge

python3 -m pip install -r skills/ai-film-grok/requirements.lock   # 建议 3.11+

skills/ai-film-grok/scripts/aifilm doctor
# 改过 scripts 后：
# skills/ai-film-grok/scripts/aifilm lock-runtime
```

**运行时依赖**：本机 **ffmpeg / ffprobe**；Grok Build 会话内 **Imagine 图像 + Video**；可选 **FRW**、**RTX 5090 Comfy（H3）**。

### 触发方式

- 对话：`/ai-film-grok` · `/aifilm`  
- 意图：AI 电影、漫剧、分镜成片、色气竖屏剧、角色一致性短片、配音后期  

Agent 应同时加载 Grok 的 **Imagine / Imagine Video** 工具能力（本 skill 的 Python **不**代发 Imagine 付费请求）。

---

## 最小生产命令

```bash
SKILL_DIR="${HOME}/.grok/plugins/ai-film-grok/skills/ai-film-grok"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"
ROOT="/abs/path/film"

"$AIFILM" doctor
"$AIFILM" init --theme "色气里番 竖屏" --title "片名" --aspect 9:16 --root "$ROOT"

# 故事价值 → 保真 → 设计一页（锁前）
"$AIFILM" plan debrief --root "$ROOT" --action seed
"$AIFILM" plan debrief --root "$ROOT" --action confirm --user-phrase "确认"
"$AIFILM" fidelity apply --root "$ROOT"
"$AIFILM" design-go --root "$ROOT"

# 定妆 + 镜表 + pilot（用户批准后 bulk）
"$AIFILM" write-spec --root "$ROOT"
"$AIFILM" pilot pick --root "$ROOT"
# … pilot score / approve …
# hybrid_h3 时：aifilm h3 plan|run；空闲：h3 cycle

"$AIFILM" final --root "$ROOT" --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge
"$AIFILM" review-final --root "$ROOT" --approve --reviewer "you" \
  --notes "完整观看通过" \
  --score-identity pass --score-style pass --score-motion pass \
  --score-escalation pass --score-audio pass --score-subs pass --score-dead-air pass
"$AIFILM" export-desktop --root "$ROOT" --name "中文片名"
```

开场三连：

```bash
"$AIFILM" doctor
"$AIFILM" dispatch --root "<root>"   # 优先：读 next_action
"$AIFILM" next --root "<root>"       # 旧兼容
```

---

## 仓库结构

| 路径 | 说明 |
|------|------|
| `docs/architecture.png` | 架构总览图（Imagine + Video + 本地流水线） |
| `SKILL.md` | Agent 执行规范（流程、门禁、禁区 · 短主脊） |
| `scripts/aifilm` | 统一 CLI 入口（锁 pyenv） |
| `scripts/media-queue` | I2V 任务队列 |
| `scripts/input_fidelity.py` · `script_value_debrief.py` | 输入保真 / 剧本价值 |
| `scripts/h3_workflow.py` · `still_challenge.py` | 5090 H3 + FRW still 挑战 |
| `scripts/render_final.py` | 成片：stretch 槽位、TTS、BGM、字幕 |
| `scripts/pilot_review.py` | pilot scorecard / 批准词 / run_to_completion |
| `scripts/production_gates.py` | pilot / loop-risk 等硬门禁 |
| `references/` | hard-defaults · weapon-lane · stages · lessons… |
| `memory/` | 短记忆卡（会话索引） |
| `templates/` | film-spec / style-bible / debrief 示例 |
| `schemas/` | film-spec · script-value-debrief 等 |
| `tests/` | 门禁与流程单测 |
| `config.env.example` | 本地配置模板（**无密钥**） |

---

## 安全

- **禁止**提交 `config.env` 或任何 API key / Gitea 密码。  
- 密钥只写本机 `config.env`（chmod 600）。  
- 外部 TTS/lipsync 仅 **JSON argv**，禁用 shell 模板；子进程最小环境。  
- 日志与 manifest **不写**密钥或 prompt 明文。  
- 聊天里贴过的 key/密码应 **轮换**。

---

## 测试

```bash
cd ~/.grok/skills/ai-film-grok
scripts/test tests/ -q
```

`scripts/test` 和 `aifilm` 使用相同的 Python 3.11+ 解析器；如果环境把
`python3` 指向旧版，会明确失败而不是产生误导性的测试结果。

## 个人品质复盘

每次 `review-final` 成功后都会写入 `receipts/quality-ledger.json`，汇总每镜生成
尝试、真实或 `unknown` 成本、身份/动作审阅、镜头去重、终片审阅与失败 Pareto。
完整看片后，只记录下一条片唯一的 P0：

```bash
scripts/aifilm quality-ledger record --root "<film-root>" \
  --director-score 82 --worth-publishing \
  --p0-improvement "先修正动作起讫状态，再开始下一条 pilot" \
  --reshoot-reason "shot03: 动作结果不可读"
```

---

## 不可宣称（交付诚实）

- 未 lock-style + cast → 不得声称「角色已锁定」。  
- 未 pilot 用户批准 → 不得批量。  
- 无 Imagine Video 动态 clip、只有字卡/Ken Burns → 不得声称「Grok 动态成片」。  
- 无 `review-final` → 不得声称正式交付完成。

---

## License

Private skill for team use unless otherwise stated.

---

## 致谢 / 模型标注

本流水线的**画面与运动生成**建立在可插拔多轨上：

- **Grok Imagine** — 关键帧与角色/画风锁定（text-to-image / image-edit）  
- **Grok Imagine Video** — 安全 bulk 镜头运动（image-to-video）  
- **FRW LTX 2.3** — 安全向对白原生有声  
- **本机 MiniMax H3（RTX 5090）** — 肉戏/高难/FLF/R2V 攻坚  

本地侧负责导演规格、输入保真、火力路由、一致性门禁、队列编排、音画合成与验收——让你把算力花在「拍片」，而不是重复踩坑。

<!-- BEGIN GENERATED: project-status -->
### 当前项目状态（自动同步）

- 插件版本：`2.40.32`
- Published skills：`2`
- Skill Registry：`32/34` 项标记为 `implemented`
- Python 脚本：`676` 个
- pytest 文件：`439` 个
- 同步入口：`make sync-docs`（只更新文档）或 `make sync`（验证、提交并 push）
- Graph：[`docs/GRAPH.md`](./docs/GRAPH.md)
<!-- END GENERATED: project-status -->
