"""C5.5 — subprocess hang protection contract."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_util_run_defaults_timeout_60() -> None:
    from util import subprocess as usp

    sig = inspect.signature(usp.run)
    assert sig.parameters["timeout"].default == 60
    with mock.patch("subprocess.run") as m:
        m.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        usp.run(["true"], check=False, timeout=None)
        assert m.call_args.kwargs.get("timeout") == 60


def test_run_compose_env_none_means_60() -> None:
    from util.subprocess import run_compose_env

    with mock.patch("subprocess.run") as m:
        m.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        run_compose_env(["true"], check=False, timeout=None)
        assert m.call_args.kwargs.get("timeout") == 60


def test_compose_render_run_default_60() -> None:
    from post import compose_render

    sig = inspect.signature(compose_render.run)
    assert sig.parameters["timeout"].default == 60
    with mock.patch.object(compose_render, "run_compose_env") as m:
        m.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        compose_render.run(["ffprobe", "-version"], check=False)
        assert m.call_args.kwargs.get("timeout") == 60


def test_raw_subprocess_run_must_pass_timeout_or_kwargs() -> None:
    """Bare subprocess.run without timeout= and without **kwargs is banned outside util impl."""
    scripts = SCRIPTS
    offenders: list[str] = []
    for path in sorted(scripts.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(scripts).as_posix()
        if rel == "util/subprocess.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
                and func.attr == "run"
            ):
                continue
            kw = {k.arg for k in node.keywords if k.arg}
            has_starstar = any(k.arg is None for k in node.keywords)
            if "timeout" in kw or has_starstar:
                continue
            offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, f"subprocess.run without timeout: {offenders}"
