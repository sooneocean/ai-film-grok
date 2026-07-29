# 教训 · Comfy 多片抢占 + 本机 OOM + 批脚本坑（P0 · 2026-07-29）

> **后面不要再犯。**  
> 片例：`AI FILM SPACE/0729/night-lock-encore-max`（bare-comfy-v1/v2 · shot09 真 meat 冲不过）  
> 关联：`lessons-2026-07-28-comfy-ssh-self-restart.md` · `comfy-weapon-armory.md` · capacity 资源塔

## 用户原话 / 收工要求

「把教训写回去 不要再犯」—— 多片同抢 5090、本机 16GB 被双 client 打死、假 meat 顶替，禁止再静默当 DONE。

## 一句话

**5090 是共享闸门，不是你的专机；本机 Mac 16GB 同时只能跑一个 `comfy_video.py` client。**  
抢不到窗口就 **PARTIAL 诚实**，禁用邻镜 meat **静默冒充**真 reshoot。

**补课（ch05 pilot 同日）**：用户 **GO 优先片** 时改「一机一 owner」；**running 本片禁 interrupt**；`TN`→CONT；experimental 要 `stage=pilot`。见 `lessons-2026-07-29-comfy-gpu-priority-pilot-i2v.md`。

## 绝对禁止

| 坑 | 为啥会犯 | 正确做法 |
|---|---|---|
| **双 client 并行** | e-virus / btc-vessel / night-lock 各开 `comfy_video.py generate` | **同时本机只 1 个** generate 客户端；别片先 `kill -STOP` 编排器或等 idle |
| **`pgrep -f comfy_video` 自杀** | 脚本自身 argv 含字符串 → 匹配到自己 → SIGSTOP/SIGKILL | 只按 **路径片根** 匹配（`e-virus-ch05-…` / `btc-vessel-…`），**禁止**宽泛 `comfy_video.py generate` |
| **`$((…+09))` 八进制** | bash 把 `09` 当 octal → `value too great for base` 批脚本秒死 | shot id 用 `printf '%02d' $s` 或 seed 写死十进制，**禁止** `$s` 带前导 0 做算术 |
| **capacity 假窗口** | free-memory / run=0 瞬间被外片抢回 → `COMFY_QUEUE_BUSY` / `VRAM_BELOW_FLOOR` | 提交 **紧贴** capacity ok；失败即重等；卡死 **SSH restart**（见 07-28 课） |
| **zsh errreturn** | `aifilm comfy capacity` blocked 时 exit 2 → 整条批脚本被 ERR 杀掉 | 批脚本 **`set +e` / `NO_ERR_RETURN`**；capacity 一律 `\|\| true` 再解析 JSON |
| **macOS 无 setsid** | `setsid` command not found 当「已提交」 | 用 `nohup … &` + pidfile；**不要**假设 Linux 工具 |
| **邻镜 meat 静默顶替** | shot09 OOM → 复制 shot08 meat 进 final 不写明 | **允许** fallback **仅**当 receipt 写明 `FALLBACK` + delivery **PARTIAL**；禁止当 DONE |
| **OOM 当「Comfy 坏了」** | exit **137** / `Killed: 9` = 本机内存，不是 5090 死 | 先 `vm_stat`/RSS；杀外片 client；单 client 再交；仍 137 → PARTIAL 收工 |

## 资源塔（提交前硬门）

已有 `aifilm comfy capacity`：

- 队列 **idle**（running=0 且 pending=0）
- VRAM free ≥ **24 GiB**
- 本机 RAM free ≥ **12 GiB**（资源塔 floor）

**额外 IRON（本课新增）：**

1. 提交前 `ps`：**本机 0 个其他片的 `comfy_video.py generate`**
2. 长批 **nohup + 日志文件**；工具 session 超时 ≠ job 结束，以 **out mp4 + receipt** 为准
3. 外片占闸 >15min 且用户 `go` 本片：可 interrupt / SSH restart（用户授权全权时），但 **收工要 CONT/说明** 别片

## 推荐作业流（单镜 meat）

```bash
# 1) 独占：停外片编排（按路径，勿宽匹配）
# 2) capacity ok → free-memory --confirm
# 3) 单次 generate（nohup 或前台一条）
# 4) 成功：scale 720x1280 → clips/shotXX.mp4 → remux
# 5) 失败 137/BUSY：PARTIAL + receipt，禁静默邻镜冒充
```

## 片例证据（night-lock-encore-max）

| 结果 | 说明 |
|---|---|
| bare stills Qwen | undress-anchor + shot04–10 有真 bare 静帧 |
| meat I2V | 04/05/06/07/08/10 **真** Wan experimental |
| shot09 | 多次 OOM/抢占 → **FALLBACK08**；delivery `bare-comfy-v2` **PARTIAL** |
| 成片 | ~80s 720×1280 桌面有；heat 未降 |

## 与解剖 IRON 并列

尺度拉满仍要 bare 静帧过解剖门再 I2V；**资源门与解剖门独立**——有 bare still 也不代表能立刻 I2V（闸门忙 / 本机 OOM）。

## 关联

- hard-defaults 表行 **Comfy 多片独占 + 本机单 client**
- memory: `memory/2026-07-29-comfy-multifilm-contention-oom.md`
- SSH 重启: [comfy-ssh-self-restart](lessons-2026-07-28-comfy-ssh-self-restart.md)
