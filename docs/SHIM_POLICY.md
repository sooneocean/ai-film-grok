# Shim policy · ai-film-grok

Hard-compat top-level modules under `skills/ai-film-grok/scripts/*.py` that only
re-export a package implementation. Authority lives in the **package path**.

## What a shim is

```python
"""Shim — implementation in narrative.edit_policy_shared."""
from narrative import edit_policy_shared as _impl
import sys as _sys
_sys.modules[__name__] = _impl
```

- **≤ ~30 lines**, no business logic, no second copy of algorithms.
- `import name` and `import package.name` must be the **same module object**.
- Covered by `tests/test_w3_package_shims.py` (identity + thinness).

## When to add

| Situation | Action |
|-----------|--------|
| Move code into `scripts/<pkg>/` and callers still `import old_name` | Add thin top-level shim |
| New domain module with no legacy import | **No** shim — import package path only |
| Temporary alias during rename | Shim + CHANGELOG; remove only after callers grepped clean |

## When to refuse

- Putting real logic in the shim (gates, I/O, CLI parsing).
- Dual-maintaining algorithm in both shim and package.
- Claiming “peel done” when only a shim was added.

## Authority map (examples)

| Public import | Authority |
|---------------|-----------|
| `edit_policy` / `edit_policy_heat` | `narrative.edit_policy*` |
| `edit_policy_shared` | `narrative.edit_policy_shared` |
| `compose_render` / `render_final` | `post.*` |
| `dispatch` / `next_actions` | `spine.*` |
| `cli_post` / `cli_media` | `cli.*` |

## CI / review

- New shim: extend `test_w3_package_shims` if it is a new domain leaf.
- PR checklist: no logic in shim; public CLI strings unchanged.
- See also: [CONTRIBUTING.md](./CONTRIBUTING.md) · [REVIEW_CHECKLIST.md](./REVIEW_CHECKLIST.md).
