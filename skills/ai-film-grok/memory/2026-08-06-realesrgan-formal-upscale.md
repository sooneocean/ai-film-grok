# Memory · 2026-08-06 · Real-ESRGAN formal 超分

**完整课**：[realesrgan-formal-upscale.md](../references/realesrgan-formal-upscale.md) · 策略课：[lowres-first](../references/lessons-2026-07-28-lowres-first-then-upscale.md)

## 用户原话
> 分析能否串到工作流：先生成低画质再用 Real-ESRGAN 做高清

## 三句话
1. **策略对**：先通片再升画质已是铁律；Real-ESRGAN 适合当 **selects 后 formal 刀**，不是 bulk 默认。
2. **今日缺口**：H3「upscale」= ffmpeg 几何 floor；后期 enhance=去噪锐化——**没有**生产 AI 超分。
3. **边界**：清细节 ≠ 好动作；motion 红仍 re-I2V；anime 权重；禁 GFPGAN 默认；不抢 5090 bulk。

## 检查清单
- [x] canary A/B：`aifilm upscale canary`（证据 registry/evidence/realesrgan-canary-ab-20260806.json）
- [x] CLI：`aifilm upscale plan|run|promote`（默认不 promote）
- [ ] 只升 preferred / hero / 用户点名（默认 off）
- [ ] 视频 `realesr-animevideov3`；静帧 anime_6B；face_enhance off
- [ ] 字幕硬烧 **前** 超分无字 clip
- [ ] 保 aac / fps / duration；重算 media_sha；禁静默 promote
- [ ] GPU busy → 零 submit；禁 until-empty 长驻
- [ ] 真片 hero 人审后才 `upscale.enabled=true`

## 用法
```bash
aifilm upscale plan --root <film>
aifilm upscale run --root <film> --execute --max 5 --i-own-the-gpu
aifilm upscale promote --root <film> --shot-id <id>
```

## 上游
https://github.com/xinntao/Real-ESRGAN
