# Memory · I2V 静帧–prompt 对齐 + interrupt 假进度（P0 · 2026-07-29）

> 用户：「质量太差了」→ 写回记忆后收工。  
> **全文**：[lessons-2026-07-29-i2v-still-prompt-match-comfy-interrupt](../references/lessons-2026-07-29-i2v-still-prompt-match-comfy-interrupt.md)  
> 连带：[multifilm OOM](2026-07-29-comfy-multifilm-contention-oom.md) · [pilot 独占](2026-07-29-comfy-gpu-priority-pilot-i2v.md)

## 一句话

**静帧是什么 prompt 就写什么；interrupt=零进度；mean 绿≠质量过关；抢不到 5090 就 PARTIAL。**

## 片例

- `0728/btc-vessel-ep02-power-seed` · `ep01_sc11_bt03_sh01`  
- 静帧=机房站姿 bare；旧 prompt=床戏 afterglow → hero mean **12.16** 质量差  
- 重渲 46011–13/21 被 `execution_interrupted @ KSamplerAdvanced`；无新 mp4  
- 路径：`clips/ep01_sc11_bt03_sh01.mp4` · `keyframes/ep01_sc11_bt03_sh01.png`

## 硬禁

- 不看静帧套 afterglow/meat 模板  
- RUNNING 时 free-memory / interrupt 本片  
- 用排队分钟数报 ETA（无 success 落盘）  
- 连续 interrupt 仍空转 seed  
- bare 镜死磕 Grok I2V（易 moderated）

## 提交前 10 秒

1. 目视 still 姿态/场景  
2. foreign `comfy_video generate` = 0  
3. 落盘 mp4 + mean + 中末帧语义  
