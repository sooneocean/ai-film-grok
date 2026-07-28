# 教训 · 先低分辨率提速，够用再升画质（2026-07-28）

## 用户原话要点
- **可以先低分辨率来加快速度** — 很好的技巧
- **请记忆起来**
- **先压；质量够后再去提升画质也可以**

## 铁律
1. **Bulk / 通片优先墙钟时间**：I2V 默认先 **低压**（如 480×832 9:16、turbo 4-step），不默认 720/1080 吃满 5090。
2. **先齐 30 镜可剪可审**，再挑 hero/肉戏/定器做 **二轮升画质**（更高 res、adult-motion 20-step、或 topaz/Comfy upscale）。
3. **不要**在未通片前为「单镜更清」拖慢整批。
4. 升画质只针对：**selects 通过的镜 / 成片可见硬伤 / 用户点名**。

## 本集默认（ch04 shelter）
| 阶段 | 设置 |
|---|---|
| 通片 bulk | Wan `official+turbo` · **480×832** · 3–4s · bare KF 源 |
| 二轮（可选） | 同 still 再跑 720×1280 或 adult-motion quality；或输出后 upscale |
| 静帧 | 仍 720×1280 keyframe（I2V 输入可压；源图可保留高） |

## 工程挂钩
- `scripts/batch_bare_still_i2v.py` → `I2V_W/H=480/832` · `I2V_TURBO=True`
- 卡 Comfy → SSH 自启（`lessons-comfy-ssh-self-restart`）
- 单卡禁止双开 Wan 当真并行

## 类比
先用草稿笔画完整分镜，再上色精修关键帧 — 不是第一笔就 8K。
