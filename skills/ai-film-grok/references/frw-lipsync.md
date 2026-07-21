# FRW 口型（音画同步）· 接入 ai-film-grok

> 让**对白近景**嘴型跟旁白更贴，影片更顺。  
> **说书人默认仍 off**——全片硬上口型会毁动漫脸。  
> 2026-07-21 本机 key 探针：**seedance lipsync=403**；**ltx/wan lipsync=502**。代码路径已接好，平台恢复即可用。

## 一句话

```text
storyteller / 中远景  → lipsync off（默认）
character 近景 + lipsync:true + 短句 VO
  → aifilm frw-lipsync probe
  → 可用则 face still + edge VO → FRW 音画同步 → register
  → 不可用则 local Wav2Lip（须 backend-lock）或跳过
```

## FRW 模板（线上）

| CLI model | 平台名 | templateId | 探针样例 |
|-----------|--------|------------|----------|
| `ltx-lipsync` | ltx-音画同步 | 3507007950994542592 | **502** platform |
| `wan-lipsync` | wan-音画同步 | 3507253019391561728 | **502** platform |
| `seedance-2-pro-lipsync` | seedance-2-pro-音画同步 | 3500510034968711168 | **403** 无权 |

输入：**正脸/微侧静帧图 URL + 参考音频 URL**（本地文件先 `frw upload`）。  
竖屏 LTX：`720×1280` 字符串参数。

## 何时用（更顺，不毁片）

| 条件 | 开 |
|------|----|
| `vo_mode` character / hybrid | 可 |
| 镜 `lipsync: true` | 必 |
| 景别 CU/MCU、遮挡少 | 必 |
| 单句短 VO（≤镜长） | 必 |
| 用户明确要开口 | 必 |
| storyteller 旁白说书 | **默认关** |
| 全身/远景/快切 | **关** |

## 命令

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"

# 1) 先探针（不依赖片子）
"$AIFILM" frw-lipsync probe

# 2) 有 201 的 model 后再跑
"$AIFILM" tts-rehearse --root "<film>" --backend edge   # 或单镜 VO wav
"$AIFILM" frw-lipsync run \
  --root "<film>" --shot-id shot03 \
  --face "keyframes/shot03.png" \
  --audio "receipts/tts-rehearsal-audio/shot03.mp3" \
  --model auto --register --wait
# register endpoint: frw_ltx_lipsync | frw_wan_lipsync | frw_seedance_lipsync
```

也可：

```bash
"$AIFILM" frw newvideo --model ltx-lipsync \
  --img-url <url> --audio-url <url> --prompt "subtle talk" \
  --width 720 --height 1280 --duration 5 --fps 24 --wait
```

## film-spec

```json
{
  "vo_mode": "character",
  "audio_policy": { "allow_lipsync": true },
  "shots": [
    {
      "id": "shot03",
      "lipsync": true,
      "nar": "你……还在看？",
      "dsl": { "camera": { "shot_size": "close-up" } }
    }
  ]
}
```

`final --lipsync off` 仍是默认；**对白片**可在 register 阶段用 FRW 口型 clip **替换**原 I2V（音画已在片里），final 不必再跑本地 lipsync。

## 编排（dispatch / 流畅度）

```text
hero 近景对白镜:
  Grok image_edit(cast) 正脸 still
  → edge TTS 该镜 wav
  → frw-lipsync probe
  → [201] frw-lipsync run → register frw_*_lipsync
  → [403/502] skip 或 local wav2lip lock 后 canary
env 镜: 不走口型（用 env-plate ltx-t2v）
```

这样：**说书不糊脸**；**对白近景嘴贴音**；FRW 无限额度在可用时拉满。

## 与本地口型

| | FRW | Wav2Lip/MuseTalk |
|--|-----|------------------|
| 算力 | 云端 | 本机 |
| 权限 | 403/502 常见 | 须 backend-lock |
| 默认 | 探针后 opt-in | opt-in |
| final | 常在 production 替换 clip | final --lipsync auto |

## 故障

| 码 | 含义 | 动作 |
|----|------|------|
| 403 | key 未开通模板 | 找运营；或换 model |
| 502 | 平台挂 | 稍后重试；本地兜底 |
| 400 | 参数/URL 不可达 | 用 frw upload 公网 URL |
| 毁脸 | 景别/角度差 | 关该镜 lipsync，保留 I2V |

## 验收

- 只对 `lipsync:true` 近景  
- 完整观看：无糊脸、无抽搐、音画同步  
- register 真 endpoint，勿假装 seedance i2v  
- `review-final` score-audio / identity  

交叉：[lipsync.md](lipsync.md) · [ltx-env-plate.md](ltx-env-plate.md) · [i2v-grok-primary.md](i2v-grok-primary.md)
