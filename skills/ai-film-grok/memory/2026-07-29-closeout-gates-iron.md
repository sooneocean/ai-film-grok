# Memory · 成片收尾门禁 IRON（P0 · 2026-07-29 · 后面不要再犯）

> 用户：「推进到最后」→ 收尾；「把这些经验写回去」；**「GO」**；**「把教训回写就可以收工」**
> 片例：`AI FILM SPACE/0729/chaebol-cast-rule-max` · **`0729/e-virus-ch04-shelter`（DELIVERED_GO · 体位运镜返工）**
> 完整课：[lessons-2026-07-29-closeout-gates-chaebol](../references/lessons-2026-07-29-closeout-gates-chaebol.md)

## 一句话

**有 plate ≠ 收尾完。** 必须：heat final → sensory → motion gate → truth_contract → 字幕切镜 → 叙事证据 → 清 quality 缓存 → review-final → post-audit → export-desktop。

## 后面不要再犯（16 条）

| # | 坑 | 铁律 |
|---|---|---|
| 1 | S:100 仍 hard_fail | 看 `codes`；`SEX_BOTH_UNDRESS_UNSTATED` → 写 `partner_wardrobe_state` |
| 2 | adult sensory 失败 | sound_plan `sex_sfx` + mix `artifacts` hash + AV alignment≥90 |
| 3 | clips 全 approved 仍 incomplete | 改 film-spec 后刷 `truth_contract.contract_sha256` |
| 4 | pilot 假绿 | 字段 `approved_by=user`；短语进白名单（`做完`…）；禁 agent 自拟 |
| 5 | still 假齐 | `frame_chain_seed` ≠ approved |
| 6 | 字幕跨切 | timeline/film_timeline = **真 concat 钟**；cue 不跨 hard boundary |
| 7 | quality 冻帧缓存 | 改 final 后 **删** `out/quality-report.json` |
| 8 | narrative hash stale | 改 final 后 **重绑 media_sha256**（可只刷 hash，勿乱改 planned shot_ids） |
| 9 | post_engine 打架 | register 标签 = post-plan owner |
| 10 | motion --rows | **JSON 文件路径**，禁内联超长 |
| 11 | 简化 final | 允许 amix+PIL，但 delivery **PARTIAL** 写 honest_limits |
| 12 | bare 冒充 | Imagine 拦 → 双轨暗示 PARTIAL，禁内衣装插入 |
| 13 | **手拼 6s plate 与旧 timeline 双钟**（ch04 GO） | `receipts/film_timeline.json` + `timeline.json` 的 `shot_starts` **必须=片上槽位**（如 0,6,12…）；旧 VO 钟（7.6s/11s…）→ `SUBTITLE_CROSSES_HARD_CUT` 挡 review-final |
| 14 | **SRT 与 duration 不一致** | plate 几秒一镜，`film-spec.duration_sec` 与 SRT 同槽；`sub_lead=0`；cue 止于切点前 ≥40ms |
| 15 | **SIZE_LADDER 挡 GO** | act 禁回宽 ≥2 档（`SIZE_LADDER_ACT_REOPEN`）；禁连续 3 镜同 rank（`SIZE_STACK_FLAT`）；纸面 `shot_size` 可调，**像素体位差**另见 shot-variety |
| 16 | **export 链漏步** | `review-final` 绿后 → **`post-audit`（delivery_ready）** → 才 `export-desktop --force`；跳过 post-audit 必「evidence changed」 |

## 收尾最小序

```text
heat check →（手拼 plate 则先写齐 film_timeline/timeline=片上钟）
→ register-final → narrative 重绑 media_sha256 / validate
→ rm quality-report → review-final (11维+watched_full+screening dim@sec:note)
→ post-audit (delivery_ready) → export-desktop --force
→ 抽帧：字幕可见才算完（无 libass 用 burn_srt_pil）
```

## ch04 GO 实证（2026-07-29 晚）

- 状态：**DELIVERED_GO** · `final_complete`+`desktop_exported`
- 路径：`out/film_final.mp4` · `~/Desktop/e-virus-ch04-shelter/`
- 中文 **PIL 硬烧** 14 cue；体位/运镜返工见 [shot-variety-anti-boring](2026-07-29-shot-variety-anti-boring.md)
- 诚实 PARTIAL：软词亲密 ≠ 真 bare 插入

## 关联

- bulk→plate：[evirus-ch04-bulk-final-iron](2026-07-29-evirus-ch04-bulk-final-iron.md)
- 体位/特写/运镜：[shot-variety-anti-boring](2026-07-29-shot-variety-anti-boring.md)
- 高动桌面门：[07-27 high-motion](2026-07-27-high-motion-style-final.md)
- 毒镜：[poison-shot-anatomy-iron](2026-07-29-poison-shot-anatomy-iron.md)
