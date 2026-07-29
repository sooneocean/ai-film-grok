# Memory · 2026-07-29 E病毒 ch4 避难所 · Comfy 5090 批跑 + 解剖铁律

片例：`AI FILM SPACE/0728/e-virus-ch04-shelter`（adult-max IRON，bare/露乳常态）

## 一句话
5090 单卡串行 + `free-memory --confirm` + 解剖硬 NEG/POS；修毒镜失败**不得**挡住 bulk；register 超时抬到 300s。

## 资源塔（Comfy 5090）
| 现象 | 根因 | 操作 |
|------|------|------|
| `VRAM_BELOW_FLOOR` / `RAM_BELOW_FLOOR` | Wan/i2i 卸不干净或竞态 | `aifilm comfy free-memory --base-url $URL --confirm`（**必须 --confirm**） |
| `COMFY_QUEUE_BUSY` 但 free 高 | 幽灵队列 | interrupt + clear queue；`wait_capacity` 后再 submit |
| free 显示 32GB 仍被拦 | 提交瞬间竞态 | 脚本内 retry 3 次 + 每次 free |
| SSH 隧道 | aifilm **禁纯 HTTP LAN** | `AIFILM_COMFYUI_BASE_URL=http://127.0.0.1:18188` → 远程 **`8188` only**（**禁 8189**；401=`unauthorized` 多半指错端口，见 [tunnel-8188](../references/lessons-2026-07-29-comfy-tunnel-8188-not-8189.md)） |

**铁律**：不要与 Wan 并行占 5090（ACE-Step BGM / lipsync / 第二 Comfy 任务互斥）。先通片 480 turbo，再升。

## 解剖毒点（用户：「性器官跟乳汁很多问题」）
| 镜 | 毒 |
|----|-----|
| sc02_bt03 | 女体长阴茎 futa |
| sc02_bt04 / sc03_bt02 | 乳汁滴/流 |
| sc04_bt01 | 霓虹阴茎符号、衣着错 |

**NEG 硬禁（中英双写）**：lactation / breast milk / milk streams / futa / hermaphrodite / penis on woman / neon dick glyph / 扶他 / 喷奶 / 母乳
**POS**：女仅女器、男仅男器；乳头**干燥**（可汗禁奶）；`penis only on man / DELETE penis on woman`
流程：毒镜 → `clips/_archive_anatomy_poison` → Qwen i2i（解剖安全）→ Wan turbo → register
脚本：`film/scripts/fix_anatomy_shots.py` · `batch_bare_still_i2v.py` · `go_fix_then_bulk.sh`（`set +e`，fix 失败仍 bulk）

## 批跑脚本教训
1. `go_fix_then_bulk`：**禁止** `set -e` 因 fix 退出码 2 杀死 bulk
2. `register-still` 默认 120s 不够 → **300s**
3. 多 seed 解剖重试吞吐差 → 通片用 **single-seed**；毒镜再 multi
4. 进度：`receipts/anatomy_fix/progress.json` + `go.log`
5. 结构优化（下一批）：**先全量 i2i 再全量 I2V**，减模型来回加载

## 衣着 / IRON（本片叠加）
- 卸装不回穿；bare keyframe 链；有毒穿衣图归档 `_archive_clothed_*`
- 口白中文 Edge / 角色日文 Edge / 字幕中文
- BGM：`audio/bgm/rnb-primary-ace-step.wav`（ACE-Step rnb，vol≈0.56）
- 毒 preview 不交付；final 见 `receipts/next-final-runbook.md`

## 完成定义（本片）
30/30 clip → endframe 审 futa/奶/回穿 → `i2v-final-gate` → final + 硬烧字幕；不是 partial preview。
