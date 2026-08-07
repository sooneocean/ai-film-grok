---
title: "fix: CI per-module coverage floors resolve the real implementation, not the shim"
type: fix
status: shipped
created: 2026-08-07
target_repo: ai-film-grok
scope: CI contract + guard test
---

**Shipped:** 2.40.93

# CI 覆盖门禁被 shim 架空 → 修正为指向真实实现模块

## Problem frame

模块重构（W3/W6 package move）后，`media_qa`、`quality_evidence`、`continuity`
的实现已迁入 `media/`、`gates/`、`assets/` 包内。但
`.github/workflows/ci.yml` 的 per-module coverage floor 契约仍用
`key.endswith(f"scripts/{name}")` 匹配——命中的是顶层**硬兼容 shim**（纯
`sys.modules` 别名，永远 100% covered），而真实实现被完全绕过。

**实测基线**（`coverage run --source=scripts` · 3727 passed / 32 failed / 2 skipped，非 slow）：

| floor 契约 | CI 现打到（shim） | 真实实现覆盖 | 修后判定 |
|---|---|---|---|
| `media_qa.py` ≥ 45 | 100%（假） | 55.8% | PASS |
| `quality_evidence.py` ≥ 80 | 100%（假） | 86.1% | PASS |
| `continuity.py` ≥ 85 | 100%（假） | 92.3% | PASS |

这是一个「机读门禁被 shim 架空」的真绿假绿——so把 floor 契约指到真实实现，
且当前真实覆盖全部 ≥ floor，**修后不会炸 CI**。

## Scope boundaries

- **In**: CI floor 解析逻辑、指向真实实现模块；一个防回归 guard 测试。
- **Deferred (follow-up)**: 提升各 floor 阈值、把更多模块纳入 floor 契约；与 CI 无关的
  existing 32 failed（env 相关）不在此范围。
- **Explicit non-goal**: 不 alter production code；不改 shim 层；不做模块拆分。

## Key technical decision

Floor key 解析从「文本 `endswith`」改为**运行时通过 importlib 解析模块真实 origin**：

```python
import importlib.util, os, sys
sys.path.insert(0, "scripts")
spec = importlib.util.find_spec(name)
rel = os.path.relpath(spec.origin, "scripts")     # 例: media/media_qa.py
key = f"scripts/{rel}"
row = files.get(key)
```

这样 floor 永远锁定真实实现位置，对未来的 module move 具韧性，不再依赖包路径硬编码。

## Implementation units

### U1. CI floor 解析改指真实实现

- **Goal**: `.github/workflows/ci.yml` 的 coverage floor 契约命中真实实现模块
- **Requirements**: 硬规则 #4（机读门禁只改 hard-defaults + 对应测）、#9（doctor+green）
- **Dependencies**: 无
- **Files**: `.github/workflows/ci.yml`
- **Approach**: 见 Key technical decision——用 `importlib.find_spec` 解析模块真实
  `scripts/` 相对路径，再取值。阈值保持不变（media_qa 45 / quality_evidence 80 /
  continuity 85），全部真实覆盖在阈值之上。
- **Test scenarios**:
  - Guard 测试（见 U2）确保 CI 不再用裸 `endswith("scripts/{name}")` 匹配。
- **Verification**: 在**本机**用同款解析逻辑对 `coverage.json` 跑一遍，三个 floor
  全部 PASS 且打印真实覆盖；真实覆盖全部 ≥ 触发。

### U2 — guard test: floor 契约必须解析到真实实现

- **Goal**: 防止回归（未来 shim 重构又把 floor 架空）
- **Dependencies**: U1
- **Files**: `skills/ai-film-grok/tests/test_ci_roi_contract.py`
- **Approach**: 在既有 CI 契约测试文件追加断言：
  - floor 块使用 `importlib`/`find_spec` 解析真实位置（断言 `endswith(f"scripts/{name}")`
    的 naive 匹配不再出现在 floor 循环）；
  - 三个受契模块（`media_qa`/`quality_evidence`/`continuity`）真实实现文件存在且非空；
  - 若 floor 命中顶层 shim（`_sys.modules[__name__] = _impl` 且文件 ≪ 真实实现）
  → 视为契约失效，测试失败。
- **Test scenarios**:
  - 当前（未修）ci.yml → 失败（命中 shim）——RED。
  - 修后 ci.yml → 通过（命中真实实现）——GREEN。
- **Verification**: pytest 断言在 RED（未修）时失败、在 U1 后通过。

## Risks & mitigation

- **CI 炸档**: 已用真实覆盖实测，三个 floor 全部 ≥ 阈值，修后 CI 必绿（低风险）。
- **importlib 在 CI 解析差异e**: 与 CI runner 的 python patch 可能不同，但 `find_spec`
  只做静态解析脚本路径，不跑字节码 / 不受版本漂移影响。
- **回归**: guard 测试（U2）在人任何将来 move 前就把 floor 裸奔挡住。

## Definitions of done

- [ ] `coverage.run --source=scripts` 后，用 floor 解析逻辑对本机 `coverage.json`
     三个模块全部 PASS，输出真实覆盖 %。
- [ ] `test_ci_roi_contract.py` 新 guard 测试 GREEN；RED（未修时）可见断言失败。
- [ ] 无 production 源码变更；无 shim 层变更。