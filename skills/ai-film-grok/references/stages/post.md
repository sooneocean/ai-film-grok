# Post 阶段卡

- `stage_plate` 只做 clips、VO、BGM；**字幕唯一 owner = HyperFrames**（`final --post-engine hyperframes`，plate **`subs=off`**）。
- 每集先选一个 `post owner`：默认 HyperFrames；只有逐词字幕、参数化 variant 或 React 帧级 MG 是明确需求时才选 Remotion。`engine=both` 仅导出对照，不能双正式渲。
- **禁止** FFmpeg/PIL 在 plate 路径烧字当交付；SRT 仅作 HF 底稿；抽帧须可见中文 `caption_text`。
- 字幕必须真正进入交付 MP4 像素；外挂 SRT 或抽帧存在不等于可读。
- selected owner 未烧字时显式进入 `stage_caption` recovery，禁止清空 `final.srt` 过关。
- title、subtitle、end card、轻 grade 与设计转场只允许 selected post owner 输出；另一个引擎只能 preview/variant，避免双烧与双转场。
- `final` 技术成功不等于 `final_complete`；仍需 post audit、caption attestation 与完整观看。

## P0 · final 工程（2026-07-24 ep2 复盘 · 2026-08-03 Wave D）

| 坑 | 纪律 |
|----|------|
| SRT `segment starts before previous ends` | **`sub_lead` 默认 0**；cue 写盘前非重叠钳制（`render_final` 已内建） |
| `aifilm final` 假超时 | 默认 `estimate_plate_timeout`：**短片 floor 1200s**；**长片/≥480s floor 1800s**（cap 21600）。可 `--plate-timeout`。超时文案给 **直调 render_final** + `AIFILM_FFMPEG_TIMEOUT≥1800` |
| sidechain 混音卡死/失败 | **自动降级 amix**，写 `receipts/final-mix-partial.json`（PARTIAL，不静默当满分） |
| 字幕路径空格 / force_style | SRT 镜像无空格 `/tmp`；主路径 **PIL 烧字**（禁依赖 `subtitles=` force_style） |
| `review-shot --approve` 未变 approved | 换片后 **再** `register-clip --status approved --review-receipt`（sha 对齐） |
| plate 无字当交付 | plate `subs=off` 后必须由 **HyperFrames** 真烧中文；失字即修复 HF 并重渲，禁其他烧字器兜底 |

深入资料：[post-compose.md](../post-compose.md) · [postproduction.md](../postproduction.md) ·  
[subs-always-burn-hard](../lessons-2026-07-23-subs-always-burn-hard.md) ·  
**[ep2-voice-heat-final](../lessons-2026-07-24-ep2-voice-heat-final.md)**
