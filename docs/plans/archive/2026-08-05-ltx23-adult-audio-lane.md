# LTX 2.3 adult audio lane + FRW i2i repair（工程正文）

> 会话规划：`plan.md`（session）。权限档 **A**：safe 对白 + soft 半衣 → LTX；bare/meat → H3。

## 一句话

`ltx23_adult` = 云端有声第三轨 + 本地肉戏硬轨 + i2i 修底片；不替换 `h3_primary`。

## 触发

| 条件 | Motion | Audio |
|------|--------|-------|
| poison still | 禁 I2V | — |
| restricted / bare / meat | H3 I2V/R2V/FLF | prefer_native |
| safe dialogue + lanes/profile 允许 | LTX `img2video-audio` | prefer_native |
| soft + `ltx23_adult` | LTX；失败→H3 | prefer_native |
| 弱 still / hijack / 身份漂 | FRW i2i still-challenge → promote → 重 motion | 继承 |
| env 无脸 | ltx-t2v 或 H3 T2V | 环境 |

## Profile

```bash
export AIFILM_I2V_PROFILE=ltx23_adult
```

- auto `i2v_provider` label = `frw-ltx23`
- `h3.enabled` 自动 true（肉戏）
- `motion_lanes.still_repair` = FRW i2i

## CLI

```bash
aifilm frw canary --root "$FILM" --full
aifilm still-challenge next --root "$FILM"
aifilm frw img2video-audio --model ltx2.3 --img-url … --prompt … --wait
aifilm register-clip … --source-endpoint frw_ltx23_img2video_audio --audio-policy prefer_native
aifilm h3 run --root "$FILM" --shot-id <meat> --mode i2v --register
```

## 限流

- i2i ≥30s/unit · video ≥5min/unit · dispatch 1 unit/回合

## 代码

- `film_spec_profile.I2V_PROFILES` + `ltx23_adult`
- `production_router.build_shot_intent` → `cloud_ltx23_audio`
- hard-defaults / weapon-lane-matrix 补丁
- memory: `skills/ai-film-grok/memory/2026-08-05-ltx23-adult-audio-i2i-repair.md`
