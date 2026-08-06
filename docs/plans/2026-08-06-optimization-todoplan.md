# ai-film-grok 优化迭代 Todo Plan（2026-08-06 综合）

**结论先行：** 产线「规则硬 + 包边界拆完」阶段已过；下一轮不该再开绿地 IRON / 虚荣 LOC 冲刺，而应 **(1) 锁死 08-06 正牌 final 实坑 (2) 运维把 5090 until-empty 烧穿 (3) 按出片风险做叶拆与热路径诚实**。

**Status:** ACTIVE · Wave **A1–A5 + B + D1 SHIPPED** (2.39.77–79) · **C1 OPEN_OPS** (capacity busy)  
**Repo:** `/Users/dex/.grok/plugins/ai-film-grok` · plugin **2.39.79**  
**依据：** memory 08-06 · strategy/AF/opt residual · residual-monolith · 本机探针（LOC / closeout / film_spec auto-extend）

---

## 0. 类比（文科一眼）

仓库像 **已装消防规范、分车间的片厂**：  
- 再写规章收益小；  
- 宿色 EP01 证明 **出片时仍会在「槽长 / 口白窗 / 假绿 final」上翻车**——这是下一轮真正该修的「夜班事故」；  
- 大石拆包像 **把布景搬到分库房**——包边界已搬完，库房里仍有大木箱（orchestrator），只在挡路时再拆。

---

## 1. 现状地图（SHIPPED vs 真残余）

### 1.1 已完成（禁止当绿野重开）

| 轨道 | 证据 | 状态 |
|------|------|------|
| ROI A–E · Workflow A–H+W8 | `docs/plans/2026-08-03-*` | **CLOSED / SHIPPED** |
| Opt W0–2/4/5 · Material Fidelity M0–M6 | optimization + material plans | **SHIPPED** |
| Strategy S0–S7 勾选项 | strategy §5 几乎全 [x] | **代码/文档面基本完** |
| AF1–AF6/AF8 核心 | closeout 已串 `post_doctor`；tts-partial；handoff partial；fill-idle timeout | **SHIPPED** |
| Module W0–W7 包边界 | `core/post/narrative/audio/media/plan/cli…` + shims | **SHIPPED** |
| Routing rewire R0–R7 | CHANGELOG 2.39.74–75 | **SHIPPED** |
| 产品 IRON（成人 MAX / 毒镜 / 不回穿 / h3_primary / 字幕硬烧 / 防抢走） | hard-defaults + 08-06 memory | **法条在**；执行有缺口见下 |

### 1.2 本机探针（2026-08-06）

| 项 | 数值 / 观察 |
|----|-------------|
| hub `aifilm_grok.py` | **~1017** LOC（≤2500） |
| `post/render_final.py` | **~2710**（叶拆后仍厚 orchestrator） |
| `narrative/edit_policy_heat.py` | **~4026**（bug-driven 才拆） |
| `plan/film_spec.py` | **~3176**（含 act/climax **静默拉 10s**） |
| `post/export_composition.py` | **~2804** |
| `media/h3_fill_idle.py` | **~2002** |
| bare `subprocess.*`（scripts excl util） | **~150** |
| closeout × post_doctor | **已接线**（AF3 不再是 gap） |
| media_queue handoff | 有 `media-queue-partial`；仍有多处 `except Exception` 需审计 |

### 1.3 08-06 生产事故（最高优先级信号）

片根：`AI FILM SPACE/0805/suse-evolution-ep01` · plate ~154s · `OFFICIAL_FINAL_PLATE`（非 master-lock）

| 坑 | 根因（代码/流程） | 用户可见 |
|----|------------------|----------|
| final 假成功 | shim 只换 module 不调 main（**已修**） | 1s 绿、无 TTS |
| 槽位爆炸 | validate 遇 `HEAT_SEX_DURATION_LOW` → act/climax `duration_sec=max(10,…)`；H3 源 ~5.2s + forbid_loop → 可 stretch ≤~5.9 | stretch 炸 / 假办事时长 |
| 口白窗三角 | TTS 实测 > cue 或 cue 超 slot；atempo 在检查后才压 | VO 溢出 |
| rnb 无 wav | assets 仅 license | 须 procedural |
| gate-auto 红 | five_track / motion / variety | 诚实 plate ≠ final_complete |
| 衣着 | 不回穿 + 全裸诱惑 + **模型极限勿硬上** 已入 hard-defaults | 仍需机读/promote 兜底验 |

`film_spec.py` 仍在：

```python
# HEAT_SEX_DURATION_LOW → 静默
sh["duration_sec"] = max(10.0, float(...))
```

这与「槽位认源、禁空改 duration」直接冲突 → **P0 工程债**。

---

## 2. 优化原则（铁律）

1. **不重开** ROI / Workflow / h3_primary 主实现 / 包边界搬家。  
2. **不**静默改 heat / pilot GO / `i2v_provider`。  
3. **不**虚荣「全员 <1500 行」。  
4. 行为变更与大搬迁 **分 commit**。  
5. DONE = 测绿 +（若 CLI/指纹）`make check-all` + 必要时 `lock-runtime` + 英文 commit。  
6. 出片：`final`≠`final_complete`；plate 可 PARTIAL；master 须 gate-auto 绿。  
7. 圣旨：短令 `go` = 按本 plan 当前 P0 链推进，不重开辩论。

---

## 3. 双镜头目标

### 导演（craft / 吞吐）

- 提高 **首过可交片率**（closeout 绿、少 re-final）  
- 降低 still / I2V **废片率**（fidelity · 毒镜 · 不回穿 · 防抢走）  
- 5090 **有用烧满率**（until-empty → `queue_empty`）  
- 成人弧 **稳帧优先于虚高 MAX 标签**（模型极限阶梯）

### 工程（structure / 诚实）

- 正牌 final 路径 **不可假绿**（shim + 槽长 + 口白窗）  
- 热路径 **有超时、有 PARTIAL 回执**  
- 巨石 **只在挡修 bug 时 peel**  
- 文档 / plan 状态与 origin **帐实一致**

---

## 4. 优先 Todo（可勾选 · 建议执行序）

### Wave A · 正牌 Final IRON 机读化（P0 · 来自宿色 EP01）

> 对应 memory：`2026-08-06-suse-ep01-official-final-iron`  
> Owner 域：`plan/film_spec` · `post/render_final` · gates · tests

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **A1** | **禁 validate 静默把 act/climax 拉到 10s 而不管片源** | `HEAT_SEX_DURATION_LOW` 时：优先 **fail + 明确 next**（加镜 / 降 `sex_min_duration_ratio` / 重 I2V 更长）；若保留 auto-extend，须 **受 media 实测时长 cap**（ffprobe take 或 `max_stretch_sec`），写 receipt `honest_limits` | 单测：短 H3 源 + low ratio → **不**产出不可 stretch 的 10s 槽；宿色类 fixture 不炸 stretch |
| **A2** | **口白窗三角机检** | final/preflight：`tts_dur ≤ cue.duration ≤ slot`；失败给 `vo_rate` / 砍 spoken 建议，**禁止**只拉长 cue 超 slot | 单测 + 宿色回归清单项绿 |
| **A3** | **shim / CLI 入口契约测** | `python render_final.py` 与 `aifilm final` 必须进入真正 TTS/stretch 路径（防再 1s 假绿） | `test_final_hotpath` 或新测：mock 断言 main 被调 |
| **A4** | **rnb 无 wav → procedural 默认诚实** | 无 licensed wav 时自动 procedural + receipt；有 wav 才 `--music` | final 有 aac；`receipts/*` 标 BGM 来源 |
| **A5** | **plate vs master 交付语义** | skip gate / gate-auto 红 → 强制 `OFFICIAL_FINAL_PLATE` / PARTIAL，禁文案写成 master-lock | closeout / delivery 字段测 |

**不做：** 为了绿 gate 静默降 heat、假五轨、blind promote。

---

### Wave B · 衣着阶梯机读闭环（P0 · 08-06 圣旨）

> memory：`2026-08-06-wardrobe-no-redress-fullnude-fallback` · hard-defaults 已有表行

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **B1** | **审计现有码是否覆盖「模型极限勿硬上」** | 扫 promote / heat / still_source：崩坏·毒镜·连续 fail → 须 **停 + PARTIAL 档**，禁止继续加 bare 词硬刷 | 表：码 ↔ 路径；缺则补 |
| **B2** | **soft-max / implied-bare 诚实档** | delivery / heat report 可标实际 wardrobe 档（undressed / implied-bare / soft-max），非口头 | 单测 + 一份 receipt schema |
| **B3** | **plan 单调衣着** | write-spec clamp 已有则加「后镜回穿」回归测；缺则补 | `HEAT_WARDROBE_RE_DRESS` 硬测 |

**默认：** 文档已够则只补 **缺口测 + promote 停手**；勿重写 adult playbook。

---

### Wave C · 运维吞吐（P0 ops · 等人+GPU）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **C1** | **真片 until-empty drain → `queue_empty`** | 5090 idle + pilot GO：`capacity-plan` → `h3 cycle --until-empty --execute --free-first [--capacity-wait-sec]` | `fill-idle-until-empty.json` stop∈{queue_empty,max_cycles}；takes 文件数↑；memory 短卡 |
| **C2** | **多 job 连烧诚实** | 确认 free-first 不杀 foreign；contention recover 路径再压一轮 | canary JSON 入 `artifacts/` |
| **C3** | **（可选）指标收据** | 片根计数：still scrap / I2V scrap / re-final 次数（strategy D0） | 一个 `receipts/throughput-counters.json` 即可，勿新 IRON 段 |

**阻塞：** 无空闲 5090 则标 **OPEN_OPS**，不装代码未完成。

---

### Wave D · 反脆弱残余清扫（P1 eng）

AF 主项多已 ship；清扫「探针时代的尾巴」：

| ID | Todo | 验收 |
|----|------|------|
| **D1** | media_queue 残余 `except Exception` 审计 → warning / partial，禁 silent pass（完成侧已有 AF2，扫 claim/reclaim 等） | rg 清单 + 行为测 |
| **D2** | bare subprocess 热路径：compose_preview / speech_preview / 抽帧 再收一波 timeout（全仓 150 处不冲刺） | 触达文件带 timeout；过夜路径无无限 hang |
| **D3** | until-empty + identity soft-skip 回归保持绿 | `pytest -k h3_until_empty` |
| **D4** | doctor 对「假 plate 当 master」advisory | doctor 文案或 soft code |

---

### Wave E · 结构叶拆（P1–P2 · 风险驱动）

沿 [residual-monolith-w4-todo](../../docs/plans/2026-08-05-residual-monolith-w4-todo.md)，**只在修 A/B/D 碰到文件时 peel**：

| 序 | 模块 | ~LOC | 触发条件 |
|----|------|-----:|----------|
| E1 | `post/render_final` orchestrator | ~2710 | A2–A4 改动跨多段 |
| E2 | `plan/film_spec` validate vs projectors | ~3176 | **A1 必碰** → 趁机把 auto-extend 抽 `film_spec_sex_floor.py` 之类纯函数 + 测 |
| E3 | `export_composition` / `compose_render` | ~2.8k / 1.6k | 字幕/双烧 bug 或 coverage 门 |
| E4 | `edit_policy_heat` packs | ~4026 | **仅** heat 码 bug |
| E5 | `h3_fill_idle` | ~2002 | 过夜 hang / capacity 逻辑再变 |

Iron：public CLI 字符串不变；shim hard-compat；每 peel 独测。

---

### Wave F · 导演工艺（P1 process · 少写代码）

| ID | Todo | 说明 |
|----|------|------|
| **F1** | design-go one-pager 出片前必存在 | 已有 CLI；纪律：pilot 前检查 receipt |
| **F2** | multi-seed 强制 `anti-hijack` | 禁只比 mean/音量；记忆 08-05 |
| **F3** | 对白主链：Grok/H3 原音优先 | 禁后期对嘴复活 |
| **F4** | gate-auto 后人审只做 pilot / PK / review-final | 减 thrash |

---

### Wave G · 文档与账实（P2 · 便宜）

| ID | Todo |
|----|------|
| **G1** | 本 plan 确认后写入 `docs/plans/2026-08-06-optimization-todoplan.md`，strategy/opt 旧档 header 指过来 |
| **G2** | residual-monolith / module-refactor LOC 数字刷新为本机 2.39.76 |
| **G3** | AF plan 状态：标 AF3/closeout 等已 ship，避免 agent 按旧 probe 重做 |
| **G4** | 宿色检查单链到 stages/post + deliver（短指针） |

---

## 5. 建议执行序（缺资源时）

```text
A1 槽位认源（最高杠杆）
 → A2 口白窗 → A3 shim 契约测 → A5 plate 语义
 → B1–B3 衣着阶梯（可与 A 并行读代码）
 → C1 5090 drain（等人）
 → D 清扫 → E 仅顺手 peel → F 纪律 → G 落档
```

**默认 `go` 最小链：** A1 → A2 单测绿 → commit →（有 GPU）C1。

---

## 6. 明确非目标

- 自动批 pilot / 静默降 heat / 静默换 provider  
- 全自动毒镜 CV 完美识别  
- 全仓 subprocess / FilmError 大扫除  
- 一切模块压到 1500 行  
- 用 FRW/ltx23 取代 h3_primary 默认  
- 把 plate 红 gate 刷成假 master  
- 重写 references 全书 / 删 lesson  

---

## 7. 成功定义（本迭代结束时）

| 标准 | 达成 |
|------|------|
| 短 H3 源片 validate+final 不再被静默 10s 拉爆 | A1 绿 |
| 口白溢出可机读拦截 | A2 绿 |
| final 入口不可 1s 假成功 | A3 绿 |
| 衣着阶梯有码+测或审计证明已覆盖 | B* |
| 至少一次真实 `queue_empty` 或诚实 OPEN_OPS 记录 | C1 |
| 无新 IRON 散文；hard-defaults 只补缺口行 | 文档纪律 |
| `make check-all` 相关测绿 | 工程纪律 |

---

## 8. 与既有 plan 关系

| 文档 | 角色 |
|------|------|
| **本档（确认后 2026-08-06-optimization-todoplan）** | **下一轮单一执行板** |
| `2026-08-05-strategy-…` | 历史 dual-lens；S 波次已勾 → 指到本档 residual |
| `2026-08-05-optimization-todoplan` | W0–5 SHIPPED；next=本档 A/C |
| `2026-08-05-antifragility-…` | AF 核心 SHIPPED；D 波为尾巴 |
| `2026-08-05-residual-monolith-w4` | E 波结构 owner |
| memory 08-06 ×2 | A/B 需求圣旨源 |

---

## 9. 实现时注意

- 改制度 / hard-defaults：先备份 `~/.grok/backups/`  
- 功能变更：bump `plugin.json` + CHANGELOG  
- 脚本指纹变：`make lock-runtime`  
- 装机副本：`grok plugin update ai-film-grok`  
- 非琐碎收尾：派 `verifier`  

---

## 10. 请你拍板的点（确认 plan 时）

1. **A1 策略偏好（推荐 #1）：**  
   - **#1 fail-closed + 明确 next**（不静默 10s）  
   - #2 保留 auto-extend 但 **cap 到源片可 stretch 上限**  
2. **C1** 是否在本迭代必须真烧 GPU，还是代码 A/B 先做、ops 另约。  
3. 落档路径：默认 `docs/plans/2026-08-06-optimization-todoplan.md`。
