# Memory · Seedance 质量 + 403 fallback（2026-07-20）

**User**: 胃镜室质量很差 → Seedance 新版本；男娘片生产时 Seedance 403。

## 产品结论

1. bulk 2V **默认** `frw newvideo --model seedance-2-fast-i2v`（9:16 **720p 原生**）。
2. **禁止**默认 legacy `img2video` / 576→720 放大。
3. register：`frw_seedance_i2v` / `frw_seedance_flf`。
4. **403 无权使用该模板** → **不要**退 legacy；fallback **Grok Imagine Video 720p**；receipt 记账。
5. 权限恢复 → 回 Seedance 重烤动态。
6. frwclaw：`cmd_newvideo` 用 `from scripts.config`（修相对导入）。

## Canonical

- `references/lessons-2026-07-20-seedance-quality.md`
- `references/frw-degrade-dispatch.md`
- `sediment-cn-codex` Opt5 + Opt9

## P 码

P0 可观测 · P1 身份 · P5 分层
