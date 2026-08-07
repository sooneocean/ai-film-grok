# Memory · Comfy 多片抢占 / 本机 OOM（P0 · 2026-07-29）

> **用户**：把教训写回去不要再犯  
> **片例**：`0729/night-lock-encore-max` bare-comfy-v2 PARTIAL  
> **全文**：[lessons-2026-07-29-comfy-multifilm-contention-oom](../references/lessons-2026-07-29-comfy-multifilm-contention-oom.md)

## 一句话

**5090 共享闸门；Mac 16GB 同时只许 1 个 `comfy_video.py`。** 抢不到 → PARTIAL 诚实，禁邻镜 meat 静默冒充。

## 硬禁

- 双 client 并行 generate  
- `pgrep -f comfy_video` 宽匹配（会杀自己）  
- bash `$s=09` 算术八进制  
- capacity exit2 不处理（zsh errreturn 整批死）  
- OOM 137 当「Comfy 坏了」  
- shot 失败复制邻镜进 final 不写 FALLBACK  

## 提交前

capacity ok + **本机无其他片 generate** + free-memory；卡死 SSH restart。
