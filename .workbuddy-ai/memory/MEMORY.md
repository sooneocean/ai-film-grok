# ai-film-grok — 项目长期笔记

本地 AI 影视生产流水线：资产+元数据仓库（无应用源码）。路径 `/Users/dex/.grok/ai-film-grok`。

## 数据契约（写前必校验）
- catalog 顶层 schema `aifilm-bgm-library-v1`；资产 `aifilm-bgm-asset-v1`；TTS `tts-evaluations/manifest.json` schema `aifilm-tts-manifest-v1`。
- 校验器：`tools/validate_catalog.py`（自包含，无第三方依赖）。**任何修改 catalog.json 前先跑它**作为 gate。

## bgm-library
- `catalog.json`：46 资产（revision 90）。`technical.fingerprint` 为 101 维声纹。
- `similarity_cluster`：全部 46 资产已填（曾 3 个 pending 为 null，已修）。聚类规则 = 同 mood 内对 fingerprint 做余弦相似度、阈值 0.95 贪心归组。新增资产后需重跑聚类。
- `gap-queue.jsonl`：每行含 `status`(open) / `dedup_key` / `suggested_asset_id` / `action`(fill|generate)。当前 60 可填充、10 待生成（全 ambient，需补生成）。
- 修改前备份：`catalog.json.bak`、`gap-queue.jsonl.bak`（已被 .gitignore 忽略）。

## tts-evaluations
- 统一 `manifest.json`（6 引擎 / 16 样本）。fish 引擎 8/8 HTTP 402 已归档至 `_archive/2026-07-29-fish`，移出活跃轮换。

## 治理
- 仓库已 `git init`；`.gitignore` 忽略 `*.lock`/`.DS_Store`/`melo-cache/`/`*.wav`/`*.mp3`/`*.onnx`/`*.bak`。媒体不入 git（后续可上 Git LFS）。
- 仍未解决：BGM 母带为 PCM wav（可转 FLAC 省 ~50%）；`use_count` 全 0（下游装填回路未接或埋点坏）；melo-cache 模型缓存应移出资产库。
