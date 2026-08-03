# FRW 2V · Seedance / LTX / 经典通道（官方 dispatch 契约）

> 2026-07-21 · **质量路由 + Key 能力位版**
> **运营默认**：`AIFILM_I2V_PROFILE=ltx23_primary`；动作顺序为 FRW LTX → FRW API I2V → Grok Video 1.5。`grok_primary` 仅保留给旧项目显式锁定。
> 探针课：[lessons-2026-07-20-frw-ltx-probe.md](lessons-2026-07-20-frw-ltx-probe.md)
> 胃镜室：[lessons-2026-07-20-seedance-quality.md](lessons-2026-07-20-seedance-quality.md)
> **Key 矩阵**：[lessons-2026-07-21-frw-key-capability.md](lessons-2026-07-21-frw-key-capability.md)
> 平台 templates：`GET /api/frwapi/v1/templates`（≈17）+ frwclaw `NEW_VIDEO_TEMPLATES`

## 一句话

**Still → 已批准角色状态图锁身份。**
**Clip → FRW LTX 2.3 primary → FRW API `img2video` → Grok Video 1.5。**
未就绪 provider 可留下原因后跳过；已开始的任务只有可判定技术失败才进入下一路线。
FRW 多模型评测使用独立 [A/B 工作流](frw-ab-workflow.md)：pilot 全候选并行，
production 只跑人审 champion＋challenger；它不会改写 primary。
**禁止**默认 legacy `img2video`。
**403 ≠ 参数错**；**502 ≠ 没权限**。

---

## Key 能力位（2026-07-21 沉定）

换 key / 新账号 **bulk 前**必须 canary（写 `receipts/frw-key-capability.json`）：

| 探针 | 期望 | 失败时 |
|------|------|--------|
| `GET …/balance` | 200 + credits | 停，查 key |
| `seedance-2-fast-i2v` 提交 | **201** | **403** → 未开通，走下方「无 Seedance 路由」 |
| `ltx-t2v` | 201→**completed** | 再探 classic t2v |
| frwcore upload 换票 | 拿 view URL | 403 → 只用公网可达图 URL |

### 判读

| 信号 | 含义 | 动作 |
|------|------|------|
| **403** 无权使用该模板 | 能力位 | 找运营；勿死重试 |
| **502** | 平台挂 | 换族 / 稍后；勿当 403 |
| **400** 资源无法访问 | 图 URL FRW 抓不到 | upload 或换开放 CDN |
| **201→completed** | 真可用 | 可 bulk |

### 典型样本 key（Seedance 全关）

| 通道 | 状态 | 漫剧用途 |
|------|------|----------|
| seedance / byteplus 全族 | ❌ 403 | 不能当默认 bulk |
| **`ltx-t2v`** | ✅ completed | **L2 环境主力** |
| ltx-i2v / flf / lipsync | ⚠️ 502 | 暂不可当 L1 备胎 |
| classic T2I / T2V / **I2V** / FLF | ✅ completed | 兜底；I2V=质量地板 |
| classic I2I | ⚠️ 502 | 慎 |
| gimm-vfi / wan | ⚠️ 502 | 勿依赖 |
| frwcore 上传 | ❌ 部分 key 无效 token | 公网 URL |

---

## 分层路由（生产 · 人物一致 × 合成层）

权威细表：[lessons-2026-07-20-layer-routing.md](lessons-2026-07-20-layer-routing.md)。

| 层 | 职责 | **主力**（权限开） | **Fallback** | 禁止 |
|----|------|-------------------|--------------|------|
| **L0** 身份静帧 | cast/style | **Grok** `image_edit(cast)` | FRW text2image（非身份）；img2image 慎 | 每镜纯 T2I 重抽脸 |
| **L1** 人物 A-roll | 有脸 `hero` | **FRW LTX 2.3** | FRW API I2V → Grok Video 1.5 | **LTX T2V 当脸**；冒充模型 |
| **L2** 合成/环境 | `env\|bridge\|insert` | **LTX T2V** | Seedance t2v → **classic t2v** | 用 T2V 声称人物一致 |
| **L3** 设计后期 | 字幕/片头 | HyperFrames | Remotion | Ken Burns 当戏 |

```text
# 人物动作
FRW LTX 2.3
  → 未就绪/技术失败：Grok image_to_video
  → 未就绪/技术失败：仅模型身份已证明的 FRW Wan
  → 未就绪/技术失败：通过资源门槛的本地 I2V
  → 全部不可用：失败关闭，不冒充完成

# 无脸床（合成层 · 本类 key 最稳）
ltx-t2v (主力, completed) → classic text2video
```

film-spec：`frw_video_model` = L1；`frw_env_model: ltx-t2v` = L2；每镜 `shot_role`。
write-spec 写入 `_frw_fallback_chain` / `_layer_routing`。

---

## film-spec

```json
{
  "i2v_provider": "frw",
  "frw_video_model": "seedance-2-fast-i2v",
  "frw_aspect_ratio": "9:16",
  "frw_resolution": "720p",
  "frw_duration": "5",
  "frw_env_model": "ltx-t2v"
}
```

无 Seedance 权限时（capability 回执 `seedance_i2v=403`）：

```json
{
  "i2v_provider": "grok",
  "frw_env_model": "ltx-t2v",
  "frw_video_model": "seedance-2-fast-i2v"
}
```

说明：L1 走 Grok；L2 仍可用 FRW `ltx-t2v`。**勿**把 `frw_video_model` 改成 seedance 却实际提交 classic。

仅 FRW-only 救生艇（显式）：

```json
{
  "i2v_provider": "frw",
  "frw_video_model": "legacy-img2video"
}
```

write-spec 会 WARN；register 必须 `frw_img2video`。

LTX 像素：

```json
{
  "frw_video_model": "ltx-i2v",
  "frw_width": "720",
  "frw_height": "1280",
  "frw_duration": "5",
  "frw_fps": "24"
}
```

write-spec：`ltx-*` 自动钉竖屏 `720×1280` 字符串。

---

## CLI（经 aifilm）

stdout：一行 JSON，含 `protocol_version`（1.0）/ `data.video_url` / `data.model`；入口 `frw_dispatch` / `"$AIFILM" frw`。
平台：frwclaw `NEW_VIDEO_TEMPLATES`；legacy：`img2video` / `first-last-frame` / `text2video` / `text2image`。

全模型 A/B 控制面入口为 `"$AIFILM" frw ab …`；完整命令见
[frw-ab-workflow.md](frw-ab-workflow.md)。

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"

# 优先 upload；换票失败则改用公网 HTTPS 图
"$AIFILM" frw upload --file-path "<keyframe.png>" --category image
# 优先 data.raw.data.url → https://frwcore6…/files/view/<id>.jpg

# ✅ 默认 bulk I2V（账号已开 Seedance）
"$AIFILM" frw newvideo --model seedance-2-fast-i2v \
  --img-url "<url>" --prompt "@Image1 …" \
  --aspect-ratio 9:16 --resolution 720p --duration 5 --wait

# ✅ L2 环境（多数 key 可 completed）
"$AIFILM" frw newvideo --model ltx-t2v \
  --prompt "anime neon cafe soft motion" \
  --width 720 --height 1280 --duration 5 --fps 24 --wait

# ⚠️ LTX 图生（schema 对；多次 502）
"$AIFILM" frw newvideo --model ltx-i2v \
  --img-url "<https-view-url>" \
  --prompt "subtle blink, subject stays centered" \
  --width 720 --height 1280 --duration 5 --fps 24 --wait

# 经典（稳定兜底 · 非默认质量）
"$AIFILM" frw text2image --prompt "..." --width 720 --height 1280 --wait
"$AIFILM" frw text2video --prompt "..." --width 576 --height 1024 --wait
"$AIFILM" frw img2video  --prompt "..." --img-url "<url>" --width 576 --height 1024 --wait
"$AIFILM" frw first-last-frame --img1 "<a>" --img2 "<b>" --positive-prompt "..." --wait
```

---

## LTX 参数契约

| 规则 | 说明 |
|------|------|
| 类型 | `width` `height` `video_duration` `video_fps` **必须 string**（int → 400） |
| 竖屏推荐 | **`720`×`1280`** 或 `512`×`896` |
| 避免 | `768`×`1344`（探针 502） |
| i2v 字段 | `image_url` + `prompt`（不是 imageUrl） |
| flf 字段 | `image_url` + `image2_url` + `prompt` |

| key | template_id | 探针（跨会话） |
|-----|-------------|----------------|
| `ltx-t2v` | 3507313183813537792 | **201 → completed** ✅ |
| `ltx-i2v` | 3507007578464849920 | **502** ⚠️ |
| `ltx-flf` | 3507008394730934272 | **502** ⚠️ |
| `ltx-lipsync` | 3507007950994542592 | **502** ⚠️ |

完整矩阵：[lessons-2026-07-20-frw-ltx-probe.md](lessons-2026-07-20-frw-ltx-probe.md) · key 样本：[lessons-2026-07-21-frw-key-capability.md](lessons-2026-07-21-frw-key-capability.md)。

---

## `frw_video_model` 键

| key | 说明 |
|-----|------|
| `seedance-2-fast-i2v` | FRW 技术故障 fallback 的优先质量档（需权限与 provider-switch receipt） |
| `seedance-2-pro-flf` | 首尾帧高档（**需权限**） |
| `byteplus-seedance-2-*` | 字节渠道（**需权限**） |
| `ltx-i2v` / `ltx-t2v` / `ltx-flf` / `ltx-lipsync` | 精确宽高；i2v 常 502 |
| `legacy-img2video` | **仅显式**；质量地板；FRW-only 救生艇 |

register endpoint：`frw_seedance_i2v` · `frw_seedance_flf` · `frw_ltx_i2v` · `frw_ltx_t2v` · `frw_img2video`（legacy）· `image_to_video`（Grok）

---

## 入组

```text
download mp4
  → reencode-clips（不升分辨率）
  → register-clip --source-endpoint frw_seedance_i2v|frw_ltx_t2v|frw_img2video|image_to_video
       --review-note "provider=… model=… res=… fallback=… identity_lock_ok"
```

---

## 禁用

1. 默认 legacy `img2video`
2. Seedance **403** 后假装仍是 Seedance
3. LTX 用整数 width/height
4. 576→720 reencode 当高清
5. 把 Grok I2V 说成 FLF / Seedance
6. 忽略 capability 回执直接 bulk
7. 本机可达、FRW 403 的图 URL 当唯一输入

## 探针 / canary（推荐入口）

```bash
# bulk 前：余额 + Seedance 权限 + ltx-t2v；写 receipts/frw-key-capability.json
"$AIFILM" frw canary --root "<film-root>"

# 等 ltx-t2v 跑完（会耗积分）
"$AIFILM" frw canary --root "<film-root>" --wait

# 连 classic I2V / ltx-i2v 一并探
"$AIFILM" frw canary --root "<film-root>" --full

# 手动分枪（同上）
"$AIFILM" frw newvideo --model ltx-t2v \
  --prompt "test soft motion" --width 720 --height 1280 --duration 5 --fps 24
"$AIFILM" frw newvideo --model seedance-2-fast-i2v \
  --img-url "<url>" --prompt "@Image1 blink" \
  --aspect-ratio 9:16 --resolution 720p --duration 5
```

实现：`scripts/frw_canary.py`（经 `frw_dispatch canary` / `"$AIFILM" frw canary`）。
