# Lessons · FRW Seedance 质量纪律（胃镜室复盘）· **ARCHIVED 非生产**

> **现行（2026-08-07）**：Seedance bulk **退役**；motion primary = **H3**；禁规划 `provider=seedance`。  
> 本文仅保留 2026-07-20 历史事故与当时策略（当时曾走 FRW/Seedance bulk）。

> 2026-07-20 · 历史 P0 · 样本 `xixifu-autopsy-60s` — 用户判定质量差。

## 一句话

**无限 FRW 配额 ≠ 高质量。**  
bulk 2V 必须走 **`newvideo --model seedance-2-fast-i2v`（或 byteplus / pro-flf）**，  
**禁止默认**旧 `img2video` 模板 `3487718692404334592`（576 起 + 黑盒旧模型）。

---

## 胃镜室实际用了什么（账本）

| 阶段 | 实际 | 问题 |
|------|------|------|
| 定妆 | Codex ImageGen | 与 Grok still **混 provider** |
| still | Grok Imagine `image_edit` | 可保留（身份层） |
| **动态 7 镜** | FRW **legacy `img2video`** | **质量地板** |
| 分辨率 | 576×1024 → reencode **放大** 720×1280 | 假清晰 / 糊 |
| 时长 | 每镜 ≈4.77s | 不是规划 6/10s；整片 ≈33s |
| 接戏 | promote 后仍 image_edit 改姿态 | 跳切 |
| 旁白 | Edge XiaoxiaoNeural | 可用 |
| 后期 | HyperFrames | 救不了 I2V；路径空格还炸过 |
| 双字幕 | zh_en | SRT 碎句与 nar_en 错位 |

---

## 新默认（Seedance 版）

### film-spec

```json
{
  "i2v_provider": "frw",
  "frw_video_model": "seedance-2-fast-i2v",
  "frw_aspect_ratio": "9:16",
  "frw_resolution": "720p",
  "frw_duration": "5"
}
```

| `frw_video_model` | 用途 |
|-------------------|------|
| **`seedance-2-fast-i2v`**（默认） | 单 keyframe bulk，720p，快 |
| `byteplus-seedance-2-i2v` | 备用渠道 i2v |
| `seedance-2-pro-flf` | 有明确首尾帧时（锁构图） |
| `legacy-img2video` | **仅显式**；write-spec 打 WARN |

### Agent CLI（硬配方）

```bash
# 1) upload keyframe
"$AIFILM" frw upload --file-path "keyframes/shot0N.png" --category image

# 2) Seedance I2V（禁止 frw img2video）
"$AIFILM" frw newvideo \
  --model seedance-2-fast-i2v \
  --img-url "<url>" \
  --prompt "@Image1 <motion… subject stays centered, full head headroom>" \
  --aspect-ratio 9:16 \
  --resolution 720p \
  --duration 5 \
  --wait --poll-timeout 600

# 3) 下载 video_url → reencode（禁止放大）→ register
"$AIFILM" register-clip … --source-endpoint frw_seedance_i2v \
  --review-note "provider=frw model=seedance-2-fast-i2v res=720p identity_lock_ok"
```

首尾帧（有 tail）：

```bash
"$AIFILM" frw newvideo \
  --model seedance-2-pro-flf \
  --img1 "<head-url>" --img2 "<tail-url>" \
  --prompt "@Image1 @Image2 continuous mid-action …" \
  --aspect-ratio 9:16 --resolution 1080p --duration 5 --wait
# register: --source-endpoint frw_seedance_flf
```

### 查询

```bash
"$AIFILM" frw newvideo-query --task-id <id> --wait
```

---

## 质量硬纪律（agent 不可跳）

1. **禁止**默认 `frw img2video` / template `348771…`。  
2. **禁止** 576 生成再 scale 到 720「当高清」。reencode 只 clean codec，**不升分辨率**。  
3. **静帧同源**：全片 still 同一 provider（推荐 Grok cast 锚）；禁止 Codex 定妆 + Grok still + FRW 动 混身份而不对照。  
4. **continue 缝**：下镜 I2V **只**吃 promote 字节 keyframe；禁止 edit 成「新姿势」再假装接戏。  
5. **时长真相**：Seedance `duration` 与 film-spec `duration_sec` 对齐（5/6/10）；不够就加镜，不靠 loop。  
6. **HF 工程路径**：避免空格路径（`AI FILM SPACE`）；失败时拷到 `/tmp/...` 再 compose-render。  
7. **双字幕**：按 **shot_id** 绑 `nar`/`nar_en`，禁止 SRT 碎句乱贴 EN。  
8. **pilot 质量门**：3 镜 Seedance 人审 fail → 不 bulk。

---

## register endpoint 对照

| endpoint | 含义 |
|----------|------|
| `frw_seedance_i2v` | newvideo seedance/byteplus i2v（推荐） |
| `frw_seedance_flf` | newvideo flf |
| `frw_newvideo` | 其它 NEW_VIDEO 模板 |
| `frw_img2video` | **legacy** 旧模板（不推荐） |
| `image_to_video` | Grok 兜底 |

---

## 与旧文档关系

| 文档 | 变更 |
|------|------|
| [frw-degrade-dispatch.md](frw-degrade-dispatch.md) | FRW-first **升级为 Seedance-first** |
| [lessons-2026-07-20-frw-2v-first.md](lessons-2026-07-20-frw-2v-first.md) | 仍有效；2V 命令改为 newvideo |
| 本文 | 质量事故 + Seedance 默认 |

## 403 无权使用该模板（男娘片 2026-07-20 · 全量 key 矩阵 2026-07-21）

账号对 `seedance-*` / `byteplus-seedance-*` 返回 **403 无权使用该模板** 时：

| 做 | 不做 |
|----|------|
| 先 canary：`balance` + Seedance 一枪 + `ltx-t2v` | 当参数错无限重试 |
| 先试 **`ltx-i2v`**（`width/height` **string** `720`/`1280`） | 默认退 **legacy img2video 576** 并当高质量 |
| LTX i2v **502** → `i2v_provider: grok` + Imagine Video **720p** | 假装「已用 Seedance」 |
| Grok 也不可用且**必须** FRW → **显式** `legacy-img2video` + WARN + `frw_img2video` 账本 | 静默用 legacy 写 `model=seedance` |
| 写 `receipts/frw-key-capability.json` / `seedance-blocked-*.json` | 用 403 旧 clip 冒充质量版 |
| 权限开通后 **重烤** Seedance | |

空镜用 **`ltx-t2v`**（跨 key 多次 **201→completed**，比 LTX i2v 稳）。  
经典 `text2video` / `img2video` / `first-last-frame` 在「Seedance 全 403」样本 key 上 **能 completed**，但是**质量地板 / 救生艇**，不是默认 bulk。  

完整能力矩阵：[lessons-2026-07-21-frw-key-capability.md](lessons-2026-07-21-frw-key-capability.md)。  
参数：[lessons-2026-07-20-frw-ltx-probe.md](lessons-2026-07-20-frw-ltx-probe.md)。

## 不可宣称

- 用了 FRW = 用了 Seedance  
- reencode 放大 = 高清  
- 33s 七段旧 I2V = 60s 成片  
- Grok fallback 720p = Seedance（须在账本写明 fallback）  

## 验证

```bash
# write-spec 后 film-spec 应含 frw_video_model=seedance-2-fast-i2v
"$AIFILM" frw newvideo --model seedance-2-fast-i2v --help   # via frw help
# register-clip 接受 frw_seedance_i2v
```
