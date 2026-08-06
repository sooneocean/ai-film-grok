# Real-ESRGAN · formal 超分武器规范（2026-08-06）

> Research → optional formal。**默认 off**。  
> 策略母课：[lessons-2026-07-28-lowres-first-then-upscale.md](lessons-2026-07-28-lowres-first-then-upscale.md)  
> 上游：https://github.com/xinntao/Real-ESRGAN

## 一句话

用 AI 超分把 **已选中的** 低清/糊放大 clip 抬到更清的 704 或 1080；**不**代替 I2V 重拍，**不**放行运动门。

## 在流水线的位置

```text
I2V draft → geometry floor (ffmpeg 今日) → gates → human selects
  → [optional] Real-ESRGAN formal upscale
  → re-register preferred → ship-prep / final
```

| 挂载 | 何时 | 备注 |
|------|------|------|
| P0 Clip formal | selects / preferred 后 | 主路径 |
| P1 H3 geometry AI 支路 | raw <704 | 替换或并联 ffmpeg；默认仍 ffmpeg |
| P2 Master ship | plate 无字 → 1080 | **字幕后禁止**再超分 |

## 模型默认

| 介质 | 模型 | scale |
|------|------|-------|
| 视频（cel / 漫剧） | `realesr-animevideov3` | 2（常用；可 1–4） |
| 静帧 anime | `RealESRGAN_x4plus_anime_6B` | 按需 |
| 写实 / 杂片 | `RealESRGAN_x4plus` | 非默认 |
| 人脸 GFPGAN | **默认 off** | 易毁 cel 脸 |

## 硬规则

1. **默认 off**；film-spec `upscale.enabled=true` 或 CLI 显式才跑。
2. **范围**：preferred / hero / 用户点名；禁 bulk 每 take。
3. **门禁**：motion-gate 红 → 不 promote；毒镜红 → 拒；超分 **不**改 mean 结论。
4. **守恒**：fps / duration 与源一致（容差后 fail）；音频 **copy**；失败 strip 须 PARTIAL 诚实。
5. **身份账本**：输出新 path + 新 `media_sha256`；默认不 promote，须 `upscale promote` / 人审。
6. **GPU**：busy 零 submit；`--max N`；禁 `--until-empty` 抢 H3；见 multi-agent-gpu-no-hog。
7. **静帧源**：keyframe 仍须 ≥704×1280 先验；**禁止**故意压糊 still 再指望 SR 救。
8. **分辨率变体** `*_esrgan_*` / `*_704x1280` **不算**创意 multi-take。

## 后端候选（执行优先级）

1. 5090：`inference_realesrgan_video.py` 或 Comfy `UpscaleModelLoader` 帧工作流  
2. 旁路：`realesrgan-ncnn-vulkan`（不占 CUDA 队列时）  
3. 研究对照：SeedVR2（weights 未验证前禁 production）

## CLI（已落地）

```bash
aifilm upscale plan --root <film>
aifilm upscale run  --root <film> --execute --max 5 --i-own-the-gpu
aifilm upscale promote --root <film> --shot-id <id>
aifilm upscale canary --source <lowres.mp4> --out-dir artifacts/realesrgan-canary
```

- 默认 **不 promote**；`promote` 只拷到 `takes/<shot>/`，仍须人 `register-clip`。
- H3 几何：`AIFILM_H3_GEOMETRY=ffmpeg|realesrgan|auto`（默认 ffmpeg）。
- film-spec：`{"upscale":{"enabled":true}}` 时 dispatch/next 会推 formal upscale 建议。

## 探测（只读）

```bash
cd skills/ai-film-grok
./scripts/runtime-python scripts/realesrgan_probe.py
# 可选 Comfy 节点面：
./scripts/runtime-python scripts/realesrgan_probe.py --base-url http://127.0.0.1:18188
```

- 永不自动下载权重、永不 submit prompt、永不 promote。
- 本机 canary（2026-08-06）：`registry/evidence/realesrgan-canary-ab-20260806.json` — ncnn animevideov3 ×2，1.5s@352×608 → 704×1280，~5.8s wall（M1），音频 copy。

## Canary 夹具（Phase 1）

| 夹具 | 目的 |
|------|------|
| H3 小帧 take（~352×608） | 对比 ffmpeg scale vs ESRGAN |
| 已 704 低 mean 肉戏 | 证明「更清仍无聊」→ 须 re-I2V |
| 高 mean 英雄镜 | 过锐 / 闪烁 / 毁脸回归 |

A/B 记录：墙钟、VRAM、闪烁、脸手文字、是否过锐、mean 是否假变。

## 回执最小字段

`receipts/upscale/<shot_or_take_id>.json`：

- `source_path` / `source_sha256`
- `model` / `scale` / `backend`
- `output_path` / `output_sha256`
- `width` / `height` / `fps` / `duration_sec`
- `audio_policy` (`copy` \| `strip_partial`)
- `promoted` (bool，默认 false)
- `gpu_busy_skipped` (bool)

## 非目标

- 不修 mean / 体位 / 毒解剖  
- 不做 bulk 默认  
- 不静默改 `i2v_provider`  
- 不与 H3 until-empty 并行占满卡  
