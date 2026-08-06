# P0 · 静帧不得跨镜复用（2026-07-29 · btc-vessel-ep02）

## 现象
成片「好几个画面都是重复的」：剪辑节奏上像同一姿势连播，观众读成 loop / 偷懒镜。

## 根因（本片实证）
| 共用 still sha（前缀） | 镜 |
|---|---|
| `dab12c40…` | `sc07_bt01` + `sc07_bt03` + `sc08_bt02`（**3 镜同图**） |
| `47996d6c…` | `sc06_bt03` + `sc09_bt01` |
| `9c6489f4…` | `sc09_bt02` + `sc11_bt03` |

- 文件名不同（`keyframes/<shot_id>.png`），**像素 sha 相同** = 复制粘贴 / 同图 register。
- I2V 输出文件 sha **互不相同** → 现有 `clip_uniqueness`（视频指纹）**放行**。
- 同 still 起的 I2V 运动路径极像 → 肉眼 = 重复画面。
- 次因：plate 把 6s 源 fit 到 2.4–5s，相似构图更「连着跳」。

**不是** `stream_loop` 双播（本片 stretch `loops=0`）。

## 铁律
1. **一镜一静帧（byte-unique）**：`approved` still 的 `sha256` 不得与其它 `shot_id` 的 approved still 相同。
2. **禁止** `cp keyframes/A.png keyframes/B.png` / 硬链 / 同图多 register。
3. 连续亲密弧也要 **换景别·换相位·换机位**：前戏 / 插入 / 抽送 / 高潮 / 余韵 各有独立 still（可 `image_edit` 上一镜，**不得**零改复制）。
4. `register-still --status approved` 撞 sha → **硬失败**（`still_uniqueness`）。
5. `stills_complete` 依赖 still uniqueness；仅 clip 唯一不算过门。

## Agent 操作
- bulk 前：`python`/`status` 看 `still_uniqueness` / 本课；或扫 `keyframes/*.png` sha 分组。
- 撞车：保留叙事最早一镜，其余 **重画 still → 重 I2V → re-register-clip**，再 final。
- 续集：`state-index` / promote 只锁**下一镜首帧**，promote 后须确认与上一镜 still **非同一 sha**（若 promote 结果与上一镜仍同 sha，说明末帧≈首帧，须 edit 出相位差再 register）。

## 验收
- 任意两 approved still：`sha256` 不同。
- 成片抽帧 contact：相邻亲密镜构图可读差异（景别或相位至少变一维）。
- `aifilm status`：`still_uniqueness.ok == true` 且 `stills_complete`。

## 本片返工清单（若用户要重出）
| 保留 | 重做 still + I2V |
|---|---|
| `ep01_sc07_bt01_sh01` | `ep01_sc07_bt03_sh01`, `ep01_sc08_bt02_sh01` |
| `ep01_sc06_bt03_sh01` | `ep01_sc09_bt01_sh01` |
| `ep01_sc09_bt02_sh01` | `ep01_sc11_bt03_sh01` |
