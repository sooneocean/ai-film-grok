# Lessons · FRW LTX / 经典 T2I·T2V·I2V 探针（参数契约）

> 2026-07-20 · **P0 可观测 · P5 分层**  
> 探针账号：本机 frwclaw `FRW_API_KEY`；模板源：`GET /api/frwapi/v1/templates`（17 个）

## 一句话

**LTX 在 FRW 里有完整 t2v / i2v / flf / lipsync 模板；参数必须全是字符串。**  
本账号：**ltx-t2v 可提交**；**ltx-i2v / flf 当前 502（平台侧）**；**Seedance 403**；经典 text2image / img2image / text2video / img2video **201 可用**。

---

## 官方 inputSchema（线上 templates）

### `ltx-t2v` · template `3507313183813537792`

| 字段 | 类型 | 必填 |
|------|------|------|
| `prompt` | string | ✅ |
| `width` | **string** | 否 |
| `height` | **string** | 否 |
| `video_duration` | **string** | 否 |
| `video_fps` | **string** | 否 |

### `ltx-i2v` · template `3507007578464849920`

| 字段 | 类型 | 必填 |
|------|------|------|
| `prompt` | string | ✅ |
| `image_url` | string | ✅ |
| `width` / `height` / `video_duration` / `video_fps` | **string** | 否 |

### `ltx-flf` · template `3507008394730934272`

| 字段 | 类型 | 必填 |
|------|------|------|
| `prompt` | string | ✅ |
| `image_url` | string | ✅ |
| `image2_url` | string | ✅ |
| dims/duration/fps | string | 否 |

### `ltx-lipsync` · template `3507007950994542592`

| 字段 | 类型 | 必填 |
|------|------|------|
| `prompt` | string | ✅ |
| `image_url` | string | ✅ |
| `audio_url` | string | ✅ |
| dims/duration/fps | string | 否 |

**硬约束（探针 400）**：`width`/`height`/`video_duration`/`video_fps` 传 **数字** →  
`cannot unmarshal number into … of type string`。dispatch 必须送字符串。

---

## 本账号探针结果（2026-07-20）

| 用例 | HTTP | 结论 |
|------|------|------|
| ltx-t2v `width=720` `height=1280` str | **201** | ✅ 竖屏可下单 |
| ltx-t2v `1280×720` str | **201** | ✅ 横屏可下单 |
| ltx-t2v `512×896` str | **201** | ✅ |
| ltx-t2v `768×1344` | **502** | ❌ 避免此尺寸 |
| ltx-t2v int width | **400** | ❌ 必须 string |
| ltx-i2v 全参数矩阵（https/http/camel/无 fps…） | **502** | ⚠️ 模板在、上游/网关挂 |
| ltx-flf | **502** | ⚠️ 同上 |
| seedance-2-fast-i2v | **403** | ❌ 无权 |
| classic `text2image` / `img2image` | **201** | ✅ |
| classic `text2video` / `img2video` | **201** | ✅ 质量地板 |

说明：502 是 Cloudflare/网关 HTML，不是参数 400——**参数契约已对齐官方 schema**，i2v/flf 属平台可用性，不是 key 写错。

---

## Agent CLI 配方

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"

# 上传 keyframe（优先用返回的 https files/view URL）
"$AIFILM" frw upload --file-path "keyframes/shot01.jpg" --category image

# ✅ LTX 文生视频（竖屏 9:16）
"$AIFILM" frw newvideo --model ltx-t2v \
  --prompt "anime neon cafe, soft continuous motion" \
  --width 720 --height 1280 --duration 5 --fps 24 \
  --wait --poll-timeout 600

# ⚠️ LTX 图生视频（schema 正确；若 502 则换 Grok / 等平台恢复）
"$AIFILM" frw newvideo --model ltx-i2v \
  --img-url "https://frwcore6.aiaiartist.com/files/view/<id>.jpg" \
  --prompt "subtle blink, subject stays centered, full head headroom" \
  --width 720 --height 1280 --duration 5 --fps 24 \
  --wait --poll-timeout 600

# ✅ 经典 T2I / I2I / T2V / I2V（稳定、非 Seedance 质量）
"$AIFILM" frw text2image --prompt "..." --width 720 --height 1280 --wait
"$AIFILM" frw img2image  --prompt "..." --img-url "<url>" --wait
"$AIFILM" frw text2video --prompt "..." --width 576 --height 1024 --wait
"$AIFILM" frw img2video  --prompt "..." --img-url "<url>" --width 576 --height 1024 --wait
```

dispatch 会把 `--duration` / `--fps` 映射为 LTX 的 `video_duration` / `video_fps`（string）。

---

## film-spec 键

| `frw_video_model` | 用途 |
|-------------------|------|
| `seedance-2-fast-i2v` | 默认 bulk 质量（账号开了才行） |
| `ltx-i2v` | FRW 图生；精确 720×1280；平台健康时 |
| `ltx-t2v` | 空镜/无角色文生视频 |
| `ltx-flf` | 首尾帧（平台健康时） |
| `legacy-img2video` | 仅显式；质量地板 |

LTX 竖屏建议同时写：

```json
{
  "frw_video_model": "ltx-i2v",
  "frw_width": "720",
  "frw_height": "1280",
  "frw_duration": "5",
  "frw_fps": "24"
}
```

---

## 路由（Seedance 不可用时）

```text
1) seedance-2-fast-i2v     → 403? 下一步
2) ltx-i2v (720×1280 str)  → 502? 下一步
3) grok image_to_video 720p
4) 禁止默认 legacy img2video
```

Still 仍优先 Grok；经典 FRW T2I/I2I 仅备用（防混 provider）。

---

## 不可宣称

- 模板在列表里 = 一定能 201  
- LTX 默认 1280×720 = 适合 9:16 短片（竖屏必须显式 720×1280）  
- legacy i2v 201 = 质量合格  

## 验证

```bash
# 参数类型
"$AIFILM" frw newvideo --model ltx-t2v --prompt "test" --width 720 --height 1280 --duration 5
# 期望 201 或 completed；勿用整数 width
```
