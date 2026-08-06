# Session wrap · round-2 · 2.39.92

## 三行

1. Residual **volumedetect** 收敛到 `probe_volume_stats`（canary/quality_check/reference_audit）。  
2. Edge TTS 空流重试接入 **`util.retry`**；与 Gitea 并行 **2.39.91** hotpath 门禁测合并为 **2.39.92**。  
3. **hotpath 102 绿**；Gitea 推送（见 git log）；GitHub 若仍 suspended 则 PARTIAL。

## Commits

- `ffd636d5` residual volume + edge retry (later rebased/merged)
- `c5c131eb` merge gitea 2.39.91 + residual as 2.39.92

## OPEN

- media_queue 等全仓 retry 替换  
- heat↔policy sys.modules  
- GitHub origin 若 403  
