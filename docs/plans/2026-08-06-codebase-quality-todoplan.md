# ai-film-grok 代码库工程质量 & 团队技术能力优化迭代 Todo Plan（2026-08-06）

> **作者角色**：Senior Developer — 资深工程 / 代码质量把控  
> **结论先行**：产线规则已成熟；本档管「代码与团队能否持续、安全地出片」。

**Status: CLOSED / SHIPPED (2026-08-06 closeout · plugin 2.39.95)**  
**仓库真相：** `/Users/dex/.grok/plugins/ai-film-grok`  
**互补产品板：** `2026-08-06-optimization-todoplan.md`（出片；C1 GPU 仍 OPEN_OPS）

---

## 账实快照（全部可交付项）

| 项 | 状态 | 版本 |
|----|------|------|
| CONTRIBUTING + REVIEW_CHECKLIST | **DONE** | 2.39.90 |
| CI secret scan + hotpath job | **DONE** | 2.39.90 |
| 本地 check-all ≡ CI（secret+hotpath+coverage 58%） | **DONE** | 2.39.92–95 |
| pre-push **必跑** `scripts/secret_scan.py`（不依赖 gitea-publish） | **DONE** | 2.39.95 |
| `make review`（secret + hotpath） | **DONE** | 2.39.95 |
| IRON coverage table | **DONE** | 2.39.90 |
| util.read_json_source + semantic_index | **DONE** | 2.39.90 |
| volume probe → core.media_ops | **DONE** | 2.39.90–92 |
| util.retry + edge TTS + comfy + frw_rate + frw_lipsync poll | **DONE** | 2.39.90–95 |
| media_queue job-level backoff `scheduled_backoff_sec` | **DONE** | 2.39.95 |
| heat↔policy cycle → edit_policy_shared | **DONE** | 2.39.93 |
| SHIM_POLICY | **DONE** | 2.39.94 |
| MEMORY_GOVERNANCE | **DONE** | 2.39.95 |
| hotpath markers + gate suites | **DONE** | 2.39.91+ |
| 虚荣 peel / process-level media_queue sleep 重写 | **NON-GOAL** | — |
| 真片 C1 GPU until-empty | **OPEN_OPS**（非本板） | — |
| GitHub origin push | **外部依赖**（账号 suspended 时 PARTIAL） | — |

---

## 成功定义对照

| 标准 | 信号 |
|------|------|
| 门禁真相 + secret 兜底 | CI + pre-push + check-all 均跑 `secret_scan.py` |
| volume 主路径单一 | `core.media_ops` |
| JSON 单一真相 | `util.read_json*` / `read_json_source` |
| 共享 retry | `util.retry`（retry_call + poll_until） |
| heat 无 sys.modules 循环 hack | `edit_policy_shared` |
| hotpath | `make test-hotpath` / CI job / `make review` |
| 团队文档 | CONTRIBUTING · REVIEW · SHIM · MEMORY · IRON map |

---

## 维护

- 新 IRON → hard-defaults + 测 + IRON coverage 表一行  
- 新 shim → SHIM_POLICY + `test_w3_package_shims`  
- 新 process 重试循环 → 优先 `util.retry`  
- PR 前：`make review` 或 `make check-all`  

## 非目标（永久）

- 虚荣「全员 <1500 行」  
- 静默改 heat / pilot / i2v_provider  
- 把 plate 刷成假 master  
- 重写 references 全书  
