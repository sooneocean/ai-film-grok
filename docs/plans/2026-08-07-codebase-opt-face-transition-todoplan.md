# 代码库优化 + 模组拆分迭代 Todo Plan（含剪辑转场 · 锁脸 P0）

**结论先行：** 仓库已是 **能力齐备的成熟片厂**（v**2.40.97**），包边界与安全迁移队列已收口；下一轮优化 **不是再贴标语 / 虚荣压行数**，而是三条真轴：

1. **锁脸全链 hard-closed（用户点名：必要）** — enroll → register → promote → final，禁止「有片=脸对」。  
2. **剪辑层转场观感与机读闭环（用户点名：仍要优化）** — 从「spec 政策 soft 绿」推进到「成片缝可验收 + 语法不粥」。  
3. **巨石挡路才拆** — 优先把转场/锁脸触达的厚函数剥成可测叶子，其余保持 terminal residual freeze。

| 项 | 本机探针（2026-08-07 · plugins checkout） |
|----|------------------------------------------|
| 版本 | `plugin.json` **2.40.97** |
| scripts | **~181k** LOC · 顶层约 **360** 文件（绝大多数 thin shim） |
| 包体积 | plan≈32k · media≈32k · post≈19k · audio≈19k · cli≈17k · narrative≈16k · gates≈12k |
| 巨石函数 ≥200 行 | **~87**；最大 `render_final` **~2483** / `validate_film_spec` **~2360** / `run_preflight` **~2120** / `build_dispatch` **~1249** |
| 顶层 intentional residual | **`aifilm_grok.py` hub** + **`workflow_pack.py`**（代谢 inventory 已 freeze） |
| 测试 | **~483** test 文件 / 测码 ~86k LOC |
| 主执行板（历史） | [CTO plan](docs/plans/2026-08-06-cto-optimization-todoplan.md) · 结构 [metabolism inventory](docs/reports/2026-08-06-code-metabolism-inventory.md) |
| 本 plan 角色 | **本会话单一执行板**（挂 CTO 下，不另起第三综合板）；**新增/抬升 F 锁脸 + T 转场** |
| **执行进度** | **F1+T1+T2 SHIPPED 2.40.101** · **F2+T3 SHIPPED 2.40.105**（closeout 三联 + 转场抽帧 status）；F3 still 绑 / T4 plate↔ops / T5 residual |
| **执行进度** | **F1 + T1 + T2 SHIPPED 2.40.101**（默认 hard + soft-soup）；F0/T0 账实见代码注释；F2–F4 / T3–T5 residual |

**仓库类比：** 分车间门牌已贴好，总控台（final/preflight/edit）仍塞满旋钮；锁脸像「每镜必须刷脸进棚」，转场像「剪辑师的刀口语法」——门绿不等于观众不跳戏。

---

## 0. 现状诊断（只读账实）

### 0.1 已 ship（禁止当绿地重开）

| 层 | 状态 | 证据 |
|----|------|------|
| 包边界 W0–W7 | **DONE** | `core/spine/assets/plan/post/narrative/audio/media/gates/cli/final/util` + hard-compat shim |
| 安全迁移 C6 | **DONE / freeze** | 可整文件迁队列空；只剩 hub + workflow_pack intentional residual |
| 工程纪律 C5 | **DONE** | logging pilot · FilmError 增量 · JSON util · subprocess timeout 触达补 |
| 出片诚实 R0–R5 | **CLOSED** | skip 记账 · PARTIAL 字段 · plate≠master 契约 |
| heat 结构 facade | **DONE** | packs 已拆；禁预防性再拆 wardrobe/coitus |
| 转场 **策略门** | **部分 DONE** | `transition_policy_report` + `transition_export_readback` + preflight（**默认 soft**；`transition_policy_strict` / adult max 才 hard） |
| 锁脸 **子系统** | **部分 DONE** | `face_identity` / `style_lock` / `identity_generation_lock` / `partner_cast_gate` / `assert_face_identity_passed` 已接线；**多处仍 soft 或 strict 开关** |

### 0.2 真痛（本轮要解）

| 痛点 | 为什么仍痛 | 杠杆 |
|------|------------|------|
| **锁脸未成为默认肌肉** | enroll 有、audit 有，但 register/promote/final 路径仍可在 `verified≠true` / soft gate / skip 下出片；配角/代际锁是独立门，易漏 | 废片率 · 角色漂移 |
| **转场「政策绿 ≠ 成片丝」** | 策略与 export read-back 多在 **spec/ops 层**；plate ffmpeg xfade 与 HF 糖衣双路径；`edit_policy` **~2601** 仍混 stretch/rhythm/xfade；continue 硬切已有，**soft 缝易粥、缺像素抽帧验收默认 hard** | 观感 · 剪辑语言 |
| **巨石改不动** | 触达转场/锁脸时要在 preflight / production_gates / edit_policy / render_final 里翻几千行 | 维护速度 |
| **文档板发散** | 多份 optimization/cto/residual 并存；agent 易重做已 ship | token · 误工 |

### 0.3 健康处（默认别动）

- IRON / hard-defaults 法条层（成人 MAX、毒镜、不回穿、字幕硬烧、GPU no-hog…）  
- public `aifilm` 子命令字符串 + shim hard-compat  
- CI check-all / secret-scan / hotpath / mypy 种子  
- terminal residual freeze（禁虚荣整仓搬文件）

---

## 1. 锁脸轨（Wave F · **P0 必要 · 用户点名**）

> **类比：** 进棚刷脸。没有定妆脸锁 = 不能声称「同一角色」。技术 plate 可以出，但必须 **IDENTITY_PARTIAL 诚实**，禁止文案 master。

### 1.1 目标状态机（端到端）

```text
立项日 cast_master + face_lock
        ↓
face-identity enroll（fingerprint）
        ↓
still / keyframe 只绑当前 gen master（禁 archive 混）
        ↓
register-clip / promote：verify 失败 → reject（默认 hard）
        ↓
bulk / H3：I2V 锁脸主责；T2V 无脸 env only
        ↓
closeout：identity_generation + partner_cast + face_identity
        ↓
final / ship：verified=true 或 显式 IDENTITY_PARTIAL plate
```

### 1.2 现状缺口（相对目标）

| 缺口 | 现状 | 目标 |
|------|------|------|
| F-G1 默认 hardness | `assert_face_identity_passed` 常 **soft**，靠 `face_identity_strict` / adult max 才 hard | **有 enroll 的片默认 hard**；逃生仅 `AIFILM_SKIP_FACE_IDENTITY*=1` + receipt |
| F-G2 register | 历史曾仅 `--require_face_identity` hard | enroll 存在 → **默认 reject 漂移**（复核 `cli_media` 真路径） |
| F-G3 代际/配角 | 两门独立（identity_generation / partner_cast） | **final 前 AND**：缺任一 → 禁声称角色稳定 |
| F-G4 半帧贴脸 | memory IRON 已有 | promote / I2V 源路径再压 fail-closed（禁 mid-frame composite 当 face-lock） |
| F-G5 像素弱 | aHash/dHash + hist；高动/侧脸假阴假阳 | 阈值内：阈值调参 + face_region；**不**上假 CV 分类器 |
| F-G6 模块边界 | face 逻辑散落 gates + assets + closeout | 契约测锁住；触达时抽 `assets/face_pipeline.py` 纯报告函数（可选） |

### 1.3 Todo（可勾选）

| ID | Todo | 做法 | 验收 | Pri |
|----|------|------|------|-----|
| **F0** | 锁脸路径账实审计 | 扫 `register_clip` / promote / preflight / closeout / ship-prep：soft vs hard vs skip | `docs/reports/…-face-lock-audit.md` 表：入口→硬度 | P0 |
| **F1** | **默认 hard 策略** | 有 `receipts/face-identity.json` enroll 任一主角色 → gate hard；无 enroll 且片含 on-cam 人 → hard 要求 enroll 或 IDENTITY_PARTIAL | 新测：enroll 坏图 register 失败；skip env 写 receipt | P0 |
| **F2** | closeout 三联 | `face_identity` ∧ `identity_generation` ∧ `partner_cast` 在 ship-prep / official-final 同一诚实字段 | `test_*` 三联红时 delivery_class≠master | P0 |
| **F3** | still 源绑定 | generation_ready / still_source：未绑当前 face-lock 禁 H3 | 契约测 + 1 条 fixture | P0 |
| **F4** | 禁半帧当锁脸 | 与 no-midframe IRON 对齐：register/I2V 源校验 | 既有测 + 缺口 1–2 | P0 |
| **F5** | doctor 探针 | doctor：主角色未 enroll / verified false 红 | doctor 输出含 next_cmd | P1 |
| **F6** | （结构）纯报告 peel | 触达时：`face_identity_report` 与 assert 分文件，禁大 rewrite | 行为不变 + 测绿 | P1 触达 |

**明确非目标（锁脸）：** 上真 CV 人脸识别模型；用 FRW T2V 声称锁脸；删 hard-compat shim。

---

## 2. 剪辑层转场轨（Wave T · **P0 产品 · 用户点名仍要优化**）

> **类比：** 剪辑师的刀口。continue 接戏缝 = 同一动作延续，**必须硬切**；场景/章缝才允许 soft 糖衣。现在「政策文档 + spec 门」较齐，**观感与成片抽帧验收**仍弱。

### 2.1 分层真相（避免改错层）

| 层 | 该做什么 | 不该做什么 |
|----|----------|------------|
| **L0 接戏 / plate** | continue → hard match-cut / concat | dissolve/blur 盖字节缝 |
| **L1 剪辑语法（edit_policy）** | intent/style 轮转、禁 soft 粥、时长/xfade 图 | 把 HF MG 转场塞进接戏 underlay |
| **L2 designed-post（HF/Remotion）** | 片头片尾 / 段落 / 纯 MG | 装饰 continue 缝 |
| **L3 验收** | transition_ops 全覆盖 + final 抽帧 + 人审窗口 | 只看 spec 字段绿 |

### 2.2 现状模块与 LOC

| 模块 | ~LOC | 角色 |
|------|-----:|------|
| `narrative/edit_policy.py` | **2601** | stretch + rhythm + **xfade 总控**（厚） |
| `plan/transition_ops.py` | 210 | 每缝 operations 契约 |
| `post/transition_frame_audit.py` | 397 | final MP4 缝抽帧 |
| `gates/production_gates` transition_* | ~大段 | policy + export read-back |
| `references/hf-transition-policy.md` | — | 人读母法 |

### 2.3 优化目标（观感 + 机读）

1. **continue 缝 0 例外 hard**（已有 → 保持 + final 像素抽帧默认可机读）。  
2. **soft 缝反粥**：禁连续 ≥N 次同 style；rotation 在 9:16 可读（已有部分 `_STYLE_SOFT_ROTATION` → 升为 gate）。  
3. **双路径一致**：film-spec intents/styles ↔ `transition_ops` ↔ export/HF 声明 **同一真相**（read-back 已有 → 默认 hardness 抬升可配置）。  
4. **成片证据**：`transition-frame-audit` 进 closeout / ship-prep 可选 hard（成人 max 或 `transition_policy_strict` 默认开）。  
5. **结构**：从 `edit_policy` 剥 `edit_transition.py`（xfade graph + craft map），原文件 re-export（bug-driven 优先，但本轨允许 **有计划 peel** 因用户点名优化）。

### 2.4 Todo（可勾选）

| ID | Todo | 做法 | 验收 | Pri |
|----|------|------|------|-----|
| **T0** | 转场路径账实 | 列：write-spec → build_ops → render_final xfade → export HF → audit 抽帧；标 soft/hard | 报告 1 页 | P0 |
| **T1** | **硬度策略** | 默认：continue 违规 **always hard**；soft 粥 / whip-on-scene **preflight hard**（非仅 adult）；escape `AIFILM_SKIP_TRANSITION_POLICY=1` | 测：continue+dissolve 红；strict 字段可删依赖 | P0 |
| **T2** | soft 反粥门 | 连续 soft 同 style ≥2（punchy）/≥3（silk）→ fail；扩展现有 `_punctuate_soft_run` 为 gate 输入 | `test_transition_policy` 扩 | P0 |
| **T3** | final 抽帧默认 | ship-prep / closeout：有 final 则 `transition_frame_audit` 写 receipt；关键 fail 码进 PARTIAL | 合成 fixture + 测 | P0 |
| **T4** | plate xfade 与 ops 对齐 | render_final / compose 使用的 style 必须 ∈ ops.picture；禁 silent fallback 成 fade 粥 | 契约测 | P0 |
| **T5** | **模组拆分** `edit_transition` | 从 `edit_policy` 抽出：normalize_* · craft map · build_xfade* · join duration；shim re-export | LOC 表 + `test_edit_policy` + transition 测全绿 | P1 |
| **T6** | transition_ops 归属澄清 | 保持 `plan/`；gates 只消费 report 函数；禁第三份 intent 解析 | import 图干净 | P1 |
| **T7** | HF catalog 只读门 | 非 MG 禁用 whip/grid 再压一层（read-back 已有则补缺口） | 测 | P2 |
| **T8** | 人读 stages 快卡 | `stages/post.md` 三行：continue hard · soft 轮转 · audit 路径 | agent 不靠长 lesson | P2 |

**明确非目标（转场）：** 把 HF blur/push 默认盖全部接戏缝；虚荣重写整个 `edit_policy` 而不加测；用「转场炫技」掩盖缺镜。

---

## 3. 模组拆分轨（Wave M · 结构 · 挡路 + 与 F/T 联动）

### 3.1 原则（沿用 metabolism IRON）

1. **挡路才拆**；本轮因 F/T 触达，**允许计划内 peel** 下列入口。  
2. 行为与结构 **分 commit**。  
3. public CLI + shim hard-compat 不变。  
4. 禁止「全员 <1500 行」冲刺。  
5. DONE = 路径 + LOC 前后 + 相关测绿 +（指纹变）lock-runtime。

### 3.2 拆分优先级（风险 × 触达 × 本轮主题）

| 序 | 目标 | ~现状 | 策略 | 与 F/T |
|----|------|------:|------|--------|
| **M1** | `narrative/edit_policy` → `edit_transition` (+ 可选 `edit_stretch`) | 2601 | **本轮计划 peel**（T5） | T |
| **M2** | `gates/production_gates` 中 transition_* / face_* report 纯函数簇 | 2301 文件 | 触达时迁 `gates/transition_policy.py` · `gates/face_identity_gate.py` | F+T |
| **M3** | `post/render_final` stage 叶 | 3082 | **仅** VO/mix/字幕/转场接线 bug 时 peel → `final/*` | 触达 |
| **M4** | `plan/film_spec_validate` | 2467 | 触达 lint 时再 peel projector | 触达 |
| **M5** | `gates/preflight` | 2224 | fail-closed 改造时按 gate 族拆 | A1 联动 |
| **M6** | hub / workflow_pack | intentional residual | **禁 vanity move** | — |

### 3.3 安全迁移（已空队列）

- C6.1 safe migrate：**保持 empty**；新代码 **直接写 package**，顶层只留 shim。  
- Lane A 删除：仅 0-import 工具/示例；护栏测不红。  
- 双 checkout：只改 `git rev-parse --show-toplevel`；禁手拷。

---

## 4. 工程与运维残余（Wave E · 挂 CTO · 不抢 F/T）

| ID | 主题 | 状态建议 |
|----|------|----------|
| E1 | gates 静默 except 子集 fail-closed | 续 A1；**改到 face/transition 相关 except 优先** |
| E2 | final hotpath / plate≠master 永不回退 | 守测；与 F2 诚实字段对齐 |
| E3 | 5090 drain | 有独占 GPU 才做；否则 OPEN_OPS |
| E4 | mypy 扩名单 | 每清一文件加名单；优先 `assets/face_*` · `plan/transition_ops` |
| E5 | plan 文档卫生 | 旧 optimization header 指针 → 本 plan / CTO；禁第三综合板 |

---

## 5. 迭代波次时间盒（建议 3 周可执行）

```text
Week 1 · 止血与必要
  F0 账实 → F1 默认 hard → F2 closeout 三联
  T0 账实 → T1 continue/ soft 硬度 → T2 反粥
  每 PR：测绿 + CHANGELOG bump + 英文 commit

Week 2 · 成片证据 + 接线
  F3 still 绑定 · F4 半帧禁
  T3 final 抽帧 · T4 plate↔ops 对齐
  E1 触达 except 改 fail-closed

Week 3 · 模组代谢
  T5/M1 edit_transition peel
  M2 gates face/transition 报告簇（若 Week1–2 已 thrash）
  F5 doctor · T8 stages 快卡
  inventory 刷新 · 旧 plan 指针
```

**圣旨短令 `go`：** 按 Week 当前未勾选的 **最小 P0 链** 推进（默认 F1→T1→F2），不重开辩论。

---

## 6. 成功定义（一迭代结束）

| 标准 | 信号 |
|------|------|
| 锁脸必要 | 有 enroll 片：漂移 register/promote **红**；final 无 verified 不得 master 文案 |
| 转场优化 | continue+dissolve **硬红**；soft 粥 **硬红**；有 final 则缝抽帧 receipt 存在 |
| 模组 | `edit_transition` 存在或等价 peel；`test_edit_policy`+transition 套件绿；shim 不红 |
| 工程 | `make check-all` 绿；无静默改 heat/i2v/pilot |
| 诚实 | 无 GPU / 无真片时 OPEN_OPS 或 PARTIAL，不假 DONE |

---

## 7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 锁脸 hard 误杀侧脸/高动 | face_region + 阈值可调；IDENTITY_PARTIAL 诚实出口；skip env + receipt |
| 转场 hard 拦旧片 | 旧 root 可 `transition_policy_strict=false` 过渡一周；新片默认 hard |
| peel 改静默行为 | 黄金主/契约测先于抽取；行为/结构分 commit |
| 与 CTO OPEN 表冲突 | 本 plan F/T 并入支柱 A；C4 虚荣 peel 仍禁止 |

---

## 8. 非目标（全局）

- 虚荣 LOC 冲刺 / 重做 W0–W7 包边界  
- 复活 lipsync 生产路径  
- FRW 替换 h3_primary  
- 全仓 except 扫荡 / 全树 mypy 一次开满  
- 软化成人 MAX / 毒镜 / 不回穿等 IRON  
- 把 plate 刷成假 master  

---

## 9. 落档与执行（你确认 plan 后）

| 动作 | 说明 |
|------|------|
| 写入仓库 | 建议 `docs/plans/2026-08-07-codebase-opt-face-transition-todoplan.md` |
| 互指 | CTO plan §5 OPEN 冻结集 **增补/抬升**：锁脸默认 hard · 转场硬度/抽帧 · edit_transition peel |
| memory 短卡（可选） | 三句：锁脸必要 hard · 转场 continue hard + soft 反粥 · 挡路 peel |
| **不**自动大改 | 等你确认或圣旨 `go` 指定波次（推荐 **F1 + T1**） |

---

## 10. 请你拍板

1. **主攻顺序（推荐）：** F 锁脸 hard 链 → T 转场硬度+抽帧 → M1 `edit_transition` peel。  
2. **锁脸默认 hard 是否适用于所有 on-cam 新片？**（推荐：**是**；旧片 escape + PARTIAL）  
3. **转场 soft 违规是否新片默认 hard？**（推荐：**是**；不仅限 adult max）  
4. 确认后退出 plan mode，按 Week1 最小链执行。

---

*基线：`/Users/dex/.grok/plugins/ai-film-grok` @ 2.40.97 · 只读诊断 · 未改业务代码。*  
*用户增量：剪辑层转场需优化 · 锁脸为必要（已升为 P0 主轴）。*
