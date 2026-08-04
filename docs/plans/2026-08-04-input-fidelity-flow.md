# Input Fidelity + Flow · 2026-08-04

**Status:** F0 SHIPPED (v2.38.8) · F1–F3 / S backlog  
**Full plan:** session plan `input-fidelity-flow` (链路优化 · 更顺 + 与 input 更相关)

## Shipped

| ID | Item |
|----|------|
| F0.1 | `receipts/input-fidelity.json` schema via `input_fidelity.py` |
| F0.2 | `aifilm fidelity status\|check` |
| F0.3 | hard-defaults + memory + SKILL pointer + tests |

## Next

- **F1** plan `source_quote` / must_keep project / entity hard paths  
- **F2** still/I2V source anchors  
- **F3** closeout/final fidelity step  
- **S** dispatch compact line + `design-go`

## Commands

```bash
aifilm fidelity status --root "<film>"
aifilm fidelity check --root "<film>"
aifilm fidelity check --root "<film>" --strict
```
