# FRW LTX T2V · 无角色环境床 / 首帧（无限额度通道）

> 2026-07-21 实测：账号可 **submit 201 → completed**，`templateId=3507313183813537792`（平台名 **ltx-文生视频** / CLI **`ltx-t2v`**）。  
> 平台**不**单独挂名「LTX 2.3」——FRW 暴露的就是这支 LTX 文生视频；与开源 LTX-2.3 同族能力，以 FRW 模板为准。  
> **用途**：与角色无关的环境/道具/空镜运动与首帧；**禁止**用 T2V 锁脸当身份。

## 一句话

```text
hero / 有脸  → Grok still + Grok I2V（seedance 关时）
env / 无角色 → FRW ltx-t2v（无限额度）→ 可当 clip，或抽首帧当 keyframe
```

## 可用性（本机探针）

| 项 | 结果 |
|----|------|
| 模板 | `ltx-t2v` · 3507313183813537792 · ltx-文生视频 |
| 参数 | `prompt` + `width`/`height`/`video_duration`/`video_fps` **字符串** |
| 竖屏 | `720`×`1280` · duration `5` · fps `24` |
| 提交 | **201** |
| 完成 | **completed**（约 1–2 min） |
| 计费样例 | costPoints≈20（无限额度账下仍记账，可跑） |

同族还有：`ltx-i2v` / `ltx-flf` / `ltx-lipsync`（i2v 历史上常 502，env 优先 **t2v**）。

## 何时用

| 场景 | 用 LTX T2V | 不用 |
|------|------------|------|
| `shot_role`: env / bridge / insert | ✅ | |
| 空镜、走廊、更衣室无脸、氛围床 | ✅ | |
| 需要**首帧**再交给 Grok 加角色 | ✅ 生成后 `extract-frame --which first` | |
| 女主/脸/定妆一致 | ❌ | Grok `image_edit(cast)` |
| 声称人物身份锁定 | ❌ | hero I2V only |

## CLI

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"

# 提交并等待（stdout JSON）
"$AIFILM" frw newvideo --model ltx-t2v \
  --prompt "empty locker room, soft warm light, no people, no faces, anime bg plate" \
  --width 720 --height 1280 --duration 5 --fps 24 --wait

# 查询
"$AIFILM" frw newvideo-query --task-id <id> --wait

# 成片侧：下载后
"$AIFILM" register-clip --root "<film>" --shot-id shot_env01 \
  --source "<clip.mp4>" --source-endpoint frw_ltx_t2v \
  --identity-approved --motion-approved \
  --review-note "provider=frw model=ltx-t2v role=env no-face"

# 抽首帧作后续 keyframe（可选）
"$AIFILM" extract-frame --root "<film>" --shot-id shot_env01 \
  --which first --promote-keyframe shot_env01
```

一键包装（推荐）：

```bash
"$AIFILM" env-plate --root "<film>" --shot-id shot_env01 \
  --prompt "…" --wait
# → clips/ + keyframes/ 首帧 + register frw_ltx_t2v
```

## film-spec

```json
{
  "i2v_provider": "grok",
  "frw_env_model": "ltx-t2v",
  "shots": [
    {
      "id": "shot_env01",
      "shot_role": "env",
      "nar": "更衣室灯还亮着。",
      "dsl": {
        "action": "ambient hold",
        "motion": "slow dust drift",
        "visible_change": "still air → floating dust"
      }
    }
  ]
}
```

`write-spec` 已默认 `frw_env_model=ltx-t2v`。  
`dispatch` 在 `grok_primary` 下会提示 env 走 FRW LTX。

## Prompt 纪律（无脸）

- 英文/中英均可；显式：**no people, no faces, empty, unoccupied**  
- 跟 style-bible medium/signature（场景材质），**不**带 cast 名  
- 禁 shot ID 水印进画面  

## 与 hero 拼接

1. env 镜：`ltx-t2v` 整段进时间线（soft 转场可）  
2. 或：ltx 抽首帧 → Grok `image_edit` 加角色 → Grok I2V（角色戏）  
3. continue 字节缝只用于 **hero 链**，env↔hero 用 soft/hard 策略见 edit_policy  

## 恢复 Seedance 后

hero 可回 `seedance_first`；**env 仍建议 ltx-t2v**（省 hero 配额、无限 FRW 烧环境）。

权威交叉：[i2v-grok-primary.md](i2v-grok-primary.md) · [frw-degrade-dispatch.md](frw-degrade-dispatch.md) · [layer-routing lessons](lessons-2026-07-20-layer-routing.md)
