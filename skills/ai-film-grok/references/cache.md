# 本地内容缓存

`scripts/cache.py` 提供不依赖外部服务的 content-addressed cache，缓存目录位于 film root 下：

```text
<film-root>/cache/<namespace>/<sha256>.json
```

缓存键必须是 SHA-256 十六进制值，写入采用临时文件加原子替换；缓存损坏、路径不安全或不可读时，调用方必须回退到真实计算，不得把缓存当作交付证据。

当前接入点是 `media_duration.probe_duration_sec(..., cache_root=<film-root>)`。它以媒体路径、inode、大小、mtime 和参数生成 fingerprint；媒体变化后旧 duration 自动失效。未传 `cache_root` 时保持原有每次直接 ffprobe 行为。

缓存只优化本地确定性读取，不代表 provider 生成成功，也不替代 manifest、receipt、人工审片或 hash read-back。
