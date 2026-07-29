# 教训 · Comfy 隧道必须 8188 非 8189 + 队列抢空档（2026-07-29 · 后面不要再犯）

> 片例：`AI FILM SPACE/0729/receipts/canary-maxgo/wave3` · 5090 canary  
> 用户原话：「把教训写回去 不要再犯」

## 一句话

**`127.0.0.1:18188` 只能 SSH 转到远程 Comfy `8188`。**  
转到 **`8189`（或其它鉴权服务）会得到 `{"detail":"unauthorized"}` 401**——不是 Comfy 挂了，是**指错端口**。  
`ssh` 进程还在听本地端口 ≠ 隧道指对了业务。

## 端口地图（IRON）

| 本机 loopback | 远程 | 服务 | 健康探针 |
|---|---|---|---|
| **18188** | **8188** | **ComfyUI** | `curl -sS http://127.0.0.1:18188/system_stats` → **JSON + HTTP 200**（有 `system`/`devices`） |
| 18790 | 8790 | lipsync / audio node | 需 token；**不是** Comfy |
| （错例）18188→**8189** | 鉴权 HTTP | lipsync 类 | `{"detail":"unauthorized"}` **401** |

默认 env（与 `comfy_recovery.py` 一致）：

- `AIFILM_COMFYUI_BASE_URL=http://127.0.0.1:18188`
- `AIFILM_COMFY_TUNNEL_PORT=18188`
- `AIFILM_COMFY_REMOTE_PORT=8188`（**禁止**改成 8189）

正确隧道：

```bash
KEY="$HOME/.ssh/aifilm_5090_ed25519"
HOST="user@192.168.88.52"
# 先杀错隧道（确认 PID 的 -L 目标）
ps aux | grep 'L 18188' | grep -v grep
ssh -fN -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 18188:127.0.0.1:8188 "$HOST"
curl -sS -m 8 -w "\nHTTP:%{http_code}\n" http://127.0.0.1:18188/system_stats | head -c 200
```

### 401 诊断顺序（禁止空转 recover）

1. `ps aux | grep 'L 18188'` → 看 **远程端口是 8188 还是 8189**
2. 若是 8189 / 非 8188 → **kill 该 ssh → 重建 18188→8188**
3. 探针必须是 **`/system_stats` 200 + Comfy JSON**，不是「端口在听」
4. `aifilm comfy recover` 在 **错端口仍返回 401** 时可能报 tunnel repair failed——先修端口映射，再 recover
5. **勿**把 lipsync 的 bearer 401 当成 Comfy 要登录

## 队列抢空档（bulk 进行时）

5090 **单卡串行**。别人 bulk（如 sc07 Wan I2V）会占满 `running=1`，空档只有数秒。

| 禁 | 要 |
|---|---|
| 看到 idle 后再 `queue` 二次 assert、再 `free-memory` 再 submit（**必丢空档**） | idle 瞬间 **直接** `run-workflow` |
| 盲 `cancel` 未知 running prompt | 先 peek queue payload（LoadImage / 镜号）；仅用户 **go** 或确认幽灵才 cancel |
| free-memory 当「占位」 | free 只在 **VRAM_BELOW_FLOOR** 或 **自己的** job 结束后 |

竞态失败典型：`ComfyUI submission blocked by resource tower: COMFY_QUEUE_BUSY`  
→ 短 sleep 重 poll，**不要**先 free 再慢慢准备。

## bare-union canary 霓虹结合符（与解剖 IRON 并列）

Wave3 Qwen bare still **技术可 OK**，但仍可能：

- 结合处 **青霓虹光爆 / 红霓虹球 / spark / orb**（= 霓虹生殖器符号毒）
- 站姿抬腿软贴，**非** hips-sink 可读插入

处置（**后面不要再犯**）：

1. 视觉回读 → 记 PARTIAL；`production_eligible=false`
2. **禁** `register-still approved` / **禁** 肉戏 I2V / **禁** promote
3. re-edit 硬 NEG 追加：  
   `neon genital glow, spark, orb, lens flare on genitals, blue energy at pelvis, red ball censor, glowing genitals, 霓虹生殖器, 光球挡下体`
4. 硬 POS：`hips-sink straddle pelvis-lock, penetration readable, no glow on genitals, anatomical contact only`

关联： [anatomy-milk-futa](lessons-2026-07-29-anatomy-milk-futa-comfy-batch.md) · [poison memory](../memory/2026-07-29-poison-shot-anatomy-iron.md)

## 收工对照（本轮）

- 隧道修好后两张 still 落地：  
  `0728/e-virus-ch04-shelter/stills/canary_5090/wave3/bare_from_undress_s63001.png`  
  `0728/e-virus-ch04-shelter/stills/canary_5090/wave3/bare_from_meat_s63002.png`
- 收据：`0729/receipts/canary-maxgo/wave3/SUMMARY.json` · `WRAP.md` → **PARTIAL**（neon fail-closed）
