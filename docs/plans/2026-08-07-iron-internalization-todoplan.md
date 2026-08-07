# 铁律 / 记忆 → 系统内化 Todo Plan（2026-08-07）

**结论先行：** 不是缺铁律，而是约 70%+ 已进门禁，**像素假绿 + 人证可绕 + dispatch 上下文盲区** 仍掉片。内化 = L3→L4 默认肌肉 + L5 废文，**禁止**再写第二套 IRON 散文。

**类比：** hard-defaults = 消防规范；memory = 事故三句话；gates = 喷淋。要「走错就喷水」。

| 项 | 值 |
|----|-----|
| Status | **I0 SHIPPED 账实** · I1+ 待 `go` |
| Repo | `/Users/dex/.grok/plugins/ai-film-grok` |
| Version probe | plugin.json **2.40.48** |
| 主执行板 | [CTO](2026-08-06-cto-optimization-todoplan.md)（本档 = 支柱 A 内化子板，不平行第三综合板） |
| 养分对账 | [nutrient-matrix](2026-08-06-nutrient-matrix.md) |
| 记忆反查 | [memory-optimization-inventory](2026-08-06-memory-optimization-inventory.md) |
| 治理 | [MEMORY_GOVERNANCE](../MEMORY_GOVERNANCE.md) |

---

## 0. A/B/C 与 L 阶（出 todo 前必填）

| 类 | 含义 | 动作 |
|----|------|------|
| **A** | 法条 IRON 已定性 | 守住；不重写 prose |
| **B** | 工程已 ship | 当基础；禁绿野重开 |
| **C** | 仍 OPEN / 半吞吐 | **唯一进队列** |

| 阶 | 含义 |
|----|------|
| L3 | 机读能拦 |
| L4 | 默认路径必走 |
| L5 | 散文可 archive |

**五问卡** → [MEMORY_GOVERNANCE § Iron internalization](../MEMORY_GOVERNANCE.md)

---

## 1. 挂载层（新门必选一层）

| 层 | 时机 |
|----|------|
| validate-time | write-spec / validate_film_spec |
| dispatch-time | dispatch / next（只推 next_cmd） |
| queue/generate | media-queue · h3 run |
| promote/select | register · shortlist · pk |
| render-time | render_final / mix |
| closeout/export | gate-auto · closeout · export-desktop |

---

## 2. 半吞吐缺口（与 nutrient-matrix §2 同集）

| ID | 缺口 | 波次 |
|----|------|------|
| H-anti-hijack-all | multi-seed 非全入口强制 anti-hijack | I1.1 |
| H-variety-pixel | 改 spec 不 re-I2V 假绿 | I1.2 |
| H-plate-boring | 门绿≠好看；mean≪20 装片 | I1.3 |
| H-mix-deadlock | mix 默认可假死 | I1.4 |
| H-scale-chain | promote_ban 未盖全入口 | I1.5 |
| H-pixel-poison | 缺 anatomy attestation 可过 | I2.1 |
| H-endframe | 末帧不回穿无自动闸 | I2.2 |
| H-speaker | speaker-frame 默认 soft | I2.3 |
| H-material | restricted 缺 request soft | I2.4 |
| H-context-blind | 关键红线不进 routing | I3 |
| H-run-next-hog / H-dual | 软 hog / 双片误杀 | I5 |

**已 L4（勿重开）：** sex floor、until-empty 独占 flag、plate≠master 机读拦、zero-nar、true-video 主路径。

---

## 3. Todo 波次

### Wave I0 · 账实（✅ 本批）

| ID | Todo | 状态 |
|----|------|------|
| I0.1 | 刷新 nutrient-matrix H* + LOC + 版本 | ✅ |
| I0.2 | 冻结 OPEN ≤10（CTO §5 + 本档 §2） | ✅ |
| I0.3 | MEMORY_GOVERNANCE 内化 checklist | ✅ |
| I0.4 | CTO / memory README 指针本档 | ✅ |

### Wave I1 · 假绿 fail-closed（P0 · 下一 `go`）

| ID | Todo | 挂载 | 验收 |
|----|------|------|------|
| I1.1 | multi-seed **全入口** 强制 anti-hijack | promote/select | 无 SKIP 时缺跑不可 promote |
| I1.2 | variety：字段绿 ≠ 像素绿（邻差/mean 门槛） | gate-auto + promote | 只改 spec 不能过 ship-prep |
| I1.3 | plate-boring：肉戏 mean 大面积≪20 → 禁 master + PARTIAL | closeout/export | 测锁文案 |
| I1.4 | mix 默认不假死（broadband duck 或等价） | render | 无 mixed.wav 路径诚实失败 |
| I1.5 | scale promote_ban 盖全 register 入口 | promote | 硬冲 bare 拦测 |

### Wave I2 · 人证 harden（P0–P1）

| ID | Todo | 挂载 |
|----|------|------|
| I2.1 | restricted still→I2V 缺 `anatomy_safe` fail-closed | queue |
| I2.2 | register-clip 末帧启发式 + receipt（不宣称真 CV） | promote |
| I2.3 | max + dialogue_drama → speaker-frame hard | preflight |
| I2.4 | restricted 缺 generation_request soft→hard | queue |

### Wave I3 · 上下文

| ID | Todo |
|----|------|
| I3.1 | stages 压回指针（禁 mini-hard-defaults） |
| I3.2 | context-routing 关键 issue_code → 短 ref |
| I3.3 | h3-core-day 进 visual/media routing |
| I3.4 | 已 L4 memory 指针化或 archive |

### Wave I4 · 元机读（optional）

| ID | Todo |
|----|------|
| I4.1 | 契约测锁 sex 0.50 / mean 18·20 / max5 / i-own-gpu |
| I4.2 | `aifilm iron-status` 列门 + 逃生 env |
| I4.3 | **禁止** hard-defaults.md 全自动 parser |

### Wave I5 · 运维

| ID | Todo |
|----|------|
| I5.1 | run-next 软 hog 收紧 |
| I5.2 | dual-film / 禁 pgrep 源码匹配审计+测 |
| I5.3 | 真片 canary：queue_empty 或 OPEN_OPS+原因 |

---

## 4. 非目标

- 第二套 hard-defaults / 假 CV 当 Done  
- 软化 IRON / 默认 SKIP  
- 机器代签 pilot·PK·review-final  
- 重做 A1–A5 绿地 / 包边界 W0–W7  
- 虚荣 LOC  

---

## 5. `go` 默认链

```text
I0 已完 → I1.1 → I1.2 → I1.3
       → I2.1 + I2.3
       → I3.1–I3.2（穿插）
       → 其余按真片翻车插入
```

DONE = 相关 pytest 绿 +（指纹变）lock-runtime + CHANGELOG + 英文 commit。  
Ops 无 GPU = OPEN_OPS 诚实，不算工程失败。
