# Lip-sync 后端政策

默认关闭。动漫脸、中远景与快速头部运动会让免费 lip-sync 明显毁脸；说书人叙事是稳定默认。

**FRW 云端口型（音画同步）** 已接入：`aifilm frw-lipsync` — 见 [frw-lipsync.md](frw-lipsync.md)。  
FRW 仅作显式 fallback；**历史 key 常见 403/502 不代表当前 live 状态**，每次使用前须先 `frw-lipsync probe`。

RTX 5090 方案研究与 canary 门槛见
[lessons-2026-07-28-rtx5090-lipsync-routing.md](lessons-2026-07-28-rtx5090-lipsync-routing.md)。
该文中的新增方案都是**候选**，未接线或未通过实片 canary 前不得写成 ready。

## 何时可用

只有以下全部成立才打开：

1. 用户明确要求角色开口（或 `character`/`hybrid` + 镜标 `lipsync: true`）。
2. 镜头为正脸/微侧近景，遮挡少，语句短。
3. 后端就绪：本地后端已通过实片 canary 且 lock；或用户批准云端后 **FRW probe 201**。
4. 输出逐镜完整观看，脸部没有抽动、漂移或崩坏。

## 当前可执行优先级（生产）

| 顺序 | 后端 | 说明 |
|------|------|------|
| 1 | 锁定 MuseTalk | `backend-lock` + final `--lipsync auto` |
| 2 | 锁定 Wav2Lip | 仅基线/应急；先确认权重许可 |
| 3 | external argv | RTX 5090 canary 或其他已审计本地客户端 |
| 4 | **FRW** `ltx-lipsync` / `wan-lipsync` / `seedance-2-pro-lipsync` | 仅明确技术失败后的显式 fallback；register `frw_*_lipsync` |

`final --lipsync auto` 仍只走**本地已 lock** 后端（历史路径）。  
若显式使用 FRW，生产阶段直接 register 成 clip，final 保持 `--lipsync off`，避免双处理。

目标优先级是 `LatentSync 1.6 → MuseTalk 1.5 → Wav2Lip`，但 LatentSync 尚未接入 registry；
在接线、5090 canary、fingerprint receipt 和人工完整观看通过前，当前执行顺序不冒充目标顺序。

质量差、人工拒绝或未知错误不算 provider 技术失败，禁止静默切 FRW。

上游 MuseTalk 泛用入口若使用 `os.system`，已被拒绝。不得仅因为文件存在就认定后端“ready”。

## 检查与锁定

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
- `auto`：优先尊重 film-spec 的显式 `lipsync`；字段缺失时，当前实现仍会按景别/标题启发式推断。生产前必须审阅目标镜清单；没有后端则跳过。
- `require`：有任一目标镜头失败就终止成片。
- `external | musetalk | wav2lip`：显式指定后端；当前逐镜失败仍会记录并跳过，只有配合 `require` 语义才是硬闭锁。此处是待修实现缺口。

Lip-sync 输出仍必须走最终 `review-final`，不得只信技术成功码。
