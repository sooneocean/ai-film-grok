# Memory · 成片收尾门禁 IRON（P0 · 2026-07-29 · 后面不要再犯）

> 用户：「推进到最后」→ 收尾；「把这些经验写回去」  
> 片例：`AI FILM SPACE/0729/chaebol-cast-rule-max`  
> 完整课：[lessons-2026-07-29-closeout-gates-chaebol](../references/lessons-2026-07-29-closeout-gates-chaebol.md)

## 一句话

**有 plate ≠ 收尾完。** 必须：heat final → sensory → motion gate → truth_contract → 字幕切镜 → 叙事证据 → 清 quality 缓存 → review-final → post-audit → export-desktop。

## 后面不要再犯（12 条）

| # | 坑 | 铁律 |
|---|---|---|
| 1 | S:100 仍 hard_fail | 看 `codes`；`SEX_BOTH_UNDRESS_UNSTATED` → 写 `partner_wardrobe_state` |
| 2 | adult sensory 失败 | sound_plan `sex_sfx` + mix `artifacts` hash + AV alignment≥90 |
| 3 | clips 全 approved 仍 incomplete | 改 film-spec 后刷 `truth_contract.contract_sha256` |
| 4 | pilot 假绿 | 字段 `approved_by=user`；短语进白名单（`做完`…）；禁 agent 自拟 |
| 5 | still 假齐 | `frame_chain_seed` ≠ approved |
| 6 | 字幕跨切 | timeline/film_timeline = **真 concat 钟**；cue 不跨 hard boundary |
| 7 | quality 冻帧缓存 | 改 final 后 **删** `out/quality-report.json` |
| 8 | narrative hash stale | 改 final 后 **重 record** 三点 evidence |
| 9 | post_engine 打架 | register 标签 = post-plan owner |
| 10 | motion --rows | **JSON 文件路径**，禁内联超长 |
| 11 | 简化 final | 允许 amix+PIL，但 delivery **PARTIAL** 写 honest_limits |
| 12 | bare 冒充 | Imagine 拦 → 双轨暗示 PARTIAL，禁内衣装插入 |

## 收尾最小序

```text
heat check → post-plan init → i2v-motion-gate --write (rows=file)
→ register-final → narrative record/validate
→ rm quality-report → review-final (11维+watched_full+screening)
→ post-audit (delivery_ready) → export-desktop --force
```

## 关联

- bulk→plate：[evirus-ch04-bulk-final-iron](2026-07-29-evirus-ch04-bulk-final-iron.md)
- 高动桌面门：[07-27 high-motion](2026-07-27-high-motion-style-final.md)
- 毒镜：[poison-shot-anatomy-iron](2026-07-29-poison-shot-anatomy-iron.md)
