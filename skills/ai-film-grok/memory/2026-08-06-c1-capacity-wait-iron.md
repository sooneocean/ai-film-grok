# C1 capacity-wait IRON · 2026-08-06

## 原话
go c1 然后一路修完 · 有独占 5090 → N2 / C1 until-empty

## 三句
1. `--capacity-wait-sec` hard max 抬到可长等；idle free + heartbeat + P1 轮转已 ship。
2. **真烧闭合**：suse-evolution-ep01 独占 `--until-empty --execute --free-first --i-own-the-gpu` → **`stop_reason=queue_empty`**。
3. 进度只认 **takes 文件数**（91→103）；pending 可假高；free-first 不 cancel 外片。

## 清单
- [x] hard max 8h · idle free · heartbeat · P1 rotate · L4 fix · contention map
- [x] velvet 半程 canary（历史）
- [x] **suse `queue_empty`** · canary `artifacts/2026-08-06-c1-until-empty-suse-ep01-canary.json`
- [x] 片根回执 `receipts/fill-idle-until-empty.json`

## 人下一步
- `aifilm h3 pk-compare` · shortlist promote（须人）· ship-prep

## 链
- `media/h3_fill_idle.py` · hard-defaults 多 agent no-hog
- film: `AI FILM SPACE/0805/suse-evolution-ep01`
