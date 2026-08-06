# Lesson · 宿色 EP01 正牌 final（2026-08-06）

## 背景

`suse-evolution-ep01` 26 镜 H3 已批后走正牌 final（Edge + rnb + ship_hardburn）。  
产品侧衣着教训见 [lessons-2026-08-06-wardrobe-no-redress-fullnude-fallback.md](lessons-2026-08-06-wardrobe-no-redress-fullnude-fallback.md)。  
本课只收 **final 工程 IRON**。

## P0 · render_final shim 假成功

`scripts/render_final.py` 原为：

```python
from post import render_final as _impl
sys.modules[__name__] = _impl
# 无 main() —— 作脚本执行时立刻结束，exit 0
```

`aifilm final` 的 stage_plate 子进程因此 **1 秒完成、无 TTS、无 mix**，pipeline-events 却记 completed。

**修复**：`if __name__ == "__main__": raise SystemExit(_impl.main())` 再替换 module。  
**验收**：日志出现 `TTS …` / `stretch …` / `ok:true`，`film_final.mp4` 有 aac。

## P0 · sex duration 强拉 10s vs 短 H3

`validate_film_spec` 在 `HEAT_SEX_DURATION_LOW` 时对 act/climax：

```python
sh["duration_sec"] = max(10.0, …)
```

短 H3 源 ~5.17s，`forbid_loop` 最大约 5.9s →  
`forbid_loop stretch cannot cover target=10.00s from src=5.17s`。

**处置**：

- 调 `sex_min_duration_ratio` 使 ratio 达标、不再触发强拉；或  
- 真要 10s 槽 → **重 I2V 长片**；  
- 禁止只改 film-spec duration 不认源。

## P0 · 口白窗

检查顺序：TTS 自然时长 ≤ `audio_cues[].duration_sec` ≤ `duration_sec - offset`。  
`vo_fit=atempo` **不能**先救超窗。缩句 / `vo_rate=+18%` / 加大 slot（且源够长）。

## P1 其它

| 项 | 要点 |
|----|------|
| cinematic | 邻镜景别 rank 不同；角 bucket 变化；保留 beat 语义动词 |
| BGM rnb | 仅 license 无 wav → procedural；有文件再挂 music+license |
| plate 诚实 | skip gate = 可交付 plate，**不是** master-lock / final_complete |
| HF | 无音 plate 先 final；再 compose |

## 记忆短卡

`memory/2026-08-06-suse-ep01-official-final-iron.md`
