# 历史错误内化 · 持续进化 Todo Plan（2026-08-07）

**结论先行：** 库的记忆/铁律**立法体系已经成熟**（hard-defaults > stages > memory > lessons；五问卡；L3/L4/L5 阶梯）。I0–I5 产品内化与 delivery-honesty R0–R5 **已 CLOSED**。真正让错误「贰过」的，不是再贴标语，而是：**(1) 08-07 真片事故仍停在「表行+短卡」半吞吐；(2) 养分表/iron 门清单落后于实码；(3) 事故→闸门的飞轮没有固化成每周必跑纪律。**

| 项 | 值 |
|----|-----|
| Status | **SHIP 2.40.99** · E1–E5 + F4/F5 + E6.3 iron set · 真 CV DEFERRED |
| 探针版本 | `plugin.json` **2.40.99** |
| 挂 CTO | [CTO 主执行板](docs/plans/2026-08-06-cto-optimization-todoplan.md)（不新开第三综合板） |
| 既有子板（**勿重开**） | iron I0–I5 · honesty R0–R5 · shot-lane 0–6 |
| 治理 | [MEMORY_GOVERNANCE](docs/MEMORY_GOVERNANCE.md) · [nutrient-matrix](docs/plans/2026-08-06-nutrient-matrix.md) |
| 类比 | 消防规范齐全、喷淋已装；现在要的是 **新火灾立刻加探头 + 每周对账灭火器是否过期** |

---

## 0. 诊断：根因不是「记不住」，而是「记了拦不住」

### 0.1 已 thrash 过、勿再当 OPEN 重做

| 波次 | 状态 | 代表事故 → 内化 |
|------|------|----------------|
| I0–I4 铁律→代码 | **CLOSED 2.40.51+** | 假绿 / 毒人证 / speaker / material / stages |
| I5 机读 hog | **CLOSED 2.40.63** | multi-agent GPU；真 overnight 仍 OPEN_OPS |
| honesty R0–R5 | **CLOSED 2.40.75** | SKIP 记账 · 人证 ledger · checkout drift |
| shot-lane 0–6 | **CLOSED 2.40.60** | 分型 · poison · fill · variety · continue |
| composition_fill | **有码+测** | 席德 EP02 小主体；闭环 measure→ensure→H3 |

### 0.2 历史错误的**重复模式**（跨月同构）

按「掉片频率 × 假绿伤害 × 可机读程度」归类——这就是内化优先级：

| 模式 | 用户可见 | 工程根因 | 正确内化形态 |
|------|----------|----------|--------------|
| **P-假绿** | 门绿但难看/不对人 | 只比 mean/音量/字段；缺像素或代际绑定 | L4 promote/closeout fail-closed + receipt |
| **P-半套立法** | 规章写了仍犯 | memory/hard-defaults 有行，**无 gate / 无 pytest / 不在 iron-status** | 五问只收 C；ship = 码+测+表行 |
| **P-图方便绕链** | 怪镜/跳戏 | 盲 `--mode i2v`、半帧贴脸、archive 填洞 | resolve 强制 + 源 still 纯净门 + 混代拒 |
| **P-修错轴** | 声干净脸漂 | final 优先音轨不先 identity | closeout 身份轴 ≥ 声轴 |
| **P-账实漂移** | agent 重做已 ship / 读旧 plan | nutrient/CTO header 落后；双 checkout；缺卡死链 | 周 reconcile + doctor drift + 缺链测 |
| **P-逃生无痕** | SKIP 静默放行 | 112+ 散读 env；中央 `skip_flag` 只触达 ~半 | 触达式迁 + closeout 清点 |
| **P-假 Done** | 标 SHIPPED 无行为 | 只改 prose / 假 CV | DoD：pytest + receipt 字段 + 可选 canary |

### 0.3 当前真洞（本机探针 · 2026-08-07）

| # | 洞 | 证据 | 类 |
|---|-----|------|----|
| **E1** | **身份代际锁未机读** | hard-defaults + memory 有；`cast_generation` / `IDENTITY_PARTIAL` **无 promote/closeout 硬门**；face aHash 仅 post_audit 软路径 | **C · 假绿最高伤** |
| **E2** | **配角/男主定妆锁半套** | hard-defaults 链到 `partner-cast-master-iron.md` → **文件 MISSING**；立项日 `face_lock` 无全 cast 硬校验 | **C · 立法死链** |
| **E3** | **原声隔离双真相** | hard-defaults 仍写狠 `arnndn+agate`；`no-midframe` 卡已改「轻处理默认」；`h3-native-speech-isolate.md` **MISSING** | **C · 双写法条** |
| **E4** | **禁半帧复合未机读** | memory 事故卡完整；promote/register **无** composite/seam 启发式或 attestation 字段 | **C · 图方便绕** |
| **E5** | **FLF/continue 盲 i2v 可绕** | shot-lane/resolve 在；agent 可 CLI 强盖 mode；缺「override 须收据 + 禁 silent」硬契约 | **C 半吞吐** |
| **E6** | **iron-status 清单落后** | 无 `composition_fill` / `identity_gen` / `partner_cast` / `skip_audit` 行 | **B 卫生** |
| **E7** | **nutrient-matrix 过期** | 表头仍 ~2.40.51 / 无 08-07 E* 行；与 CTO 2.40.93+ 脱节 | **B 账实** |
| **E8** | **memory active 超 cap** | ~48 活跃 vs 软 cap 40；缺卡 + 旧卡并存 | **B 税** |
| **E9** | **SKIP 触达未完** | ~253 处读 `AIFILM_SKIP`；`skip_flag` 接入约 27 文件 | residual honesty |
| **E10** | **gates 静默 except 残余** | CTO OPEN#1；cinematic 等仍多 `except` | residual A1 |

**人判边界（永不机器代签）：** pilot / PK / review-final / 脸 verified 人签。  
**明确 DEFERRED：** 真 CV 毒镜分类器、全树 except 扫荡、markdown→AST 全表 parser、虚荣 peel。

---

## 1. 进化飞轮（永久制度 · 先于具体洞）

> 类比：不是一次灭火，而是 **每次火后自动加探头**。

```text
事故/用户原话
  → 五问卡（A/B/C · L阶 · 挂载层 · 证据 · 人判）
  → 只 C 进队列（本 plan Wave 或 CTO OPEN）
  → 代码 gate + hard-defaults 一行 + pytest
  → iron_status 登记 + nutrient 行 L3/L4
  → memory 三句指针（禁双写全表）
  → stages 一行（若阶段动作变）
  → L5：已 L4 则 archive/瘦卡
  → 周 reconcile：header vs plugin.json vs OPEN 表
```

### Wave F · 飞轮固化（P0 纪律 · 低码）

| ID | Todo | 做法 | 验收 |
|----|------|------|------|
| **F0** | 事故入口卡模板 | 在 `MEMORY_GOVERNANCE` 或 `memory/README` 固化「事故→五问→IRON-xx 卡」；**禁**只改 memory 当 ship | 新 IRON 必有五问答完截断 |
| **F1** | nutrient 刷新协议 | 每次 ship IRON：同 PR 改 nutrient 一行 + 版本探针 | CI 可选：nutrient 内版本 ≤ plugin.json |
| **F2** | iron-status = 机读目录 | 新 L3+ 门必须进 `_IRON_GATES` | `test_iron_status` 含新 id |
| **F3** | 周 reconcile 15min | CTO §6：OPEN · nutrient · iron plan header · 缺链 memory | 产出 `receipts/` 或 plan 勾选日期 |
| **F4** | 死链测 | pytest：hard-defaults 内 `memory/*.md` 链接 **文件存在** | `test_hard_defaults_memory_links` 红=缺卡 |
| **F5** | active memory ≤40 | archive canary/session/已 L4 长卡；README P0 表同步 | `ls memory/*.md \| wc` ≤40 |

**非目标：** 不新建「第四块综合 todo」；F* 挂本 plan 与 CTO Wave 9。

---

## 2. 产品内化波次（E* · 08-07 不准再犯）

每项用五问卡；默认 **fail-closed + 逃生 env 写 skip_audit + receipt**。

### Wave E1 · 身份代际锁（P0 · 掉片最高）

| 问 | 答 |
|----|-----|
| A/B/C | **C**（法条有 · 机读无） |
| L | 目标 **L4** closeout/ship-prep；promote **L3** |
| 挂载 | register-clip / final closeout / ship-prep |
| 证据 | `receipts/cast-generation.json` · `face-identity.verified` · IDENTITY_PARTIAL |
| 人判 | verified 仍须人签；机读只拦混代与假「脸对」 |

| ID | Todo | 文件（预期） | 验收 |
|----|------|--------------|------|
| E1.1 | 定义 `cast_generation_id`（film 或 restyle batch）写 receipt | `assets/` 或 `media/register*` | 字段存在 |
| E1.2 | active timeline **禁** `_archive_*` / 异 gen path 混 final | closeout / delivery_class | 混代 → 红或 IDENTITY_PARTIAL |
| E1.3 | `verified≠true` → 禁文案 master；强制 PARTIAL 类 | closeout / export | 契约测 |
| E1.4 | aHash/drift 审计进 ship-prep hard（阈值可配） | post_audit 升 hard when premium 或默认 | 测 + escape `AIFILM_SKIP_IDENTITY_GEN` |
| E1.5 | iron-status + hard-defaults 一行「机读」+ memory 三句 | iron_status · nutrient | F2 |

### Wave E2 · 配角/男主定妆锁（P0）

| ID | Todo | 验收 |
|----|------|------|
| E2.0 | **补死链卡** `memory/2026-08-07-partner-cast-master-iron.md`（三句+清单） | F4 绿 |
| E2.1 | 上镜 character_id 须 `cast_master`+`face_lock` 路径存在 | preflight / write-spec |
| E2.2 | 双人镜 prompt 须 `Character <id>:`（lint） | h3 prompt / preflight |
| E2.3 | `style.locked` 假绿：全 cast master 齐才 true | style_lock / preflight | 测 |

### Wave E3 · 原声诚实（P0 · 先消双真相）

| ID | Todo | 验收 |
|----|------|------|
| E3.0 | 补或 archive：`h3-native-speech-isolate`；**hard-defaults 改轻处理默认**（与 no-midframe 一致） | 单一法条 |
| E3.1 | native XOR TTS 路径再钉（已有则契约加固） | 双轨对话 → 拒或 PARTIAL |
| E3.2 | 默认滤镜 profile：`native_light` vs `native_gate_aggressive`（后者须 flag+抽听 receipt） | 禁默认 agate |
| E3.3 | 交付命名：`film_native_stable` 默认；狠 gate 产物禁冒充 final | closeout 名检查 |

### Wave E4 · 禁半帧复合 + 源 still 纯净（P0）

| ID | Todo | 验收 |
|----|------|------|
| E4.1 | register-still / I2V 源：拒「composite/seam」启发式或 **强制** `still_provenance=whole_frame` attestation | 缺字段 hard |
| E4.2 | 毒 composite 目录约定 `_archive_poison_*` 禁进 timeline | path lint |
| E4.3 | 测：合成 still fixture → 拒 H3 | pytest |

### Wave E5 · H3 mode / continue 不可 silent 盖（P1）

| ID | Todo | 验收 |
|----|------|------|
| E5.1 | CLI/run 若 override resolve mode → 写 `receipts/h3-mode-override.json` | 有 override 必有 receipt |
| E5.2 | continue 镜缺同代 endframe → fail-closed（已有则 harden） | 测 |
| E5.3 | stages/visual 一行指针 | dispatch 可见 |

### Wave E6 · 卫生与半吞吐收口（P1）

| ID | Todo | 验收 |
|----|------|------|
| E6.1 | iron_status 登记：composition_fill · identity_gen · partner_cast · skip_audit | CLI 可见 |
| E6.2 | nutrient-matrix 整表刷新到 2.40.96+；E1–E5 行；删过时 pending | 账实 |
| E6.3 | SKIP 触达：下一批 hotpath（media-queue / h3_workflow / motion）迁 `skip_flag` | 覆盖率↑ 可测 |
| E6.4 | CTO A1：再清 **一个** gates 子集静默 except | 表征测 |

### Wave E7 · L5 废文（P2 · 持续）

| ID | Todo | 验收 |
|----|------|------|
| E7.1 | 已 L4 主题 memory 瘦到三句；lesson 不进默认 context | active ≤40 |
| E7.2 | 过期 plan header 统一 CLOSED 指针（防 agent 重开） | 抽检 0 误导 |

---

## 3. 优先级与 `go` 默认链

**公式：** `掉片频率 × 假绿伤害 × 可机读`  
→ **E1 > E2/E3/E4 > F0–F4 > E5 > E6 > E7**

```text
工程日（无 GPU）：
  F4 死链测红 → E2.0/E3.0 补卡+hard-defaults 消双真相
  → E1.1–E1.5 身份代际机读（主交付）
  → E4 源 still 纯净
  → E6.1–E6.2 iron-status + nutrient
  → F5 memory 瘦身

出片日：
  只用已绿门；不混大 peel；事故当场五问 → 记入本 plan 不另开板

有 5090：
  真 drain 或 OPEN_OPS；不抢 E* 工程队列
```

**完成定义（单 IRON）：**

1. pytest 绿 +（指纹变）`lock-runtime`  
2. hard-defaults 一行可执行语义（非散文复述）  
3. memory ≤ 三句指针；**无**缺链  
4. 默认 fail-closed；`AIFILM_SKIP_*` 经 skip_audit + reason  
5. nutrient + iron-status 同 PR 账实  
6. **永不**机器代签 pilot / PK / review-final  

---

## 4. 非目标 / 忌讳

| 禁止 | 原因 |
|------|------|
| 再开第二套「记忆内化综合板」抢 CTO | 协作税 · agent 读错板 |
| 只改 memory/AGENTS 当 Done | P-半套立法 根因 |
| 假 CV「已识别毒镜/已锁脸」 | 假 Done |
| 默认 `AIFILM_SKIP_*=1` 换绿 | 软化 IRON |
| 虚荣 peel render_final 为内化 KPI | 与错误贰过无关 |
| 重开 I1–I4 / R0–R5 已 ship 项 | 误工 |

---

## 5. 与既有板关系（单一真相）

```text
CTO 主执行板
├── 本 plan（E*/F* · 08-07 事故内化 + 飞轮）← 新 OPEN 子集
├── iron-internalization（I0–I5 CLOSED · 仅指针）
├── delivery-honesty-rail（R0–R5 CLOSED · SKIP 触达 residual → E6.3）
├── nutrient-matrix（对账表 · E6.2 刷新）
└── shot-generation-lane（0–6 DONE · E5 挂 harden）
```

---

## 6. 验收证据（执行时落档）

建议路径：`docs/reports/2026-08-07-error-internalization-evidence.md`  
每 unit：pytest 名 · receipt 字段 · SURFACE（真片或 fixture）· 版本 bump。

---

## 7. 一句话给主理人

**规章与喷淋已经很多；下一步不是再写教训，而是把「abroad 混代脸 / 里昂无定妆 / 半帧贴脸 / 狠 gate 毁声 / 死链 memory」变成和 composition_fill 同级的默认闸门，并用死链测 + 周对账保证系统只会变严、不会变忘。**

---

*Plan drafted 2026-08-07 · probe v2.40.96 · read-only plan mode*
