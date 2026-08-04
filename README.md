# ai-film-grok

**Grok Build 插件**：把「灵感到可验收的 AI 动态短片」收成一条**可恢复、可门禁、可插拔模型**的流水线。

- **不是**静图轮播 / Ken Burns / 只有关键帧  
- **是** I2V 真动态 + 旁白混音 + 字幕 + 十一维验收 → 可交付 MP4

| | |
|---|---|
| **版本** | 见 [`plugin.json`](./plugin.json) |
| **仓库** | https://github.com/sooneocean/ai-film-grok |
| **斜杠命令** | `/ai-film-grok` · `/aifilm` |
| **CLI** | `skills/ai-film-grok/scripts/aifilm` |
| **Agent 入口** | [`AGENTS.md`](./AGENTS.md) · skill 主脊 [`skills/ai-film-grok/SKILL.md`](./skills/ai-film-grok/SKILL.md) |

---

## 目录

1. [安装](#安装)
2. [使用逻辑（先读这个）](#使用逻辑先读这个)
3. [架构图](#架构图)
4. [可插拔模型一览](#可插拔模型一览)
5. [最小成片路径](#最小成片路径)
6. [配置](#配置)
7. [本机开发 / 发版](#本机开发--发版)
8. [验证](#验证)

---

## 安装

### 前提

- [Grok Build](https://grok.x.ai)（或已安装 `grok` CLI 的本机环境）
- Python **3.11+**、`ffmpeg` / `ffprobe`
- 成片时建议：已 `grok login`（OAuth → `~/.grok/auth.json`），便于 Imagine / OAuth I2V / opt-in Grok TTS

### A · 从 GitHub 安装（另一台机器 / 干净环境）

```bash
grok plugin install sooneocean/ai-film-grok --trust
grok plugin enable ai-film-grok
# 之后拉更新：
grok plugin update ai-film-grok
```

TUI：`/plugins` → 选 `ai-film-grok` → `Space` 启用 · `r` 重载。

### B · 本机开发（源码即运行）

源码默认在用户插件目录（本仓绝对路径）：

```text
~/.grok/plugins/ai-film-grok
```

```bash
grok plugin validate ~/.grok/plugins/ai-film-grok
grok plugin install ~/.grok/plugins/ai-film-grok --trust
grok plugin enable ai-film-grok
# 改完源码后刷新 installed 副本：
grok plugin update ai-film-grok
```

### C · 用户 skill 路径

本机推荐：

```text
~/.grok/skills/ai-film-grok  →  symlink →  ~/.grok/plugins/ai-film-grok/skills/ai-film-grok
```

**不要**再开第二份可写副本；单一真相只在 plugin 源码树。

### D · 密钥与本地配置

```bash
cp ~/.grok/plugins/ai-film-grok/skills/ai-film-grok/config.env.example \
   ~/.grok/plugins/ai-film-grok/skills/ai-film-grok/config.env
chmod 600 ~/.grok/plugins/ai-film-grok/skills/ai-film-grok/config.env
# 按需填 FISH_ / MINIMAX_ / VOICEBOX_ / XAI_API_KEY 等；config.env 永不提交
```

---

## 使用逻辑（先读这个）

类比拍短片：**先定剧本与试镜，再批量开拍，再剪辑成片**——不能跳步 bulk。

### 单一主流程，内部多层证据

| 轴 | 解决什么 | 入口 |
|---|---|---|
| **七段主流程** | 使用者唯一的项目进度 | 定义故事 → 设计演出 → Pilot → 批量制作 → 选片与粗剪 → 后期母版 → 审片与交付 |
| 八环检查表 | 内部创作证据与回退定位 | Idea → Story → Beats → Shots → Media → Selects → Rough → Verified MP4 |
| Professional 11 阶段／工具层 | 旧项目相容、路由与审计 | 相容诊断字段，不作为第二套进度 |

### 自动调配（每回合主入口）

开任何片子、每完成一步后，**优先**：

```bash
SKILL_DIR="${HOME}/.grok/plugins/ai-film-grok/skills/ai-film-grok"
[ -d "$SKILL_DIR" ] || SKILL_DIR="${HOME}/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"

"$AIFILM" doctor
"$AIFILM" dispatch --root "<film-root>"
# 读 JSON：phase · next_action · blocked_by · required_proof · optional_actions
# 本回合只做 next_action；做完再 dispatch。禁止跳过 Pilot 后直接 bulk。
```

| 字段 | 含义 |
|------|------|
| `phase` | **唯一**对外阶段与完成所需证据 |
| `next_action` | **唯一**可执行下一步；`next_cmd` 是兼容字段 |
| `blocked_by` | 当前必须解除的阻塞原因 |
| `required_proof` | 进入下一段需要的实际证据 |
| `optional_actions` | 非主线辅助项，不可替代下一步 |
| `workflow` / `craft_stage` | 旧项目相容与诊断投影 |

`dispatch` **不会**：自批 pilot、静默改 film-spec、默认开 lipsync。  
用户说「可以 / 一路做完」才 unlock 批量。

### 七段流程 → 你该做什么

| 阶段 | 通过证据 | 典型下一步 |
|------|----------|------------|
| 定义故事 | 主题、故事来源与叙事图已确认 | `plan run` / Lens / narrative lock |
| 设计演出 | 画风、状态、镜头与时长计划已锁定 | `lock-style` · `write-spec` |
| Pilot 样片 | 代表镜完整审看，用户明确批准 | `pilot report` / `pilot approve` |
| 批量制作 | 所需镜头已生成、审查、登记 | `media-queue` · `register-clip` |
| 选片与粗剪 | 选择集、接戏、节奏有当前证据 | `selects` · `editor-cut` |
| 后期母版 | 字幕、混音、final review、post-audit 已绑定 | `tts-rehearse` · `final` · `review-final` |
| 审片与交付 | 完整观看、解码、hash、导出回读完成 | `export-desktop` |

### 硬门禁（工程 · 不可跳）

1. **write-spec 过** → 才 `media-queue`  
2. **pilot 用户批准** → 才 bulk（无批准 ≤3 shot）  
3. **continue**：末帧 SHA = 下镜 keyframe；缝 **hard**  
4. **VO 预算**：`nar`≤55 字；hook/action 不 loop  
5. **双烧**：设计路径 `plate-cards blank` + `subs off`  
6. **交付**：十一维全 pass + 完整观看 → `final_complete`
7. **失败**：`media-queue fail/requeue`；禁手改 queue JSON  
8. **同源**：禁半片 Grok + 半片 FRW still/2V  

叙事/尺度/女主人数跟 brief 走（软）；`heat_scale=max` 时另有产品硬底（性爱时长 ≥20%、卸甲阶梯、旁白荤梗）——见 skill 内 `references/ecchi-story.md`。

### Agent 在 Grok Build 里怎么用

1. 会话加载 skill：`/ai-film-grok` 或 `/aifilm`  
2. 给主题 / 参考图 / film root  
3. Agent 跑 `dispatch`，先解除 `blocked_by`，只执行 `next_action`
4. 静帧 / I2V 优先会话内 Imagine 工具；量产可用 OAuth 队列  
5. 你批准 pilot → bulk → `final` → 你完整看片签十一维

---

## 架构图

### 总览（七段主流程 + 工具层）

![ai-film-grok 架构：Prompt → 七段主流程 → 视觉/语音/设计/FFmpeg → 交付；侧栏可插拔模型](skills/ai-film-grok/docs/architecture.png)

矢量源：[`skills/ai-film-grok/docs/architecture.svg`](./skills/ai-film-grok/docs/architecture.svg) · PNG：[`architecture.png`](./skills/ai-film-grok/docs/architecture.png)

### Mermaid（GitHub 可渲染）

```mermaid
flowchart TB
  subgraph IN["输入"]
    P["用户 Prompt / 剧本 / 参考图"]
  end

  subgraph AGENT["规划层 · Agent + aifilm"]
    D["dispatch 每回合"]
    L["Director's Lens"]
    S["film-spec + write-spec"]
    STY["lock-style / cast master"]
    PI["pilot 三镜 · 用户批准"]
    D --> L --> S --> STY --> PI
  end

  subgraph VIS["1 · 视觉层 · 可插拔"]
    STILL["静帧<br/>image_gen / image_edit / OAuth image"]
    I2V["I2V bulk<br/>默认 grok_primary → Grok image_to_video"]
    FRW["对白讲话镜锁 FRW LTX 2.3 原生有声<br/>分类技术失败 fallback → FRW API I2V → Grok"]
    Q["media-queue · register-clip · continue"]
    STILL --> I2V --> Q
    FRW -.-> Q
  end

  subgraph VOI["2 · 语音层 · 可插拔"]
    TTS["TTS 默认 edge<br/>+ voicebox / grok / minimax / fish / external"]
    BGM["BGM 默认程序化 rnb<br/>+ 用户提供的已授权曲库"]
    LIP["Lipsync 默认 off<br/>+ MuseTalk / Wav2Lip / FRW lipsync"]
  end

  subgraph POST["3–4 · 设计 + 后处理 · 可插拔"]
    HF["HyperFrames 优先"]
    REM["Remotion 备选"]
    FF["FFmpeg plate · loudnorm · 封装"]
    HF --> FF
    REM --> FF
  end

  subgraph OUT["交付"]
    RV["review-final 十一维"]
    EX["export-desktop · final MP4"]
    RV --> EX
  end

  P --> AGENT
  PI -->|批准后 bulk| VIS
  VIS --> VOI
  VOI --> POST
  POST --> OUT

  note1["一键 final --post-engine hyperframes<br/>= FFmpeg plate → HF → 封装"]
  POST --- note1
```

### 数据落盘（film root）

```text
<film-root>/
├── film-spec.json          # 镜表 · provider · VO · 门禁字段
├── style-v1 / cast/        # 画风与角色锚
├── keyframes/ · clips/     # 静帧与 I2V
├── audio/                  # TTS · BGM · mix
├── receipts/               # dispatch / pilot / queue / review
└── out/                    # 成片与导出
```

### 生成次数 / token / 费用

```bash
aifilm usage status --root "<film-root>"
aifilm usage list --root "<film-root>" --format table
aifilm usage summary --scan-root "/Users/dex/AI FILM SPACE"
```

每次 T2I、image edit、I2V/T2V 与 TTS 请求写入
`receipts/generation-usage.json`。真实费用只认 provider 返回的
`usage.cost_in_usd_ticks`；没有真实字段时为 `unknown`，不会根据 quota 差倒推。

### 可量化优化

`aifilm metrics emit --root <film>` 会把 receipts 聚合成 `metrics.json`；未知成本、
时间或人工输入会明确保留为 `unknown`，绝不当作零。用 `aifilm metrics human-time`
追加人工分钟，`aifilm experiment` 保存单变量 baseline/treatment 比较，`aifilm gold
calibrate` 只校准 early-reject 指标，不能替代 `review-final`。`aifilm dashboard build`
输出只读 receipts 的静态 HTML，默认只扫最近 30 天。
原生 Imagine 工具须在调用后执行 `aifilm usage record`。详见
[generation-usage-accounting.md](skills/ai-film-grok/references/generation-usage-accounting.md)。

### 成片生成复盘

`review-final` 通过后会自动写入 `receipts/production-report.json` 与
`out/production-report.html`，统计 T2I、I2I、I2V、T2V、TTS 的请求、状态、重试、
Token 与真实成本；HTML 会随 Desktop export 一起带出。算力统一采用真实成本，未知
provider 回执绝不换算为零。

在 `production-book.json` 中明确配置可比作品库，才会生成同模板趋势：

```json
"optimization": {
  "template_id": "vertical-drama-v1",
  "history_root": "/Users/dex/AI FILM SPACE"
}
```

也可只读重建或临时覆盖作品库：

```bash
aifilm production-report emit --root "<film-root>" --history-root "/Users/dex/AI FILM SPACE"
```

### 工程一键交付顺序（勿与工序心智搞反）

```text
final --post-engine hyperframes
  = [4] FFmpeg plate（subs off）→ [3] HyperFrames → [4] 封装
```

纯 FFmpeg 烧字：`--post-engine ffmpeg` · Remotion：`--post-engine remotion`。

---

## 可插拔模型一览

所有「默认」可用环境变量或 `film-spec.json` 覆盖；**禁止静默换声 / 静默换 I2V provider**。  
机位一页：`aifilm capability` · 深度鉴权：`aifilm grok-oauth doctor --deep`。

### 1 · 静帧 / 图像

| 插槽 | 默认 | 可切换 | 怎么换 |
|------|------|--------|--------|
| 会话出图 | Grok Imagine `image_gen` / `image_edit` | 同左（主路径） | 加载 `/imagine`；角色用 **edit(cast)** |
| OAuth 批处理 | `aifilm grok-oauth image` / `image-edit` | 模型名 env | `AIFILM_GROK_IMAGE_MODEL`（默认 `grok-imagine-image`） |
| 鉴权 | OAuth `~/.grok/auth.json` | API key 兜底 | `AIFILM_GROK_AUTH=auto\|oauth\|api_key` · `XAI_API_KEY` |

### 2 · I2V / 视频（人物动）

| 插槽 | 默认（当前季） | 可切换 | 怎么换 |
|------|----------------|--------|--------|
| **运营 profile** | `grok_primary` | `ltx23_primary`（仅旧项目锁定） | `AIFILM_I2V_PROFILE=…` |
| **L1 人物 I2V** | Grok `image_to_video`（对白讲话镜锁 FRW LTX 2.3 有声） | FRW API `img2video` → FRW LTX 2.3 | 每路均需影片级 approved canary；仅分类技术失败可切换 |
| OAuth 批 I2V | `queue-run-oauth` / `grok-oauth video --wait` | 视频模型 env | `AIFILM_GROK_VIDEO_MODEL`（默认 `grok-imagine-video`） |
| L2 无脸环境床 | FRW **`ltx-t2v`**（`env-plate`） | — | `aifilm env-plate` · register `frw_ltx_t2v` |
| 会话工具 | `image_to_video` | `reference_to_video`（少用） | 无原生 T2V |

```bash
# 当前默认
AIFILM_I2V_PROFILE=grok_primary

# 仅旧项目显式锁定时使用 LTX-first 兼容路径
# AIFILM_I2V_PROFILE=ltx23_primary
```

### 3 · TTS（旁白）

| 后端 ID | 角色 | 默认？ | 配置要点 |
|---------|------|--------|----------|
| **`edge`** | 中文量产说书 | **是** | `zh-CN-*-Neural`；零依赖 |
| `voicebox` | 本机克隆 / 多引擎 | 否 | `VOICEBOX_BASE_URL` + **固定** `VOICEBOX_PROFILE` |
| `grok` | SuperGrok OAuth TTS | 否（永不 auto） | `AIFILM_TTS_BACKEND=grok` · `AIFILM_GROK_TTS_VOICE` |
| `minimax` | 在线情感 | 否 | `MINIMAX_API_KEY` + 固定 `MINIMAX_VOICE_ID` |
| `fish` | 在线克隆 | 否 | `FISH_API_KEY` + 固定 `FISH_VOICE_ID` |
| `external` | CosyVoice 2 / ElevenLabs / 自研 | 否 | **仅** `AIFILM_TTS_ARGV` JSON argv（禁 shell 字符串） |
| `auto` | 按就绪度排序 | 可选 | external → voicebox → minimax → fish → edge |

```bash
AIFILM_TTS_BACKEND=edge          # 推荐中文成片
# AIFILM_TTS_VOICEBOX_FALLBACK=1 # opt-in：显式后端失败再试 Voicebox 一次
# 试听对照：
# aifilm tts-ab --root <film> --shot shot01 --backends edge,voicebox
```

**硬规则**：不要把 `zh-CN-*-Neural` 塞进 ElevenLabs；一角一声；显式后端失败不静默跨商换声。

### 4 · BGM / 音乐

| 插槽 | 默认 | 可切换 | 说明 |
|------|------|--------|------|
| 听感池 | 内置 5 首 CC0 程序化 R&B loop；也可放入已授权纯乐器 | `playful` / `warm` / `dark` | 每首内置或用户曲目均须有 `.license.txt` |
| 工程默认 | 程序化 multi-style v3 | `--music-seed` / `audio_policy.music_seed` | 当前无已授权本地曲目时的唯一默认床轨 |
| 用户文件 | — | `--music <path>` | 优先于生成 |
| 外接生成 | off | `AIFILM_MUSIC_ARGV` | 失败回落池 / 程序化 |

### 5 · Lipsync（口型）

| 后端 | 默认 | 说明 |
|------|------|------|
| `off` | **是** | 说书强制 off |
| MuseTalk / Wav2Lip | 否 | `backend-lock` 审权重后 lock |
| FRW lipsync | 否 | `frw-lipsync probe`→201 再 run；403/502 跳过 |
| `external` | 否 | `AIFILM_LIPSYNC_ARGV` JSON argv |

```bash
AIFILM_LIPSYNC_BACKEND=off
# final 时：--lipsync off|auto|require
```

### 6 · 后期合成引擎

| 引擎 | 默认 | 命令 |
|------|------|------|
| **HyperFrames** | **是** | `final --post-engine hyperframes` |
| FFmpeg 纯烧 | 否 | `--post-engine ffmpeg` |
| Remotion | 否 | `--post-engine remotion` |

### 7 · 推理 / 规划（Grok 侧）

| 能力 | 默认模型 / 入口 | 覆盖 |
|------|-----------------|------|
| 会话推理 | Grok Build 主模型 | 会话内 |
| OAuth chat | `AIFILM_GROK_CHAT_MODEL`（默认 `grok-4.5`） | env |
| 结构化规划 | film-spec + Director’s Lens | 本地 JSON |

### 适配器目录（插拔实现）

```text
skills/ai-film-grok/scripts/adapters/
├── grok_oauth_image.py / grok_oauth_image_edit.py / grok_oauth_video.py / grok_oauth_tts.py
├── voicebox_tts.py
├── cosyvoice_tts.py · cosyvoice_infer.example.py
├── elevenlabs_tts.py
├── music_external.py
└── xai_openai_compat.example.py
```

---

## 最小成片路径

```bash
SKILL_DIR="${HOME}/.grok/plugins/ai-film-grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"
MEDIA_QUEUE="$SKILL_DIR/scripts/media-queue"
ROOT="/path/to/my-film"   # 绝对路径

"$AIFILM" doctor
"$AIFILM" init --theme "都市雨夜重逢" --title "雨停之前" --aspect 9:16 --root "$ROOT"
# … 写 Director’s Lens / style / cast 后：
"$AIFILM" lock-style --root "$ROOT" --canonical "<style-v1.png>" \
  --cast-master "<cast/id-v1.png>" --signature "<signature_block>"
"$AIFILM" write-spec --root "$ROOT"
"$AIFILM" pilot pick --root "$ROOT" && "$AIFILM" pilot report --root "$ROOT"
# 用户原话批准后：
"$AIFILM" pilot approve --root "$ROOT" --user-phrase "可以" --shots shot01,shot02,shot03

# 批量前：完整看片并建立带抽帧、时间点与评分的镜头审片回执
"$AIFILM" review-shot --root "$ROOT" --shot-id shot01 --source "<clip.mp4>" \
  --approve --reviewer "you" --notes "完整观看" \
  --score-identity 4 --score-continuity 4 --score-composition 4 --score-motion 4 --score-narrative 4 \
  --evidence "identity@0.0:角色匹配" --evidence "continuity@1.0:状态连续" \
  --evidence "composition@2.0:构图清晰" --evidence "motion@3.0:动作连续" \
  --evidence "narrative@4.0:信息落点"

# 每步都可：
"$AIFILM" dispatch --root "$ROOT"

# 视觉 bulk（会话 image_to_video 或 OAuth 队列）后 register-clip …
"$AIFILM" tts-rehearse --root "$ROOT" --backend edge
"$AIFILM" final --root "$ROOT" --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge --compose-preset auto
"$AIFILM" review-final --root "$ROOT" --approve --reviewer "you" \
  --notes "已完整观看" \
  --score-identity pass --score-style pass --score-motion pass \
  --score-escalation pass --score-audio pass --score-subs pass --score-dead-air pass
"$AIFILM" export-desktop --root "$ROOT" --name "雨停之前"
```

v1.6 新项目还需为 final 的七个维度各提供 `--screening-evidence "维度@秒数:观察"`；旧项目先用 `aifilm review-contract migrate` 显式升级，历史布尔审批不会被伪造成新审片。

细节命令与门禁全文：[`skills/ai-film-grok/SKILL.md`](./skills/ai-film-grok/SKILL.md)。

---

## 配置

| 变量 | 默认 | 含义 |
|------|------|------|
| `AIFILM_TTS_BACKEND` | `edge` | TTS 后端 |
| `AIFILM_I2V_PROFILE` | `grok_primary` | I2V 运营季；LTX-first 仅旧项目显式锁定 |
| `AIFILM_LIPSYNC_BACKEND` | `off` | 口型 |
| `AIFILM_GROK_AUTH` | `auto` | OAuth / API key |
| `AIFILM_GROK_CHAT_MODEL` | `grok-4.5` | OAuth chat |
| `AIFILM_GROK_IMAGE_MODEL` | `grok-imagine-image` | OAuth 图 |
| `AIFILM_GROK_VIDEO_MODEL` | `grok-imagine-video` | OAuth 视频 |
| `AIFILM_TTS_ARGV` | — | 外部 TTS JSON argv |
| `AIFILM_MUSIC_ARGV` | — | 外部音乐 JSON argv |
| `AIFILM_LIPSYNC_ARGV` | — | 外部口型 JSON argv |

完整模板：[`skills/ai-film-grok/config.env.example`](./skills/ai-film-grok/config.env.example)。

**成片硬默认（产品）**

- 中文 final TTS → **edge**  
- 色气 BGM → **rnb**（`dark` 仅恐怖）  
- I2V → **`grok_primary`**（Grok image_to_video 主链；对白讲话镜锁 FRW LTX 2.3 有声；每路须当前影片 canary）
- pilot 须用户批准才 bulk  

---

## 本机开发 / 发版

```bash
cd ~/.grok/plugins/ai-film-grok
# 1) 只改本树
# 2) make release-check（统一使用 Python 3.11+；含 doctor、plugin validate、全量 pytest）
# 3) 行为变更 → bump plugin.json semver
# 4) make update
# 5) git commit（message 英文）&& git push origin main
```

| 路径 | 用途 |
|------|------|
| `plugin.json` | 插件元数据 / 版本 |
| `commands/` | `/ai-film-grok` · `/aifilm` |
| `skills/ai-film-grok/SKILL.md` | Agent 主脊（短） |
| `skills/ai-film-grok/scripts/` | `aifilm` CLI + 适配器 |
| `skills/ai-film-grok/references/` | 稳定规则 |
| `skills/ai-film-grok/tests/` | pytest |
| `.github/workflows/ci.yml` | validate + 全量 pytest |

Coding agent 协议：[`AGENTS.md`](./AGENTS.md)。变更日志：[`CHANGELOG.md`](./CHANGELOG.md)。

---

## 验证

```bash
make validate
make doctor
make release-check
test -x skills/ai-film-grok/scripts/aifilm
grok plugin details ai-film-grok
# 快速核心回归：make test-fast
# 全量：make test
```

CI：push / PR 跑 `plugin validate` + 全量 pytest（见 `.github/workflows/ci.yml`）。

---

## License

MIT © [dex](https://github.com/sooneocean)

<!-- BEGIN GENERATED: project-status -->
### 当前项目状态（自动同步）

- 插件版本：`2.38.6`
- Published skills：`2`
- Skill Registry：`32/34` 项标记为 `implemented`
- Python 脚本：`329` 个
- pytest 文件：`363` 个
- 同步入口：`make sync-docs`（只更新文档）或 `make sync`（验证、提交并 push）
- Graph：[`docs/GRAPH.md`](./docs/GRAPH.md)
<!-- END GENERATED: project-status -->

<!-- BEGIN GENERATED: maintainer-install -->
### 文档与远端同步（维护者）

代码或插件结构变更后，在仓库根目录执行：

```bash
make audit       # 只读审计 + fast tests + 更新 baseline
make coverage    # 生成 coverage.json 并检查 baseline 门槛
make sync-docs   # 生成 Graph、状态摘要与安装说明
make release-check
make sync        # 验证通过后提交、push，并核对 origin SHA
```

首次启用本地 push 门禁：

```bash
make install-hooks
```

同步器不会提交 `.env`、`config.env`、`.codegraph`、`.omo`、`.kilo` 或备份目录。
<!-- END GENERATED: maintainer-install -->
