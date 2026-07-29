# Lesson · 毒镜 · 解剖畸形 / 乳汁 / Comfy 批跑（P0 · 2026-07-29）

> **后面不要再犯。** 已挂：`hard-defaults` · `SKILL.md` §9b · `Agents.md` §5b · `memory/2026-07-29-poison-shot-anatomy-iron.md`

晋升自 ch4 避难所：`receipts/lessons-anatomy-milk-futa-fix.md` + batch 备忘。

## 用户信号
「性器官跟乳汁这些都有很多问题」→ **立即**停交付毒 preview，开 anatomy pass。
**尺度 MAX ≠ 畸形 MAX。**

## 解剖 IRON（像素）
1. **禁止**：futa / 女体阴茎 / 泌乳喷奶 / 霓虹生殖器符号 / 错装回穿冒充插入
2. **要求**：两性分明；女仅女器、男仅男器；乳头干燥（汗 OK，奶禁止）
3. **提示**：中英双写 NEG；POS 写死 `penis only on the man, DELETE any penis on the woman`；`dry nipples`
4. **流程**：archive 毒 clip/still → i2i 解剖安全 → I2V → 抽帧复核再 register
5. **门**：毒 still **禁 I2V**；毒 clip **禁 register / promote / final**

弱 i2i 常残留 futa：**不要**只靠 soft negative；须显式 DELETE + 中文「扶他/喷奶/母乳」。

## Comfy 5090 批跑 IRON
1. `aifilm comfy free-memory … --confirm` — 无 confirm 等于没卸
2. 单卡串行；Wan 进行时禁 ACE/lipsync/第二任务抢卡
3. `wait_capacity` + submit 失败 3 次 retry；幽灵 busy → clear queue
4. 隧道：`127.0.0.1:18188`（aifilm 拒裸 HTTP LAN）
5. `register-still` timeout ≥300s
6. **fix 失败退出码不得 `set -e` 杀死 bulk**（`go_fix_then_bulk` 用 `set +e`）
7. 吞吐：通片 single-seed；毒镜再 multi-seed
8. 结构：先全 i2i 再全 I2V（减 Qwen↔Wan 来回）

## 交付
毒 partial 可给人看进度，**禁止**当 final。通片后 endframe 审 → ACE rnb BGM → 字幕硬烧。

## 关联
- memory: `memory/2026-07-29-evirus-ch04-comfy-anatomy-batch.md`
- wardrobe no-redress / adult-max sex-arc / high-motion style-lock
