# I2V · Grok Primary 运营模式（Seedance 暂不可用）

> 2026-07-21 · FRW Seedance 权限/通道不可用时的**默认做片机制**。  
> 恢复 Seedance：`AIFILM_I2V_PROFILE=seedance_first` + canary 201。

## 一句话

```text
Still = Grok image_edit(cast)
Motion bulk = Grok image_to_video 720p（6s/10s）
Env 可选 = FRW ltx-t2v（有 canary 再开）
禁止 = 默认 seedance bulk、legacy img2video 冒充质量、T2V 锁脸
```

## 环境开关

```bash
# config.env（推荐当前）
AIFILM_I2V_PROFILE=grok_primary
# 或
AIFILM_SEEDANCE_AVAILABLE=0

# Seedance 恢复后
# AIFILM_I2V_PROFILE=seedance_first
# AIFILM_SEEDANCE_AVAILABLE=1
```

`write-spec`：`i2v_provider: auto` → **`grok`**，并写 `_i2v_profile` / `_layer_routing`。

## 生产循环（agent）

```bash
aifilm dispatch --root "<film>"
aifilm write-spec --root "<film>"   # auto→grok
# 每镜：
# 1) image_edit(cast) → keyframes/shotXX.png
# 2) media-queue add image_to_video --input keyframe --prompt-file …
# 3) claim → Grok image_to_video（串行，防 429）
# 4) register-clip --source-endpoint image_to_video --identity-approved --motion-approved
# continue：extract last → promote next keyframe → 只对该图 I2V
```

```bash
"$MEDIA_QUEUE" --budget-units 12 add --root "<root>" --shot-id shot01 \
  --operation image_to_video --prompt-file "prompts/shot01-i2v.txt" \
  --input "keyframes/shot01.png"
"$MEDIA_QUEUE" claim --root "<root>"
# Agent: image_to_video(image=…, prompt=…, duration=6)
"$AIFILM" register-clip --root "<root>" --shot-id shot01 --source "<clip.mp4>" \
  --source-endpoint image_to_video --identity-approved --motion-approved \
  --review-note "provider=grok model=image_to_video res=720p profile=grok_primary"
```

## film-spec 示例

```json
{
  "i2v_provider": "grok",
  "frw_env_model": "ltx-t2v",
  "frw_video_model": "seedance-2-fast-i2v",
  "frw_aspect_ratio": "9:16",
  "frw_resolution": "720p"
}
```

`frw_video_model` 可保留 seedance 标签（权限恢复时用）；**L1 以 `i2v_provider=grok` 为准**。

## 纪律

| 项 | 规则 |
|----|------|
| 并发 | **一次一件** image_to_video（429） |
| 时长 | 6s 优先（或 10s）；film-spec duration_sec 对齐 VO |
| 接戏 | promote 末帧 SHA；禁 cast 重起 |
| 同源 | 整片 hero still 都 Grok；勿半 FRW still |
| 环境床 | 可选 FRW `ltx-t2v`；失败则 hero 镜盖全片 |
| 注册 | 必须 `image_to_video` endpoint，禁止假装 seedance |
| 配额 | 用 OAuth / 会话 Imagine；`grok-oauth doctor` 看机位 |

## 与旧 Seedance 路径对照

| | Seedance first | **Grok primary（当前）** |
|--|----------------|-------------------------|
| bulk 动 | FRW newvideo | **image_to_video** |
| canary | bulk 前硬建议 | 可选（仅 env） |
| register | frw_seedance_i2v | **image_to_video** |
| 身份 still | Grok edit | Grok edit（不变） |

## 恢复 Seedance

1. `AIFILM_I2V_PROFILE=seedance_first`  
2. `aifilm frw canary --root <film>` → seedance 201  
3. `capability --suggest-i2v --apply` → `i2v_provider=frw`  
4. `write-spec` 再 queue  

权威：[frw-degrade-dispatch.md](frw-degrade-dispatch.md) · [grok-build-sdk.md](grok-build-sdk.md) · [hard-defaults.md](hard-defaults.md)
