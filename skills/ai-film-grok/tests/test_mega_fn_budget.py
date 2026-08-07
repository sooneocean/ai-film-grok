"""Guard: no *new* mega-functions without an intentional allowlist entry.

Orchestrator relief (2026-08-07) freezes known 800+ LOC callables. Adding
another without documenting it in ALLOWLIST fails CI — prevents silent
re-growth while peels land. Not a vanity "everything <1500" rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
BUDGET_LINES = 800

# (relative path under scripts/, qualified name) — intentional residuals
# Refresh when a Wave peel drops a name below BUDGET (remove from list).
ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        # P0 orchestrators (Wave 1–3 targets)
        # validate_film_spec peeled under budget (W2) — residual body leaf allowlisted
        ("plan/film_spec_validate_body.py", "apply_bgm_shots_and_edit_body"),
        ("gates/preflight.py", "run_preflight"),
        # Secondary mega-fns discovered 2026-08-07 probe (Wave 6 watch)
        ("post/closeout.py", "closeout_status"),
        ("spine/dispatch.py", "build_dispatch"),
    }
)


def _iter_function_spans(path: Path) -> list[tuple[str, int, int]]:
    """Return (qualified_name, start_line, span_lines) for module-level callables."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    out: list[tuple[str, int, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            out.append((node.name, node.lineno, end - node.lineno + 1))
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end = getattr(child, "end_lineno", None) or child.lineno
                    out.append(
                        (
                            f"{node.name}.{child.name}",
                            child.lineno,
                            end - child.lineno + 1,
                        )
                    )
    return out


def test_no_new_mega_functions_without_allowlist() -> None:
    offenders: list[str] = []
    stale: list[str] = []
    seen_allow: set[tuple[str, str]] = set()

    for path in sorted(SCRIPTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(SCRIPTS).as_posix()
        # Thin hard-compat shims at scripts root are never mega-fns
        if path.parent == SCRIPTS and rel not in {
            "aifilm_grok.py",
            "workflow_pack.py",
        }:
            # still scan hub + workflow_pack; skip other root files for speed
            if not rel.endswith(".py"):
                continue
            # root shims: skip if tiny
            if path.stat().st_size < 20_000 and rel not in {
                "aifilm_grok.py",
                "workflow_pack.py",
            }:
                continue

        for name, _lineno, span in _iter_function_spans(path):
            key = (rel, name)
            if span > BUDGET_LINES:
                if key in ALLOWLIST:
                    seen_allow.add(key)
                else:
                    offenders.append(f"{rel}:{name} span={span} (>{BUDGET_LINES})")
            elif key in ALLOWLIST:
                stale.append(f"{rel}:{name} span={span} (peel landed — drop allowlist)")

    assert not offenders, (
        "New mega-function(s) over budget without allowlist entry. "
        "Either peel into stages or add to ALLOWLIST with a plan note:\n  "
        + "\n  ".join(offenders)
    )
    # Allowlist entries that shrank below budget should be cleaned up (soft fail → assert)
    assert not stale, (
        "ALLOWLIST entry under budget — remove to keep the list honest:\n  "
        + "\n  ".join(stale)
    )
    # Known P0 mega-fns / peel targets must still be present (don't silently delete)
    for required in (
        ("plan/film_spec_validate_body.py", "apply_bgm_shots_and_edit_body"),
        ("gates/preflight.py", "run_preflight"),
    ):
        assert required in ALLOWLIST
        path = SCRIPTS / required[0]
        assert path.is_file(), f"missing {required[0]}"
        names = {n for n, _, _ in _iter_function_spans(path)}
        assert required[1] in names, f"{required[1]} missing from {required[0]}"
    # Orchestrator entry must remain thin and importable after W2 peels
    vpath = SCRIPTS / "plan" / "film_spec_validate.py"
    assert vpath.is_file()
    vnames = {n for n, _, span in _iter_function_spans(vpath)}
    assert "validate_film_spec" in vnames
    vspan = next(span for n, _, span in _iter_function_spans(vpath) if n == "validate_film_spec")
    assert vspan <= BUDGET_LINES, f"validate_film_spec re-grew to {vspan}"
