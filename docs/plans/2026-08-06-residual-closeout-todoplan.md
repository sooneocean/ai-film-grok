# Residual 收口 Todo Plan（2026-08-06 · 四条尾巴）

> **Slim board (structure/docs deadcode):** [2026-08-07-code-slim-consolidation-todoplan.md](2026-08-07-code-slim-consolidation-todoplan.md) — do not reopen package vanity / whole-file delete waves here.

**Status:** PARTIAL SHIPPED（机跑段完成 · 人门仍红）  
**Note:** 片上证据在 **film root receipts**（不依赖 git 分支）。结构账实见 [monolith-closeout](2026-08-06-monolith-closeout.md)（若本分支无此档则以 LOC 探针为准）。

**原则：** 处理掉 = 账实闭合 + 能机跑就机跑 + 禁虚荣 peel + 人审边界诚实

---

## 0. 结论

| 尾巴 | 处理结果 |
|------|----------|
| **A 巨石 residual** | heat 已 facade 化；**final/export 厚体仅触达 peel**；无 bug 不 peel |
| **B 片上人审链** | pk + shortlist + **promote 26** 已机跑；**ship-prep PARTIAL（门红诚实）** |
| **C inventory OPEN** | 冻结 ≤5：C7 · C9 · C10 · C12 · C14 |
| **D 双 checkout / 脏树** | **plugins 唯一可写**；`~/.grok/ai-film-grok` 禁手拷；本会话末 `main` 有 UU 冲突勿盲 commit |

---

## 1. A · 巨石（挡路才拆）

| 模块 | 诚实状态 |
|------|----------|
| heat packs + facade | **结构 DONE**（勿预防性再拆） |
| `render_final` 编排体 | residual · 仅 VO/mix/字幕/timeout 触达 peel |
| `export_composition` writers | residual · 仅 export bug peel |
| film_spec validate | 触达 peel |

默认结构 `go` = **PARTIAL(无触发)**。

---

## 2. B · suse-evolution-ep01（已机跑）

**片根：** `~/AI FILM SPACE/0805/suse-evolution-ep01`

| 步 | 结果 | 回执路径 |
|----|------|----------|
| B1 pk-compare | ok · multi≈26 | `receipts/pk-dailies.md` · `pk-compare-ship-prep.json` |
| B2 shortlist | ok · anti-hijack | `receipts/select-shortlist.json` |
| B3 promote | 机写 preferred（26） | 同上（manifest.clips） |
| B4 ship-prep | **ok=false** | `receipts/ship-prep.json` · `ship-prep-human.md` |
| B5 review-final | **人** | 不代签 |

### ship-prep 红（诚实 · 2026-08-06）

- i2v_motion_gate 红  
- film_core issues  
- five_track / sex_sfx  
- input_fidelity  
- gate_auto / cinematic 被上游拦  
- fill_idle 仍可能再报 pending（与 C1 queue_empty 不矛盾：挑战/再排队可生长）  
- 流水线可标 **human PK required**（不把 promote 当终审）

### 人下一步

```bash
ROOT="$HOME/AI FILM SPACE/0805/suse-evolution-ep01"
open "$ROOT/receipts/ship-prep-human.md"
open "$ROOT/receipts/pk-dailies.md"
aifilm i2v-motion-gate --root "$ROOT" --write
aifilm gate-auto --root "$ROOT"
aifilm ship-prep --root "$ROOT"
# 绿后再人 review-final → export-desktop（禁 plate 当 master）
```

---

## 3. C · OPEN 冻结集（≤5）

| ID | 状态 | 说明 |
|----|------|------|
| C1 | **SHIPPED** | until-empty queue_empty suse |
| C7 | **冻结纪律** | material fidelity 新片抽检 |
| C9 | **=A** | 触达 peel only |
| C10 | **冻结** | subprocess timeout 触达补 |
| C12 | **冻结** | provider 签名另会 |
| C14 | **冻结 optional** | throughput counters |

其余 C2–C6 / C15–18 = 已 ship 机读，禁当绿野重开。

---

## 4. D · checkout 纪律

| 树 | 角色 |
|----|------|
| `~/.grok/plugins/ai-film-grok` | 本机插件真相 · 只改 `git rev-parse` 当前树 |
| `~/.grok/ai-film-grok` | 分叉开发树 · **禁止** 手动 cp 同步 |

**当前注意：** 若 `git status` 见 `UU plugin.json` / `UU CHANGELOG.md`，先解决合并再 commit；**不要**把片上 PARTIAL 当代码失败。

launchd 日志：`artifacts/comfy-tunnel-launchd.*` **不入库**。

---

## 5. DONE 定义

| 项 | 本轮 |
|----|------|
| A 账实 + 非目标写死 | ✅ |
| B 机跑到 ship-prep 诚实红 | ✅ PARTIAL |
| C 冻结 ≤5 | ✅ |
| D 纪律说明 | ✅；merge 冲突留给人/下轮 |
| 人修门 ship-prep 绿 | ⏳ 片上债 |

*2026-08-06 residual closeout.*
