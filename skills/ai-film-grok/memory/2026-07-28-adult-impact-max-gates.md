# Memory · 2026-07-28 色情冲击全闸（plugin 2.9.0）

## 用户目标
色情指数拉满：肉戏、抽插、脱光、定器特写、冲击力。

## 代码真相
| 项 | 行为 |
|----|------|
| max 默认 strict | `coitus` · `size_ladder` · `pose` · `montage` · `sex_arc` · `sex_detail_cu` · `both_undress` |
| 禁裸抱假绿 | `bare+act` 不算 penetration；须 hips-sink/thrust/union… |
| 合拍 | climax 相位 alone 不算射出；须 release 标记 |
| 定器 | `SEX_DETAIL_CU_MISSING` hard |
| 双方脱 | `partner_wardrobe_state`；弱则 `SEX_BOTH_UNDRESS_MISSING` |
| 报告 | heat check：四拍占比 + detail_cu + erotic impact 0–100 |
| pilot | undress / union(+detail) / rhythm |
| review | max act/climax approve 须 mute-frame coitus≥4 |
| 模板 | `film-spec.adult-max.example.json` 真办事序列，impact=S |

## 逃生
各 `*_strict:false` 或 `adult_max_iron:false` / `heat_scale:soft`。

## 未做（诚实）
- 真·像素 CV 肤色连通仅为后续可选项（本版用字段+Mute Frame）
- `test_automation_verify` runtime_lock 与本改无关的既有环境依赖
