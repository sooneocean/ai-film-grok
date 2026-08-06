# 混合火力 · API × 本地（2026-07-28 强化 · **2026-08-03 H3 更新**）

> **2026-08-03**：本地动作主武器由退役的 Wan 2.2 I2V 换为 **MiniMax H3**（`comfy-h3` · T2V/I2V/R2V pilot 均已 canary）。  
> **2026-08-04**：效果最大化实机课 → [lessons-2026-08-04-h3-max-effect.md](lessons-2026-08-04-h3-max-effect.md)（I2V 锁脸 · R2V 高动/大嘴 · T2V 无脸 · 续镜末帧 · free-memory）。  
> 配置：`AIFILM_I2V_PROFILE=hybrid_h3` 或片级 `h3.enabled=true`。云 bulk 仍默认 Grok；敏感/肉戏 soft-lock H3。  
> 成片默认 `h3.audio_policy=prefer_native`（H3 立体声可用则直接用；不可用或显式 strip 才 Edge TTS + rnb）。  
> **工作流入口**：`aifilm h3 list|plan|run --register`（非仅 armory canary）。


## 用户原话
还有 Grok Imagine、FRW API；**API 与本地交叉使用可以迸发更大力量** — 请思考。

## 武器全表（不是二选一，是编队）

### A. 本地 5090（Comfy）
| 能力 | 用途 | 成本/墙钟 |
|---|---|---|
| Qwen Image Edit i2i | bare 补图、卸装不回穿、pose 改 | 免费 · 中速 |
| **MiniMax H3 I2V**（`minimax-h3-i2v-pilot`） | 人物/肉戏/敏感 I2V（pilot） | 免费 · 中速 |
| **MiniMax H3 T2V** | 本地环境/气氛（可与 FRW 并行策略择一） | 免费 · 中速 |
| MiniMax H3 R2V | 多 ref 锁脸/风格（ref2va pilot 已 canary） | 免费 · 较慢 |
| **Real-ESRGAN formal upscale**（research→formal） | selects 后抬清晰度（默认 off） | 免费；见 [realesrgan-formal-upscale](realesrgan-formal-upscale.md) |

**独占理由**：尺度、无审核、无限重试、脸+衣着可控。

### B. Grok Imagine API（xAI）
| 能力 | 用途 | 边界 |
|---|---|---|
| `image_gen` / image | 概念、环境板、非审核敏感仍 | 成人 bare 常拦 |
| `image_edit` | 轻改构图/光（脸锁时仍优先 cast/已批 still） | bare 易拦 |
| `video` / **video-1.5** I2V | **非露人物**、轻动作、推镜 | bare/办事 moderated；有 rps 限 |
| TTS（可选） | 备胎；本集中文口白仍 edge | — |

**独占理由**：云端并行、不等 5090 队列、迭代概念快。

### C. FRW API
| 能力 | 用途 | 边界 |
|---|---|---|
| text2image / img2image (qwen 等) | 静帧双打、场景 still | endpoint 曾 404 |
| **text2video / ltx-t2v** | **L2 环境/空镜/桥接** | 不锁脸 |
| img2video / seedance / newvideo | 人物救生艇 / 技术失败切换 | 勿默认 bulk 换 Seedance |
| first-last-frame | 转场两端帧 | — |
| video-continue / compose | 长段拼接 | 积分 |
| upload / merge | 资产回传 | — |

**独占理由**：场景 T2V 不占 GPU；与本地/Grok **真正时间重叠**。

---

## 交叉原则（最大力量）

1. **同一像素责任只认一个 owner**
   - 脸+衣着状态：本地 still 链为真相
   - 环境空气：FRW T2V 可独立
   - 勿「Grok 出一张露胸 + Wan 动一下」却无 undress-anchor

2. **API 负责宽度，本地负责深度**
   - API：多镜并行、场景、试拍、非敏感
   - 本地：尺度、一致性、通片主角、二轮质量

3. **先压后升对所有车道生效**
   - Grok/FRW 也先 480p / 短时长
   - selects 后再 720 / quality / upscale

4. **失败退路写死**
   - Grok moderated → 不重试烧钱 → 落 5090
   - FRW 404/积分 → 本地 Wan 环境镜降级（远景/弱人物）
   - 本地挂 → SSH 自启；仍挂 → Grok 非露顶一阵
   - H3 OOM → free-memory；降 mp/duration；单 client

5. **时间重叠 > 单引擎极限**
   ```
   t0  本地：bare i2i 批
       FRW：env T2V 全扔队列
       Grok：setup 非露 I2V（限流内 1–2 并发）
       本机：TTS/BGM
   t1  本地：H3 肉戏 I2V 串行（≤8s · draft mp0.2）
       FRW：query 回收 env
       Grok：query 回收
   t2  人工/门禁：衣着连贯 + 运动门
   t3  二轮：本地 quality 只升 selects
   t4  final
   ```

---

## 镜头 → 编队（决策表）

| 镜头语义 | 首选编队 | 交叉补强 |
|---|---|---|
| 主角近景 / 表情 / 露乳 | 本地 still → **H3 I2V** | Grok 禁；FRW 仅补空镜垫 |
| 办事 / 定器 / climax | 本地 only（**comfy-h3**） | — |
| setup 未露 / 走路推镜 | Grok 1.5 I2V | 失败→H3 I2V pilot |
| 墙外、灯、白板、实验室空气 | FRW T2V | 本地做一张 style still 作文字锚（可选） |
| 转场 A→B | FRW FLF 或 本地 last→next still + **H3 I2V** | 禁 60s 超长一镜占卡 |
| 静帧尺度抬升 | 本地 Qwen **主** + FRW i2i **并行 A/B** | 择优（dual-lane 已定） |
| 概念分镜/look | Grok image 快扫 | 定妆后锁本地 cast |

---

## 「迸发更大力量」的具体增益

| 只本地 | API×本地交叉 |
|---|---|
| 30 镜全压 5090 串行 | 肉戏 20 镜本地 + 环境 5 镜 FRW 并行 + 轻 5 镜 Grok 并行 |
| 墙钟 ≈ 人物镜之和 | 墙钟 ≈ **max(肉戏本地, 云任务)** |
| 场景也吃 VRAM | 场景卸出 GPU → 肉戏更快轮转 |
| 审核一刀切 | 敏感只走本地，干净走云 |

---

## 本集落地优先级

1. **5090 继续肉戏 turbo 通片**（主路径不中断）
2. **FRW endpoint 修好** → 立刻抽 env/bridge 用 T2V 并行补
3. **Grok Imagine**：仅非露/轻镜；**image** 可做下集 look，不代替 undress-anchor
4. **静帧 dual-lane**：5090 Qwen + FRW qwen i2i（修好后）
5. TTS 已本地完成，final 时混 rnb

## 军规一句话
**本地守尺度与身份；Grok Imagine 抢轻量并行；FRW 抢场景与静帧双打——交叉的是时间与职责，不是同一镜三家各画一张脸。**
