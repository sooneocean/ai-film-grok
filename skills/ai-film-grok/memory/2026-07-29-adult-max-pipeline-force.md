# Memory · 2026-07-29 成人尺度全链路强制拉满（Wave 1）

## 用户目标
整条生成链路把尺度 / 色气 / 成人指数强制顶格（解剖 IRON 不放行畸形）。

## 代码真相（plugin ≥2.17.3）

| 漏热 | 修法 |
|------|------|
| genre=adult 未钉 max | `normalize_story` + `select_beat_spine` → ADULT_MAX + extreme |
| sex_arc 字段缺 | plan 投影写 `sex_arc_beat` / coitus / wardrobe；lock→detail |
| 四拍时长可偏 | `SEX_ARC_RATIO_SKEW` + `SEX_ARC_RELEASE_RATIO_LOW` **warning→hard** |
| impact 只记分 | write-spec + review-final：**≥75 (A)** |
| 弱 VO 靠人改 | `apply_vo_spice_auto`（`sex_vo_auto_apply` 默认开） |
| state 缺口 soft | undress-anchor + undressed/bare **hard** on max |

## 逃生
`heat_scale:soft` · `adult_max_iron:false` · `erotic_impact_strict:false` · `sex_vo_auto_apply:false` · 各 `*_strict:false`

## Wave 2 已做（同日续）
| 项 | 入口 |
|----|------|
| plan 秒数预分配 | `rebalance_adult_beat_durations`；multi-scene compact 含 climax bare |
| soften-compensate | `aifilm heat soften-compensate --apply` |
| promote 回穿硬拦 | `promote_wardrobe_ok` / `should_auto_promote_next` |
| music_energy 跟 phase | `inject_music_energy_spotting` → sound_plan.music_spotting |
| pilot 三拍绑 bulk | `_assert_pilot_adult_three_beat`（undress + union/rhythm） |

## Wave 3 已做（同日）
| 项 | 入口 |
|----|------|
| impact S 冲分 | `aifilm heat boost [--apply] [--target-score 90]` · `suggest_impact_boost_actions` |
| 色气 6 项 | `lint_ecchi_checklist`；`heat check` 输出；`ecchi_checklist_strict:true` 才 hard |
| mute-frame advisory | 诚实列表 act/climax 须人工 `--score-coitus`（**无假 CV**） |

## Wave 4 已做（同日 · agent 回路）
| 项 | 入口 |
|----|------|
| dispatch 优先 heat-boost | `heat_agent_status` → next_action 插队 |
| next_actions | clips 前/final 前注入 heat boost |
| preflight max hard | duration/wardrobe/arc/impact&lt;A |
| write-spec 收据 | 自动 `receipts/heat-boost.json`；`auto_heat_boost:true` 才自动 patch |

## Wave 5 已做（同日 · fail-closed bulk）
| 项 | 入口 |
|----|------|
| media-queue 硬拦 | `assert_heat_allows_media` — `heat_agent_status.hard_fail` 时 `QueueError`（**不**被 `--allow-without-pilot` 绕过） |
| 逃生 | `AIFILM_SKIP_HEAT_QUEUE_GATE=1` |
| craft 露出 | `detect_craft_stage.heat` + blocker `heat_agent_hard_fail`；`next_hint` 优先 heat boost |
| dispatch/compact | packet.`heat`；`HEAT_AGENT_HARD_FAIL` attention + hard_gate_codes；primary 选 heat-boost 先于 bulk |

## Wave 6 已做（同日 · final 闭环 · **链路终点**）
| 项 | 入口 |
|----|------|
| `final_ok` | heat_agent：非 hard + 非 needs_boost（≥S 默认 90）+ field/arc ok |
| final 硬拦 | `assert_heat_allows_final` 绑 `aifilm final`（`--skip-heat-gate` / `AIFILM_SKIP_HEAT_FINAL_GATE=1`） |
| review-final | 同 gate，禁 A 档冒充 final_complete |
| export-desktop | 再验 heat final_ok，禁凉尺度出桌面 |
| compact | `HEAT_FINAL_NOT_OK` block attention |
| 分层 | **queue=A 硬拦**；**final/export=S 硬拦**（bulk 可 A+，成片必须 S） |

## 闭环状态
**plan → write-spec → pilot → bulk → final → review → export** 尺度只升不降已 fail-closed。  
刻意不做：真·肤色/暴露像素 CV（mute-frame 人眼保留）。
