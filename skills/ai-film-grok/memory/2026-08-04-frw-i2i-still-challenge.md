# Memory · 2026-08-04 · FRW i2i 素材挑战（I2V/R2V 源 still）

**运营矩阵**：[weapon-lane-matrix.md](../references/weapon-lane-matrix.md)  
**限流代码**：`scripts/frw_rate_limit.py` · `scripts/still_challenge.py`

## 用户原话
> frw i2i 最高限制半分钟调用一次生图 帮我依照这个规范去优化 使用i2i 去进行素材挑战 让i2v r2v的素材生成优化替换

## 三句话
1. **FRW img2image ≥30s/次**（与 ai-film-frw 共享 rate 文件）；默认 **1 unit** 提交。
2. **still-challenge** 产 candidate → **人 promote** 换 I2V/R2V 源；不静默、不抢 5090。
3. 弱 take / 软 still：先换零件再试跑，优于盲堆 R2V。

## 检查清单
- [ ] `aifilm still-challenge plan|next --root`
- [ ] `run --execute --max-submits 1`（付费显式）
- [ ] `promote --identity-approved --anatomy-safe --review-note`
- [ ] `h3 run` 用新 still；或 `--still` 试用 candidate
- [ ] 续镜/毒镜不入队

## 作战序
```text
still-challenge next → (wait image_wait_s) → run --execute
→ 人审 promote → h3 I2V/R2V → pk-compare
```
