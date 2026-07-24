# Lesson 2026-07-22 · 先验后生 · 算力放在刀口上（Verify Before Generate）

> **已晋升**：本规则已整合进稳定文档 [production-discipline.md](production-discipline.md) §先验后生。
> 此 lesson 保留为踩坑历史记录，新代码/文档请引用稳定版本。

> **触发原话**（续 EP01 压缩 still 案）：
> 「对的验证完再生成视频 图片也是一样逻辑 这样才能把算力放在刀口上 重复生成的成本过高 请写入教训」
> **P 码**：**P0 工序/成本** · Visualize → Generate
> **互补**：
> - [keyframe-no-compress](lessons-2026-07-22-keyframe-no-compress.md) → 几何/压缩硬指标
> - [keyframe-first-frame-poison](lessons-2026-07-21-keyframe-first-frame-poison.md) → 结构/解剖
> - [consistency.md](consistency.md) · pilot 批准  

---

## 一句话

```text
验证通过 → 才烧下一级算力
坏输入上的生成 = 双倍烧钱（错一次 + 重做一次）
```

| 层级 | 便宜 | 贵 | 规则 |
|---|---|---|---|
| 静帧 still | 单次 image_edit / image_gen | 错 still 后整批重出 | **出图后先验**（几何+身份+结构）再入库 |
| I2V 视频 | 在已过闸 keyframe 上串行 1 镜 | 坏 still 上 bulk 30 段 I2V | **keyframe 全过闸才 claim/video** |
| final 成片 | 选片 + 混音 | 30 镜糊片拼完再发现 | **selects 人审/门禁过再 final** |

**算力刀口** = 正确输入上的一次成功生成；不是「先堆数量再碰运气」。

---

## 失败解剖

| 用户感受 | 工程事实 | 根因 |
|---|---|---|
| 影片是压缩态 | I2V 吃了缩水/横图 still | **未先验 WxH/画幅就 video** |
| 整集要重做 | bulk 已烧完 | **跳过 still QA 直接队列** |
| 图片也糊 | 在坏 ref 上再 edit | **未先验 ref/cast 就 image_edit 批量** |

成本公式（量级）：

```text
重做代价 ≈ (坏输入次数) × (下游单价)
I2V 单价 ≫ still 单价 ≫ 本地 ffprobe/读图
→ 多花 1 秒验图，省一次 6s I2V 额度
```

---

## 硬规则（V0–V7 · 先验后生）

| # | 规则 | 适用范围 |
|---|---|---|
| **V0** | **先验后生**：任一下游生成前，上游资产必须过闸；**禁止**「先生成、后补验」当默认 | 图 + 视频 |
| **V1** | **静帧出库前验**：`image_gen` / `image_edit` / OAuth image 落盘后 → **立即** `analyze_still_geometry` + 目视身份/结构（或 pilot 三镜）→ 过才 `register-still approved` / 写入 keyframes 真源 | **图片** |
| **V2** | **I2V 前验 keyframe**：`pick_best_keyframe` + geometry ok +（结构清单 F1–F2）→ 才 `image_to_video` / `grok-oauth video` / queue claim | **视频** |
| **V3** | **坏了只修上游**：几何/身份/结构 fail → **停下游**；重出 still 或 `image_edit` 修帧；**禁止**对坏 still 重试 I2V「碰运气」 | 两者 |
| **V4** | **批量前 canary**：bulk ≥4 镜前，至少 **1 镜 still 全闸 + 1 镜 I2V 人审**（pilot 可并）；canary fail → 禁 bulk | 两者 |
| **V5** | **算力优先级**：修 1 张坏 still ＞ 盲跑 10 段 I2V；token/额度报告里 **重做次数** 视为事故 | 工序 |
| **V6** | **同 stem 择优再烧**：有 png/jpg 双份时先验再选；**禁止**未比较就吃第一个扫到的小 jpg | 图→视频 |
| **V7** | **失败收据**：几何/身份 fail 写 `receipts/` 一句原因；requeue 须注明「已换全分辨率 still」 | 可追溯 |

### 图片链路（与视频同逻辑）

```text
ref/cast 过闸
  → image_edit / image_gen
  → 【停】读图：分辨率 · 画幅 · 脸/发/服 · 解剖 · 无水印
  → pass → register-still / 进 lookbook / 作下一级 ref
  → fail → 只修图，不进 I2V、不进 bulk edit
```

### 视频链路

```text
keyframe 过闸（V1 已过）
  → 【停】再确认 pick_best_keyframe + geometry
  → image_to_video 串行 1 件
  → 【停】抽 t=0 / motion；structure 继承
  → pass → register-clip
  → fail → 改 still 或 re-I2V 同一过闸输入，不换缩略图
```

---

## Agent 操作清单（每镜）

```text
[ ] 出图后：PIL/ffprobe 读 WxH（9:16 ≥720×1280）
[ ] 读图：身份 · 发色 · 结构 · 无 shot 水印
[ ] geometry fail / 结构 fail → STOP，不 I2V
[ ] 仅 pass 的 path 进入 media-queue / oauth video
[ ] bulk 前：canary 1 still + 1 I2V 过
[ ] 禁止：未验 30 张 still 就开 30 路 I2V
[ ] 禁止：审核失败后用更糊预览图重试
```

---

## 反例 / 正例

| 反例（烧钱） | 正例（刀口） |
|---|---|
| 30 张 still 未读尺寸就串行 I2V | 先脚本扫 geometry，只对 pass 队列 |
| 横图 jpg 失败后换同图再 video 三次 | 先重出 720×1280 竖屏 still 一次 I2V |
| 坏 cast 上 bulk 20 张 edit | 先 lock-style + pilot 3 镜过再 bulk |
| final 拼完发现 1/3 糊 | selects 前每镜 t=0 抽检 |

---

## 与代码/门禁挂载

| 挂载点 | 作用 |
|---|---|
| `analyze_still_geometry` · `pick_best_keyframe` | 静帧几何先验 |
| `register-still approved` | 未过几何 → 拒注册 |
| `preflight` `KEYFRAME_COMPRESS_OR_ASPECT` | final/ bulk 前硬拦 |
| pilot approve | 人审 canary（V4） |
| 本课 V0–V7 | **工序纪律**：agent 行为，不单是函数 |

Agent **不得**用「赶工期」跳过 V0–V2。用户说「一路做完」仍须 **每镜先验**；只是不反复停问，不是不验。

---

## 验收

- [ ] 任意 I2V 的 `--image` 路径：geometry ok  
- [ ] bulk 收据里无「先 fail 后换小图」轨迹  
- [ ] 重做原因可归因到「上游未先验」（事故）vs「模型随机」（可接受重试 1 次）  

**完成定义**：下游烧算力时，上游已有可展示的验证证据（geometry 回执 / pilot / 读图笔记），不是「文件存在」。
