# H3 核心日课（一屏）

> **ACTIVE 工作流板**：[docs/plans/2026-08-06-h3-core-workflow-todoplan.md](../../../../docs/plans/2026-08-06-h3-core-workflow-todoplan.md)  
> Profile：**`h3_primary`** · 影=H3 · 图=Qwen/Grok 辅 · 声=原声 XOR Edge · 后=HF/gate-auto

## 角色

| 核心 | 辅 | 禁当主轨 |
|------|-----|----------|
| 5090 H3 I2V/FLF/R2V/T2V | Qwen still · Grok 定妆 · still-challenge · Edge · rnb · HF | Grok Video bulk · 后期对嘴 · Ken Burns |

## 12 步

1. `export AIFILM_I2V_PROFILE=h3_primary` · `doctor` · tunnel `18188→8188`
2. receive → debrief → 用户确认 promise
3. `plan run`：镜数 ≥ ceil(target/5.2) · 禁静默 duration=10
4. `write-spec`：确认 `_i2v_profile=h3_primary`
5. locks · state-index（undress/bare）· 一镜一 still
6. still 先验：身份/毒/几何/anti-hijack；弱 still 先修再烧
7. `pilot pack` 三看（构图/衣着/毒）→ **用户 GO** 才 bulk
8. `h3 capacity-plan` → **平日** `h3 run-next --execute --max 5`
9. **独占**（仅用户点名）：`cycle --until-empty --execute --i-own-the-gpu`
10. `ship-prep` · 人 PK（禁只比 mean）· promote preferred
11. `gate-auto` → `final`（门红=plate PARTIAL，禁假 master）
12. closeout 读 report · 每场抽听 1 句中文 · `review-final` 人签

## mode 一眼

| 条件 | mode |
|------|------|
| 有 end still / continue+last | **FLF** |
| 单 still 默认 | **I2V** |
| 高动 / 大嘴 / force_r2v | **R2V** |
| 无脸 env | **T2V** |


## prompt 方言（auto 默认）

| 方言 | 何时 | 形态 |
|------|------|------|
| **auto**（默认） | 未强制 env | 对白→official · high→legacy · 其他 official |
| **official** | `AIFILM_H3_PROMPT_DIALECT=official` | 三字段 / Ref2VA + `<d>[Mandarin]` |
| **legacy** | `…=legacy` 或 `prompt_format=timeline` | `[0s-2s] Primary action…` |

O3 canary：`skills/ai-film-grok/artifacts/2026-08-07-h3-official-ab-canary.json`（6/6 seed 20260807）。

## Fill-Idle（h3_primary 语义）

- **P0** = 缺 approved clip 的主生成（不是「挑战 Grok」）
- **P1** = 已有 take 但 mean/gate 失败 → 补烧
- **P2** = 仅 **`hybrid_h3`** 下挑战已有 Grok take；**h3_primary 无 Grok 铺底**
- 平日 max5 · 禁默认 until-empty · busy 零 submit

## 忙卡纪律

- `comfy queue` **running>0** → **零 submit**（禁 free-memory 打断他会话）
- capacity `VRAM_BELOW_FLOOR` 且 queue 空 → 再 `free-memory --confirm`
- 平日 max5；until-empty 仅用户点名独占 + `--i-own-the-gpu`

## 金句

```text
先验后生 · 脏 still 不烧 H3 · 忙卡零提交 · 门绿≠好看 · plate≠master · 原声 XOR TTS
```
