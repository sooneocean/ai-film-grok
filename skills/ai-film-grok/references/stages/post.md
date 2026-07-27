# Post 阶段卡

- `stage_plate` 只做 clips、VO、BGM；HyperFrames/Remotion 负责 designed post。
- 每集先选一个 `post owner`：默认 HyperFrames；只有逐词字幕、参数化 variant 或 React 帧级 MG 是明确需求时才选 Remotion。`engine=both` 仅导出对照，不能双正式渲。
- 字幕必须真正进入交付 MP4 像素；外挂 SRT 或抽帧存在不等于可读。
- selected owner 未烧字时显式进入 `stage_caption` recovery，禁止清空 `final.srt` 过关。
- title、subtitle、end card、轻 grade 与设计转场只允许 selected post owner 输出；另一个引擎只能 preview/variant，避免双烧与双转场。
- `final` 技术成功不等于 `final_complete`；仍需 post audit、caption attestation 与完整观看。

## P0 · final 工程（2026-07-24 ep2 复盘）

| 坑 | 纪律 |
|----|------|
| SRT `segment starts before previous ends` | **`sub_lead` 默认 0**；cue 写盘前非重叠钳制（`render_final` 已内建） |
| `aifilm final --plate-timeout 900` 假失败 | **长片直调** `scripts/render_final.py`（15–30min+） |
| `review-shot --approve` 未变 approved | 换片后 **再** `register-clip --status approved --review-receipt`（sha 对齐） |
| plate 无字当交付 | plate `subs=off` 后必须 **burn 中文**（`burn_srt_pil` 或 HF 真烧） |

深入资料：[post-compose.md](../post-compose.md) · [postproduction.md](../postproduction.md) ·  
[subs-always-burn-hard](../lessons-2026-07-23-subs-always-burn-hard.md) ·  
**[ep2-voice-heat-final](../lessons-2026-07-24-ep2-voice-heat-final.md)**
