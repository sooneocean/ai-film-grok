# 流程优化 Todo Plan — 2026-08-03

**Status:** **Wave A–C SHIPPED** (v2.31.20–21) · Wave D pending  
**视角：** 你怎么把一集从故事做到桌面成片（不是再拆 CLI 行数）。  
**前置已完成：** ROI A–E · Process slim P0–P5（v2.31.16–19）  
**方法：** 7 步主流程 × 近两周片例 PARTIAL × 门禁密度  
**原则：** 砍「重复决策 / 假进度 / 收尾手搓」；不砍 pilot 人审、不静默降 heat

---

## 0. 一句话诊断

管线**规则够硬、命令够全**；真正吃时间的是四段：

1. **静帧合格环**（毒镜 / 解剖 / still≠prompt / 回穿）——失败一次整段 I2V 作废  
2. **GPU 与队列现实**（5090 独占、隧道、本机 OOM、interrupt 假进度）  
3. **plate 之后的收尾阶梯**（heat codes · timeline 双钟 · sensory · post-audit）——「有成片」≠「可交付」  
4. **Agent 回合税**（dispatch 后仍要记一长串补救命令；autopilot 预算窄）

文档/token 瘦身已做完。下一阶段 ROI 在 **成片吞吐与可预期交付**，不是再写一篇 IRON。

---

## 1. 七步流：卡点地图

| 用户步 | 现状 | 主要浪费 | 优化方向 |
|--------|------|----------|----------|
| 1 定义故事 | plan + heat + spine 较成熟 | 用户原文被 spicy 兜底污染；多段剧本双 climax 克隆 | 保真门默认开；plan 一键「用户句锁定」回执 |
| 2 设计演出 | shot 体位/运镜门硬 | plan 绿仍「无聊」；返工在 bulk 后才发现 | **设计期** variety 预检 + 体位矩阵表人审 1 页 |
| 3 Pilot | 强制人批（对） | 证据散落；批完仍缺 undress 三拍 | pilot 打包：3 镜 + 状态照 + heat 摘要 **一屏 GO** |
| 4 批量 | queue + heat hard_fail | 先验后生被跳；poison 进 I2V；多片抢卡 | batch preflight 单命令；毒 still 硬拦；5090 lease |
| 5 选片粗剪 | mean/gate 有 | mean 高≠好看；邻镜 motion 撞车后补 | select 时 variety+contact 可读分；自动 shortlist |
| 6 后期母版 | final 路径长 | timeout/sidechain/字幕路径；双烧风险 | `final-one-shot` 包装：超时策略+receipt 链 |
| 7 审片交付 | closeout 15 秒清单 | 人靠记忆跑 6 条命令 | **`closeout run`** 串 review→post-audit→export |

**已做得对、不要动：** pilot 人批 · 毒镜禁 I2V · heat max 不静默降 · 字幕 HF 单 owner · grok_primary 主链。

---

## 2. 优先级矩阵（impact × 可行性）

| ID | 主题 | 痛感 | 成本 | 建议波次 |
|----|------|------|------|----------|
| **W1** | Closeout 一键串 | 极高（每集成一次） | 低 | **本周 P0** |
| **W2** | Pilot GO 证据包 | 高（卡 bulk） | 低 | **本周 P0** |
| **W3** | Bulk preflight 单门 | 高（假进度） | 中 | 本周 P1 |
| **W4** | 设计期 variety 预检 | 高（bulk 后返工） | 中 | 本周 P1 |
| **W5** | 5090 lease / 队列诚实 | 高（PARTIAL 主因） | 中 | 并行（运维+小码） |
| **W6** | Final 超时/混音包装 | 中高 | 中 | 有成片痛再开 |
| **W7** | Still 毒检自动化加深 | 中高 | 高 | 有 CV/启发式才开 |
| **W8** | Autopilot 扩 allowlist | 中 | 中 | 观察 W1–W3 后再扩 |
| **W9** | CLI 再抽 aifilm_grok | 低（对拍片） | 高 | **不单独 sprint**（=旧 P6/F） |
| **W10** | hard-defaults 再拆表 | 低 | 中 | 仅当门禁测难写时 |

---

## 3. 可执行 Todo（验收=机测或实跑回执）

### Wave A — 收尾与 Pilot 打包（推荐先做 · 1–2 会话）

- [x] **A1 · `aifilm closeout status|run --root`**  
  - 串：heat 摘要 → review-final 闸（不自动批）→ post-audit →（可选）export next_cmd  
  - hard fail：**停 + next_cmd + required_proof**；回执 `receipts/closeout.json`  
  - 测：`tests/test_workflow_wave_a.py`  

- [x] **A2 · `aifilm pilot pack --root`**  
  - `receipts/pilot-go.json`：三镜 · 卸装三拍 · score/approval · heat · state-index · GO 模板  
  - bulk：若存在 pilot-go 且 `ok=false` → `assert_pilot_go_allows_bulk` 挡 media-queue  

- [x] **A3 · `next_actions` plate 优先 closeout-run**  
  - final 在 + 未 final_complete → `closeout-run` 先于 `review-final`  

### Wave B — 批量诚实与设计期省返工 · **DONE (v2.31.21)**

- [x] **B1 · `aifilm bulk-preflight --root`**  
  - 合并 pilot/heat/state/still/anatomy/tunnel/lease；`media-queue add --require-preflight`  
  - 回执 `receipts/bulk-preflight.json`；测 `test_workflow_pack.py`  

- [x] **B2 · `aifilm variety-precheck`**  
  - 体位 / 脸 CU / L4 / 邻镜 motion·camera 撞车 → `variety-matrix.md`  

- [x] **B3 · `aifilm select-shortlist`**  
  - 多 take preferred（不删 take）→ `receipts/select-shortlist.json`  

### Wave C — 算力与队列 · **DONE (v2.31.21)**

- [x] **C1 · `aifilm gpu-lease`** — `~/.grok/run/gpu-lease.json` 一机一 owner  
- [x] **C2 · `tunnel-probe` + doctor `comfy_tunnel`** — `TUNNEL_WRONG_PORT`  
- [x] **C3 · `queue-progress`** — 非空 takes/clips 才算进度  

### Wave D — Final 包装（有成片回归痛再开）

- [ ] **D1 · final 超时策略表**（长片默认 ≥1800s / 或直调 render_final）写进 stages/post + CLI 默认  
- [ ] **D2 · sidechain 失败自动降级 amix**（带 PARTIAL receipt，不静默）  
- [ ] **D3 · 字幕路径空格 / force_style 炸 → 已有 /tmp 路径；确保 final-one-shot 默认走稳路径  

### Wave E — 明确不做 / 延后

| 项 | 原因 |
|----|------|
| 再发明第四套阶段名 | Phase2 刚收敛 7 步 |
| 无行为 diff 抽 11k CLI | 对拍片吞吐无直接增益 |
| 自动批 pilot / 静默降 heat | 产品铁律 |
| 全自动毒镜 CV 完美识别 | 成本高；先 B1 标记+硬拦已标毒 |
| 清 `.local-runtimes` 4.5G | 先清单再确认 |
| 未授权 push origin | 对外动作 |

---

## 4. 建议执行顺序

```text
A1 closeout run  →  A2 pilot pack  →  A3 dispatch 接线
        ↓
B1 bulk-preflight  →  B2 variety 预检  →  B3 select shortlist（可后）
        ‖
C1–C3 运维并行（lease / 隧道 / 进度诚实）
        ↓
D 仅当 final 再炸
```

**默认推荐下一会话：`Wave A`（A1+A2+A3）。**  
回报口径：`GO` / `只 A1` / `A+B` / `全开 Wave A–C`。

---

## 5. 成功指标（两周后回看）

| 指标 | 基线（近片例） | 目标 |
|------|----------------|------|
| plate→export 命令次数 | ~6–10 手搓 | ≤2（closeout + 可选 export） |
| bulk 启动前可避免的重渲 | still 毒/回穿进 I2V | preflight 拦下 ≥80% 已知类 |
| Pilot→bulk 来回 | 证据不全再问 | 1 次 GO 包过闸 |
| 交付标 PARTIAL 因「流程漏步」 | 常见 | 仅剩模型/审核硬墙（bare 等） |
| Agent 每步默认 context | 已瘦 | 保持 stages≤3 refs，不回灌 lesson |

---

## 6. 与旧计划关系

| 计划 | 状态 | 关系 |
|------|------|------|
| `2026-08-03-roi-optimization-plan` | A–E DONE | 工程绿线；本计划不重复 |
| `2026-08-03-process-slim-phase2` | P0–P5 DONE · P6 未开 | 文档税；本计划吃 **成片吞吐** |
| 本档 | **Wave A 已落地** · B–D 待开 | 拍片主流程 ROI |

---

_Generated 2026-08-03 from SKILL 7-step · hard-defaults · 07-29 memory PARTIAL 片例 · live plugin v2.31.18._
