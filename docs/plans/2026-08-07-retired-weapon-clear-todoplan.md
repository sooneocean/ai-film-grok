# 退役武器库退干净 · 心智清晰优化 Todo Plan

> **结论先行**：你不是缺武器，是**退役了的还在视野里晃**——政策已退、代码/文档/CLI 仍挂「尸体 + 半退役 + 研究柜」，默认一想路由就同时冒出 Seedance / Wan / lipsync / 日文 / 16 个 research。  
> **目标**：默认脑子里只剩 **4 件套 + 明确 secondary**；退役的压成「一行墓碑 + 硬拒」；实验的进「研究柜」默认不可见。  
> **单一真相**：`registry/weapon-inventory.json` · 运营矩阵 `references/weapon-lane-matrix.md` · Comfy `registry/comfy-weapons.json`

| 项 | 值 |
|----|-----|
| 仓库 | `/Users/dex/.grok/plugins/ai-film-grok` |
| 互补已关 | lipsync v2.40 墓碑（`lipsync.md`）· code metabolism freeze · slim 板 |
| 本板性质 | **武器心智 + 表面清理**（非再开一轮 lipsync 大删；非 GPU 调度器） |
| 建议版本 | patch 系列 `2.41.x`（无 breaking 政策变）或一次 `2.42.0` 若卸掉 `SeedanceProvider` 注册名 |

---

## 0. 类比（先建立画面）

| 类比 | 武器库现状 |
|------|------------|
| **军械库墙上贴「在役」** | primary：H3 影 · Qwen 图 · Edge 声 · rnb BGM |
| **仓库后门贴「退役」但仍摆展台** | inventory 的 4 条 retired + 文档 89 处 seedance / 219 处 lipsync |
| **门口保安还拿着报废枪说明书** | `SeedanceProvider` 仍 `register`；`seedance_bridge` 仍 150 行真逻辑 |
| **地下室研究柜门开着** | `research_weapons` 16 条 + wan22-s2v/dancer/fun + InfiniteTalk pilot 进 default 视野 |
| **墓碑太厚** | lipsync 已 thin（好事）；Wan/FrwWan **类还在** i2v_provider；路由表仍列 lipsync CLI |

**退干净 ≠ 物理删历史**：历史 lesson / archive / 硬兼容 shim 可留；**默认 agent context 与默认 CLI 输出不得再当「可选武器」推销**。

---

## 1. 账实：什么算「退役」、什么还活

### 1.1 机读 `tier: retired`（仅 4 条 · inventory SSoT）

| id | 模态 | why |
|----|------|-----|
| `qwen-layered-control` | still | registry blocked |
| `wan22_local_i2v` | motion | H3 接管 |
| `seedance_primary` | motion | 非 spine primary |
| `elevenlabs_ja_path` | audio | 日文路径退役 |

### 1.2 代码硬退役 / 墓碑（政策已退 · 实现厚薄不一）

| 项 | 状态 | 心智污染点 |
|----|------|------------|
| **Wan 2.2 local I2V** | `WAN22_I2V_RETIRED` raise；**未 register** | `LocalComfyWan22Provider` 类体仍在；docs/comfy 多处「stays retired」 |
| **FRW Wan I2V** | `FRW_WAN_I2V_RETIRED`；**未 register** | 同上 `FrwWanProvider` |
| **Seedance bulk** | `name==seedance` + 无 `AIFILM_ALLOW_SEEDANCE` → raise | **仍 `register(SeedanceProvider())`**；`seedance_bridge` **仍可组合 prompt**（非 raise-only） |
| **后期 lipsync** | v2.40 thin 墓碑 · `final --lipsync` 仅 `off` | 文件名/CLI 名/route-catalog/219 文件提及仍刷存在感 |
| **日文对白** | preflight retired · hard-defaults | 偶发 lesson/字段残留 |
| **Qwen layered** | blocked_capabilities | 已干净，低优 |

### 1.3 不该当退役、但会抢心智的「实验柜」

| 桶 | 例子 | 建议默认 |
|----|------|----------|
| inventory **experimental** | InfiniteTalk / FantasyTalking / local LTX / Hunyuan SR / LipDub / voicebox / mmaudio | 默认 `weapon inventory` **不列出** |
| comfy **research_weapons**（16） | wan22-s2v/dancer/fun · seedvr2 · realesrgan · echomimic… | 仅 `AIFILM_RESEARCH_ARMORY=1` 或 `weapon inventory --research` |
| comfy **experimental pilots** | talking-avatar / ltx23 native… | 同上；禁 production_promoted 静默升 |

### 1.4 Active 心智模型（目标默认只记这些）

```text
Still   → Qwen T2I / edit（Grok cast 辅 · FRW i2i still-challenge 辅）
Motion  → MiniMax H3 I2V/FLF/R2V/T2V（profile h3_primary）
          secondary: Grok Video escape · FRW LTX 有声（ltx23_adult opt-in）
Audio   → Edge 中文 VO · rnb BGM · prefer_native 对白原声
Post    → HyperFrames final · lipsync 已死（勿再规划）
禁      → Seedance bulk · Wan22 本地 I2V · 后期对嘴 · 日文生产路径
```

---

## 2. 污染面量化（清理 KPI）

| 信号 | 现状（约） | 目标 |
|------|------------|------|
| `rg -l seedance skills docs` | ~89 文件 | 生产路径 docs 仅 tombstone 指针 + archive；代码除 gate/bridge-tombstone 外 0 推销 |
| `rg -l lipsync` | ~219 | 可保留历史；**SKILL/README/route 默认表** 0 行「后端挑战」 |
| `register()` 含 seedance 名 | 有 | 决策：**卸注册** 或 **改名 escape-only + inventory 不列** |
| `seedance_bridge` 真逻辑 | 150 行 | 纯 raise 墓碑 **或** 改名为 generic `cinema_prompt_zh_bridge` 且不提 Seedance |
| doctor / dispatch 默认输出 | 可能带 research/soft 噪音 | 默认只 `primary` line + 禁列表 1 行 |
| agent 默认读 weapon-lane | 长文含大量历史 | stages/visual + hard-defaults **短表**；lane 长文按需 |

---

## 3. 分波 Todo（按 ROI · 可勾选）

### Wave M0 — 心智立法（半天 · 先做 · 零风险）

> 类比：先换墙上的「在役名录」，再清仓库。

| ID | 任务 | 验收 |
|----|------|------|
| **M0.1** | 写短卡 `memory/2026-08-07-retired-weapon-clear-mind.md`：原话 + 目标 4 件套 + 禁 4 条 + 链本 plan | 卡 ≤40 行；Agents/SKILL **只挂指针不复写** |
| **M0.2** | `weapon-inventory.md` 增「默认只看 primary」+ 退役附录 4 行表；**禁止**在 primary 区重复 Seedance/Wan | `aifilm weapon inventory --tier primary` 文档一致 |
| **M0.3** | `hard-defaults.md` 增 **一行表**「已退役勿规划」：Wan22 I2V · Seedance bulk · post lipsync · ja path | doctor/人读同源 |
| **M0.4** | `weapon-lane-matrix.md` 顶部加 **退役折叠**（3 句）+ 正文不再用「Wan stays retired」当主叙事 | 主表只剩 active lanes |
| **M0.5** | `docs/plans/2026-08-07-retired-weapon-clear-todoplan.md` ← 本 plan 落仓副本（与 session plan 同步） | 路径可引用 |

**完成定义**：新人 / 新 session 只读 inventory.md + hard-defaults 退役表 + stages/visual，**不必**打开 16 research 才能开片。

---

### Wave M1 — 默认输出变干净（1 天 · 高 ROI）

| ID | 任务 | 文件倾向 | 验收 |
|----|------|----------|------|
| **M1.1** | `aifilm weapon inventory` **默认 tier=primary**（或 default 隐藏 retired/experimental） | `cli_weapon.py` · `weapon_inventory.py` | 无 flag 时 stdout 无 retired/experimental 名 |
| **M1.2** | 显式：`--tier retired` / `--tier experimental` / `--all` / `--research`（research 读 comfy research_weapons） | 同上 + 测 | 单测覆盖 4 模式 |
| **M1.3** | doctor soft 字段 `weapon_inventory.line` **只 primary**；retired 合并成 `retired_count=N` 不列名 | `cli_status.py` | doctor 输出一眼可懂 |
| **M1.4** | dispatch compact：`weapon_inventory_line` 仅 primary；禁把 research 写进 next_why | `dispatch_compact` / next_actions | 快照测 |
| **M1.5** | `route-catalog`：lipsync-* / frw-lipsync 标 `status: tombstone` 且 **默认 catalog list 过滤** | `route-catalog.json` + list CLI | 默认列表无 lipsync 子命令推销 |

---

### Wave M2 — 代码尸体减重（1–2 天 · 与 optimization-plan #13/#28 对齐）

| ID | 任务 | 风险 | 验收 |
|----|------|------|------|
| **M2.1** | `FrwWanProvider` / `LocalComfyWan22Provider`：缩成模块级常量 + 若被 import 名解析则 **单函数 raise**（或删类、测改期望） | 低（未 register） | `i2v_provider` 行数下降；测绿 |
| **M2.2** | **Seedance 注册策略（二选一，拍板后做）** | 中 | 见下 |
| **M2.2a** | **推荐**：unregister `SeedanceProvider` 名；escape 仅走 `frw-api-i2v` / 显式 provider；`AIFILM_ALLOW_SEEDANCE` 删或改映射到 frw-api | 旧脚本 `provider=seedance` 会 unknown | 文档 + FilmError 文案指向 h3/grok |
| **M2.2b** | 保守：保留 register 但 `probe()` 永远 unavailable + inventory 永不 primary；generate 仍 gate | 低 | 名字仍在 registry 列表 → **心智仍脏**（不推荐作终点） |
| **M2.3** | `seedance_bridge.py`：按 archive 计划 **X2** — 默认入口 raise `SEEDANCE_BRIDGE_RETIRED`；若 cinema 中文运镜词仍有价值 → **rename** `motion_prompt_zh_pack.py` 且 **零 Seedance 字符串** | 中（`test_seedance_bridge`） | 无「给 Seedance 用」叙事；H3/Grok 可复用纯词表则迁走 |
| **M2.4** | `film_spec_validate` 已禁 seedance model：补 **migrate 提示**（旧 root → 改 model 字符串）到 error message | 低 | 旧片 fail 时 next_cmd 清晰 |
| **M2.5** | lipsync：**不再 L0c 大删**（已 thin）；仅保证 shims 全 raise + README 矩阵删「多后端」若仍有 | 低 | `rg 'lipsync' README SKILL` 无生产挑战表 |

**M2 明确不做**：批发删 hard-compat shim；静默改 `i2v_provider` heat/pilot 默认；动 `workflow_pack` 虚荣搬家。

---

### Wave M3 — 研究柜关门（0.5–1 天）

| ID | 任务 | 验收 |
|----|------|------|
| **M3.1** | `comfy_armory.select_weapon` / route：**永不**默认选 `research_weapons` 或 `status=experimental` 除非 `--allow-experimental` | 既有 pilot 测保留；新增负例 |
| **M3.2** | wan22-s2v/dancer/fun：**仅** research_weapons；`wan_*_probe.py` 入口 docstring 第一句「非生产」 | agent 扫 scripts 不误当 lane |
| **M3.3** | inventory experimental 条目加 `"visibility": "research"`（schema 可选字段）；validate 忽略 | `--all` 才见 |
| **M3.4** | talking-avatar / lipdub：**禁止**写进 weapon-lane 主表；若出现在 schema 旧文案 → 改 tombstone | `film-spec.schema.json` 与政策一致 |

---

### Wave M4 — 文档与记忆消噪（可并行 · 1 天）

| ID | 任务 | 验收 |
|----|------|------|
| **M4.1** | INDEX：`seedance-camera-vocab` / 旧 lipsync lessons 标 **ARCHIVED · 非生产** | INDEX 人读不误导 |
| **M4.2** | `seedance-camera-vocab.md` 顶栏：若词表仍服务 H3，改标题为 **运镜中文词表（原 Seedance 桥）**；否则 archive | 无「Seedance 主链」 |
| **M4.3** | README 模型矩阵：对齐 weapon-lane **四工具**；删过期 lipsync 后端表 | 与 SKILL P0 一致 |
| **M4.4** | 外部旧 film-spec（Desktop seedance model）：**不**本仓 bulk 改内容；仅报告指针 `docs/reports/2026-08-05-film-spec-health.md` + M2.4 文案 | deferred 保持 |
| **M4.5** | CHANGELOG 一节 **Retired weapon surface cleanup** | 版本可追溯 |

---

### Wave M5 — 门禁与防回流（半天 · 收口）

| ID | 任务 | 验收 |
|----|------|------|
| **M5.1** | 测：`test_weapon_inventory` — primary 集合硬断言含 H3/Qwen/Edge；**断言** retired ids 不进 `demand_primary_index` | 防再注册成 primary |
| **M5.2** | 测：`test_i2v_provider` — 无 env 时 seedance generate raise；可选 unknown after unregister | 防回流 |
| **M5.3** | 测：production_router restricted → `comfy-h3` **不是** wan22（已有则锁死） | 回归 |
| **M5.4** | `make check-all` + `aifilm doctor` 本机绿 | 完成定义 |
| **M5.5** | 可选 CI 注释：secret/hotpath 不变；本板不加慢测 | CI 绿 |

---

## 4. 推荐执行顺序（sprint）

```text
Day 0  M0 立法（memory + hard-defaults 一行 + plan 落仓）
Day 1  M1 默认输出干净（CLI/doctor/dispatch）  ← 立刻「思路清晰」
Day 2  M2.1 + M2.3 + M2.2a（若接受 breaking 名） 
Day 3  M3 研究柜 + M4 文档消噪
Day 4  M5 测锁 + check-all + commit +（可选）plugin bump
```

**最小可交付（只做也值）**：M0 + M1 + M5.1 → **不改行为边界**，但默认输出与文档心智立刻干净。

**真退干净（推荐终点）**：最小 + M2.2a + M2.3 + M3.1。

---

## 5. 拍板点（只需 1 个关键决策）

**Seedance 名字是否从 provider 注册表消失？**

| 选项 | 含义 |
|------|------|
| **A · 卸注册（推荐）** | 心智最干净；旧 `provider=seedance` 直接 unknown + 指向 H3/FRW-api |
| **B · 保留 escape 门** | 兼容旧脚本；名字仍在 `list providers` → 半退役 |

计划默认假设 **A**；若你要 B，M2.2 走 b 且 M1 仍隐藏名字。

其余（lipsync 不再大删、research 默认隐藏、文档 archive）可合理默认，无需再问。

---

## 6. 非目标（防范围膨胀）

- 不重做 H3 Fill-Idle / GPU 多 agent 调度  
- 不批发删 `scripts/*` hard-compat shim（metabolism IRON）  
- 不 bulk 改用户 Desktop 旧 film root 内容  
- 不把 experimental 升 production  
- 不恢复 post lipsync / Wan22 生产 I2V  
- 不把本板做成又一次「optimization-plan 全 P0–P4」大杂烩——**只清武器心智面**

---

## 7. 验证清单（每波末）

```bash
# 心智 / CLI
aifilm weapon inventory              # 应≈仅 primary
aifilm weapon inventory --tier retired
aifilm weapon inventory --all
aifilm doctor                        # line 干净

# 代码门
make -C "$(git rev-parse --show-toplevel)" check-all
pytest skills/ai-film-grok/tests/test_weapon_inventory.py \
  skills/ai-film-grok/tests/test_cli_weapon.py \
  skills/ai-film-grok/tests/test_production_router.py -q

# 回流扫描（允许 tombstone 字符串，禁止「如何启用 Seedance bulk」类教程出现在 SKILL/stages）
rg -n 'Seedance bulk|comfy-wan22|final --lipsync auto' \
  skills/ai-film-grok/SKILL.md \
  skills/ai-film-grok/references/stages \
  skills/ai-film-grok/references/hard-defaults.md
```

---

## 8. 与既有板的关系

| 既有 | 关系 |
|------|------|
| `docs/optimization-plan.md` #13/#28 | M2.1 直接勾掉 |
| lipsync removal archive v2.40 | **已 SHIP**；本板只消噪/防推销，不重开 L0c |
| code-metabolism / code-slim | 遵守 shim IRON；本板不 vanity move |
| weapon-lane / h3-primary 定策 | **不改** active 路由；只清退役噪声 |

---

## 9. 收工定义

**DONE** 当且仅当：

1. 默认 `weapon inventory` / doctor line **只谈 primary**  
2. hard-defaults + memory 短卡写明禁表  
3. M2 选定策略落地且测绿  
4. research 默认不进 select_weapon / dispatch why  
5. `make check-all` 绿；CHANGELOG 有一节  

**PARTIAL** 可接受：只完成 M0+M1（文档+默认输出），代码 M2 待 Seedance 拍板。

---

## 10. 一句话给自己

> **在役四件套记牢；退役只留墓碑一行；研究柜上锁；别再让 Seedance/Wan/lipsync 出现在「下一步可选武器」里。**
