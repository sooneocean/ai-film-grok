# Lesson 2026-07-22 · 静帧压缩/错幅 = 整段 I2V 糊（Keyframe No Compress）

> **片例**：`vivian-ep01-rain-first`（薇薇安·夜啼01）  
> **用户原话**：「有几个片段图片被压缩 导致生成的影片也是压缩状态生成的 这个教训请记忆 不要再犯 写入 plugins,skills」  
> **P 码**：**P0 可交付** · P1 画质 · Visualize → Generate  
> **互补**：[keyframe-first-frame-poison](lessons-2026-07-21-keyframe-first-frame-poison.md)（结构坏）· 本课（**分辨率/压缩/画幅坏**）· [verify-before-generate](lessons-2026-07-22-verify-before-generate.md)（**先验后生·算力刀口**）

---

## 现象

- 成片里若干镜「像被压糊 / 像横图被硬塞竖屏 / 细节糊成一坨」。  
- 不是 xfade 问题，也不是 VO——**毒源在 I2V 输入 still（keyframe）本身已糊或画幅错**。  
- 本片实证：`keyframes/shot30.jpg` = **1152×864 横图**，同时 `shot30.png` 才是 **720×1280** 竖屏；若 I2V 吃了 jpg → 整段按压缩横图生成。

## 根因（铁律）

```text
I2V 首帧 ≈ keyframe 文件字节真相
keyframe 分辨率低 / 横图 / 重 JPEG 压糊
  → 模型只能在糊画上「演」6s
  → 整 clip 永远是压缩态，后期无法救
```

| 失败链 | 说明 |
|---|---|
| 会话 `image_edit` / OAuth 出图后 **未校验 WxH** | 偶发横图/错幅仍写入 `keyframes/` |
| **优先 `.jpg` 小图** 覆盖同 stem 的高清 `.png` | bulk 脚本 `shotXX.jpg` 存在就用，无视更大 png |
| register-still 只看「有文件 + identity」 | **未做几何/画质 QA** |
| I2V 后 motion 可过门 | 糊像素也在动 → **QA 漏检画质** |

**抽象**：`motion_ok` ≠ `geometry_ok` ≠ `sharp_enough`。能动但横图/缩水 = **仍 fail**。

---

## 硬规则（C0–C7 · 静帧几何门）

| # | 规则 |
|---|---|
| **C0** | **交付分辨率**：竖屏 9:16 片默认 keyframe **≥ 720×1280**（宽≥720 且 高≥1280）。不足 = **禁 I2V / 禁 register approved** |
| **C1** | **画幅锁**：9:16 片要求 `width/height` 在 **0.50–0.62**（约 9:16）；横图/方图硬 fail（码 `KEYFRAME_ASPECT`） |
| **C2** | **禁用缩水图做 I2V**：禁止把预览缩略图、会话压缩附件、低于 C0 的导图直接当 `keyframes/shotXX` |
| **C3** | **同 stem 择优**：`shotXX.png` 与 `.jpg` 并存时，I2V/register **优先更高分辨率且过 C0/C1 的文件**；禁止默认「先扫到 jpg 就用」 |
| **C4** | **register-still 硬闸**：`approved` 前跑 `analyze_still_geometry`；fail → 拒注册 |
| **C5** | **I2V 前硬停**：geometry fail 的 still → **禁止** `image_to_video` / OAuth video / queue claim |
| **C6** | **promote 末帧必须 PNG 全像素**：`extract-frame --promote-keyframe` 写 **png**；禁止把 promote 结果再压成低质 jpg 再 I2V |
| **C7** | **成片抽检**：final 后任镜 t≈0 糊/错幅 → 该镜 **重出 still（全分辨率）→ re-I2V**，不得只 re-final |

### 软建议（不挡 hard，但写进 checklist）

- 文件体积极小（如 9:16 720p jpg ≪ 80KB）→ soft warn `KEYFRAME_BYTES_LOW`，目视是否块状糊。  
- bulk 静帧优先存 **png 或高质量 jpg（q≥90）**；勿二次 `sips`/预览导出缩小。  
- OAuth `image-edit --aspect 9:16` 后 **立即 `identify`/PIL 读 WxH**，不对就重出，不入库。

---

## Agent 操作清单

```text
写入 keyframes/ 后、register-still / I2V 前：
  [ ] 读图宽高：9:16 → ≥720×1280
  [ ] 宽高比 ≈ 0.5625（允许 0.50–0.62）
  [ ] 同 stem 有 png 时：比 jpg 更大/更对则用 png
  [ ] 横图/缩略图 → 丢弃，重生成
  [ ] 【先验后生】以上未全过 → 禁止 image_to_video（算力刀口）

register-still --status approved：
  [ ] analyze_still_geometry 过
  [ ] 与 F1–F2 结构 QA 并列（本课 + first-frame-poison）

I2V：
  [ ] --image / --input = 过闸 keyframe 路径（全分辨率）
  [ ] 失败重试不得换用更小预览图
  [ ] 图片侧同理：ref 未验不 bulk image_edit
```

## 反例 / 正例

| 反例 | 正例 |
|---|---|
| `shot30.jpg` 1152×864 横图直接 I2V | 用 `shot30.png` 720×1280 或重出竖屏 still |
| bulk 脚本 `if jpg exists use jpg` | 选 max(w×h) 且过 C0/C1 的候选 |
| 会话附件缩略图拷进 keyframes | 仅用 OAuth/Imagine 出图原件 |
| 为省盘把 keyframe 压到 50KB | 保留 ≥ 交付分辨率；成片后再说归档压缩 |

## 代码挂载

- `media_qa.analyze_still_geometry` · 码 `KEYFRAME_TOO_SMALL` / `KEYFRAME_ASPECT` / soft `KEYFRAME_BYTES_LOW`  
- `aifilm register-still`：approved 前硬 fail  
- `aifilm preflight`：扫 film-spec 镜的 keyframe，不过 hard  
- 选型：`media_qa.pick_best_keyframe(root, shot_id)`

## 与既有规则

- 不替代 [首帧毒化](lessons-2026-07-21-keyframe-first-frame-poison.md)（结构）——本课管 **几何/压缩**  
- 与 [consistency.md](consistency.md) §1e 并列  
- I2V 路径见 [i2v-grok-primary.md](i2v-grok-primary.md)

## 本片修复动作（EP01）

1. 审计 `keyframes/shot*.{jpg,png}`：错幅/低分 → 重出  
2. I2V 输入统一走 `pick_best_keyframe`  
3. 坏镜 re-I2V + re-register + 必要时 re-final  
