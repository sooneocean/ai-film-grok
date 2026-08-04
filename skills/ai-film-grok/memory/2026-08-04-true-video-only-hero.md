# Memory · 2026-08-04 · True-video-only（要影片不要图 · 机读硬闸）

**运营**：`scripts/true_video_policy.py` · hard-defaults「要影片不要图」  
**计划**：session plan true-video + 电影规格 todoplan Wave α

## 用户原话
> 工作流内核心为 grok i2v and h3 r2v i2v 不接受图片的运镜 只接受生成的视频影片剪辑输出 … 最终的影片输出需要像是电影一样的规格

## 三句话
1. **Still = 定妆输入**；**运镜只在 Grok/H3 生成视频内**；禁止 Ken Burns/zoompan/panel 当 hero。
2. **机读**：`register-clip` / `preflight` / `final` / `ship-prep` 扫 `TRUE_VIDEO_*`；panel 仅 `production_mode=panel`。
3. **电影规格后续**：β 意涵运镜 · γ VO-fit · δ 5 轨声 · ε cinematic-gate（见 plan）。

## 检查清单
- [ ] `pytest tests/test_true_video_policy.py`
- [ ] drama 项目无 panel motion-plan
- [ ] approved clip 全是 mp4 + 生成 endpoint
- [ ] ship-prep step `true_video` 绿再 final
