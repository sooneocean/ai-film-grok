# 养分对账矩阵（教训 → 代码面 · 2026-08-07 E* 刷新）

**Purpose:** 一眼看出「已吞吐可废文」vs「半吞吐补默认」vs「真 OPEN」。  
**Authority:** hard-defaults + 代码 > memory > lesson。  
**Probe:** plugin.json **2.40.99** · memory active **≤40 (F5)** · I0–I5/R0–R5 CLOSED · **E1–E5 + F4/F5 ship**。  
**执行板:** [CTO](2026-08-06-cto-optimization-todoplan.md) · **[铁律内化](2026-08-07-iron-internalization-todoplan.md)**（I0–I5 CLOSED）· 事故内化 E*（本表 §2b）

---

## 0. 内化阶梯（速查）

`lesson → memory 短卡 → hard-defaults → gate/receipt/CLI → pytest → stages 指针 → archive 废文`

| 阶 | 含义 |
|----|------|
| L3 | 机读能拦 |
| L4 | 默认路径必走 |
| L5 | 散文可 archive |

**新 IRON 五问卡**（只 C 类进队列）：见 [MEMORY_GOVERNANCE](../MEMORY_GOVERNANCE.md) § Iron internalization。

---

## 1. 已吞吐（L3–L4）· 禁重开工程 · 可 L5 废文

| 主题 | hard-defaults | 代码锚 | 测锚（代表） | memory 处置 |
|------|---------------|--------|--------------|-------------|
| 成人 MAX / sex 时长 / 卸装字段 | adult/sex/wardrobe | heat · sex_floor · wardrobe | `test_adult_*` · heat | **指针**；禁复写法条 |
| 毒镜 prompt + 人证闸 | 毒镜行 | NEG/POS · anatomy_safe 路径 | anatomy / poison | 指针；**像素 CV 仍半吞吐 H-pixel** |
| 字幕硬烧 / caption_path | 字幕行 | post · caption-pixel · closeout | delivery / caption | stages 指针 |
| true-video | true-video 行 | `true_video_policy` | `test_true_video_policy` | 可瘦 |
| anti-hijack **工具** | 构图行 | `composition_anti_hijack` · shortlist/pk | `test_composition_anti_hijack` | 指针；**全入口 L4 见 H-anti** |
| GPU until-empty 独占 | 多 agent 行 | `--i-own-the-gpu` · h3 cycle | `test_h3_until_empty` · no-hog | 指针 + OPEN_OPS |
| gate-auto | gate-auto 行 | `ensure_machine_lane` | gates / workflow | stages/deliver |
| final 诚实 A1–A5 | bulk→final / suse | sex floor · VO · plate · BGM | `test_suse_final_iron` | deliver 清单 |
| plate≠master 机读 | suse / closeout | closeout + export-desktop | closeout / plate 测 | **H1 已 ship** |
| 零旁白 | 零旁白行 | film_spec.zero_narration_gate | zero_narration | 指针 |
| scale soft-max 策略 | 模型极限行 | `scale_fallback` SCALE_* | scale 系 | 指针；**promote 链 H-scale** |
| 时长目标 / crop-master | duration / crop | duration_target · crop report | duration / ship-native | 指针 |
| 原声 XOR TTS | 对白原音行 | native_audio · render_final | native 测 | 指针 |
| 包边界 W0–W7 | — | packages + shims | `test_w3_package_shims` | plan CLOSED |
| film_spec facade | — | facade ~101 + validate | story/spec | **禁**写 3147 单文件 |
| heat peel 族 | — | heat_*.py 叶 + edit_policy_heat facade | heat 相关 | residual 在 edit_policy |
| lipsync 墓碑 | 对白原音 | v2.40 移除 | lipsync frozen | 勿复活 |
| process-slim P0–5 | 文档分层 | stages · max_refs | — | P6 deferred |

---

## 2. 半吞吐（有码 / 缺 L4 肌肉）· I0 对齐铁律内化

| ID | 缺口 | L 现状 | 内化波次 | 下一步 |
|----|------|--------|----------|--------|
| ~~H1~~ | plate≠master 口头 DONE | → **L4** | — | ✅ closeout + export 机读 |
| ~~H2~~ | multi-seed shortlist 纪律 | → **L3+** | I1.1 | ✅ promote fail-closed；**全入口**仍 I1.1 |
| ~~H-material~~ | restricted 缺 generation_request | → **L4 hard** | I2.4 | ✅ assert_generation_request_for_i2v |
| ~~H4~~ | promote 硬冲 bare | → **L3+** | I1.5 residual | nested ban 已有 |
| H-listen (H5) | aac≠可懂中文 | L2 人抽听 | deferred | ASR 后置 |
| H-dual (H6) | 双片 drain | 纪律 | **I5** OPEN_OPS | — |
| ~~H-pixel-poison~~ | 缺/毒 attestation | → **L4 人证** | I2.1 | ✅ |
| ~~H-endframe~~ | 末帧不回穿 | → **L3 启发式** | I2.2 | ✅ endframe_wardrobe |
| ~~H-variety-pixel~~ | 改 spec 假绿 | → **L4** | I1.2 | ✅ |
| ~~H-plate-boring~~ | mean≪20 + mix 假死 | → **L4** | I1.3+I1.4 | ✅ plate + default broadband |
| ~~H-anti-hijack-all~~ | multi-seed | → **L4** | I1.1 | ✅ |
| ~~H-speaker~~ | speaker soft | → **L4** | I2.3 | ✅ |
| H-scale-chain | scale ban 全入口 | L3+ residual | 触达 | — |
| H-run-next-hog | 软 hog | ops | **I5** | OPEN_OPS |
| ~~H-context-blind~~ | dispatch 盲 | → **L3** | I3 | ✅ stages 瘦 + routing |

### 2b. 2026-08-07 事故内化（E*）

| ID | 主题 | L 现状 | 代码锚 | 测 |
|----|------|--------|--------|-----|
| **E1** | 身份代际锁 / 禁 archive 混 final | **L3–L4** | `gates/identity_generation_lock.py` · closeout step | `test_error_internalization_e1_e4` |
| **E2** | 配角/男主 cast_master+face_lock | **L3** | `gates/partner_cast_gate.py` | 同上 |
| **E3** | 原声轻处理默认（消双真相） | **L4 文** | hard-defaults 行改轻处理 | 契约/死链测 |
| **E4** | 禁半帧复合 still | **L3** | `gates/still_provenance.py` · h3_workflow | 同上 |
| **E5** | H3 mode override 收据 | **L3** | `h3_workflow.record_h3_mode_override` | `test_h3_mode_override_e5` |
| **F4** | hard-defaults memory 死链 | **L3 测** | F4 测含 archive 回落 | `test_error_internalization_e1_e4` |
| **F5** | memory active ≤40 | **L5** | archive 21 卡 + soft-cap 测 | 同上 |
| **E6.3** | SKIP IRON 清单扩 + 热路径 skip_flag | **L3+** | `IRON_SKIP_FLAGS` 扩；热路径已接 | residual = except 回落 |

---

## 3. 真 OPEN（≤10 · 与 CTO §5 同集 · 内化子集加粗）

| ID | 项 | 类型 |
|----|-----|------|
| CTO-1 | gates 静默 except → fail-closed | eng P0 |
| CTO-2 | final/hotpath + plate≠master 永不回退 | eng P0 |
| ~~I1*~~ | 假绿 anti-hijack/variety/plate/mix | **SHIPPED 2.40.51** |
| ~~I2*~~ | 人证 anatomy/speaker/material/endframe | **SHIPPED 2.40.51** |
| CTO-5 | 5090 drain 或 OPEN_OPS | ops P0 · I5 |
| CTO-6 | 触达式 peel final/validate/preflight | structure P1 |
| ~~I3~~ | stages 瘦 + routing | **SHIPPED** |
| ~~I4.1~~ | hard-defaults 契约测 | **SHIPPED** |
| CTO-12 | throughput-counters / provider 429 | deferred |
| H-listen | aac 可懂中文 ASR | deferred |
| ~~E5~~ | H3 mode override 收据 | **SHIP 2.40.99** |
| E6.3 residual | except 路径仍可读裸 env | low · 触达式 |

**明确 DEFERRED：** 真 CV 毒镜分类器、Job-graph 超 final、lipsync 复活、markdown→AST 全表 parser、虚荣 LOC。

---

## 4. 代码巨石账实（I0.1 探针 · 2026-08-07）

| 模块 | ~LOC | 状态一句话 |
|------|-----:|------------|
| `post/render_final.py` | **3057** | orchestrator residual · 挡路 peel |
| `plan/story_plan.py` | **2992** | watch |
| `media/h3_fill_idle.py` | **2745** | capacity thrash 才 peel |
| `narrative/edit_policy.py` | **2587** | dual-owner 才 peel |
| `post/export_composition.py` | **2573** | harness residual |
| `cli/cli_post.py` | **2499** | growth guard |
| `plan/film_spec_validate.py` | **2429** | M1 facade 外仍厚 |
| `cli/cli_media.py` | **2182** | growth guard |
| `post/compose_render.py` | **1579** | harness residual |
| heat 叶合计 (`heat_*.py`) | **~5.4k** | 已 peel 成多文件；facade `edit_policy_heat` **136** |
| `plan/film_spec.py` | **101** | facade only |
| `aifilm_grok.py` hub | **1004** | 健康 ≤2500 |

**版本账实：** `plugin.json` = **2.40.48**。旧文写 2.40.4 / 2.40.12 以本表 + json 为准。

---

## 5. L5 废文策略（持续）

| 处置 | 条件 |
|------|------|
| **指针化** | 已 L4 且 hard-defaults 有表行 → memory 只留三句+链 |
| **archive** | canary / session-wrap / 已 ship 工程卡 | 进 `memory/archive/` |
| **保留 active** | 半吞吐 H* 对应卡 + no-hog · dual-drain · wardrobe · suse-final · plate-boring · poison · variety · anti-hijack |

---

*I0 nutrient matrix · 随 I1–I5 / archive 更新本表，勿平行复制硬法条。*
