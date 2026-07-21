# Lip-sync 后端政策

默认关闭。动漫脸、中远景与快速头部运动会让免费 lip-sync 明显毁脸；说书人叙事是稳定默认。

**FRW 云端口型（音画同步）** 已接入：`aifilm frw-lipsync` — 见 [frw-lipsync.md](frw-lipsync.md)。  
平台可用时优先 FRW（无限额度）；**当前 key 常见 403/502**，须先 `frw-lipsync probe`。

## 何时可用

只有以下全部成立才打开：

1. 用户明确要求角色开口（或 `character`/`hybrid` + 镜标 `lipsync: true`）。
2. 镜头为正脸/微侧近景，遮挡少，语句短。
3. 后端就绪：**FRW probe 201** 或 本地 MuseTalk/Wav2Lip 已 lock。
4. 输出逐镜完整观看，脸部没有抽动、漂移或崩坏。

## 后端优先级（生产）

| 顺序 | 后端 | 说明 |
|------|------|------|
| 1 | **FRW** `ltx-lipsync` / `wan-lipsync` / `seedance-2-pro-lipsync` | `aifilm frw-lipsync`；register `frw_*_lipsync` |
| 2 | 锁定 MuseTalk | `backend-lock` + final `--lipsync auto` |
| 3 | 锁定 Wav2Lip | 同上 |
| 4 | external argv | `AIFILM_LIPSYNC_ARGV` |

`final --lipsync auto` 仍只走**本地已 lock** 后端（历史路径）。  
**推荐对白流程**：生产阶段 FRW 口型直接 register 成 clip，final 保持 `--lipsync off`，避免双处理。

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
- `auto`：只对 film-spec 里 `lipsync: true` 的合适镜头使用已锁定后端；没有后端则跳过。
- `require`：有任一目标镜头失败就终止成片。
- `external | musetalk | wav2lip`：显式指定；不 ready 或失败时闭锁报错。

Lip-sync 输出仍必须走最终 `review-final`，不得只信技术成功码。
