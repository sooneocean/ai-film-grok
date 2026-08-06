# 养分对账矩阵（教训 → 代码面 · 2026-08-06 N0）

**Purpose:** 一眼看出「已吞吐可废文」vs「半吞吐补默认」vs「真 OPEN」。  
**Authority:** hard-defaults + 代码 > memory > lesson。  
**Probe:** plugin.json **2.40.4** · LOC 本机 `wc` · memory active 归档后见 README。  
**执行板:** [next-optimization](2026-08-06-next-optimization-todoplan.md) Wave N · [monolith-relief](2026-08-06-monolith-relief-todoplan.md)

---

## 0. 内化阶梯（速查）

`lesson → memory 短卡 → hard-defaults → gate/receipt/CLI → pytest → stages 指针 → archive 废文`

| 阶 | 含义 |
|----|------|
| L3 | 机读能拦 |
| L4 | 默认路径必走 |
| L5 | 散文可 archive |

---

## 1. 已吞吐（L3–L4）· 禁重开工程 · 可 L5 废文

| 主题 | hard-defaults | 代码锚 | 测锚（代表） | memory 处置 |
|------|---------------|--------|--------------|-------------|
| 成人 MAX / sex 时长 / 卸装 | 表行 adult/sex/wardrobe | heat · sex_floor · wardrobe | `test_adult_*` · heat | **指针**；禁复写法条表 |
| 毒镜 anatomy | 毒镜行 | NEG/POS · promote 拦 | adult/poison 相关 | 指针 |
| 字幕硬烧 / caption_path | 字幕行 | post · caption-pixel · closeout | delivery / caption | stages 指针够用 |
| true-video | true-video 行 | `true_video_policy` | `test_true_video_policy` | 可瘦 |
| anti-hijack | 构图行 | `composition_anti_hijack` · shortlist/pk | `test_composition_anti_hijack` | 指针 |
| GPU no-hog | 多 agent 行 | h3 cycle flag | `test_h3_until_empty` | 指针 + OPEN_OPS 另列 |
| gate-auto | gate-auto 行 | `ensure_machine_lane` | gates / workflow | stages/deliver |
| final 诚实 A1–A5 | bulk→final / suse | sex floor · VO · plate · BGM | `test_suse_final_iron` · hotpath | deliver 清单；卡可瘦 |
| 零旁白 / speaker-frame | 零旁白行 | film_spec · speaker gate | zero_narration / speaker | 指针 |
| scale soft-max | 模型极限行 | `scale_fallback` | adult / scale | 指针；promote 半吞吐见 §2 |
| 时长目标 / crop-master | duration / crop 行 | duration_target · crop report | duration / ship-native | 指针 |
| 包边界 W0–W7 | — | packages + shims | `test_w3_package_shims` | plan CLOSED 指针 |
| film_spec M1 peel | — | facade + validate + constants | story/spec 相关 | **勿再报 film_spec=3147 单文件** |
| heat phase peel | — | `heat_phase.py` | heat 相关 | 结构 residual 在 relief |
| final watchdog peel | — | `final/watchdog.py` | hotpath | residual stages |
| lipsync 墓碑 | 对白原音 | v2.40 移除 | lipsync frozen | 勿复活 |
| H3 family apply | — | prompt family DSL | h3 相关 | **B 类 → archive 候选** |
| process-slim P0–5 | 文档分层 | stages 短 · max_refs | voice lesson 非 required | 仅 P6 deferred |

---

## 2. 半吞吐（有码 / 缺 L4 肌肉）

| ID | 缺口 | 下一步（Wave N1） |
|----|------|-------------------|
| H1 | plate≠master 人仍口头 DONE | closeout 字段强制；无 report 禁 final_complete 话术 |
| H2 | multi-seed 纪律 | shortlist/pk 无 anti-hijack → demote/next_cmd |
| H3 | material fidelity request | restricted 缺 receipt soft→hard |
| H4 | promote 硬冲 bare | SCALE_* 进 register fail-closed |
| H5 | aac≠可懂中文 | deliver 抽听；ASR deferred |
| H6 | 双片 drain 误杀 | 纪律 + 禁 pgrep 源码 |

---

## 3. 真 OPEN（≤10 · 唯一队列）

| ID | 项 | 类型 |
|----|-----|------|
| C1 | until-empty → queue_empty | OPEN_OPS |
| C9 | final/export/heat residual peel | structure · 挡路 |
| C3/C5 | 真片 final 诚实 / soft-max 压 | eng+ops |
| C10 | bare subprocess 触达 timeout | eng |
| C14 | throughput-counters | optional |
| C11–13 | job-graph / provider / process-slim P6 | deferred |

---

## 4. 代码巨石账实（N0.1 探针）

| 模块 | ~LOC | 状态一句话 |
|------|-----:|------------|
| `narrative/edit_policy_heat.py` | **3788** | phase 已 peel；wardrobe/coitus residual · bug-driven |
| `plan/film_spec_validate.py` | **3033** | M1 已拆门面；validate 仍厚 |
| `plan/film_spec.py` | **97** | facade only · **禁止**再写 3147 |
| `plan/story_plan.py` | **2992** | watch |
| `post/render_final.py` | **2979** | watchdog 已 peel；orchestrator residual |
| `post/export_composition.py` | **2804** | harness partial |
| `narrative/edit_policy.py` | **2584** | dual-owner 才 peel |
| `cli/cli_post.py` | **2477** | growth guard |
| `media/h3_fill_idle.py` | **2455** | capacity thrash 才 peel |
| `cli/cli_media.py` | **2172** | growth guard |
| `post/compose_render.py` | **1579** | harness residual |
| `aifilm_grok.py` hub | **999** | 健康 ≤2500 |

**版本账实：** `plugin.json` 当前 **2.40.4**；部分 plan 文案写 2.40.12——以 `plugin.json` + 本表 LOC 为准，发版再 bump。

---

## 5. 本轮 L5 消除（N0.2）

| 卡 | 原因 | 去向 |
|----|------|------|
| `2026-08-06-shortform-s5-open-ops` | 板末 canary，非法条 | `memory/archive/` |
| `2026-08-06-effect-board-film-ops` | 真片 session-wrap | archive |
| `2026-08-06-h3-prompt-system-family-apply` | 工程 B 已 ship | archive |
| `2026-08-06-ad-process-optimization` | 副导演 wave 结案卡 | archive（OPEN 进 session-index） |

**保留 active：** no-hog · dual-drain · wardrobe · suse-final · h3-native · anti-hijack · c1-capacity · tunnel-ensure · 经典 07-27/07-29 P0 指针集。

---

*N0 nutrient matrix · 随 archive / peel 更新本表，勿平行复制硬法条。*
