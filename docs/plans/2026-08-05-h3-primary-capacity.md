# h3_primary · 5090 无限主产线（2026-08-05）

**Status:** Wave 0–1 **DONE in 2.39.14** · W3 until-empty still open  
**Strategy:** Local MiniMax H3 on 5090 is the **film-wide primary** generation path. Time is free; cloud quota is not.

## 定策三句

1. **`AIFILM_I2V_PROFILE=h3_primary`** → auto provider `comfy-h3`；setup/meat/对白/env 默认本地。
2. **场景选模**仍由 `h3_mode.py`：I2V / FLF / R2V / T2V（env 无脸）；不改「R2V 全片默认」。
3. **Grok** = pilot 快看 / soft 对照；云 bulk 在 h3_primary 下默认硬拦（`AIFILM_ALLOW_CLOUD_RESTRICTED=1` 逃生）。

## 与 hybrid_h3 差异

| | hybrid_h3 | h3_primary |
|--|-----------|------------|
| auto provider | grok | **comfy-h3** |
| setup soft | Grok bulk | **H3 I2V** |
| restricted | H3 lock | H3 lock |
| env | FRW T2V | **H3 T2V** |
| safe dialogue | FRW LTX | **H3 I2V** |
| dispatch next | fill-idle + queue | **h3-run-next 优先** |

## Wave checklist

- [x] W0 本档 + SKILL/矩阵指针
- [x] W1 profile / router / media-queue / next_actions
- [x] W1 tests `test_h3_primary.py`
- [x] W2 mode table 沿用 `h3_mode` + 矩阵文案 + 路由测
- [x] W3 until-empty + capacity-plan + P0 硬断言（v2.39.16）
- [x] W4 gate 减负（v2.39.17）：单机读 next · pilot 三模式 GO · ship-prep 人审一页
- [ ] W5 CLI 拆分

### W3 用法

```bash
aifilm h3 capacity-plan --root "<film>"          # ETA 一页纸
aifilm h3 cycle --root "<film>" --until-empty --execute --max 5
# 可选：--max-cycles 40（硬顶 80）；--continue-on-capacity 不因 VRAM 停
```

## 启用

```bash
# config.env or shell
export AIFILM_I2V_PROFILE=h3_primary
aifilm write-spec --root "<film>"   # re-project lanes
aifilm dispatch --root "<film>"     # expect h3-run-next when clips incomplete + pilot GO
```

## Escape

- `AIFILM_ALLOW_CLOUD_RESTRICTED=1` — 允许 media-queue 云路径（不推荐 meat）
- `AIFILM_I2V_PROFILE=hybrid_h3` — 回到双轨
- `h3.enabled=false` — 关 H3 软锁（h3_primary 仍会标 profile）
