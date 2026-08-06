# Memory · 宿色 EP01 正牌 final IRON（P0 · 2026-08-06 · 后面不要再犯）

**片根**：`AI FILM SPACE/0805/suse-evolution-ep01`  
**交付**：`out/film_final.mp4` ~154s · Edge TTS + hardburn 中字 · rnb-mood procedural BGM  
**回执**：`receipts/official-final-report.json` · status `OFFICIAL_FINAL_PLATE`（非 master-lock）

## 三句话

1. **`aifilm final` 假成功**：`scripts/render_final.py` shim 只换 module、**不调 main** → stage_plate 1 秒 returncode=0、无音轨工。**已修**：shim 在 `__main__` 调 `post.render_final.main`；仍可直调 `python -c "from post.render_final import main; ..."`。  
2. **片长必须认源**：H3 源 ~5.17s、`forbid_loop` + max_freeze0.2 → 槽位 **≤~5.9s**。`validate_film_spec` 遇 `HEAT_SEX_DURATION_LOW` 会把 act/climax **强拉 10s** → stretch 炸。解：`sex_min_duration_ratio` 调到实际 ratio 以下，或 **重 I2V 更长片**，禁空改 duration。  
3. **口白窗三角**：`cue.duration ≥ 实测 TTS` **且** `offset+cue ≤ duration_sec`。slot+atempo 在检查**之后**才压 VO → 先缩 spoken / `vo_rate=+18%` 再进 final。

## 还踩过的坑

| 坑 | 现象 | 处置 |
|---|---|---|
| cinematic 红 | SIZE_FLAT / THIRTY_DEGREE / monotony | 景别阶梯 + 机位角 bucket + reaction 动词保留 |
| rnb 无 wav | assets/bgm/rnb 仅 license | procedural velvet BGM；有 wav 再 `--music`+license |
| gate-auto 红 | five_track / i2v_motion / variety | ship plate 可 skip-preflight；**诚实 PARTIAL**，≠ final_complete |
| HF 后置 | raw 无音再 compose 报错 | 先 plate 有 VO/BGM，再 HF |
| 口白过长 | voice cue exceeds window | 砍 spoken / 提速；禁只把 cue 拉超 duration_sec |

## 与衣着课叠乘

- [wardrobe-no-redress-fullnude-fallback](2026-08-06-wardrobe-no-redress-fullnude-fallback.md)：不回穿 → 全裸诱惑 → **模型极限勿硬上**

## 检查单（下次正牌 final）

- [ ] `python …/render_final.py --root …` 会 TTS/stretch（非 1 秒空成功）  
- [ ] flatten 后 max `duration_sec` ≤ 源片可 stretch 上限（~5.9 短 H3）  
- [ ] 无 act/climax 被 validate 静默改 10s（或已 re-I2V）  
- [ ] TTS 实测 ≤ cue window ≤ slot  
- [ ] cinematic-audit ok（或显式 skip + 说明）  
- [ ] ffprobe 有 aac + mean_volume 合理；抽帧有中字  
- [ ] delivery 写清 plate vs master-lock  

## 命令骨架

```bash
export AIFILM_PYTHON=~/.pyenv/versions/3.11.15/bin/python
export PYTHONPATH=~/.grok/plugins/ai-film-grok/skills/ai-film-grok/scripts
# 正牌 plate（CLI 修后）
aifilm final --root "<film>" --post-engine ffmpeg --tts-backend edge \
  --music-mood rnb --vo-fit atempo --vo-rate=+18% \
  --caption-path ship_hardburn --force --skip-preflight \
  --skip-heat-gate --allow-loop-risk --lipsync off
# 或直调
$AIFILM_PYTHON -c "from post.render_final import main; import sys; sys.argv=[...]; raise SystemExit(main())"
```

## 残余（本片未绿）

gate-auto five_track / i2v_motion / variety；无 licensed rnb wav；未 human review-final。
