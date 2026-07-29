# Lip-sync 后端政策

默认关闭。动漫脸、中远景与快速头部运动会让免费 lip-sync 明显毁脸；说书人叙事是稳定默认。

**FRW 云端口型（音画同步）** 已接入：`aifilm frw-lipsync` — 见 [frw-lipsync.md](frw-lipsync.md)。  
FRW 仅作显式 fallback；**历史 key 常见 403/502 不代表当前 live 状态**，每次使用前须先 `frw-lipsync probe`。

RTX 5090 方案研究与 canary 门槛见
[lessons-2026-07-28-rtx5090-lipsync-routing.md](lessons-2026-07-28-rtx5090-lipsync-routing.md)。
该文中的新增方案都是**候选**，未接线或未通过实片 canary 前不得写成 ready。
五后端的独立、无执行评测流程见
[lipsync-challenge.md](lipsync-challenge.md)。挑战报告不会改动本页的生产路由。

## 何时可用

只有以下全部成立才打开：

1. 用户明确要求角色开口（或 `character`/`hybrid` + 镜标 `lipsync: true`）。
2. 镜头为正脸/微侧近景，遮挡少，语句短。
3. 后端就绪：本地后端已通过实片 canary 且 lock；或用户批准云端后 **FRW probe 201**。
4. 输出逐镜完整观看，脸部没有抽动、漂移或崩坏。

## 当前可执行优先级（生产）

| 顺序 | 后端 | 说明 |
|------|------|------|
| 1 | RTX LatentSync 1.6 | 已批准 fingerprint + 实片 canary 后进入 `auto` |
| 2 | RTX MuseTalk 1.5 | 仅 LatentSync 可分类技术失败时按显式配置回退 |
| 3 | 锁定本机 MuseTalk / Wav2Lip / external argv | 兼容旧流程，不进入 5090 自动路由 |
| 4 | **FRW** `ltx-lipsync` / `wan-lipsync` / `seedance-2-pro-lipsync` | 仅本地明确技术失败后的显式 fallback；register `frw_*_lipsync` |

`final --lipsync auto` 优先走已配置且 health/fingerprint 就绪的 RTX 节点。
若显式使用 FRW，生产阶段直接 register 成 clip，final 保持 `--lipsync off`，避免双处理。

目标优先级是 `LatentSync 1.6 → MuseTalk 1.5`；节点接线完成不等于生产批准。
在 5090 canary、fingerprint receipt 和人工完整观看通过前，后端不得写成 ready。
节点的 `technical_ready` 只表示代码、GPU 与实测 fingerprint 可运行；
只有人工批准后将对应 `AIFILM_LIPSYNC_NODE_<BACKEND>_APPROVED=1`，`ready` 才会进入 `auto`。

质量差、人工拒绝或未知错误不算 provider 技术失败，禁止静默切 FRW。

上游 MuseTalk 泛用入口若使用 `os.system`，已被拒绝。不得仅因为文件存在就认定后端“ready”。

## 剧情讲话镜整段表演（不是后期补嘴）

InfiniteTalk 是剧情讲话镜架构首选；它与 FantasyTalking 都已进入 Comfy
armory，但当前实片证据只允许显式 pilot：

```bash
aifilm comfy route \
  --intent talking-avatar-stable-pilot \
  --production-stage pilot \
  --allow-experimental

aifilm comfy route \
  --intent talking-avatar-expressive-pilot \
  --production-stage pilot \
  --allow-experimental
```

架构首选不代表能力已获生产晋升。`dialogue_motion_route=auto` 只有在当前
InfiniteTalk capability 的 canary、时效与 promotion 证据齐全时才可继续；
否则 fail closed。第二选项是 Grok Imagine Video 生成动态后，再用同一条最终
TTS 经已批准的 LatentSync 对嘴。只允许显式选择或可分类技术失败触发，禁止把
质量不满意、身份漂移或未知错误当作自动 fallback。

它们的登记端点分别是 `local_infinite_talk` 与
`local_fantasy_talking`，真实方法是 `face_animation_to_audio`。两者都会
重新生成整张画面，不能宣称保留原片像素，也不进入
`final --lipsync auto`。InfiniteTalk 的 5090 实片较稳但日文口型驱动仍
偏弱；FantasyTalking 仅完成 6 步技术 canary，存在脸型、颜色、衣物与
背景漂移。两者在生产登记前都需要完整人工观看与逐句批准。

## 检查与锁定

RTX 节点：

```bash
# Windows 服务只绑定 loopback；Mac 通过认证 SSH 隧道传输影片与 Bearer。
ssh -N -L 18790:127.0.0.1:8790 user@192.168.88.52
export AIFILM_LIPSYNC_NODE_BASE_URL=http://127.0.0.1:18790
export AIFILM_LIPSYNC_NODE_TOKEN=...  # 仅放 config.env
aifilm lipsync-node health
aifilm lipsync-canary --root "<film>" --shot "<shot>" --backend latentsync
aifilm lipsync-canary --root "<film>" --shot "<shot>" --backend musetalk
```

节点回执必须绑定 repo commit、checkpoint SHA-256、输入/输出 SHA-256、
Python/PyTorch/CUDA/FFmpeg、ffprobe、耗时与峰值显存。人工审片仍是晋升条件。
客户端拒绝 HTTP 私网直连与所有重定向；若不用 SSH 隧道，节点必须提供 HTTPS。

```bash
SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
LOCKER="$SKILL_DIR/scripts/backend-lock"

"$LOCKER" inspect --backend wav2lip --root "/path/to/Wav2Lip"
"$LOCKER" inspect --backend musetalk --root "/path/to/MuseTalk"
```

`inspect` 只读，列出 git commit/dirty state、entrypoint hash 和权重 hash。权重来源、license 与完整性由用户审查确认后，用户才能授权执行：

```bash
"$LOCKER" lock --backend wav2lip --root "/path/to/Wav2Lip" \
  --acknowledge-trusted-weights
```

Agent 不代用户加 `--acknowledge-trusted-weights`。repo dirty、入口/权重缺失或 hash 变化都会使锁失效。

## External argv

`AIFILM_LIPSYNC_CMD` shell 模板已禁用。只接受 JSON 数组，支持 `{video}`、`{audio}`、`{out}` 三个完整参数占位：

```bash
export AIFILM_LIPSYNC_ARGV='["python","/trusted/aifilm_infer.py","--video","{video}","--audio","{audio}","--out","{out}"]'
```

不通过 shell 执行，不允许未知/格式化占位，子进程不继承 API key、token、SSH agent 或 proxy。

## 渲染

```bash
AIFILM="$SKILL_DIR/scripts/aifilm"
"$AIFILM" final --root "<root>" --lipsync auto
```

- `off`：永远不对口型（默认）。
- `auto`：只处理显式 `lipsync:true`、有 speaker/face target 的正脸或微侧近景；没有批准后端则跳过。
- `require`：有任一目标镜头失败就终止成片。
- `latentsync | external | musetalk | wav2lip`：显式指定后端；任一目标镜失败即终止成片。

Lip-sync 输出仍必须走最终 `review-final`，不得只信技术成功码。
