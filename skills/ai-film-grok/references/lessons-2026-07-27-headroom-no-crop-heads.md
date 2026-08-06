# 禁裁头 + 竖屏肉戏构图（P0 · 2026-07-27）

**用户**：「人头被裁掉了 请思考全面」

## 1. 现象

- 定器/结合特写 still：脸被裁掉或白条挡脸（误把「特写」做成无头尸身）。
- 竖屏 9:16 抬抱/缠腰全身：头与脚争像素 → 模型或 `scale…increase,crop=720:1280` **优先切头顶**。
- I2V 末帧漂移：推近/仰角把发顶顶出画。
- 成片中近景：只剩半头或无头顶安全边。

## 2. 根因分层（全面）

| 层 | 失败模式 | 为何发生 |
|----|----------|----------|
| **A 意图写错** | prompt 写 `faces out of frame` / `midsection only` 当主镜 | 定器特写 ≠ 砍主角身份；观众要认人 |
| **B 景别冲突** | 既要「全头」又要「定器」又要「全身」同镜 | 9:16 像素不够，必须 **分镜** 不能一锅炖 |
| **C 出图** | image_edit 自动上移构图填肉 | 未写死 headroom / full head |
| **D 转码** | `force_original_aspect_ratio=increase,crop=720:1280` 中心裁 | 横图/偏高主体时切顶 |
| **E I2V** | push-in / 晃动 / 抬腿 | 无 `locked headroom` 约束 |
| **F 审核软化** | 为躲 bare 改大特写 | 用裁头换尺度 → 双重失败 |

## 3. 硬规则

1. **主戏镜（hero / 有台词 / 有身份）**：**双方完整头 + 头顶安全边（headroom）**；发顶不得贴框或出框。  
2. **裁脚优先于裁头**：竖屏全身不够时，**可裁脚/小腿**，**禁裁头**。  
3. **定器特写**两种合法做法（二选一，禁止第三种砍头主镜）：  
   - **合法 A · 同镜双锁**：中近景 **脸在上 1/3 + 腰腹结合在下 2/3**，双方头完整；  
   - **合法 B · 短切 insert**：1–2s **纯肢体/结合 insert**，且 **前后镜必须有全头主镜**，insert 不承担认人；  
   - **非法**：白条挡脸、无头胴体当 10s 主镜、`faces out of frame` 写进 hero still。  
4. **双人拥抱/抬抱**：构图写死  
   `full heads both characters, ample headroom, shoulders inside frame; prefer crop feet over crop heads; vertical 9:16 medium-full`。  
5. **打包**：优先 `scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2` 保全身；仅当黑边不可接受且主体已验 headroom 才 center-crop。  
6. **验收**：register still / 成片抽帧 — 主戏镜头顶可见安全边；出现 `HEAD_CROP` 不得交付。

## 4. 与尺度/肉戏的关系

- **尺度 MAX + 脱尽 + 定器** 仍优先，但 **不得用砍头换尺度**。  
- 定器成立 = 结合部可读 **且** 身份可认（同镜双锁或 insert+全头主镜）。  
- 审核拦 bare 时：降的是衣着像素，**不是** headroom。

## 5. Prompt 强制尾缀（hero）

```text
FRAMING LOCK: full head of every on-screen lead, ample headroom above hair,
both shoulders inside frame; do not crop skulls or chins; if vertical space is
tight crop lower legs/feet instead of heads; 9:16 safe framing.
```

## 6. 码

| 码 | 含义 |
|----|------|
| `HEAD_CROP` | 主戏镜头顶/整头出画 |
| `HEAD_CROP_DETAIL_AS_HERO` | 无头 insert 被当主镜时长过长 |
| `HEADROOM_MISS` | 无安全边（发顶贴框） |
| `PACK_CROP_TOP` | 转码 center-crop 切顶 |

## 7. ep3 现场

- `ep01_sc08_detail_union_lock`：非法砍头（已记教训，须重做合法 A 或降为短 insert）。  
- sc08 抬抱 still：头大致在框内，但打包/I2V 需继续锁 headroom。  
- 成片 ~85s 中近景：头顶偏紧，后续 I2V/重装须拉远。
