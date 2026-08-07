# Memory · 5090 多片互抢 · pilot I2V 独占（2026-07-29）

**P0 · 后面不要再犯。** 全文：[lessons-2026-07-29-comfy-gpu-priority-pilot-i2v.md](../references/lessons-2026-07-29-comfy-gpu-priority-pilot-i2v.md)

## 三秒版

1. **一机一 owner**：用户 GO 优先片 → 停外片 comfy_video → 仅 foreign running 才 interrupt → free → 再 submit。  
2. **禁误杀 zsh**：只杀 argv 真路径 `/scripts/comfy_video.py`；`TN` 先 CONT。  
3. **禁掐自己**：running 图是本片 pilot → 永不 interrupt。  
4. **experimental** = `stage=pilot` + `--allow-experimental`。  
5. **clips 文件数** 才是 I2V 进度；脚本在等 ≠ DONE。

## 片例

- `0729/e-virus-ch05-sensory-rebuild`：pilot 静帧齐、approve 过；I2V 被 btc-vessel / night-lock 互抢 + STOP → **clips=0 PARTIAL**。  
- 对手战术：重生 `sc11_single_shot`、queue 塞 shot09、**SIGSTOP** 外片 worker。

## 下一句 GO

独占 18188 → 串行 sc01/sc02/sc07 Wan → `ls clips/takes` = 3 → register-clip。
