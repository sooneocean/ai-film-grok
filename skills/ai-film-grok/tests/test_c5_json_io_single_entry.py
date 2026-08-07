"""C5.3 — JSON I/O single entry: no local parser reimplementation outside util.

Allowed *names* ``read_json`` remain as hard-compat facades that only call
``util.require_json*`` / ``soft_json``. Bodies must not re-parse with
``json.loads`` / ``path.read_text``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# Module-level ``def read_json`` facades still allowed (error remap / hard-compat).
# They must not reimplement parsing — enforced by body scan below.
ALLOWED_READ_JSON_DEFS = frozenset(
    {
        "final/io.py",
        "post/compose_render.py",
        "post/export_composition.py",
        "util/__init__.py",
        "util/json_io.py",
    }
)

# Nested / fallback reimplementations are forbidden everywhere under scripts/.
FORBIDDEN_IN_READ_JSON_BODY = re.compile(
    r"json\.loads\s*\(|\.read_text\s*\(",
    re.MULTILINE,
)


def _iter_py() -> list[Path]:
    return sorted(p for p in SCRIPTS.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_local_read_json_def_outside_whitelist() -> None:
    offenders: list[str] = []
    for path in _iter_py():
        rel = path.relative_to(SCRIPTS).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "read_json":
                if rel not in ALLOWED_READ_JSON_DEFS:
                    offenders.append(rel)
    assert not offenders, f"local def read_json outside whitelist: {offenders}"


def test_allowed_read_json_defs_are_thin_facades() -> None:
    """Whitelist facades must not re-parse JSON themselves."""
    for rel in ALLOWED_READ_JSON_DEFS:
        if rel.startswith("util/"):
            continue  # util is the real implementation
        path = SCRIPTS / rel
        if not path.is_file():
            pytest.fail(f"missing whitelist module: {rel}")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not (isinstance(node, ast.FunctionDef) and node.name == "read_json"):
                continue
            body_src = ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""
            # Strip docstring for scan noise
            body_src = re.sub(r'^\s*""".*?"""\s*', "", body_src, count=1, flags=re.S)
            assert not FORBIDDEN_IN_READ_JSON_BODY.search(body_src), (
                f"{rel} read_json still looks like a local parser:\n{body_src}"
            )


def test_no_nested_read_json_reimplementation() -> None:
    """Catch try/except fallbacks that re-define read_json with json.loads."""
    nested_offenders: list[str] = []
    for path in _iter_py():
        rel = path.relative_to(SCRIPTS).as_posix()
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != "read_json":
                continue
            # Module-level handled by whitelist test
            if node.col_offset == 0 and isinstance(
                getattr(node, "parent", None), type(None)
            ):
                pass
            # Any nested FunctionDef named read_json is forbidden
            # (ast.walk does not set parent; detect by indent / parent walk)
        # simpler: nested defs have col_offset > 0 in typical formatting
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "read_json":
                if node.col_offset > 0:
                    nested_offenders.append(f"{rel}:{node.lineno}")
    assert not nested_offenders, f"nested read_json reimplementation: {nested_offenders}"


def test_no_private_write_json_reimplementation() -> None:
    """``_write_json`` must not re-dump with json.dumps + atomic_write_text."""
    offenders: list[str] = []
    for path in _iter_py():
        rel = path.relative_to(SCRIPTS).as_posix()
        if rel.startswith("util/"):
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        for node in tree.body:
            if not (isinstance(node, ast.FunctionDef) and node.name == "_write_json"):
                continue
            body = ast.get_source_segment(src, node) or ""
            if "json.dumps" in body and (
                "atomic_write" in body or "write_text" in body
            ):
                offenders.append(rel)
    assert not offenders, f"_write_json local reimplementation: {offenders}"
