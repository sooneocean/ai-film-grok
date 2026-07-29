# 5090 多片互抢 · pilot I2V 独占门（2026-07-29 · 后面不要再犯）

片例：`AI FILM SPACE/0729/e-virus-ch05-sensory-rebuild`（GO 抢 pilot 三连失败：clips=0）。  
同日对手：`btc-vessel-ep02`（sc11 重生）、`night-lock-encore-max`（shot09 + SIGSTOP 战术）。

## 用户意图（不可软化）

- 短指令 **GO / 优先 ch05** = 本片 **独占** Comfy I2V，直到 pilot 三连落地或用户改口。
- **完成** = `clips/takes` 真有 mp4 + register-clip，不是「脚本在跑」。

## IRON（必守）

### 1. 一机一 owner

- 同一 `127.0.0.1:18188`（SSH→远程 5090）**同一时刻只服务一个 film 的 I2V**。
- 用户点名优先片 → 停外片 `comfy_video.py`（路径含他片 root）→ `/interrupt` **仅当 running 图不是本片 pilot** → `free-memory --confirm` → capacity ready 再 submit。
- **禁** dual waiters 并行（`bulk_keyframes` + `bulk_i2v` 双挂抢锁）；串行 orchestrate。

### 2. 杀进程要准，禁误伤

| 可杀 | 不可杀 |
|------|--------|
| argv 含 `/scripts/comfy_video.py` 且 **不含** 本片 root | `dump_zsh_state` / grok zsh wrapper（cmd 里只是「提到」comfy_video） |
| 明确本机 film 驱动 `.py`（用户授权停片时） | 本片 `gpu_snatch_*` / `orchestrate_bulk` / 本片 comfy_video |
| | 任意只因 cmd 字符串含 `btc-vessel`/`night-lock` 的 shell |

- 被 **SIGSTOP（stat 含 T）** 的本片 worker → **`kill -CONT`**，勿当死进程重开双份。
- 外片用 STOP/KILL 战术是常态；本片 snatch 必须带 **watchdog：CONT 自己 + 只杀真 foreign cv**。

### 3. 禁误 interrupt 本片

- `unknown_node: error` / `execution_interrupted` 在 history 里成片 = **有人 interrupt 中途**，不是 Wan 坏了。
- 判定：`queue_running` 的 load_image **basename** 属于本片 pilot/kf → **禁止** `/interrupt` 与 `queue clear`。
- 仅当 **running 全是外片图** 才 interrupt；本片 running 时外片 pending 可等，勿为清 pending 掐 running。

### 4. capacity 与锁

- 提交 floor：VRAM free ≥ **24 GiB**、RAM ≥ 12 GiB、queue idle（`aifilm comfy capacity`）。
- queue 空但 VRAM 仍低 → 多次 `free` / `comfy free-memory --confirm`；勿在 VRAM~10G 硬撞 submit。
- `aifilm-comfy-submit-*.lock`：本片 comfy_video **被 STOP 十几分钟** 会占 admission lock → 先 CONT 或杀僵尸再重开。
- 隧道断连（`Remote end closed connection`）→ 等 SSH/Comfy 恢复，勿连环 kill 加重 thrash。

### 5. experimental profile 闸

```text
adult-general-experimental  → 必须同时：
  --production-stage pilot
  --allow-experimental
```

- 仅 `--allow-experimental` + `stage=production` → **立刻** `ComfyVideoError: pilot-only`。
- 通片稳妥默认：`adult-motion` + `adult-intimacy` + `stage=production`；肉戏升档再 experimental+pilot stage。
- film 内 `orchestrate_bulk` / snatch 脚本必须带对 stage，**禁止**抄半截 flag。

### 6. pilot 三连节奏

1. pilot still/kf 齐 + pilot approve + state-index hard OK  
2. **独占 GPU**（上条 1–4）  
3. 串行：sc01 → free → sc02 → free → sc07  
4. 每镜：`comfy_video generate` → 落 `clips/takes` → `register-clip candidate`  
5. clips=0 禁止宣称 pilot I2V DONE  

### 7. 诚实 PARTIAL

- 多片互抢未出 clip → 报 **PARTIAL(卡 GPU owner / clips=N)**，禁「脚本在等=已推进」。
- Grok bare moderated → comfy-wan22；comfy 也断 → 写收据，不静默空过。

## 反模式（本 session 实锤）

1. 一边 snatch 一边 **盲 interrupt** → 把自己 sc01 掐死。  
2. `pgrep -f comfy_video` / 杀「cmd 含 film 名」的 zsh → 误杀 agent / 被报复 SIGKILL。  
3. 双 snatch 并行 → 互相 free_until_ready 抢、队列 pending 爆炸。  
4. experimental 只加 allow 不加 stage=pilot。  
5. 进程 `TN` 还当「在跑」干等。  

## 最小恢复（下一句 GO）

```bash
# 1) CONT 或重启本片 snatch（单实例）
# 2) 只杀 foreign: /scripts/comfy_video.py 且 root≠本片
# 3) running 非本片 → interrupt + clear + free-memory
# 4) capacity ready → 串行 pilot 三连
# 5) ls clips/takes/*.mp4 数=3 才算过
```

脚本参考（本片）：  
`receipts/comfy/bulk/gpu_snatch_ch05.py` · `guard_cv.py`（杀进程须 argv 真路径，禁 dump_zsh）。

## 关联

- **多片抢占 + 本机 OOM（同日总课）**：`lessons-2026-07-29-comfy-multifilm-contention-oom.md`（单 client、禁 pgrep 自杀、禁假 meat）  
- capacity / free：`memory/2026-07-29-evirus-ch04-comfy-anatomy-batch.md`  
- 隧道 18188→8188：`lessons-2026-07-29-comfy-tunnel-8188-not-8189.md`  
- 混合火力：`lessons-2026-07-28-hybrid-api-local-max-firepower.md`  
