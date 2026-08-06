# Memory · Comfy 隧道 8188 + 队列空档 + bare 霓虹（P0 · 2026-07-29）

> **后面不要再犯**  
> 完整课：[lessons-2026-07-29-comfy-tunnel-8188-not-8189](../references/lessons-2026-07-29-comfy-tunnel-8188-not-8189.md)

## 一句话

1. **`18188 → 远程 8188` only**。→8189 = lipsync 鉴权 **401** `unauthorized`，不是 Comfy 宕机。  
2. bulk 占卡时：**idle 立刻 submit**，禁 free-memory 抢跑丢空档；禁盲 cancel 别人的 I2V。  
3. bare still 结合处 **霓虹光/球** = 毒镜 → **禁 register/I2V**，再 Qwen 硬 NEG。

## 探针（30 秒）

```bash
ps aux | grep 'L 18188' | grep -v grep   # 必须见 :8188 不是 :8189
curl -sS -m 5 http://127.0.0.1:18188/system_stats | head -c 120
# 要有 system/comfyui；不要 {"detail":"unauthorized"}
```

## 关联

- 隧道重启：[comfy-ssh-self-restart](../references/lessons-2026-07-28-comfy-ssh-self-restart.md)
- 解剖毒：[poison-shot-anatomy-iron](2026-07-29-poison-shot-anatomy-iron.md)
- 片例收据：`AI FILM SPACE/0729/receipts/canary-maxgo/wave3/`
