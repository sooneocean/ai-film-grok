# Post 阶段卡

- `stage_plate` 做 clips、VO、BGM；**字幕双路径（2026-08-03 v3）**：
  - **正式 master**：`post owner=HyperFrames`（`final --post-engine hyperframes`，plate **`subs=off`** 后 HF 真烧）。
  - **Ship / 门红 PARTIAL**：**PIL/底片像素硬烧** 中文 `caption_text` 优先（字号≥36–40@704、深底、安全区）；**禁止** 仅 HF `opacity:0`+GSAP 当唯一字幕。
- 每集先选一个 `post owner`：默认 HyperFrames；Remotion 仅逐词/参数化/React 帧级 MG；`engine=both` 仅对照。
- 验收 = **抽帧人眼可读**（每条对白 cue ≥1 帧），≠ ledger 有 `caption_text` / 外挂 SRT。
- selected owner 未烧字 → `stage_caption` recovery；禁止清空 `final.srt` 过关。
- title / end card / grade：正式链单引擎，避免双烧；ship 硬烧字幕可与 HF underlay 并存（字已在 plate 则 HF 勿再叠一层）。
- `final` 技术成功 ≠ `final_complete`；仍需 post audit、caption attestation 与完整观看。

## P0 · final 工程（2026-07-24 ep2 复盘 · 2026-08-03 Wave D）

| 坑 | 纪律 |
|----|------|
| SRT `segment starts before previous ends` | **`sub_lead` 默认 0**；cue 写盘前非重叠钳制（`render_final` 已内建） |
| `aifilm final` 假超时 | 默认 `estimate_plate_timeout`：**短片 floor 1200s**；**长片/≥480s floor 1800s**（cap 21600）。可 `--plate-timeout`。超时文案给 **直调 render_final** + `AIFILM_FFMPEG_TIMEOUT≥1800` |
| sidechain 混音卡死/失败 | **自动降级 amix**，写 `receipts/final-mix-partial.json`（PARTIAL，不静默当满分） |
| 字幕路径空格 / force_style | SRT 镜像无空格 `/tmp`；主路径 **PIL 烧字**（禁依赖 `subtitles=` force_style） |
| `review-shot --approve` 未变 approved | 换片后 **再** `register-clip --status approved --review-receipt`（sha 对齐） |
| plate 无字当交付 | 正式链：plate `subs=off` → **HyperFrames** 真烧中文。**Ship/门红链（2026-08-03 v3）**：优先 **PIL 硬烧** 进 plate 像素；禁止只靠 HF `opacity:0`+GSAP |
| 用户说「没有字幕」 | 先抽帧：有字→安全区/缓存/重开文件；无字→硬烧重出。验收=人眼可读，≠ ledger 有字段 |
| 等长 6s PPT 感 | **VO-fit** 对白镜 + 变长 xfade；先帧链 promote 再 dissolve |
| final 门红但用户要看片 | plate-xfade + rnb + **硬烧中文字幕** → `*-silk-v3.mp4`；**PARTIAL** 回执，不标 final_complete |
| 静图/Ken Burns 装片 | **硬拒**（true_video_policy）：final/ship-prep 扫 approved clips；须 Grok/H3 生成 mp4 再剪（2026-08-03 荒岛 · 2026-08-04 强化） |

深入资料：[post-compose.md](../post-compose.md) · [postproduction.md](../postproduction.md) ·  
[subs-always-burn-hard](../lessons-2026-07-23-subs-always-burn-hard.md) ·  
**[ep2-voice-heat-final](../lessons-2026-07-24-ep2-voice-heat-final.md)** ·  
**[huangdao-rhythm-still-voice-silk](../lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md)** ·  
**[caption-hardburn-meat](../memory/2026-08-03-huangdao-caption-hardburn-meat-variety.md)**
